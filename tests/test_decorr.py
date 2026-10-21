"""1.6.0: production / self correlation read with BRAIN's check as the authority, theme hints, and
decorrelate() - lower the overlap while keeping the signal."""
import os
import tempfile
import unittest

os.environ.setdefault("HYPOLAB_HOME", tempfile.mkdtemp(prefix="hypolab_test_"))

import pandas as pd  # noqa: E402

from hypolab import config, decorr  # noqa: E402
from hypolab.ideas import LadderStep  # noqa: E402
from hypolab.research import Researcher  # noqa: E402

THEME_ROW = {"name": "MATCHES_THEMES", "result": "WARNING",
             "message": "Theme GLB/D1 Risk Handled Crowding Factors/Fast Factors Theme does not match with "
                        "multiplier of 2.5."}
ISSUANCE = ("-group_rank(log(ts_backfill(sharesout, 21) / ts_delay(ts_backfill(sharesout, 21), 504)), "
            "subindustry)")


class TestReading(unittest.TestCase):
    def test_brain_check_wins_over_our_reading(self):
        checks = [{"name": "PROD_CORRELATION", "result": "PASS", "value": 0.78, "limit": 0.7}]
        st = decorr.corr_status(checks, {"max": 0.78})
        self.assertEqual(st["prod"]["result"], "PASS")              # BRAIN let it through: we never block
        self.assertEqual(st["prod"]["source"], "BRAIN check")

    def test_pending_keeps_our_reading_as_a_hint(self):
        checks = [{"name": "PROD_CORRELATION", "result": "PENDING"}]
        st = decorr.corr_status(checks, {"max": 0.7802, "min": -0.4484})
        self.assertEqual(st["prod"]["result"], "PENDING")
        self.assertAlmostEqual(st["prod"]["reading"], 0.7802)

    def test_no_check_falls_back_to_our_reading(self):
        self.assertEqual(decorr.corr_status([], {"max": 0.81})["prod"]["result"], "FAIL?")
        self.assertEqual(decorr.corr_status([], {"max": 0.41})["prod"]["result"], "PASS?")
        self.assertIn("production FAIL?", decorr.status_line(decorr.corr_status([], {"max": 0.81})))


class TestThemes(unittest.TestCase):
    def test_theme_warning_becomes_a_neutralization(self):
        h = decorr.theme_hints([THEME_ROW], offered=["SUBINDUSTRY", "CROWDING", "FAST"], current="SUBINDUSTRY")
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["multiplier"], 2.5)
        self.assertEqual(h[0]["neutralization"], "CROWDING")
        self.assertIsNone(decorr.theme_hints([THEME_ROW], offered=["SUBINDUSTRY"])[0]["neutralization"])
        matched = {"message": "Pyramid theme GLB/D1/PV matches with multiplier of 1."}
        self.assertEqual(decorr.theme_hints([matched]), [])     # a Pyramid line, not a "Theme ... with" line

    def test_diagnose_offers_the_theme_neutralization_first_among_extras(self):
        from hypolab.diagnose import diagnose
        old = config.REGION_DEFAULTS["GLB"].get("neutralizations")
        config.REGION_DEFAULTS["GLB"]["neutralizations"] = ["SUBINDUSTRY", "CROWDING", "FAST"]
        try:
            summary = {"alpha_id": "X", "is_sharpe": 1.87, "is_fitness": 0.78, "is_turnover": 0.039,
                       "is_returns": 0.03, "failed": [], "checks": [THEME_ROW]}
            d = diagnose(summary, ISSUANCE, {"region": "GLB", "neutralization": "SUBINDUSTRY"})
            titles = [a.title for a in d.actions]
            self.assertTrue(any("x2.5 theme: neutralization CROWDING" in t for t in titles), titles)
        finally:
            if old is None:
                config.REGION_DEFAULTS["GLB"].pop("neutralizations", None)
            else:
                config.REGION_DEFAULTS["GLB"]["neutralizations"] = old


class TestVariants(unittest.TestCase):
    def test_issuance_alpha_gets_principled_variants(self):
        old = config.REGION_DEFAULTS["GLB"].get("neutralizations")
        config.REGION_DEFAULTS["GLB"]["neutralizations"] = ["SUBINDUSTRY", "CROWDING", "FAST", "SLOW"]
        try:
            vs = decorr.variants(ISSUANCE, {"region": "GLB", "neutralization": "SUBINDUSTRY"}, checks=[THEME_ROW],
                                 style_corr={"momentum": -0.1, "value_proxy": 0.45}, k=6, turnover=0.04)
        finally:
            if old is None:
                config.REGION_DEFAULTS["GLB"].pop("neutralizations", None)
            else:
                config.REGION_DEFAULTS["GLB"]["neutralizations"] = old
        names = [v.name for v in vs]
        self.assertEqual(names[0], "neutralization CROWDING")         # BRAIN's theme hint comes first
        self.assertIn("remove value_proxy exposure", names)
        self.assertIn("neutralization SLOW", names)                    # low turnover -> SLOW, not SLOW_AND_FAST
        hz = next(v for v in vs if v.kind == "horizon")
        self.assertIn("ts_delay(ts_backfill(sharesout, 21), 252)", hz.expression)   # 504 -> 252
        self.assertIn("ts_backfill(sharesout, 21)", hz.expression)                    # backfill untouched
        self.assertLessEqual(len(vs), 6)

    def test_backfill_windows_are_not_horizons(self):
        self.assertIsNone(decorr._shorter_horizon("group_rank(ts_backfill(fnd_cfo, 252) / cap, subindustry)"))

    def test_recommend_never_picks_a_copy(self):
        rows = pd.DataFrame([{"sharpe": 1.8, "prod_corr": 0.76}, {"sharpe": 1.2, "prod_corr": 0.55},
                             {"sharpe": 1.6, "prod_corr": 0.66}, {"sharpe": 0.5, "prod_corr": 0.2}])
        self.assertEqual(decorr.recommend(rows, 2.0), 2)                # 1.6 under the limit, keeps 80%
        self.assertIsNone(decorr.recommend(rows.iloc[[0]], 2.0))        # only copies left -> nothing
        self.assertIn("IS the crowded part", decorr.lesson(rows.iloc[[3]], 0.8, 2.0))

    def test_is_test_label_reflects_brain_evidence(self):
        from hypolab.linter import Linter
        s = LadderStep("core", "rank(close)", "", Linter().lint("rank(close)"), {"single": True, "cutoff": 2.38})
        self.assertIn("1.58-2.38", s.is_test)


class TestResearcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = Researcher.sandbox()
        cards = {c.hypothesis.id: c for c in cls.R.ideas("SBX", n=40, one_per_family=False)}
        cls.t = cls.R.test(cards["FND_CASHFLOW_YIELD"], rung=0)       # the sandbox pool's own alpha: a copy

    def test_correlation_read_is_free_and_cached(self):
        before = len(self.R.journal.experiments())
        c = self.R.correlation(self.t.alpha_id, "prod", refresh=True)
        self.assertGreater(c["max"], 0.9)
        self.assertEqual(len(self.R.journal.experiments()), before)   # no simulation spent
        self.assertTrue(self.R.correlation(self.t.alpha_id, "prod").get("cached"))

    def test_decorrelate_reports_and_counts_tries(self):
        trials0 = self.R.journal.trials(self.t.key)
        rep = self.R.decorrelate(self.t, k=3)
        self.assertGreater(rep.base_prod, 0.9)
        self.assertEqual(set(rep.style_corr), set(decorr.STYLE_PROXIES))
        self.assertFalse(rep.table.empty)
        self.assertEqual(self.R.journal.trials(self.t.key), trials0 + len(rep.results))   # every variant is a try
        self.assertTrue(rep.table["prod_corr"].notna().all())
        self.assertIn("Lowering correlation", rep.markdown())
        if rep.best is not None:                                      # recommended only when under the limit
            self.assertLess(rep.table.set_index("alpha").loc[rep.best.alpha_id, "prod_corr"], 0.7)
        # style probes are simulated once, then served from the journal
        n = len(self.R.journal.experiments())
        self.R.decorrelate(self.t, k=1)
        self.assertLessEqual(len(self.R.journal.experiments()) - n, 1)

    def test_gate_uses_brains_production_check(self):
        g = self.R.gate(self.t, self.R.robustness(self.t))
        self.assertFalse(g.ready)
        self.assertTrue(any("production correlation FAILS on BRAIN" in r for r in g.reasons), g.reasons)
        self.assertGreaterEqual(decorr.family_prod_corr(self.R.journal).get("fnd_value", {}).get("max", 0), 0.9)


if __name__ == "__main__":
    unittest.main()

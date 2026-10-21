"""1.8.1: regressions for the bugs found in the full-code review of 19 Oct 2026."""
import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path

_HOME = tempfile.mkdtemp(prefix="hypolab_test_")
os.environ["HYPOLAB_HOME"] = _HOME

import pandas as pd  # noqa: E402

from hypolab import account as acct  # noqa: E402
from hypolab import config, decorr, rules  # noqa: E402
from hypolab import fastexpr as fx  # noqa: E402
from hypolab import robustness as rob  # noqa: E402
from hypolab.brain import BrainClient  # noqa: E402
from hypolab.diagnose import diagnose  # noqa: E402
from hypolab.ideas import generate_ideas  # noqa: E402
from hypolab.journal import Journal  # noqa: E402
from hypolab.research import Researcher  # noqa: E402
from ideaengine import planner  # noqa: E402
from ideaengine.store import IdeaStore  # noqa: E402


class TestDelayZero(unittest.TestCase):
    def test_delay_of(self):
        self.assertEqual(rules.delay_of(0), 0)
        self.assertEqual(rules.delay_of("0"), 0)
        self.assertEqual(rules.delay_of(None), 1)
        self.assertEqual(rules.delay_of(float("nan")), 1)

    def test_rerun_of_a_d0_alpha_stays_d0(self):
        R = Researcher.sandbox()
        v = R.rerun_variants({"region": "USA", "delay": 0, "neutralization": "SUBINDUSTRY"})
        self.assertFalse(any("delay 0" in x["label"] for x in v))         # it IS delay 0 already
        self.assertTrue(all(x["settings"]["delay"] == 0 for x in v))

    def test_quarter_pyramids_keep_d0(self):
        j = Journal(":memory:")
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        a = {"id": "D0A", "type": "REGULAR", "status": "ACTIVE", "dateSubmitted": now, "dateCreated": now,
             "settings": {"region": "USA", "universe": "TOP1000", "delay": 0}, "regular": {"code": "rank(fa)"},
             "is": {"sharpe": 2.5}}
        acct.store_alphas(j, [a], op_names={"rank"})

        class Cat:
            def fields(self, region, universe, delay, enrich=False):
                return pd.DataFrame({"id": ["fa"], "category": ["analyst"]})
        counts, _ = acct.quarter_pyramids(j, Cat())
        self.assertEqual(counts["delay"].tolist(), [0])


class TestScanRepeat(unittest.TestCase):
    def test_second_scan_is_served_from_the_journal(self):
        R = Researcher.sandbox()
        a = R.scan("sbx_model", max_fields=10)
        n_sims = len(R.journal.experiments())
        b = R.scan("sbx_model", max_fields=10)
        self.assertEqual(len(a), len(b))
        self.assertTrue(b["cached"].all())
        self.assertEqual(len(R.journal.experiments()), n_sims)              # no new simulation
        self.assertEqual(sorted(zip(a["field"], a["lens"])), sorted(zip(b["field"], b["lens"])))


class TestRobustness(unittest.TestCase):
    def test_liquid_universe_only_when_smaller(self):
        names = lambda st: [v.name for v in rob.variants("rank(close)", st)]  # noqa: E731
        self.assertNotIn("universe TOP1200", names({"region": "EUR", "universe": "TOP800"}))
        self.assertIn("universe TOP1200", names({"region": "EUR", "universe": "TOP2500"}))
        self.assertIn("universe TOP1000", names({"region": "USA", "universe": "TOP3000"}))
        self.assertNotIn("universe TOP1000", names({"region": "USA", "universe": "TOP500"}))

    def test_not_run_is_not_a_failure(self):
        rows = pd.DataFrame({"variant": ["rank test", "outlier test"], "sharpe": [1.9, None]})
        sc = rob.score(2.0, rows)
        self.assertEqual(sc["score"], 1.0)
        self.assertEqual(sc["passed"], [True, None])


class TestBrainOrder(unittest.TestCase):
    def test_results_follow_the_input_order(self):
        b = BrainClient(verbose=False)
        b._run_batch = lambda batch, cb=None: [{"ok": True, "alpha_id": p["regular"], "status": "COMPLETE",
                                                "payload": p} for p in batch]
        mk = lambda e, u: {"regular": e, "settings": {"region": "USA", "delay": 1, "universe": u}}  # noqa: E731
        ps = [mk("a", "TOP3000"), mk("b", "TOP1000"), mk("c", "TOP3000"), mk("d", "TOP1000")]
        out = b.simulate(ps, progress=None)
        self.assertEqual([r["alpha_id"] for r in out], ["a", "b", "c", "d"])


class TestSubmitRefused(unittest.TestCase):
    def test_nothing_recorded_when_brain_refuses(self):
        R = Researcher.sandbox()
        c = R.card("ANL_REVISION_BREADTH")
        t = R.test(c, rung=min(1, len(c.steps) - 1))
        g = R.gate(t, R.robustness(t))
        self.assertTrue(g.ready, g.reasons)              # 1.10.2: only a READY gate reaches BRAIN at all
        R.brain.submit = lambda aid, confirm="": {"status_code": 403, "body": "checks failed"}
        with self.assertRaises(RuntimeError):
            R.submit(g, confirm=f"SUBMIT {g.alpha_id}")
        self.assertTrue(R.journal.submissions().empty)


class TestDecorrWrapping(unittest.TestCase):
    def test_residual_of_a_multi_statement_alpha_parses(self):
        expr = "a = rank(close);\nb = rank(volume);\nrank(a) + rank(b)"
        out = decorr._residual(expr, decorr.STYLE_PROXIES["momentum"])
        fx.parse(out)
        self.assertTrue(out.startswith("a = rank(close)"))
        vs = decorr.variants(expr, {"region": "USA", "neutralization": "MARKET"},
                             style_corr={"momentum": 0.6}, own_corr=[{"alpha_id": "X", "corr": 0.8,
                                                                       "code": "x = rank(close); x"}])
        for v in vs:
            fx.parse(v.expression)
        self.assertFalse(any(v.kind == "own_residual" for v in vs))      # a multi-statement alpha is skipped


class TestDiagnoseNegativeWeak(unittest.TestCase):
    def test_flip_comes_first(self):
        d = diagnose({"alpha_id": "X", "is_sharpe": -0.9, "is_fitness": -0.5, "is_turnover": 0.2,
                      "is_returns": -0.03, "checks": []}, "rank(close)", {"region": "USA"})
        self.assertEqual(d.verdict, "WEAK")
        self.assertEqual(d.actions[0].kind, "flip")
        self.assertIn("negative", " ".join(d.findings))


class TestFallbackUniverse(unittest.TestCase):
    def test_cards_bind_from_another_universe_of_the_region(self):
        R = Researcher.sandbox()
        cards = generate_ideas(R.catalog, "SBX", "NOT_DOWNLOADED", n=5)
        self.assertTrue(cards)
        c = next(x for x in cards if x.bindings)
        self.assertEqual(c.universe, "NOT_DOWNLOADED")                  # simulated where you asked
        self.assertEqual(c.data_universe, "SANDBOX")                    # bound with the list you have
        self.assertTrue(any("field list" in n for n in c.score_notes))


class TestSettingsAndThemes(unittest.TestCase):
    def test_settings_cache_sees_changes(self):
        config.save_settings(max_sims_per_idea=7)
        self.assertEqual(config.settings()["max_sims_per_idea"], 7)
        config.save_settings(max_sims_per_idea=10)
        self.assertEqual(config.settings()["max_sims_per_idea"], 10)

    def test_theme_universe_ends_with_the_theme(self):
        config.apply_themes(dt.date(2026, 10, 20))
        self.assertEqual(config.REGION_DEFAULTS["EUR"]["universe"], "TOP800")
        config.apply_themes(dt.date(2026, 11, 20))
        self.assertEqual(config.REGION_DEFAULTS["EUR"]["universe"], "TOP2500")
        self.assertNotIn("base_universe", config.REGION_DEFAULTS["EUR"])
        config.apply_themes()                                          # back to today's state


class TestQuarterWarning(unittest.TestCase):
    def test_old_goals_are_flagged(self):
        s = IdeaStore(":memory:")
        ev = planner.evidence(Journal(":memory:"), s, "2027-W03")
        self.assertTrue(any("2026-Q4" in w and "2027-Q1" in w for w in ev["warnings"]))
        ev = planner.evidence(Journal(":memory:"), s, "2026-W43")
        self.assertFalse(any("quarter goals" in w for w in ev["warnings"]))


class TestKnowledgePack(unittest.TestCase):
    def test_pyramids_guide_has_no_raw_placeholders(self):
        from ideaengine import knowledge_pack as kp
        txt = kp.pyramids_guide()
        self.assertNotIn("{config", txt)
        self.assertIn(f"HYPOLAB setting: {config.settings()['alphas_per_pyramid']} submitted", txt)


class TestWebOriginGuard(unittest.TestCase):
    def test_foreign_post_refused(self):
        try:
            from starlette.testclient import TestClient
        except ImportError:
            self.skipTest("web dependencies not installed")
        from ideaweb import state as web_state
        from ideaweb.app import app
        old = config.HOME
        tmp = tempfile.TemporaryDirectory()
        try:
            config.HOME = Path(tmp.name)
            config.save_settings(mode="sandbox")
            web_state.reset()
            c = TestClient(app)
            r = c.post("/cards/ERN_PEAD/bin", data={"reason": "x"}, headers={"Origin": "http://evil.example"},
                       follow_redirects=False)
            self.assertEqual(r.status_code, 403)
            r = c.post("/cards/ERN_PEAD/bin", data={"reason": "x"}, headers={"Origin": "http://127.0.0.1:2719"},
                       follow_redirects=False)
            self.assertEqual(r.status_code, 303)
        finally:
            web_state.reset()
            config.HOME = old
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

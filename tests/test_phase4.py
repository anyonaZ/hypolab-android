"""Phase 4 (HYPOLAB 1.6.0): the planner's Friday review, BRAIN rules batch 5 and the 1.5.0 bug fixes."""
import datetime as dt
import os
import tempfile
import unittest

_HOME = tempfile.mkdtemp()
os.environ["HYPOLAB_HOME"] = _HOME

import pandas as pd  # noqa: E402

from hypolab import rules  # noqa: E402
from hypolab.diagnose import Action, diagnose  # noqa: E402
from hypolab.journal import Journal  # noqa: E402
from hypolab.research import Researcher, _carry_settings  # noqa: E402
from ideaengine import drafts, planner  # noqa: E402
from ideaengine.store import IdeaStore  # noqa: E402


class TestRules(unittest.TestCase):
    def test_grouping_fields_include_atom_list(self):
        for g in ("currency", "split", "adjfactor", "subindustry"):
            self.assertIn(g, rules.GROUPING_FIELDS)
        prof = rules.dataset_profile("group_rank(fa, currency)", {"fa": "ds1"}.get)
        self.assertTrue(prof["single"])

    def test_pyramid_check(self):
        self.assertTrue(rules.pyramid_check(["analyst", "pv"])["ok"])
        bad = rules.pyramid_check(["analyst", "pv", "fundamental"])
        self.assertFalse(bad["ok"])
        self.assertIn("3 data categories", bad["note"])

    def test_power_pool_shape(self):
        ok = rules.power_pool_shape("rank(ts_delta(ts_backfill(fa, 63), 63) / close)")
        self.assertEqual(ok["operators"], 3)          # ts_backfill not counted
        self.assertEqual(ok["fields"], 2)
        self.assertTrue(ok["ok"])
        big = rules.power_pool_shape("rank(a) + rank(b) + rank(c) + rank(d)")
        self.assertFalse(big["ok"])                   # 4 fields
        nine = "rank(ts_mean(ts_delta(ts_rank(ts_zscore(abs(log(sqrt(fa))), 21), 21), 5), 5)) + 1"
        self.assertGreater(rules.power_pool_shape(nine)["operators"], 8)

    def test_recommended_neutralization(self):
        self.assertEqual(rules.recommended_neutralization(["fundamental", "pv"])[0], "INDUSTRY")
        self.assertEqual(rules.recommended_neutralization(["pv"])[0], "MARKET")
        self.assertEqual(rules.recommended_neutralization(["news"]), ["SUBINDUSTRY"])

    def test_self_corr_exception(self):
        t = pd.DataFrame({"id": ["a", "b"], "correlation": [0.8, 0.5], "sharpe": [2.0, 3.0]})
        self.assertTrue(rules.self_corr_exception(2.2, t))       # 2.2 >= 1.1 x 2.0
        self.assertFalse(rules.self_corr_exception(2.1, t))
        self.assertIsNone(rules.self_corr_exception(2.2, pd.DataFrame({"id": ["a"]})))

    def test_themes_and_warnings(self):
        names = [t["name"] for t in rules.themes(dt.date(2026, 10, 20))]
        self.assertIn("EUR/D1 TOP800 Theme", names)
        self.assertEqual(rules.themes(dt.date(2026, 11, 9)), [])
        self.assertTrue(rules.last_month_warning(dt.date(2026, 12, 2)))
        self.assertEqual(rules.last_month_warning(dt.date(2026, 11, 2)), "")
        self.assertEqual(rules.RA_UNIVERSES["SMALL"]["EUR"], "TOP800")


class TestFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = Researcher.sandbox()

    def test_carry_settings(self):
        st = {"region": "USA", "universe": "TOP1000", "delay": 0, "decay": 3, "neutralization": "SLOW",
              "truncation": 0.05, "maxTrade": "ON", "testPeriod": "P2Y"}
        out = _carry_settings(st)
        self.assertEqual(out["delay"], 0)
        self.assertEqual(out["universe"], "TOP1000")
        self.assertEqual(out["max_trade"], "ON")
        self.assertNotIn("testPeriod", out)

    def test_follow_keeps_delay(self):
        c = self.R.ideas(n=3)[0]
        t = self.R.test(c, settings={"delay": 0, "decay": 2})
        self.assertEqual(t.settings["delay"], 0)
        t.diagnosis.actions.insert(0, Action("smooth", "x", f"ts_mean({t.expression}, 5)"))
        t2 = self.R.follow(t, 0)
        self.assertEqual(t2.settings["delay"], 0)
        self.assertEqual(t2.settings["decay"], 2)

    def test_usa_d0_defaults_to_top1000(self):
        p = self.R.payload("rank(close)", settings={"region": "USA", "delay": 0})
        self.assertEqual(p["settings"]["universe"], "TOP1000")
        p = self.R.payload("rank(close)", settings={"region": "USA", "delay": 0, "universe": "TOP3000"})
        self.assertEqual(p["settings"]["universe"], "TOP3000")       # an explicit choice is kept
        p = self.R.payload("rank(close)", settings={"region": "USA", "delay": 1})
        self.assertEqual(p["settings"]["universe"], "TOP3000")

    def test_gate_reports_pyramids_and_power_pool(self):
        c = self.R.ideas(n=3)[0]
        t = self.R.test(c, rung=0)
        if not t.alpha_id:
            self.skipTest("no alpha in this sandbox draw")
        g = self.R.gate(t)
        text = " ".join(g.reasons)
        self.assertIn("Power Pool shape", text)
        self.assertIn("Pyramids:", text)

    def test_diagnose_japan_and_glb(self):
        s = {"alpha_id": "X", "is_sharpe": 2.0, "is_fitness": 1.5, "is_turnover": 0.2, "is_returns": 0.1,
             "failed": ["LOW_JPN_ROBUSTNESS_SHARPE", "LOW_GLB_AMER_SHARPE"], "checks": []}
        d = diagnose(s, "rank(close)", {"region": "ASI"})
        titles = [a.title for a in d.actions]
        self.assertIn("Weak in Japan (ASI test)", titles)
        self.assertIn("Fails in a GLB sub-geography", titles)

    def test_correlation_advice_uses_gold_operators(self):
        s = {"alpha_id": "X", "is_sharpe": 2.0, "is_fitness": 1.5, "is_turnover": 0.2, "is_returns": 0.1,
             "failed": ["SELF_CORRELATION"], "checks": []}
        d = diagnose(s, "rank(close)", {"region": "USA"})
        self.assertNotIn("ts_median", " ".join(a.why for a in d.actions))


class TestPlanner(unittest.TestCase):
    def setUp(self):
        self.j = Journal(":memory:")
        self.s = IdeaStore(":memory:")

    def _exp(self, idea, family, verdict, sharpe, n=1):
        self.j.db.execute("INSERT OR IGNORE INTO ideas (id, hypothesis_id, region, family, title, categories, created) "
                          "VALUES (?,?,?,?,?,?,?)", (idea, idea, "USA", family, idea, "analyst", 0))
        for i in range(n):
            self.j.record(idea, f"r{i}", "explore", f"rank(x{i}_{idea})", {"region": "USA", "delay": 1},
                          {"alpha_id": f"{idea}{i}", "is_sharpe": sharpe, "status": "COMPLETE"}, verdict)

    def test_near_misses_and_dead_ends(self):
        self._exp("A@USA", "fam_a", "NEAR", 1.4, n=3)
        self._exp("B@USA", "fam_b", "NOISE", 0.1, n=5)
        nm = planner.near_misses(self.j)
        self.assertEqual(nm["idea_id"].tolist(), ["A@USA"])
        self.assertEqual(int(nm["tries_left"].iloc[0]), 7)
        self.assertEqual(planner.dead_end_families(self.j), ["fam_b"])

    def test_evidence_and_propose(self):
        self._exp("A@USA", "fam_a", "NEAR", 1.4)
        self.s.save_plan({"week": "2026-W42", "region": "USA", "categories": ["analyst"], "card_target": 5,
                          "extra": {"retry": ["C@USA"], "dead_ends": ["fam_x"], "lessons": []}})
        ev = planner.evidence(self.j, self.s, "2026-W43")
        self.assertEqual(ev["retry"][:2], ["C@USA", "A@USA"])
        self.assertIn("fam_x", ev["dead_ends"])
        self.assertTrue(any("EUR" in t["name"] for t in ev["themes"]))
        p = planner.propose_from_evidence("2026-W43", self.j, self.s)
        self.assertIn("C@USA", p["extra"]["retry"])
        self.assertIn("evidence", p["extra"])

    def test_warnings_for(self):
        self.assertTrue(any("Osmosis" in w for w in planner.warnings_for("2026-W46")))
        self.assertTrue(any("Last month" in w for w in planner.warnings_for("2026-W49")))
        self.assertEqual(planner.warnings_for("2026-W41"), [])

    def test_friday_checklist(self):
        steps = planner.friday_checklist(self.j, self.s, "2026-W43")
        self.assertEqual(len(steps), 6)
        self.assertFalse(steps[4]["done"])                     # no PLAN for W44 yet
        self.s.save_plan({"week": "2026-W44", "region": "GLB", "categories": ["analyst"]})
        self.assertTrue(planner.friday_checklist(self.j, self.s, "2026-W43")[4]["done"])

    def test_state_text_and_digest(self):
        self._exp("A@USA", "fam_a", "NEAR", 1.4)
        txt = drafts.state_text(self.j, self.s, "2026-W43")
        for head in ("## Quarter goals", "## This week's plan", "## Pyramid counts this quarter",
                     "## Retry list, near misses and dead ends", "## Card ids already used"):
            self.assertIn(head, txt)
        self.assertIn("A@USA", txt)
        dg = drafts.digest(self.j, self.s, "2026-W43")
        self.assertIn("active theme: EUR/D1 TOP800 Theme", dg)
        self.assertIn("cards approved vs target", dg)


if __name__ == "__main__":
    unittest.main()


class TestEurPriority(unittest.TestCase):
    """1.6.1: EUR first while the EUR/D1 TOP800 theme runs; Zacc's priority datasets (AI first)."""

    def test_starting_plan_is_eur_first(self):
        for w in ("2026-W43", "2026-W44", "2026-W45"):
            self.assertEqual(planner.STARTING_PLAN[w][0], "EUR")
        p = planner.propose("2026-W43")
        self.assertEqual(p["universe"], "TOP800")
        self.assertEqual(p["dataset_focus"], "AI Equity Alpha Forecasts")
        self.assertNotEqual(planner.propose("2026-W46")["universe"], "TOP800")

    def test_priority_list(self):
        t = rules.themes(dt.date(2026, 10, 20))[0]
        names = [d["name"] for d in t["priority_datasets"]]
        self.assertEqual(names[0], "AI Equity Alpha Forecasts")
        self.assertTrue(all(d["value_score"] >= 3 or d["ai"] for d in t["priority_datasets"]))

    def test_theme_universe_default(self):
        from hypolab import config
        self.assertEqual(config.apply_themes(dt.date(2026, 10, 20)), ["EUR"])
        self.assertEqual(config.REGION_DEFAULTS["EUR"]["universe"], "TOP800")
        self.assertEqual(config.REGION_DEFAULTS["EUR"]["base_universe"], "TOP2500")

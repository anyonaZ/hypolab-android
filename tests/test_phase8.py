"""Phase 8 (HYPOLAB 1.10.0): the SuperAlpha builder - payload, recipes, checks, the selection evaluator, pools and
preview, the unlock, the sandbox's SuperAlpha simulation, the Researcher's guard rails (budget, duplicate, 1 a day,
lock), the gate, journal counts and the planner's lifetime count. No network."""
import json
import os
import tempfile
import time
import unittest

os.environ.setdefault("HYPOLAB_HOME", tempfile.mkdtemp(prefix="hypolab_test_"))

from hypolab import config  # noqa: E402
from hypolab import superalpha as SA  # noqa: E402
from hypolab.brain import summarize_alpha  # noqa: E402
from hypolab.journal import Journal  # noqa: E402
from ideaengine import planner  # noqa: E402
from ideaengine.store import IdeaStore  # noqa: E402

PROPS = {"alpha_id": "A", "operator_count": 5, "self_correlation": 0.3, "prod_correlation": 0.4, "turnover": 0.1,
         "datacategories": ["pv"], "datacategory_count": 1, "long_count": 500, "short_count": 500,
         "universe": "TOP3000", "own": True, "color": "NONE"}


class TestEngine(unittest.TestCase):
    def test_payload_shape(self):
        p = SA.make_payload("own", "1", "USA", selection_limit=25, component_activation="OS")
        self.assertEqual(p["type"], "SUPER")
        self.assertEqual((p["selection"], p["combo"]), ("own", "1"))          # top level, not under "regular"
        st = p["settings"]
        self.assertEqual((st["selectionLimit"], st["selectionHandling"], st["componentActivation"]),
                         (25, "POSITIVE", "OS"))
        self.assertEqual((st["universe"], st["truncation"], st["decay"]), ("TOP3000", 0.05, 4))
        self.assertNotIn("regular", p)

    def test_recipes_cap_operators_and_match(self):
        for r in SA.selections(40):
            self.assertIn("(operator_count <= 200)", r.code)
            self.assertTrue(r.why)
            self.assertTrue(SA.check(r.code, "1", 40).ok)
        self.assertEqual(SA.match_recipe("selection", SA.selections(10)[0].code, 40).key, "least_corr")
        self.assertEqual(SA.match_recipe("combo", " stats = generate_stats(alpha);  1 / (ts_std_dev(stats.returns, "
                                                  "120) + 0.0001)").key, "inv_vol")
        self.assertIsNone(SA.match_recipe("combo", "2"))
        self.assertEqual(SA.recipe_names(SA.selections(20)[1].code, "1", 20), "Tradeable turnover x Equal weight")

    def test_checks(self):
        ok = SA.check(SA.selections(20)[0].code, SA.COMBOS[3].code, 20)
        self.assertTrue(ok.ok)
        self.assertEqual(ok.warnings, [])
        bad = SA.check("own && (turnover > 0.1", "1", 9, "SOMETIMES", "XX")
        self.assertFalse(bad.ok)
        msgs = " ".join(bad.errors)
        for part in ("never closed", "at least 10", "selection handling", "IS or OS"):
            self.assertIn(part, msgs)
        w = SA.check("own && (wobble < 2)", "x = 1; x", 20)
        self.assertTrue(w.ok)
        self.assertTrue(any("wobble" in m for m in w.warnings))
        self.assertTrue(any("operator cap" in m for m in w.warnings))
        self.assertFalse(SA.check("own", "w = generate_stats(alpha)", 20).ok)    # last statement must be the weight

    def test_selection_evaluator(self):
        self.assertAlmostEqual(SA.eval_selection(SA.selections(30)[0].code, PROPS), 0.6)
        self.assertEqual(SA.eval_selection("own && (color != 'RED') && (not(in(datacategories, 'pv')))", PROPS), 0.0)
        self.assertEqual(SA.eval_selection("own && !(turnover > 0.5) || false", PROPS), 1.0)
        self.assertAlmostEqual(SA.eval_selection("(long_count + short_count) / sqrt(universe_size(universe))", PROPS),
                               1000 / 3000 ** 0.5)
        with self.assertRaises(SA.SelectionError):
            SA.eval_selection("mystery > 1", PROPS)
        with self.assertRaises(SA.SelectionError):
            SA.eval_selection("__import__('os')", PROPS)                      # nothing outside the language runs

    def test_apply_selection_handling_and_limit(self):
        alphas = [dict(PROPS, alpha_id=f"A{i}", turnover=0.05 * i) for i in range(12)]
        df = SA.apply_selection("(turnover > 0.1) * turnover", alphas, limit=5)
        self.assertEqual(int(df["kept"].sum()), 5)
        self.assertEqual(list(df.loc[df["kept"], "alpha_id"])[:2], ["A11", "A10"])     # best first
        self.assertEqual(int(SA.apply_selection("turnover - 0.1", alphas, 50, "NON_ZERO")["kept"].sum()), 11)

    def test_pools_preview_and_limit(self):
        import pandas as pd
        pool = pd.DataFrame([dict(PROPS, alpha_id=f"A{i}", region="USA", delay=1, sharpe=1.0, fitness=1.0,
                                  decay=0, neutralization="INDUSTRY") for i in range(14)]
                            + [dict(PROPS, alpha_id="E1", region="EUR", delay=1, sharpe=1.0)])
        p = SA.pools(pool)
        self.assertEqual(list(p["region"]), ["USA", "EUR"])
        self.assertEqual((bool(p.iloc[0]["ready"]), int(p.iloc[0]["limit"])), (True, 10))
        self.assertFalse(bool(p.iloc[1]["ready"]))
        self.assertIsNone(SA.suggested_limit(9))
        self.assertEqual(SA.suggested_limit(90), 60)
        pv = SA.preview("(turnover > 0)", pool, "USA", 1, 10)
        self.assertTrue(pv["ok"])
        self.assertIn("10 of 14 alphas kept", pv["note"])
        live = pool.drop(columns=["self_correlation", "prod_correlation"])
        pv = SA.preview(SA.selections(10)[0].code, live, "USA", 1, 10)
        self.assertFalse(pv["ok"])
        self.assertIn("only BRAIN knows", pv["note"])

    def test_pool_and_journal_text(self):
        self.assertEqual(SA.pool_id("EUR", 1, __import__("datetime").date(2026, 11, 3)), "SUPER@EUR-D1@2026Q4")
        st = SA.make_payload("own", "1", "USA")["settings"]
        t = SA.journal_text("own  &&  x", "1", st)
        self.assertEqual(SA.split_journal_text(t), {"selection": "own && x", "combo": "1"})

    def test_summarize_super_alpha_json(self):
        s = summarize_alpha({"id": "S1", "type": "SUPER", "combo": {"code": "1"}, "selection": {"code": "own"},
                             "settings": {"region": "USA"}, "is": {"sharpe": 2.0, "checks": []}})
        self.assertEqual((s["expression"], s["type"], s["is_sharpe"]), ("1", "SUPER", 2.0))

    def test_diagnosis(self):
        st = {"delay": 1, "decay": 4}
        d = SA.diagnose({"alpha_id": "S", "is_sharpe": 2.2, "is_turnover": 0.55, "failed": ["HIGH_TURNOVER"]}, st, 2)
        self.assertEqual(d.verdict, "NEAR")
        self.assertEqual(d.actions[0].settings, {"decay": 10})
        self.assertEqual(SA.diagnose({"alpha_id": "S", "is_sharpe": 2.2, "is_turnover": 0.1, "failed": []}, st).verdict,
                         "PASS")
        self.assertEqual(SA.diagnose({"alpha_id": "S", "is_sharpe": 0.2, "failed": ["LOW_SHARPE"]}, st).verdict,
                         "NOISE")
        e = SA.diagnose({"status": "ERROR", "error": "unknown variable wobble"}, st)
        self.assertEqual(e.verdict, "ERROR")
        self.assertIn("wobble", e.findings[0])


class TestCountsAndUnlock(unittest.TestCase):
    def setUp(self):
        self._old = config.HOME
        self._tmp = tempfile.TemporaryDirectory()
        config.HOME = __import__("pathlib").Path(self._tmp.name)

    def tearDown(self):
        config.HOME = self._old
        self._tmp.cleanup()

    def test_super_submissions_have_their_own_count(self):
        j = Journal(":memory:")
        j.record_submission("R1", "X@USA", "fam", "USA", 1, ["pv"])
        j.record_submission("S1", "SUPER@USA-D1@2026Q4", SA.FAMILY, "USA", 1, [])
        self.assertEqual((j.submissions_today(), j.super_submissions_today()), (1, 1))

    def test_lifetime_excludes_superalphas_and_unlock(self):
        st = IdeaStore(":memory:")
        path = config.HOME / "journal.sqlite"
        j = Journal(path)
        base = planner.lifetime_submitted(st, j)
        time.sleep(0.01)
        j.record_submission("R1", "X@USA", "fam", "USA", 1, ["pv"])
        j.record_submission("S1", "SUPER@USA-D1@2026Q4", SA.FAMILY, "USA", 1, [])
        self.assertEqual(planner.lifetime_submitted(st, j), base + 1)
        lock = SA.unlock_status(st, j)
        self.assertEqual(lock["lifetime"], base + 1)
        self.assertEqual(lock["unlocked"], base + 1 >= 100)
        self.assertEqual(lock["left_today"], 0)                       # S1 used today's SuperAlpha
        self.assertTrue(SA.unlock_status(st, j, sandbox=True)["unlocked"])
        self.assertIn("Locked", SA.unlock_line(dict(lock, unlocked=False)))


class TestSandboxFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from hypolab.research import Researcher
        cls.R = Researcher.sandbox()
        cls.added = cls.R.practice_super_pool(24)

    @classmethod
    def tearDownClass(cls):
        # a sandbox Researcher holds its whole practice market; released here, not at the end of the run (the full
        # suite in one process is otherwise killed for memory on an 8 GB machine)
        import gc
        cls.R = None
        gc.collect()

    def test_1_practice_pool(self):
        self.assertGreaterEqual(self.added, SA.MIN_SELECTION)
        pool = self.R.super_pool()
        self.assertEqual(len(pool), self.added)
        self.assertTrue(pool["self_correlation"].notna().all())
        self.assertTrue(bool(SA.pools(pool).iloc[0]["ready"]))
        with self.assertRaises(RuntimeError):
            type(self.R).practice_super_pool(type("Live", (), {"is_sandbox": False})())

    def test_2_simulate_gate_submit_once_a_day(self):
        R = self.R
        sel = SA.recipe("selection", "least_corr", 15).code
        t = R.super_test(sel, "1", "SBX", "SANDBOX", 1, selection_limit=15)
        self.assertTrue(t.alpha_id)
        self.assertIn(t.diagnosis.verdict, ("PASS", "NEAR", "WEAK", "NOISE"))
        self.assertEqual(t.rung, "Least correlated x Equal weight")
        self.assertTrue(R.brain.alpha(t.alpha_id)["type"] == "SUPER")
        again = R.super_test(sel, "1", "SBX", "SANDBOX", 1, selection_limit=15)
        self.assertTrue(again.cached)                                  # same SuperAlpha: never simulated twice
        other = R.super_test(sel, SA.recipe("combo", "inv_vol").code, "SBX", "SANDBOX", 1, selection_limit=15)
        self.assertNotEqual(other.alpha_id, t.alpha_id)
        self.assertIn("Inverse volatility", R.brain.alpha(other.alpha_id)["sandbox_note"])
        g = R.super_gate(t)
        self.assertTrue(any("turnover" in r for r in g.reasons))
        self.assertTrue(any("SuperAlpha tr" in r for r in g.reasons))
        self.assertTrue(g.ready, g.reasons)                            # 1.10.2: no more g.ready = True
        res = R.super_submit(g, confirm=f"SUBMIT {g.alpha_id}")
        self.assertEqual(res["status_code"], 200)
        self.assertEqual((R.journal.super_submissions_today(), R.journal.submissions_today()), (1, 0))
        with self.assertRaises(RuntimeError):
            R.super_submit(g, confirm=f"SUBMIT {g.alpha_id}")         # a gate report is good for one submission
        g2 = R.super_gate(other)
        self.assertFalse(g2.ready)
        with self.assertRaises(RuntimeError):
            R.super_submit(g2, confirm=f"SUBMIT {g2.alpha_id}")       # BRAIN accepts one a day
        self.assertIn("today", " ".join(R.super_gate(other).reasons))
        exp = R.journal.experiments()
        self.assertEqual(set(exp[exp["purpose"] == SA.PURPOSE]["idea_id"]), {SA.pool_id("SBX", 1)})
        self.assertGreaterEqual(len(R.super_results()), 2)

    def test_3_blocked_errors_and_budget(self):
        R = self.R
        b = R.super_test("own && (x > 1", "1", "SBX", "SANDBOX", 1, selection_limit=15)
        self.assertEqual(b.diagnosis.verdict, "BLOCKED")
        e = R.super_test("own && wobble > 1", "1", "SBX", "SANDBOX", 1, selection_limit=15)
        self.assertEqual(e.diagnosis.verdict, "ERROR")                  # the sandbox, like BRAIN, refuses it
        cap = int(config.settings().get("max_super_sims_per_pool", 10))
        sel = SA.recipe("selection", "slow_core", 15).code
        last = None
        for dec in range(cap + 2):
            last = R.super_test(sel, "1", "SBX", "SANDBOX", 1, decay=dec + 20, selection_limit=15)
        self.assertEqual(last.diagnosis.verdict, "BUDGET")

    def test_4_live_lock(self):
        from hypolab.catalog import Catalog
        from hypolab.research import Researcher

        class LiveStub:                        # not a MockBrain: the Researcher takes the live path
            def simulate(self, *a, **k):
                raise AssertionError("a locked SuperAlpha must never reach BRAIN")
        R = Researcher(brain=LiveStub(), catalog=Catalog(":memory:"), journal=Journal(":memory:"))
        self.assertFalse(R.is_sandbox)
        t = R.super_test("own", "1", "USA", "TOP3000", 1, selection_limit=10, store=IdeaStore(":memory:"))
        self.assertEqual(t.diagnosis.verdict, "BLOCKED")
        self.assertIn("locked", t.diagnosis.headline)


    def test_6_pyramids_after_a_sandbox_superalpha(self):
        # 1.10.1 (M1): the Pyramids tab read a["regular"]["code"] of every submitted sandbox alpha -> KeyError
        self.assertTrue(any(a.get("type") == "SUPER" for a in self.R.brain._alphas.values()))
        self.R.brain.diversity()
        self.R.pyramids()

    def test_5_lower_correlation_leaves_superalphas_out(self):
        # a SuperAlpha's stored text is two expressions, not FASTEXPR: Lower correlation must never build on it
        R = self.R
        supers = set(R.journal.submissions().query("family == 'superalpha'")["alpha_id"])
        self.assertTrue(supers)                                         # test_2 submitted one
        t = next(x for x in (R.test(c) for c in R.ideas("SBX", n=5)) if x.alpha_id)
        own = R._own_corr(t, R._daily_pnl(t.alpha_id))
        self.assertFalse({o["alpha_id"] for o in own} & supers)


class TestRecovery(unittest.TestCase):
    def test_pending_super_is_read_back_as_a_superalpha(self):
        from hypolab.research import Researcher
        R = Researcher.sandbox()
        R.practice_super_pool(15)
        p = SA.make_payload(SA.selections(10)[0].code, "1", "SBX", "SANDBOX", selection_limit=10)
        r = R.brain.simulate([p], progress=None)[0]
        st = p["settings"]
        t = R._finish_super("Least correlated x Equal weight", SA.journal_text(p["selection"], p["combo"], st), st, r,
                            SA.pool_id("SBX", 1), 0)
        self.assertEqual(t.idea_id, SA.pool_id("SBX", 1))
        row = R.journal.experiments().iloc[-1]
        self.assertEqual((row["purpose"], json.loads(row["settings"])["selectionLimit"]), (SA.PURPOSE, 10))


if __name__ == "__main__":
    unittest.main()

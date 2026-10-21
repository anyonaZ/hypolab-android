"""1.7.0: the Ideas web app (week plan, cards, drafts) and its hand-off to the marimo Lab."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("HYPOLAB_HOME", tempfile.mkdtemp(prefix="hypolab_test_"))

from hypolab import config  # noqa: E402
from hypolab import hypotheses as hyp  # noqa: E402

HAVE = all(importlib.util.find_spec(m) for m in ("starlette", "jinja2", "httpx", "markdown", "multipart"))

GOOD = {
    "id": "IE_INV_BUILD", "title": "Inventory piling up faster than sales", "category": "auto",
    "family": "inventory_build", "horizon": "slow", "strength": "2", "sign": "-1",
    "story": "When inventory grows faster than sales, demand is weaker than managers expected and margins will be "
             "cut later; investors read the income statement first and react to the balance sheet late.",
    "why_persists": "The signal sits in the balance sheet, which few investors read; analysts anchor on guidance.",
    "references": "Thomas & Zhang (2002) Inventory Changes and Future Returns",
    "role_name_0": "inv", "role_concept_0": "inventory", "role_name_1": "sales", "role_concept_1": "sales",
    "rung_name_0": "core",
    "rung_expr_0": "-group_rank(ts_delta(ts_backfill({inv}, 63) / ts_backfill({sales}, 63), 252), subindustry)",
    "rung_teaches_0": "Change in inventory per unit of sales over a year.",
    "neutralization": "SUBINDUSTRY", "decay": "0", "truncation": "0.08", "turnover_low": "0.02",
    "turnover_high": "0.1", "n_roles": "4", "n_rungs": "3", "base": "{}", "region": "SBX", "source": "test",
}


@unittest.skipUnless(HAVE, "web dependencies not installed")
class TestIdeasApp(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        from ideaweb import state as web_state
        from ideaweb.app import app
        self._old_home = config.HOME
        self._tmp = tempfile.TemporaryDirectory()
        config.HOME = Path(self._tmp.name)
        config.save_settings(mode="sandbox")
        hyp._LIB_CACHE.clear()
        web_state.reset()
        self.c = TestClient(app)

    def tearDown(self):
        from ideaweb import state as web_state
        web_state.reset()
        config.HOME = self._old_home
        hyp._LIB_CACHE.clear()
        self._tmp.cleanup()

    def test_pages_render(self):
        for url in ("/week", "/cards", "/drafts", "/drafts/new"):
            r = self.c.get(url)
            self.assertEqual(r.status_code, 200, url)
        self.assertIn("Friday review", self.c.get("/week").text)
        self.assertIn("Send to the Lab", self.c.get("/cards").text)

    def test_live_check_save_approve_and_send_to_lab(self):
        bad = dict(GOOD, role_concept_1="salez")
        j = self.c.post("/api/check", data=bad).json()
        self.assertFalse(j["ok"])
        self.assertIn("did you mean sales", j["html"])
        j = self.c.post("/api/check", data=GOOD).json()
        self.assertTrue(j["ok"], j["summary"])
        self.assertIn("binds in SBX", j["summary"])
        self.assertIn("fnd_inventory", j["html"])
        self.assertIn("# role inv (inventory) -> fnd_inventory", j["critic"])
        r = self.c.post("/drafts/save", data=dict(GOOD, action="save"), follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertIn("/drafts/IE_INV_BUILD", r.headers["location"])
        r = self.c.post("/drafts/save", data=dict(GOOD, action="approve", old_id="IE_INV_BUILD"),
                        follow_redirects=False)
        self.assertIn("lab=IE_INV_BUILD", r.headers["location"])
        self.assertTrue((config.HOME / "library" / "my_cards.yaml").exists())
        self.assertIn("IE_INV_BUILD", [h.id for h in hyp.load_library() if h.source == "mine"])
        self.c.post("/cards/IE_INV_BUILD/lab", data={"region": "SBX"})
        from ideaengine import handoff
        m = handoff.take_new()
        self.assertEqual(m["card"], "IE_INV_BUILD")
        self.assertIsNone(handoff.take_new())               # picked up once

    def test_approve_refused_with_errors(self):
        r = self.c.post("/drafts/save", data=dict(GOOD, story="", action="approve"), follow_redirects=False)
        self.assertIn("kind=err", r.headers["location"])
        self.assertFalse((config.HOME / "library" / "my_cards.yaml").exists())

    def test_cards_bin_restore_copy(self):
        self.c.post("/cards/PV_52W_HIGH/bin", data={"reason": "noise - no real signal"})
        from ideaweb.state import state
        self.assertIn("PV_52W_HIGH", state().journal.binned_ids())
        self.assertNotIn('id="PV_52W_HIGH"', self.c.get("/cards?n=60").text)
        self.c.post("/cards/PV_52W_HIGH/restore")
        self.assertNotIn("PV_52W_HIGH", state().journal.binned_ids())
        r = self.c.post("/cards/PV_52W_HIGH/draft", follow_redirects=False)
        self.assertIn("/drafts/IE_PV_52W_HIGH_V2", r.headers["location"])
        self.assertEqual(self.c.get("/drafts/IE_PV_52W_HIGH_V2").status_code, 200)

    def test_import_verdict_and_plan(self):
        text = ("```yaml\n# from: B-1\n- id: IE_X\n  title: t\n  category: auto\n  family: x_fam\n  horizon: slow\n"
                "  strength: 2\n  sign: '+1'\n  story: s\n  why_persists: w\n  references: [r]\n  roles: {}\n"
                "  ladder:\n  - {name: core, expr: 'rank(-ts_sum(returns, 21))', teaches: t}\n"
                "  settings: {neutralization: SUBINDUSTRY, decay: 0, truncation: 0.08}\n"
                "  expected_turnover: [0.1, 0.3]\n```")
        r = self.c.post("/drafts/import", data={"cards": text, "region": "SBX"}, follow_redirects=False)
        self.assertIn("/drafts/IE_X", r.headers["location"])
        r = self.c.post("/drafts/verdict", data={"verdict": "verdict:\n  id: IE_X\n  decision: keep\n  one_line: ok\n"},
                        follow_redirects=False)
        self.assertIn("Verdict+keep", r.headers["location"])
        plan = ("plan:\n  week: 2026-W44\n  region: SBX\n  categories: [pv]\n  card_target: 3\n  submit_target: 8\n"
                "  lessons: [one lesson]\n  review_note: fine\n")
        r = self.c.post("/week/review", data={"plan": plan}, follow_redirects=False)
        self.assertIn("week=2026-W44", r.headers["location"])
        from ideaweb.state import state
        self.assertEqual(state().store.plan("2026-W44")["submit_target"], 8)
        self.assertIn("2026-W44", self.c.get("/week?week=2026-W44").text)



@unittest.skipUnless(HAVE, "web dependencies not installed")
class TestLeadsAndWeek(unittest.TestCase):
    """1.8.0: phase 4 (Week evidence, Friday checklist, state text) and phase 5 (Leads) in the Ideas app."""
    def setUp(self):
        import time
        from starlette.testclient import TestClient
        from hypolab.journal import Journal
        from ideaweb import state as web_state
        from ideaweb.app import app
        self._old_home = config.HOME
        self._tmp = tempfile.TemporaryDirectory()
        config.HOME = Path(self._tmp.name)
        config.save_settings(mode="sandbox")
        hyp._LIB_CACHE.clear()
        web_state.reset()
        j = Journal()                                   # the real journal file the Ideas app reads
        def idea(i, fam, region="USA", cats="analyst", h=None):
            j.db.execute("INSERT OR IGNORE INTO ideas (id, hypothesis_id, region, family, title, categories, created) "
                         "VALUES (?,?,?,?,?,?,?)", (i, h or i.split("@")[0], region, fam, i, cats, 0))
            j.db.commit()
        n = [0]
        def res(i, v, sh, region="USA", purpose="explore", expr=None):
            n[0] += 1
            j.record(i, "core", purpose, expr or f"rank(x{n[0]})", {"region": region, "delay": 1, "universe": "TOP3000"},
                     {"alpha_id": f"A{n[0]}", "is_sharpe": sh, "status": "COMPLETE"}, v)
            time.sleep(0.002)
        idea("FND_ACCRUALS@USA", "accruals", cats="fundamental")
        for k in range(10):
            res("FND_ACCRUALS@USA", "NEAR" if k == 6 else "WEAK", 1.3 if k == 6 else 0.8)
        idea("SNT_NEWS_DRIFT@USA", "news_drift", cats="news")
        res("SNT_NEWS_DRIFT@USA", "INVERTED", -1.7)
        for k, sh in enumerate([0.1, -0.2, 0.15, 0.05, -0.1, 0.2, 0.0, 0.12, -0.05, 0.08, 2.9]):
            idea(f"LENS_f{k}@EUR", "lens_dsx", region="EUR", cats="model", h=f"LENS_f{k}")
            res(f"LENS_f{k}@EUR", "NOISE", sh, region="EUR", purpose="scan", expr=f"rank(ts_rank(f{k}, 63))")
        self.c = TestClient(app)

    def tearDown(self):
        from ideaweb import state as web_state
        web_state.reset()
        config.HOME = self._old_home
        hyp._LIB_CACHE.clear()
        self._tmp.cleanup()

    def test_week_shows_evidence_checklist_and_state_text(self):
        t = self.c.get("/week").text
        self.assertIn("What the week has to respect", t)
        self.assertIn("Download your account", t)
        self.assertIn("Text for the HYPOLAB state doc", t)
        self.assertIn("Leads from the journal", t)

    def test_leads_list_draft_skip_and_lab(self):
        from ideaengine import handoff
        t = self.c.get("/leads").text
        self.assertIn("FND_ACCRUALS@USA", t)                 # near miss at the budget: a sibling
        self.assertIn("dsx.f10", t)                          # scanned field above the noise bar
        self.assertIn("SNT_NEWS_DRIFT@USA", t)               # inverted
        r = self.c.post("/leads/act", data={"key": "sibling:FND_ACCRUALS@USA", "action": "draft"},
                        follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertIn("/drafts/IE_FND_ACCRUALS_SIB", r.headers["location"])
        self.assertNotIn("FND_ACCRUALS@USA", self.c.get("/leads").text.split("Source quality")[0])
        r = self.c.post("/leads/act", data={"key": "scan:dsx.f10@EUR", "action": "draft"}, follow_redirects=False)
        self.assertIn("/drafts/IE_SCAN_F10", r.headers["location"])
        r = self.c.post("/leads/act", data={"key": "inverted:SNT_NEWS_DRIFT@USA", "action": "lab"},
                        follow_redirects=False)
        self.assertEqual(handoff.peek()["card"], "SNT_NEWS_DRIFT")
        self.c.post("/leads/act", data={"key": "inverted:SNT_NEWS_DRIFT@USA", "action": "skip", "note": "no story"})
        self.assertIn("no story", self.c.get("/leads?show=all").text)
        r = self.c.post("/leads/act", data={"key": "nope:x", "action": "skip"}, follow_redirects=False)
        self.assertIn("gone", r.headers["location"])


if __name__ == "__main__":
    unittest.main()

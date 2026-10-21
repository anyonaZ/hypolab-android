"""HYPOLAB 1.10.3: the paste boxes between the Claude chats (agent pack v3) and HYPOLAB, and the learning loop closed.

- `# from:` lines bind to the card below them (a missing one or a "no card" slot no longer shifts every source);
- an import never overwrites a waiting or binned draft unless it is ticked as a rewrite; a rewrite keeps the source
  and clears the old verdict (kept in the verdict history);
- a PLAN says what it ignored (universe, delay, unknown keys);
- the Weekly Reviewer's lessons and dead ends reach 07_dead_ends.md, the state doc and the card checks;
- the state doc lists waiting draft ids and carries the card reference (concepts, operators, priority datasets);
- `daily brief <date> via S-...` keeps both the writer and the source in Source quality;
- the Critic's decisions are measured against results;
- Copy for the Critic carries the week's plan and says when the dry run ran elsewhere. No network."""
import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("HYPOLAB_HOME", tempfile.mkdtemp(prefix="hypolab_test_"))

from hypolab import config  # noqa: E402
from hypolab import hypotheses as hyp  # noqa: E402
from hypolab import learning  # noqa: E402
from hypolab.journal import Journal  # noqa: E402
from ideaengine import drafts as D  # noqa: E402
from ideaengine import knowledge_pack, learn  # noqa: E402
from ideaengine.store import IdeaStore  # noqa: E402

HAVE_WEB = all(importlib.util.find_spec(m) for m in ("starlette", "jinja2", "httpx", "markdown", "multipart"))
ROOT = Path(__file__).resolve().parent.parent


def card(cid, title="t", fam="inv_build"):
    return (f"- id: {cid}\n  title: \"{title}\"\n  category: auto\n  family: {fam}\n  horizon: slow\n  strength: 2\n"
            "  sign: '-1'\n  story: >\n    When inventory grows faster than sales, demand is weaker than managers expected"
            " and margins will be cut later; investors read the income statement first.\n  why_persists: >\n"
            "    The signal sits in the balance sheet, which few investors read; analysts anchor on guidance.\n"
            "  references: [\"Thomas & Zhang (2002)\"]\n  roles:\n    inv: {concept: inventory}\n"
            "    sales: {concept: sales}\n  ladder:\n    - name: core\n      expr: \"-group_rank(ts_delta(ts_backfill("
            "{inv}, 63) / ts_backfill({sales}, 63), 252), subindustry)\"\n      teaches: \"inventory per unit of sales\"\n"
            "  settings: {neutralization: SUBINDUSTRY, decay: 0, truncation: 0.08}\n  expected_turnover: [0.02, 0.1]\n")


class TestFromLines(unittest.TestCase):
    def test_each_card_gets_the_comment_above_it(self):
        text = ("```yaml\n# from: daily brief 2026-10-20\n" + card("IE_A") + "# from: S-osap-Accruals\n"
                "# NO CARD: slot 2\n# from: daily brief 2026-10-20\n" + card("IE_C") + "```\nTest first: x\n")
        p = D.parse_cards(text)
        self.assertEqual([(x.card["id"], x.source) for x in p],
                         [("IE_A", "daily brief 2026-10-20"), ("IE_C", "daily brief 2026-10-20")])
        self.assertTrue(any("several" in w for w in p[0].warnings), p[0].warnings)

    def test_missing_comment_no_longer_shifts_the_others(self):
        text = ("```yaml\n" + card("IE_A") + "# from: S-osap-Accruals\n" + card("IE_B") + "# from: B-20261021-0915\n"
                + card("IE_C") + "```")
        p = D.parse_cards(text)
        self.assertEqual([x.source for x in p], ["", "S-osap-Accruals", "B-20261021-0915"])
        self.assertIn("IE_A has no `# from:` line", " ".join(p[0].warnings))

    def test_dangling_comment_and_outside_the_fence(self):
        p = D.parse_cards("```yaml\n" + "# from: scout: a\n" + card("IE_A") + "# from: S-news-x-2026-W43\n```")
        self.assertEqual(p[0].source, "scout: a")
        self.assertTrue(any("not followed by a card" in w for w in p[0].warnings))
        p = D.parse_cards("# from: B-20261020-1200\n```yaml\n" + card("IE_A") + "```")
        self.assertEqual(p[0].source, "B-20261020-1200")

    def test_one_comment_still_covers_a_list(self):
        p = D.parse_cards("# from: scout: one paper\n" + card("IE_A") + card("IE_B"))
        self.assertEqual([x.source for x in p], ["scout: one paper"] * 2)
        self.assertEqual(p[0].warnings, [])


class TestPlanNotes(unittest.TestCase):
    def test_ignored_keys_are_named(self):
        plan, probs = D.parse_plan("plan:\n  week: 2026-W44\n  region: EUR\n  universe: TOP2500\n  delay: 0\n"
                                   "  categories: [analyst]\n  colour: blue\n", ["EUR"])
        self.assertIsNotNone(plan)
        self.assertEqual(plan["delay"], 1)
        txt = " ".join(probs)
        self.assertIn("universe and delay are not part of a PLAN", txt)
        self.assertIn("unknown key(s) ignored: colour", txt)


class TestLoop(unittest.TestCase):
    def setUp(self):
        self.j, self.s = Journal(":memory:"), IdeaStore(":memory:")
        D.apply_plan(self.s, self.j, {"week": "2026-W44", "region": "USA", "universe": "TOP3000", "delay": 1,
                                       "categories": ["analyst"], "dataset_focus": "", "card_target": 5,
                                       "submit_target": 10, "review_note": "",
                                       "extra": {"retry": [], "dead_ends": ["inv_build"],
                                                 "lessons": ["Start analyst cards with decay 3"]}})

    def test_lessons_and_dead_ends_reach_the_pack_and_the_checks(self):
        dd = learning.declared_dead_ends(self.j)
        self.assertEqual(dd["family"].tolist(), ["inv_build"])
        self.assertEqual(dd["week"].iloc[0], "2026-W44")
        txt = knowledge_pack.dead_ends(self.j)
        self.assertIn("| inv_build | 2026-W44 |", txt)
        self.assertIn("[2026-W44] Start analyst cards with decay 3", txt)
        self.assertNotIn("dead end: stop the family", txt.split("## Lessons")[1])
        import yaml
        rep = D.check_card(yaml.safe_load(card("IE_NEW"))[0], journal=self.j, library=hyp.load_library())
        self.assertTrue(any("declared inv_build a dead end in 2026-W44" in c.message for c in rep.checks))

    def test_state_doc_has_waiting_ids_lessons_and_reference(self):
        import yaml
        dr = D.Drafts(self.s)
        dr.save(yaml.safe_load(card("IE_WAITING"))[0], "scout: x")
        md = D.state_text(self.j, self.s, "2026-W44")
        used = md.split("## Card ids already used")[1]
        self.assertIn("| IE_WAITING | waiting |", used)
        self.assertIn("Dead end (2026-W44): stop the family inv_build.", md)
        self.assertIn("Lesson (2026-W44): Start analyst cards with decay 3", md)
        ref = md.split("## Card reference for the brief")[1]
        for name in ("inventory", "group_rank", "ts_backfill", "subindustry"):
            self.assertIn(name, ref)

    def test_buckets(self):
        b = lambda s: learn._bucket("IE_X", "IE_X@EUR", {}, {"IE_X": s})  # noqa: E731
        self.assertEqual(b("daily brief 2026-10-21 via S-osap-Accruals"),
                         "daily brief + outside: published predictors (OSAP)")
        self.assertEqual(b("daily brief 2026-10-21"), "daily brief")
        self.assertEqual(b("S-osap-Accruals"), "outside: published predictors (OSAP)")
        self.assertEqual(b("scout: Thomas & Zhang (2002)"), "Scout & Writer")
        self.assertEqual(b("B-20261021-0915"), "Scout & Writer")
        self.assertEqual(b("inbox: sibling IE_Y"), "inbox (learning loop)")

    def test_critic_calibration(self):
        import yaml
        dr = D.Drafts(self.s)
        for cid in ("IE_K", "IE_B", "IE_N"):
            dr.save(yaml.safe_load(card(cid, fam=cid.lower()))[0], "scout: x")
        dr.attach_verdict("verdict:\n  id: IE_K\n  decision: keep\n  scores: {novelty: 4, data_fit: 3}\n")
        dr.attach_verdict("verdict:\n  id: IE_B\n  decision: bin\n  scores: {novelty: 1, data_fit: 1}\n")
        for cid, v in (("IE_K", "NEAR"), ("IE_B", "NOISE"), ("IE_N", "PASS")):
            self.j.db.execute("INSERT INTO ideas (id, hypothesis_id, region, family, title, categories, created) "
                              "VALUES (?,?,?,?,?,?,?)", (f"{cid}@USA", cid, "USA", cid.lower(), cid, "analyst", 0))
            self.j.record(f"{cid}@USA", "core", "explore", f"rank({cid})", {"region": "USA", "delay": 1,
                          "universe": "TOP3000"}, {"alpha_id": cid, "is_sharpe": 1.0, "status": "COMPLETE",
                                                   "failed": []}, v, backend="brain")
            time.sleep(0.001)
        cc = learn.critic_calibration(self.j, self.s).set_index("decision")
        self.assertEqual((int(cc.loc["keep", "tested"]), int(cc.loc["keep", "near_or_pass"])), (1, 1))
        self.assertEqual((int(cc.loc["bin", "tested"]), int(cc.loc["bin", "near_or_pass"])), (1, 0))
        self.assertEqual(int(cc.loc["no verdict", "near_or_pass"]), 1)
        self.assertIn("novelty 4.0", cc.loc["keep", "avg_scores"])
        self.assertIn("critic_calibration", learn.digest(self.j, self.s))


class TestCriticCopy(unittest.TestCase):
    def test_plan_line_and_region_note(self):
        import yaml
        c = yaml.safe_load(card("IE_A"))[0]
        rep = D.check_card(c, library=hyp.load_library())
        rep.region = "USA"
        msg = D.critic_message(c, rep, "scout: x", {"region": "EUR", "universe": "TOP800", "delay": 1,
                                                    "categories": ["analyst", "model"]})
        self.assertIn("# this week's plan: EUR TOP800 D1, categories analyst, model", msg)
        self.assertIn("# NOTE: the dry run ran in USA, not in the plan's region EUR", msg)
        self.assertIsInstance(yaml.safe_load(msg), list)


class TestPackIndex(unittest.TestCase):
    def test_static_files_listed_and_projects_exist(self):
        out = Path(tempfile.mkdtemp())
        knowledge_pack.build(out)
        idx = (out / "INDEX.md").read_text()
        self.assertIn("| HANDOFF_CONTRACTS.md | Scout & Writer, Critic, Weekly Reviewer |", idx)
        self.assertNotIn("BRAIN Library", idx)
        for f in ("1_scout_writer.md", "2_critic.md", "3_weekly_reviewer.md", "daily_brief_prompt.md",
                  "HANDOFF_CONTRACTS.md", "briefs.md"):
            self.assertTrue((ROOT / "claude_projects" / f).exists(), f)
        self.assertIn("06_goals_and_rules.md", (ROOT / "claude_projects" / "1_scout_writer.md").read_text())


@unittest.skipUnless(HAVE_WEB, "web dependencies not installed")
class TestImportBox(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        from ideaweb import state as web_state
        from ideaweb.app import app
        self._old = config.HOME
        self._tmp = tempfile.TemporaryDirectory()
        config.HOME = Path(self._tmp.name)
        config.save_settings(mode="sandbox")
        hyp._LIB_CACHE.clear()
        web_state.reset()
        self.c = TestClient(app)
        self.st = web_state.state()

    def tearDown(self):
        from ideaweb import state as web_state
        web_state.reset()
        config.HOME = self._old
        hyp._LIB_CACHE.clear()
        self._tmp.cleanup()

    def imp(self, text, **extra):
        return self.c.post("/drafts/import", data={"cards": text, "region": "SBX", **extra}, follow_redirects=False)

    def test_no_silent_overwrite_and_rewrite(self):
        self.imp("```yaml\n# from: B-20261020-0900\n" + card("IE_A", "first") + "```")
        self.c.post("/drafts/verdict", data={"verdict": "verdict:\n  id: IE_A\n  decision: rewrite\n", "draft_id": "IE_A"})
        r = self.imp("```yaml\n# from: daily brief 2026-10-22\n" + card("IE_A", "another idea") + "```")
        self.assertIn("kind=err", r.headers["location"])
        self.assertIn("already+exists", r.headers["location"])
        self.assertEqual(self.st.drafts.get("IE_A")["title"], "first")
        r = self.imp("```yaml\n" + card("IE_A", "first v2") + "```", rewrite="1")
        self.assertIn("rewrite", r.headers["location"])
        row = self.st.drafts.get("IE_A")
        self.assertEqual((row["title"], row["source"], row["decision"]), ("first v2", "B-20261020-0900", ""))
        self.assertEqual(self.st.drafts.verdict_history("IE_A")["decision"].tolist(), ["rewrite"])

    def test_binned_draft_is_not_unbinned_by_accident(self):
        self.imp("```yaml\n# from: scout: x\n" + card("IE_B") + "```")
        self.st.drafts.bin("IE_B", "Critic said bin")
        self.imp("```yaml\n# from: scout: y\n" + card("IE_B", "reuse") + "```")
        self.assertEqual(self.st.drafts.get("IE_B")["state"], "binned")

    def test_drafts_page_has_region_choice_and_rewrite_box(self):
        t = self.c.get("/drafts").text
        self.assertIn('name="rewrite"', t)
        self.assertIn('<select name="region">', t)


if __name__ == "__main__":
    unittest.main()

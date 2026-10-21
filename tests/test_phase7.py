"""Phase 7 (HYPOLAB 1.9.0): collectors - Open Source Asset Pricing, arXiv, news themes, under-used datasets - the
sources inbox, its hand-offs (SOURCE block, skeleton draft), source quality, the state doc and the Ideas app.
No test touches the network: fetching is patched with the fixtures in tests/fixtures."""
import datetime as dt
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("HYPOLAB_HOME", tempfile.mkdtemp(prefix="hypolab_test_"))

from hypolab import config  # noqa: E402
from hypolab import hypotheses as hyp  # noqa: E402
from hypolab.catalog import Catalog  # noqa: E402
from hypolab.journal import Journal  # noqa: E402
from ideaengine import collectors as C  # noqa: E402
from ideaengine import drafts, learn, planner  # noqa: E402
from ideaengine import sources as S  # noqa: E402
from ideaengine.store import IdeaStore  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
ARXIV = (FIX / "arxiv_qfin.xml").read_text()
NEWS = (FIX / "news_feed.xml").read_text()
TODAY = dt.date(2026, 10, 20)
HAVE_WEB = all(importlib.util.find_spec(m) for m in ("starlette", "jinja2", "httpx", "markdown", "multipart"))


def fake_get(url, timeout=20, params=None, raw=False):
    if "arxiv" in url:
        return ARXIV
    if "OpenSourceAP" in url:
        return C.load_file(C.OSAP_FILE)
    return NEWS


class TestCollectors(unittest.TestCase):
    def test_osap_bundled_list(self):
        items = C.read_osap()
        self.assertEqual(len(items), 212)                       # predictors only (placebos and drops left out)
        acc = next(i for i in items if i.id == "osap:Accruals")
        self.assertEqual((acc.authors, acc.year, acc.extra["sign"], acc.extra["category"]), ("Sloan", 1996, -1,
                                                                                            "fundamental"))
        self.assertGreater(acc.extra["t_stat"], 4)
        self.assertLessEqual(max(len(i.summary) for i in items), C.SUMMARY_MAX)
        self.assertGreater(len(C.read_osap(include_placebos=True)), 300)
        with self.assertRaises(ValueError):
            C.read_osap("a,b\n1,2\n")

    def test_arxiv_keeps_cross_sectional_papers_only(self):
        items = C.read_arxiv(ARXIV)
        self.assertEqual([i.id for i in items], ["arxiv:2610.01234", "arxiv:2610.04567"])   # version dropped
        self.assertEqual(items[0].authors, "Doe et al.")
        self.assertEqual(items[1].authors, "Smith & Jones")
        self.assertEqual(items[0].published, "2026-10-15")
        self.assertIn("q-fin.ST", items[0].extra["categories"])
        self.assertEqual(C.arxiv_relevance("Rough volatility and option pricing", "hedging"), 0.0)

    def test_news_grouped_into_weekly_themes(self):
        items = {i.id: i for i in C.read_news([NEWS], today=TODAY)}
        g = items["news:guidance_cut:2026-W43"]
        self.assertEqual(g.extra["count"], 3)                    # Acme, Globex, Initech; the June story is too old
        self.assertNotIn("Soylent", g.summary)
        self.assertIn("news:management_change:2026-W42", items)  # Sunday 18 Oct is still week 42
        self.assertFalse(any("restaurant" in str(i.extra) for i in items.values()))   # no theme: dropped
        self.assertEqual(g.extra["category"], "earnings")

    def test_parse_feed_rejects_garbage(self):
        with self.assertRaises(ValueError):
            C.parse_feed("<html><body>not a feed")

    def test_datasets_collector(self):
        cat = Catalog(":memory:")
        cat.ingest_payload({"region": "EUR", "universe": "TOP2500", "delay": 1, "datasets": [
            {"id": "model162", "name": "Return prediction from conference call", "category": "model",
             "value_score": 4, "alpha_count": 24, "coverage": 0.58},
            {"id": "analyst4", "name": "Crowded analyst", "category": "analyst", "value_score": 1, "alpha_count": 90000},
            {"id": "model77", "name": "Used one", "category": "model", "value_score": 3, "alpha_count": 600}],
            "fields": [{"id": "mdl162_score", "dataset": "model162", "type": "MATRIX", "coverage": 0.6,
                        "description": "predicted return from the call"},
                       {"id": "anl4_x", "dataset": "analyst4", "type": "MATRIX", "coverage": 0.9},
                       {"id": "mdl77_y", "dataset": "model77", "type": "MATRIX", "coverage": 0.8}]})
        j = Journal(":memory:")
        j.record("X@EUR", "core", "explore", "rank(mdl77_y)", {"region": "EUR", "delay": 1, "universe": "TOP2500"},
                 {"alpha_id": "A1", "is_sharpe": 0.4, "status": "COMPLETE"}, "NOISE")
        # 1.9.0 fix: fields BRAIN sends without a description no longer crash the catalog's enrichment
        self.assertEqual(cat.fields("EUR", "TOP2500", 1).loc[lambda d: d["id"] == "anl4_x", "description"].iloc[0], "")
        self.assertEqual(len(cat.concept_map("analyst4", "EUR", "TOP2500", 1)), 1)
        items = C.read_datasets(cat, j)
        self.assertEqual([i.id for i in items], ["dataset:EUR:model162"])   # crowded and already-used left out
        self.assertEqual(items[0].extra["theme"], "EUR/D1 TOP800 Theme")     # in Zacc's priority list


class TestSourcesInbox(unittest.TestCase):
    def setUp(self):
        self.st = IdeaStore(":memory:")

    def test_upsert_keeps_decisions_and_tags(self):
        res = S.upsert(self.st, C.read_osap())
        self.assertEqual(res, {"found": 212, "added": 212})
        acc = S.get(self.st, "osap:Accruals")
        self.assertEqual(acc["covered_by"], ["FND_ACCRUALS"])               # Sloan (1996) is cited by the card
        self.assertIn("fundamental", acc["categories"])
        self.assertEqual(acc["tag"], "S-osap-Accruals")
        S.skip(self.st, "osap:Accruals", "card exists")
        self.assertEqual(S.upsert(self.st, C.read_osap())["added"], 0)
        again = S.get(self.st, "osap:Accruals")
        self.assertEqual((again["state"], again["note"]), ("skipped", "card exists"))
        self.assertNotIn("osap:Accruals", set(S.items(self.st, limit=0)["id"]))
        S.reopen(self.st, "osap:Accruals")
        self.assertIn("osap:Accruals", set(S.items(self.st, limit=0)["id"]))

    def test_covered_by_needs_the_same_paper(self):
        lib = hyp.load_library()
        mk = lambda a, y: C.SourceItem(id="osap:x", kind="osap", title="t", authors=a, year=y)  # noqa: E731
        self.assertEqual(S.covered_by(mk("Cooper, Gulen and Schill", 2008), lib), ["FND_ASSET_GROWTH"])
        self.assertEqual(S.covered_by(mk("Zhang", 2006), lib), [])          # Zhang is 4th author of Ang et al.
        self.assertEqual(S.covered_by(mk("Loughran and Wellman", 2011), lib), [])   # Loughran & McDonald (2011)
        self.assertEqual(S.covered_by(mk("Sloan", 1997), lib), [])

    def test_ranking_follows_the_plan_and_covered_items_drop(self):
        S.upsert(self.st, C.read_osap())
        plan = {"region": "EUR", "categories": ["analyst"]}
        top = S.items(self.st, plan=plan, limit=10)
        self.assertTrue(all("analyst" in c for c in top["categories"].head(3)))
        allr = S.items(self.st, plan=plan, limit=0).reset_index(drop=True)
        pos = {i: k for k, i in enumerate(allr["id"])}
        self.assertGreater(pos["osap:Accruals"], pos["osap:TotalAccruals"])   # covered by a card -> lower

    def test_news_merge_and_minimum(self):
        S.upsert(self.st, C.read_news([NEWS], today=TODAY))
        g = S.get(self.st, "news:guidance_cut:2026-W43")
        self.assertEqual(g["extra"]["count"], 3)
        more = NEWS.replace("example.com/a1", "example.com/b1").replace("Acme", "Vandelay")
        S.upsert(self.st, C.read_news([more], today=TODAY))
        self.assertEqual(S.get(self.st, "news:guidance_cut:2026-W43")["extra"]["count"], 4)
        shown = set(S.items(self.st, limit=0, today=TODAY)["id"])
        self.assertIn("news:guidance_cut:2026-W43", shown)
        self.assertNotIn("news:management_change:2026-W42", shown)          # one headline is no pattern
        self.assertIn("news:management_change:2026-W42", set(S.items(self.st, limit=0, min_news=0, today=TODAY)["id"]))

    def test_collect_logs_runs_and_errors(self):
        old = C.http_get
        try:
            C.http_get = fake_get
            self.assertEqual(S.collect(self.st, "arxiv")["added"], 2)
            self.assertEqual(S.collect(self.st, "news", today=TODAY)["added"], 5)
            self.assertEqual(S.collect(self.st, "osap", origin="download")["found"], 212)

            def boom(*a, **k):
                raise ConnectionError("no route")
            C.http_get = boom
            with self.assertRaises(RuntimeError):
                S.collect(self.st, "news")
        finally:
            C.http_get = old
        runs = S.last_runs(self.st)
        self.assertIn("no feed could be read", runs["news"]["error"])
        self.assertEqual(runs["arxiv"]["added"], 2)
        with self.assertRaises(ValueError):
            S.collect(self.st, "tweets")

    def test_writer_message_and_skeleton_draft(self):
        S.upsert(self.st, C.read_osap())
        d = S.get(self.st, "osap:Accruals")
        msg = S.writer_message(d, {"region": "EUR", "universe": "TOP800", "categories": ["analyst"]})
        self.assertTrue(msg.startswith("### SOURCE S-osap-Accruals: Accruals"))
        for part in ("Sloan (1996)", "t-stat 4.71", "FND_ACCRUALS", "# from: S-osap-Accruals", "McLean & Pontiff"):
            self.assertIn(part, msg)
        card = S.source_draft(d)
        self.assertTrue(card["id"].startswith("IE_SRC_ACCRUALS"))
        self.assertEqual(card["sign"], "-1")
        rep = drafts.check_card(card, None, None)
        errs = {(c.where, c.message) for c in rep.errors}
        self.assertIn(("why_persists", "empty"), errs)                     # the mechanism is yours to write
        self.assertTrue(any(w.startswith("rung 1") for w, _ in errs))      # and so is rung 1
        self.assertFalse(any(w.startswith("roles") for w, _ in errs))      # suggested concepts all exist

    def test_manual_source_and_import_link(self):
        sid = S.add_manual(self.st, "Operating leverage and returns", "https://example.com/p", "Fixed costs ...",
                           "Novy-Marx", "2011")
        tag = S.source_tag(sid)
        self.assertTrue(tag.startswith("S-manual-"))
        self.assertEqual(S.link_draft(self.st, f"{tag} (Scout & Writer)", "IE_OPLEV"), sid)
        self.assertEqual(S.get(self.st, sid)["state"], "drafted")
        self.assertIsNone(S.link_draft(self.st, "daily brief 2026-10-20", "IE_X"))
        with self.assertRaises(ValueError):
            S.add_manual(self.st, "  ")

    def test_source_quality_bucket_and_digest(self):
        b = learn._bucket("IE_SRC_X", "IE_SRC_X@EUR", {}, {"IE_SRC_X": "S-osap-Accruals"})
        self.assertEqual(b, "outside: published predictors (OSAP)")
        self.assertEqual(learn._bucket("IE_Y", "IE_Y@EUR", {}, {"IE_Y": "S-arxiv-2610.01234"}), "outside: arXiv papers")
        self.assertEqual(learn._bucket("IE_Z", "IE_Z@EUR", {}, {"IE_Z": "daily brief 2026-10-20"}), "daily brief")
        S.upsert(self.st, C.read_arxiv(ARXIV))
        self.assertIn("arXiv 2 new", S.digest_line(self.st))
        dg = learn.digest(Journal(":memory:"), self.st)
        self.assertEqual(dg["outside_sources"]["arxiv"]["new"], 2)

    def test_state_text_has_fresh_sources(self):
        S.upsert(self.st, C.read_arxiv(ARXIV))
        txt = drafts.state_text(Journal(":memory:"), self.st, planner.iso_week(TODAY))
        self.assertIn("## Fresh outside sources", txt)
        self.assertIn("S-arxiv-2610.01234", txt)


class TestCliAndPack(unittest.TestCase):
    def test_cli_with_a_saved_file(self):
        from ideaengine import collect
        home = tempfile.mkdtemp()
        old = config.HOME
        config.HOME = Path(home)
        try:
            self.assertEqual(collect.main(["arxiv", "--file", str(FIX / "arxiv_qfin.xml")]), 0)
            self.assertEqual(collect.main(["list"]), 0)
            self.assertEqual(collect.main(["nonsense"]), 1)
            st = IdeaStore()
            self.assertEqual(S.counts(st)["arxiv"]["new"], 2)
        finally:
            config.HOME = old

    def test_knowledge_pack_published_predictors(self):
        from ideaengine import knowledge_pack as kp
        text = kp.published_predictors()
        self.assertIn("## Not covered by any card yet", text)
        self.assertIn("| Accruals | Accruals | Sloan (1996)", text)
        cov = text.split("## Same paper as an existing card")[1]
        self.assertIn("FND_ACCRUALS", cov)


@unittest.skipUnless(HAVE_WEB, "web dependencies not installed")
class TestSourcesPage(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        from ideaweb import state as web_state
        from ideaweb.app import app
        self._old_home, self._old_get = config.HOME, C.http_get
        self._tmp = tempfile.TemporaryDirectory()
        config.HOME = Path(self._tmp.name)
        config.save_settings(mode="sandbox")
        hyp._LIB_CACHE.clear()
        web_state.reset()
        C.http_get = fake_get
        self.c = TestClient(app)

    def tearDown(self):
        from ideaweb import state as web_state
        web_state.reset()
        C.http_get = self._old_get
        config.HOME = self._old_home
        hyp._LIB_CACHE.clear()
        self._tmp.cleanup()

    def test_collect_list_draft_skip_and_import(self):
        self.assertIn("Load the bundled list", self.c.get("/leads/sources").text)
        self.assertIn("From outside", self.c.get("/leads").text)
        r = self.c.post("/leads/sources/fetch", data={"collector": "osap"}, follow_redirects=False)
        self.assertIn("212+new", r.headers["location"])
        r = self.c.post("/leads/sources/fetch", data={"collector": "arxiv"}, follow_redirects=False)
        t = self.c.get(r.headers["location"]).text
        self.assertIn("Analyst Attention and the Cross-Section", t)
        self.assertIn("### SOURCE S-arxiv-2610.01234", t)
        self.assertNotIn("Rough Volatility", t)
        r = self.c.post("/leads/sources/act", data={"id": "osap:TotalAccruals", "action": "draft"},
                        follow_redirects=False)
        self.assertIn("/drafts/IE_SRC_TOTALACCRUALS", r.headers["location"])
        self.assertEqual(self.c.get("/drafts/IE_SRC_TOTALACCRUALS").status_code, 200)
        self.c.post("/leads/sources/act", data={"id": "arxiv:2610.04567", "action": "skip", "note": "inventory card"})
        self.assertIn("inventory card", self.c.get("/leads/sources?show=skipped").text)
        card = ("# from: S-arxiv-2610.01234\n- id: IE_ANL_DISTRACTED\n  title: Distracted analysts\n  category: auto\n"
                "  family: anl_distraction\n  horizon: medium\n  strength: 1\n  sign: '+1'\n  story: s\n  why_persists: w\n"
                "  references: [r]\n  roles: {}\n  ladder:\n  - {name: core, expr: 'rank(-ts_sum(returns, 21))', "
                "teaches: t}\n  settings: {neutralization: SUBINDUSTRY, decay: 0, truncation: 0.08}\n"
                "  expected_turnover: [0.1, 0.3]\n")
        r = self.c.post("/drafts/import", data={"cards": card, "region": "SBX"}, follow_redirects=False)
        self.assertIn("from+S-arxiv-2610.01234", r.headers["location"])
        from ideaweb.state import state
        self.assertEqual(S.get(state().store, "arxiv:2610.01234")["draft_id"], "IE_ANL_DISTRACTED")
        r = self.c.get("/leads/sources/osap%3AAccruals/writer")
        self.assertIn("### SOURCE S-osap-Accruals", r.text)
        self.assertIn("Fresh outside sources", self.c.get("/week").text)

    def test_fetch_failure_is_reported(self):
        def boom(*a, **k):
            raise ConnectionError("blocked")
        C.http_get = boom
        r = self.c.post("/leads/sources/fetch", data={"collector": "arxiv"}, follow_redirects=False)
        self.assertIn("kind=err", r.headers["location"])
        self.assertIn("--file", r.headers["location"].replace("%2D", "-"))
        self.assertIn("failed", self.c.get("/leads/sources").text)

    def test_manual_add(self):
        r = self.c.post("/leads/sources/add", data={"title": "A paper I read", "text": "about accruals"},
                        follow_redirects=False)
        self.assertIn("src=manual", r.headers["location"])
        self.assertIn("A paper I read", self.c.get("/leads/sources?src=manual").text)


if __name__ == "__main__":
    unittest.main()

"""HYPOLAB 1.9.1: the phase 7 review - regressions for each fix (mixed kinds, feed decoding, background downloads,
used datasets, dataset drafts, D0/D1, counts, case-insensitive ids, the menu badge, rotating state rows, stale and
muted news themes, European feeds, "same paper" after the library changes). No network."""
import datetime as dt
import importlib.util
import os
import tempfile
import threading
import unittest
from pathlib import Path

os.environ.setdefault("HYPOLAB_HOME", tempfile.mkdtemp(prefix="hypolab_test_"))

from hypolab import config  # noqa: E402
from hypolab import hypotheses as hyp  # noqa: E402
from hypolab.catalog import Catalog  # noqa: E402
from hypolab.journal import Journal  # noqa: E402
from ideaengine import collectors as C  # noqa: E402
from ideaengine import drafts, planner  # noqa: E402
from ideaengine import sources as S  # noqa: E402
from ideaengine.store import IdeaStore  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
ARXIV = (FIX / "arxiv_qfin.xml").read_text()
NEWS = (FIX / "news_feed.xml").read_text()
TODAY = dt.date(2026, 10, 20)
HAVE_WEB = all(importlib.util.find_spec(m) for m in ("starlette", "jinja2", "httpx", "markdown", "multipart"))


def rss(*items, decl="UTF-8"):
    body = "".join(f"<item><title>{t}</title><link>https://example.com/{k}</link><pubDate>{d}</pubDate></item>"
                   for k, (t, d) in enumerate(items))
    return f'<?xml version="1.0" encoding="{decl}"?><rss version="2.0"><channel><title>t</title>{body}</channel></rss>'


class _Home(unittest.TestCase):
    """Each test gets its own ~/.hypolab (mute writes settings.json)."""

    def setUp(self):
        self._old = config.HOME
        self._tmp = tempfile.TemporaryDirectory()
        config.HOME = Path(self._tmp.name)
        self.st = IdeaStore(":memory:")

    def tearDown(self):
        config.HOME = self._old
        self._tmp.cleanup()


class TestMixedKindsAndStateRows(_Home):
    def test_new_papers_are_not_buried_under_published_predictors(self):
        S.upsert(self.st, C.read_osap())
        S.upsert(self.st, C.read_arxiv(ARXIV))
        plan = {"region": "EUR", "categories": ["analyst", "model"]}
        top = S.items(self.st, plan=plan, limit=5)
        self.assertIn("arxiv", set(top["kind"]))                      # was about 145th
        only_osap = S.items(self.st, kinds=["osap"], plan=plan, limit=0)
        self.assertTrue((only_osap["relevance"].diff().dropna() <= 0).all())   # one kind: pure ranking
        rows = S.state_rows(self.st, plan)
        self.assertEqual([r.split("|")[1].strip() for r in rows], ["1", "2", "3", "4", "5"])
        self.assertTrue(any("| arXiv |" in r for r in rows))
        self.assertTrue(any("| OSAP |" in r for r in rows))

    def test_news_stays_out_of_the_state_doc_and_pipes_are_escaped(self):
        S.upsert(self.st, C.read_news([NEWS], today=TODAY))
        S.add_manual(self.st, "A | B paper")
        rows = S.state_rows(self.st, {"region": "EUR", "categories": ["earnings"]})
        self.assertEqual(len(rows), 1)
        self.assertIn("A / B paper", rows[0])
        txt = drafts.state_text(Journal(":memory:"), self.st, planner.iso_week(TODAY))
        self.assertIn("row N on weekday N", txt)
        self.assertIn("| Row | Kind | Source id | What | Evidence |", txt)


class TestFeeds(_Home):
    def test_bytes_follow_the_documents_own_encoding(self):
        latin = rss(("Café cuts guidance by £5m", "Mon, 19 Oct 2026 12:00:00 GMT"), decl="ISO-8859-1")
        self.assertEqual(C.parse_feed(latin.encode("iso-8859-1"))[0]["title"], "Café cuts guidance by £5m")
        utf = rss(("Firm’s outlook cut – €2bn", "Mon, 19 Oct 2026 12:00:00 GMT"))
        self.assertEqual(C.parse_feed(utf.encode("utf-8"))[0]["title"], "Firm’s outlook cut – €2bn")
        self.assertEqual(C.parse_feed(utf)[0]["title"], "Firm’s outlook cut – €2bn")      # text works too

    def test_a_page_that_is_not_a_feed_is_reported(self):
        old = C.http_get
        try:
            C.http_get = lambda url, timeout=20, params=None, raw=False: (
                b"<html><body>Please enable cookies" if "bad" in url else NEWS.encode())
            texts, errors = C.fetch_feeds(["https://ok.example/rss", "https://bad.example/rss"])
        finally:
            C.http_get = old
        self.assertEqual(len(texts), 1)
        self.assertIn("bad.example", errors[0])

    def test_european_feeds_and_the_190_defaults_migrate(self):
        self.assertTrue(any("euronews" in u for u in C.DEFAULT_FEEDS))
        config.save_settings(collector_feeds=list(C.FEEDS_190))
        self.assertEqual(C.feed_urls(), C.DEFAULT_FEEDS)
        config.save_settings(collector_feeds=["https://mine.example/rss"])
        self.assertEqual(C.feed_urls(), ["https://mine.example/rss"])          # your own list is kept


class TestNewsThemes(_Home):
    def test_stale_themes_leave_the_new_list(self):
        S.upsert(self.st, C.read_news([NEWS], today=TODAY))
        sid = "news:guidance_cut:2026-W43"
        self.assertIn(sid, set(S.items(self.st, limit=0, today=TODAY)["id"]))
        later = TODAY + dt.timedelta(days=S.NEWS_FRESH_DAYS + 2)
        self.assertNotIn(sid, set(S.items(self.st, limit=0, today=later).get("id", [])))
        self.assertIn(sid, set(S.items(self.st, show="all", limit=0, today=later)["id"]))
        self.assertNotIn("news", S.counts(self.st, today=later))

    def test_mute_and_unmute_a_theme(self):
        S.upsert(self.st, C.read_news([NEWS], today=TODAY))
        self.assertEqual(S.mute_theme(self.st, "guidance_cut"), 1)
        self.assertIn("guidance_cut", C.muted_themes())
        self.assertEqual(S.get(self.st, "news:guidance_cut:2026-W43")["note"], "theme muted")
        self.assertFalse(any(i.extra["theme"] == "guidance_cut" for i in C.read_news([NEWS], today=TODAY)))
        S.unmute_theme("guidance_cut")
        self.assertTrue(any(i.extra["theme"] == "guidance_cut" for i in C.read_news([NEWS], today=TODAY)))
        with self.assertRaises(ValueError):
            S.mute_theme(self.st, "gossip")

    def test_rates_and_inflation_is_muted_by_default(self):
        doc = rss(("Fed signals rate cut as inflation cools", "Mon, 19 Oct 2026 12:00:00 GMT"),
                  ("ECB holds rates; bond yields fall", "Mon, 19 Oct 2026 13:00:00 GMT"))
        self.assertEqual(C.read_news([doc], today=TODAY), [])
        self.assertEqual(len(C.read_news([doc], today=TODAY, muted=[])), 1)

    def test_counts_and_badge_match_the_list(self):
        S.upsert(self.st, C.read_news([NEWS], today=TODAY))      # 5 themes, only guidance_cut has 2+ headlines
        S.upsert(self.st, C.read_arxiv(ARXIV))
        shown = S.items(self.st, limit=0, today=TODAY).attrs["total"]
        self.assertEqual(S.counts(self.st, today=TODAY)["news"]["new"], 1)
        self.assertEqual(S.new_count(self.st, today=TODAY), shown)
        self.assertEqual(shown, 3)


class TestDatasets(_Home):
    def _catalog(self):
        cat = Catalog(":memory:")
        for delay in (1, 0):
            cat.ingest_payload({"region": "EUR", "universe": "TOP2500", "delay": delay, "datasets": [
                {"id": "model162", "name": "Return prediction from conference call", "category": "model",
                 "value_score": 4, "alpha_count": 24, "coverage": 0.58}],
                "fields": [{"id": "mdl162_score", "dataset": "model162", "type": "MATRIX", "coverage": 0.6}]})
        return cat

    def test_one_item_per_dataset_delay_1_first(self):
        items = C.read_datasets(self._catalog(), Journal(":memory:"))
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0].extra["delay"], sorted(items[0].extra["delays"])), (1, [0, 1]))

    def test_a_dataset_you_used_leaves_the_new_list(self):
        cat, j = self._catalog(), Journal(":memory:")
        self.assertEqual(S.collect(self.st, "datasets", catalog=cat, journal=j)["added"], 1)
        j.record("X@EUR", "core", "explore", "rank(mdl162_score)", {"region": "EUR", "delay": 1,
                 "universe": "TOP2500"}, {"alpha_id": "A1", "is_sharpe": 0.4, "status": "COMPLETE"}, "NOISE")
        res = S.collect(self.st, "datasets", catalog=cat, journal=j)
        self.assertEqual(res["retired"], 1)
        row = S.get(self.st, "dataset:EUR:model162")
        self.assertEqual((row["state"], row["note"]), ("skipped", S.DATASET_USED_NOTE))


class TestTagsAndLibrary(_Home):
    def test_source_ids_match_whatever_the_case(self):
        S.upsert(self.st, C.read_osap())
        self.assertEqual(S.link_draft(self.st, "daily brief 2026-10-21 s-osap-accruals", "IE_1021_X"),
                         "osap:Accruals")

    def test_same_paper_is_refreshed_when_the_library_changes(self):
        lib0 = [h for h in hyp.load_library() if h.id != "FND_ACCRUALS"]
        S.upsert(self.st, [i for i in C.read_osap() if i.id == "osap:Accruals"], library=lib0)
        before = S.get(self.st, "osap:Accruals")
        self.assertEqual(before["covered_by"], [])
        self.assertEqual(S.refresh_covered(self.st, lib0), 0)                  # nothing changed: nothing done
        self.assertEqual(S.refresh_covered(self.st, hyp.load_library()), 1)   # FND_ACCRUALS (Sloan 1996) is back
        after = S.get(self.st, "osap:Accruals")
        self.assertEqual(after["covered_by"], ["FND_ACCRUALS"])
        self.assertAlmostEqual(after["score"], before["score"] - 1.5, places=3)


@unittest.skipUnless(HAVE_WEB, "web dependencies not installed")
class TestIdeasApp(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        from ideaweb import state as web_state
        from ideaweb.app import app
        self._old_home, self._old_fetch = config.HOME, S.fetch
        self._tmp = tempfile.TemporaryDirectory()
        config.HOME = Path(self._tmp.name)
        config.save_settings(mode="sandbox")
        hyp._LIB_CACHE.clear()
        web_state.reset()
        self.c = TestClient(app)

    def tearDown(self):
        from ideaweb import state as web_state
        web_state.reset()
        S.fetch = self._old_fetch
        config.HOME = self._old_home
        hyp._LIB_CACHE.clear()
        self._tmp.cleanup()

    def test_downloads_run_in_a_worker_thread(self):
        seen = {}

        def fake_fetch(kind, origin=""):
            seen["thread"] = threading.current_thread().name
            return {"text": ARXIV, "errors": [], "origin": "test"}
        S.fetch = fake_fetch
        r = self.c.post("/leads/sources/fetch", data={"collector": "arxiv"}, follow_redirects=False)
        self.assertIn("2+new", r.headers["location"])
        self.assertIn("worker", seen["thread"].lower())

    def test_mute_from_the_page_and_unmute(self):
        from ideaweb.state import state
        S.upsert(state().store, C.read_news([NEWS], today=TODAY))
        sid = "news:guidance_cut:2026-W43"
        self.c.post("/leads/sources/act", data={"id": sid, "action": "mute"})
        self.assertEqual(S.get(state().store, sid)["state"], "skipped")
        page = self.c.get("/leads/sources").text
        self.assertIn("Unmute Guidance cuts and profit warnings", page)
        self.c.post("/leads/sources/unmute", data={"theme": "guidance_cut"})
        self.assertNotIn("guidance_cut", C.muted_themes())

    def test_a_dataset_draft_is_checked_in_its_own_region(self):
        from ideaweb import app as webapp
        from ideaweb.state import state
        st = state()
        S.upsert(st.store, [C.SourceItem(id="dataset:EUR:model162", kind="dataset", title="Conference call model",
                                         extra={"region": "EUR", "universe": "TOP2500", "delay": 1,
                                                "dataset": "model162", "category": "model"})])
        seen = {}
        old_check, old_regions = webapp.D.check_card, type(st).regions

        def spy(card, catalog, region, **kw):
            seen["region"] = region
            return old_check(card, catalog, region, **kw)
        webapp.D.check_card = spy
        type(st).regions = lambda self: ["SBX", "EUR"]
        try:
            r = self.c.post("/leads/sources/act", data={"id": "dataset:EUR:model162", "action": "draft"},
                            follow_redirects=False)
        finally:
            webapp.D.check_card = old_check
            type(st).regions = old_regions
        self.assertIn("/drafts/IE_SRC_MODEL162", r.headers["location"])
        self.assertEqual(seen["region"], "EUR")


if __name__ == "__main__":
    unittest.main()

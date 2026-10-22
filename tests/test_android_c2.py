"""1.14.0, Android phase C2: Journal, Pyramids and SuperAlpha as shared web pages (sandbox, offline)."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for k in ("HYPOLAB_LAUNCH_SECRET", "HYPOLAB_PLATFORM"):
    os.environ.pop(k, None)
os.environ.setdefault("HYPOLAB_SANDBOX_STOCKS", "150")

from starlette.testclient import TestClient  # noqa: E402

from hypolab import config  # noqa: E402
from ideaweb.app import app  # noqa: E402
from ideaweb.jobs import JOBS  # noqa: E402
from ideaweb.lab import LAB  # noqa: E402

C = TestClient(app)


def post(path, data=None):
    r = C.post(path, data=data or {}, follow_redirects=False)
    assert r.status_code in (200, 303), (path, r.status_code, r.text[:300])
    return r


class Journal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config.save_settings(mode="sandbox")
        post("/lab/simulate", {"expression": "rank(-ts_delta(close, 5))"})
        JOBS.wait(120)

    def test_page_shows_the_practice_journal(self):
        r = C.get("/journal")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Practice journal", r.text)
        self.assertIn("Verdict mix", r.text)
        self.assertIn("rank(-ts_delta(close, 5))", r.text)

    def test_filters_and_more(self):
        r = C.get("/journal?region=SBX&v=NOISE&v=PASS&n=10")
        self.assertEqual(r.status_code, 200)
        self.assertIn('value="NOISE" checked', r.text)

    def test_add_lesson(self):
        post("/journal/lesson", {"text": "Reversal needs low turnover to pass.", "idea": "PV_TEST@SBX"})
        self.assertIn("Reversal needs low turnover", C.get("/journal").text)
        r = post("/journal/lesson", {"text": "  "})
        self.assertIn("Write+the+lesson", r.headers["location"])


class Pyramids(unittest.TestCase):
    def test_page_heatmap_plan_and_k(self):
        r = C.get("/pyramids")
        self.assertEqual(r.status_code, 200)
        self.assertIn("data:image/png;base64", r.text)
        self.assertIn("Delay 1", r.text)
        self.assertIn("Counts from: sandbox", r.text)
        post("/pyramids/k", {"k": "4"})
        self.assertEqual(int(config.settings()["alphas_per_pyramid"]), 4)
        self.assertIn('value="4"', C.get("/pyramids?sort=multiplier").text)
        post("/pyramids/k", {"k": "3"})

    def test_refresh_is_a_job(self):
        post("/pyramids/refresh")
        JOBS.wait(60)
        self.assertIn("Pyramid counts refreshed", C.get("/pyramids").text)


class SuperAlpha(unittest.TestCase):
    def test_1_check_is_free_and_shows_preview(self):
        before = len(LAB.super_results)
        r = C.get("/superalpha")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Check and preview (free)", r.text)
        post("/superalpha/check", {"region": "SBX", "delay": "1", "sel": "least_corr", "combo": "equal",
                                   "limit": "12", "go": "check"})
        self.assertEqual(LAB.super_form["limit"], 12)
        self.assertEqual(len(LAB.super_results), before)
        self.assertIn("selection:", C.get("/superalpha").text)

    def test_2_error_never_simulates(self):
        before = len(LAB.super_results)
        r = post("/superalpha/check", {"region": "SBX", "sel_own": "this is not valid ((", "combo": "equal",
                                       "go": "simulate"})
        JOBS.wait(30)
        self.assertEqual(len(LAB.super_results), before)
        self.assertIn("err", r.headers["location"])

    def test_3_pool_simulate_gate_and_refused_submit(self):
        post("/superalpha/pool")
        JOBS.wait(300)
        self.assertIn("Practice pool", LAB.super_msg)
        post("/superalpha/check", {"region": "SBX", "delay": "1", "sel": "least_corr", "combo": "equal",
                                   "limit": "10", "go": "simulate"})
        JOBS.wait(300)
        self.assertTrue(LAB.super_results, C.get("/superalpha").text[:2000])
        post("/superalpha/gate")
        JOBS.wait(120)
        self.assertIsNotNone(LAB.super_gate)
        page = C.get("/superalpha").text
        self.assertIn("hl-verdict", page)
        post("/superalpha/submit", {"confirm": "SUBMIT WRONG"})
        JOBS.wait(30)
        self.assertTrue(LAB.super_msg.startswith("NOT submitted") or "locked" in LAB.super_msg.lower(),
                        LAB.super_msg)


class Nav(unittest.TestCase):
    def test_links(self):
        page = C.get("/week").text
        for href in ('href="/journal"', 'href="/pyramids"', 'href="/superalpha"'):
            self.assertIn(href, page)



class Threads(unittest.TestCase):
    def test_researcher_opened_in_one_thread_simulates_in_a_job(self):
        """1.14.0 regression: the catalog's SQLite connection refused use from a job thread."""
        LAB.mode_key = None                    # force a fresh Researcher, opened right here (not in a worker)
        LAB.researcher()
        n = len(LAB.results)
        post("/lab/simulate", {"expression": "rank(close)"})
        JOBS.wait(120)
        self.assertNotEqual(JOBS.current.kind, "err", JOBS.current.message)
        self.assertTrue(JOBS.current.message.startswith("Simulated"), JOBS.current.message)
        self.assertEqual(len(LAB.results), n + 1)


if __name__ == "__main__":
    unittest.main()

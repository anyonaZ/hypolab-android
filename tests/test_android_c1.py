"""1.13.0, Android phase C1: the Lab, Play and Quant basics as shared web pages (sandbox, offline)."""
import os
import re
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for k in ("HYPOLAB_LAUNCH_SECRET", "HYPOLAB_PLATFORM"):
    os.environ.pop(k, None)
os.environ.setdefault("HYPOLAB_SANDBOX_STOCKS", "150")         # small market: fast tests

from starlette.testclient import TestClient  # noqa: E402

from hypolab import config  # noqa: E402
from hypolab import hypotheses as hyp  # noqa: E402
from ideaweb.app import app  # noqa: E402
from ideaweb.jobs import JOBS  # noqa: E402
from ideaweb.lab import LAB  # noqa: E402

C = TestClient(app)


def post(path, data=None):
    r = C.post(path, data=data or {}, follow_redirects=False)
    assert r.status_code in (200, 303), (path, r.status_code, r.text[:300])
    return r


def done():
    JOBS.wait(300)
    return C.get("/lab").text


class Lab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config.save_settings(mode="sandbox", last_lab_card="")
        LAB.reset()

    def test_1_page_without_card(self):
        r = C.get("/lab")
        self.assertEqual(r.status_code, 200)
        self.assertIn("No card in the Lab", r.text)
        self.assertIn("Simulate (1 simulation)", r.text)

    def test_2_own_expression_runs_as_a_job(self):
        n = len(LAB.results)
        post("/lab/simulate", {"expression": "rank(-ts_delta(close, 5))", "decay": "2", "delay": "1",
                               "neutralization": "SUBINDUSTRY", "truncation": "0.08"})
        txt = done()
        self.assertEqual(len(LAB.results), n + 1)
        self.assertIn("Simulated", txt)                          # the job's message, shown once
        self.assertNotIn("Simulated", C.get("/lab").text.split("Results this session")[0])

    def test_3_nothing_runs_without_a_button(self):
        n = len(LAB.results)
        for _ in range(3):
            C.get("/lab")
        JOBS.wait(5)
        self.assertEqual(len(LAB.results), n)

    def test_4_one_job_at_a_time(self):
        JOBS.start("a slow job", "/lab", lambda: time.sleep(1.0))
        n = len(LAB.results)
        r = post("/lab/simulate", {"expression": "rank(close)"})
        self.assertIn("Still+working", r.headers["location"])
        page = C.get("/lab").text
        self.assertIn('http-equiv="refresh"', page)              # the page reloads itself while a job runs
        self.assertIn("disabled", page)
        JOBS.wait(10)
        self.assertEqual(len(LAB.results), n)

    def test_5_card_ladder_perf_robust_gate(self):
        cid = next(h.id for h in hyp.load_library())
        post("/lab/card", {"card": cid, "region": "SBX"})
        page = C.get("/lab").text
        self.assertIn("Rung", page)
        self.assertIn(cid, page)
        post("/lab/simulate", {"rung": "0", "decay": "0", "delay": "1", "neutralization": "SUBINDUSTRY",
                               "truncation": "0.08"})
        done()
        t = LAB.current()
        self.assertIsNotNone(t.alpha_id)
        post("/lab/perf")
        page = done()
        self.assertIn("data:image/png;base64", page)
        post("/lab/robust")
        page = done()
        self.assertIn("Robustness:", page)
        post("/lab/gate")
        page = done()
        self.assertIsNotNone(LAB.gate)
        self.assertIn("hl-verdict", page)
        if not LAB.gate.ready:
            self.assertNotIn('action="/lab/submit"', page)       # no submit form without a READY gate

    def test_6_submit_goes_through_researcher_checks(self):
        if LAB.gate is None:
            self.skipTest("no gate")
        post("/lab/submit", {"confirm": "SUBMIT WRONG"})
        JOBS.wait(30)
        self.assertTrue(LAB.submitted)
        self.assertTrue(LAB.submitted[-1][1].startswith("NOT submitted"))

    def test_7_results_list_focus_and_remove(self):
        self.assertGreaterEqual(len(LAB.results), 2)
        first = LAB.results[0][0]
        C.get(f"/lab?focus={first}")
        self.assertIs(LAB.current(), LAB.results[0][1])
        post("/lab/results", {"action": "remove"})
        self.assertNotIn(first, [k for k, _ in LAB.results])

    def test_8_card_sent_from_cards_page_is_picked_up(self):
        cid = [h.id for h in hyp.load_library()][1]
        post(f"/cards/{cid}/lab", {"region": "SBX"})
        page = C.get("/lab").text
        self.assertIn(f"Picked up {cid}", page)
        self.assertEqual(config.settings().get("last_lab_card"), cid)

    def test_9_bin_from_lab(self):
        cid = config.settings().get("last_lab_card")
        post("/lab/card/act", {"action": "bin"})
        self.assertIn(cid, LAB.R.journal.binned_ids())
        self.assertEqual(config.settings().get("last_lab_card"), "")
        LAB.R.restore(cid)


class Play(unittest.TestCase):
    def test_roll_simulate_send_to_lab(self):
        r = post("/play/roll", {"mode": "mix", "n": "3", "region": "SBX", "seed": "5", "shuffle": "1"})
        self.assertIn("/play", r.headers["location"])
        page = C.get("/play").text
        self.assertIn("Rolled alphas", page)
        n = len(LAB.play)
        post("/play/sim", {"pick": ["0"]})
        JOBS.wait(120)
        self.assertGreater(len(LAB.play), n)
        page = C.get("/play").text
        self.assertIn("Send this one to the Lab", page)
        k = LAB.play[-1][0]
        post("/play/tolab", {"key": str(k)})
        self.assertIs(LAB.current(), LAB.play[-1][1])

    def test_rolling_is_free(self):
        before = LAB.R.journal.sims_today() if LAB.R is not None else 0
        post("/play/roll", {"mode": "wild", "n": "2", "region": "SBX"})
        self.assertEqual(LAB.R.journal.sims_today(), before)


class Basics(unittest.TestCase):
    def test_build_and_try(self):
        page = C.get("/basics").text
        self.assertIn("Build the lessons", page)
        post("/basics/build")
        JOBS.wait(300)
        page = C.get("/basics").text
        for h in ("1. An alpha", "3. The four numbers", "5. Ideas with a mechanism"):
            self.assertIn(h, page)
        self.assertGreaterEqual(page.count("data:image/png;base64"), 2)
        post("/basics/try", {"expression": "rank(-ts_sum(returns, 5))", "decay": "2"})
        page = C.get("/basics").text
        self.assertIn("my alpha", page)
        post("/basics/try", {"expression": "rank(no_such_field_xyz)", "decay": "2"})
        self.assertNotIn("Traceback", C.get("/basics").text)


class SharedMarket(unittest.TestCase):
    def test_one_market_per_process(self):
        from hypolab.mock import MockBrain
        from hypolab.sandbox.market import shared_market
        self.assertIs(MockBrain(seed=7).data, shared_market())
        self.assertEqual(shared_market().N, config.sandbox_stocks())


class Pages(unittest.TestCase):
    def test_nav_has_lab_pages(self):
        page = C.get("/week").text
        for href in ('href="/lab"', 'href="/play"', 'href="/basics"'):
            self.assertIn(href, page)


if __name__ == "__main__":
    unittest.main()

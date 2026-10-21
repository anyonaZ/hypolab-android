"""HYPOLAB 1.10.2: the three findings Zacc reported on 20 Oct - submit() trusts only a READY gate report this Researcher
issued (recently, once); missing evidence never leaves a gate READY; a request that changes something on BRAIN is never
re-sent after a lost answer or a server error. No network."""
import os
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("HYPOLAB_HOME", tempfile.mkdtemp(prefix="hypolab_test_"))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

from hypolab import brain as B  # noqa: E402
from hypolab.research import GateReport, Researcher  # noqa: E402


class _Sandbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = Researcher.sandbox()
        card = cls.R.card("ANL_REVISION_BREADTH")
        cls.t = cls.R.test(card, rung=min(1, len(card.steps) - 1))
        cls.rb = cls.R.robustness(cls.t)

    @classmethod
    def tearDownClass(cls):
        import gc
        cls.R = cls.t = cls.rb = None
        gc.collect()

    def ready_gate(self):
        g = self.R.gate(self.t, self.rb)
        self.assertTrue(g.ready, g.reasons)
        return g

    def submit_calls(self):
        return mock.patch.object(self.R.brain, "submit", wraps=self.R.brain.submit)


class TestSubmitTrustsOnlyAnIssuedReadyGate(_Sandbox):
    def test_a_not_ready_gate_marked_ready_is_refused(self):
        with mock.patch.object(self.R.brain, "daily_pnl", side_effect=RuntimeError("no pnl")):
            g = self.R.gate(self.t, self.rb)
        self.assertFalse(g.ready)
        g.ready = True                                          # the reported bypass
        with self.submit_calls() as sub, self.assertRaises(RuntimeError) as e:
            self.R.submit(g, confirm=f"SUBMIT {g.alpha_id}")
        self.assertIn("NOT READY", str(e.exception))
        sub.assert_not_called()
        self.assertTrue(self.R.journal.submissions().empty)

    def test_a_hand_made_report_is_refused(self):
        g = GateReport(self.t.alpha_id, True, ["trust me"], pd.DataFrame(), "")
        with self.submit_calls() as sub, self.assertRaises(RuntimeError):
            self.R.submit(g, confirm=f"SUBMIT {g.alpha_id}")
        sub.assert_not_called()

    def test_a_report_for_another_alpha_or_kind_is_refused(self):
        g = self.ready_gate()
        g.alpha_id = "SBX99999"
        with self.assertRaises(RuntimeError):
            self.R.submit(g, confirm="SUBMIT SBX99999")
        g = self.ready_gate()
        with self.assertRaises(RuntimeError):
            self.R.super_submit(g, confirm=f"SUBMIT {g.alpha_id}")   # an alpha's gate is not a SuperAlpha gate

    def test_a_stale_report_is_refused(self):
        g = self.ready_gate()
        self.R._issued[g.token]["at"] = time.time() - 31 * 60
        with self.submit_calls() as sub, self.assertRaises(RuntimeError) as e:
            self.R.submit(g, confirm=f"SUBMIT {g.alpha_id}")
        self.assertIn("minutes old", str(e.exception))
        sub.assert_not_called()

    def test_wrong_confirmation_keeps_the_report_and_success_uses_it_up(self):
        g = self.ready_gate()
        with self.assertRaises(RuntimeError):
            self.R.submit(g, confirm="yes")
        with mock.patch.object(self.R.brain, "submit", return_value={"status_code": 200, "body": "ok"}) as sub:
            self.R.submit(g, confirm=f"SUBMIT {g.alpha_id}")
            with self.assertRaises(RuntimeError):
                self.R.submit(g, confirm=f"SUBMIT {g.alpha_id}")  # one report, one submission
        self.assertEqual(sub.call_count, 1)
        self.R.journal.db.execute("DELETE FROM submissions")


class TestMissingEvidenceBlocks(_Sandbox):
    def test_empty_platform_checks(self):
        with mock.patch.object(self.R.brain, "checks", return_value=pd.DataFrame()):
            g = self.R.gate(self.t, self.rb)
        self.assertFalse(g.ready)
        self.assertTrue(any("no platform checks" in r for r in g.reasons), g.reasons)

    def test_deflated_sharpe_unavailable(self):
        with mock.patch.object(self.R.brain, "daily_pnl", side_effect=RuntimeError("no pnl")):
            g = self.R.gate(self.t, self.rb)
        self.assertFalse(g.ready)
        self.assertTrue(any("deflated Sharpe" in r and "never passes" in r for r in g.reasons))

    def test_correlation_unavailable_with_checks_that_name_none(self):
        rows = self.R.brain.checks(self.t.alpha_id)
        rows = rows[~rows["name"].str.contains("CORRELATION")]
        with mock.patch.object(self.R.brain, "checks", return_value=rows), \
                mock.patch.object(self.R.brain, "correlations", side_effect=RuntimeError("down")), \
                mock.patch.object(self.R, "correlation", side_effect=RuntimeError("down")):
            g = self.R.gate(self.t, self.rb)
        self.assertFalse(g.ready)
        self.assertEqual(sum("no evidence" in r for r in g.reasons), 2, g.reasons)     # self and production

    def test_missing_train_test_split_and_zero_train_sharpe(self):
        import copy
        t = copy.copy(self.t)
        t.summary = dict(self.t.summary, test_sharpe=None)
        self.assertFalse(self.R.gate(t, self.rb).ready)
        t.summary = dict(self.t.summary, train_sharpe=0.0, test_sharpe=-0.4)       # 1.10.1 skipped a 0 as missing
        self.assertFalse(self.R.gate(t, self.rb).ready)

    def test_superalpha_gate_without_correlation_evidence(self):
        from hypolab import superalpha as SA
        self.R.practice_super_pool(15)
        st = SA.recipe("selection", "least_corr", 12).code
        t = self.R.super_test(st, "1", "SBX", "SANDBOX", 1, selection_limit=12)
        rows = self.R.brain.checks(t.alpha_id)
        rows = rows[~rows["name"].str.contains("CORRELATION")]
        with mock.patch.object(self.R.brain, "checks", return_value=rows), \
                mock.patch.object(self.R.brain, "correlations", side_effect=RuntimeError("down")), \
                mock.patch.object(self.R, "correlation", side_effect=RuntimeError("down")):
            g = self.R.super_gate(t)
        self.assertFalse(g.ready)
        g.ready = True
        with self.assertRaises(RuntimeError):
            self.R.super_submit(g, confirm=f"SUBMIT {g.alpha_id}")
        self.assertEqual(self.R.journal.super_submissions_today(), 0)


class _Resp:
    def __init__(self, code, headers=None, text="", payload=None):
        self.status_code, self.headers, self.text, self._p = code, headers or {}, text, payload

    def json(self):
        return self._p


class _Session:
    """Answers from a script: each item is a response or an exception to raise."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def request(self, method, url, **kw):
        self.calls.append((method, url))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class TestNoBlindRetries(unittest.TestCase):
    def client(self, *script):
        b = B.BrainClient(verbose=False, credentials=("x@y", "z"))
        b.s = _Session(*script)
        b.ensure = lambda *a, **k: None
        return b

    def setUp(self):
        self._sleep = mock.patch.object(B.time, "sleep")
        self._sleep.start()

    def tearDown(self):
        self._sleep.stop()

    def test_lost_answer_to_a_post_is_not_resent(self):
        b = self.client(requests.exceptions.ReadTimeout("read timed out"), _Resp(201))
        with self.assertRaises(B.UncertainOutcome):
            b._req("POST", "/simulations", json={})
        self.assertEqual(len(b.s.calls), 1)

    def test_server_error_to_a_post_is_not_resent(self):
        b = self.client(_Resp(502, text="bad gateway"), _Resp(201))
        with self.assertRaises(B.UncertainOutcome):
            b._req("POST", "/simulations", json={})
        self.assertEqual(len(b.s.calls), 1)

    def test_safe_retries_still_happen(self):
        b = self.client(_Resp(429, {"Retry-After": "1"}), _Resp(201))
        self.assertEqual(b._req("POST", "/simulations", json={}).status_code, 201)     # rate limited: not acted on
        b = self.client(requests.exceptions.ConnectTimeout("connect timed out"), _Resp(201))
        self.assertEqual(b._req("POST", "/simulations", json={}).status_code, 201)     # never connected
        b = self.client(requests.exceptions.ReadTimeout("x"), _Resp(503), _Resp(200))
        self.assertEqual(b._req("GET", "/alphas/A1").status_code, 200)                 # reads repeat freely
        self.assertEqual(len(b.s.calls), 3)

    def test_uncertain_simulation_is_reported_not_repeated(self):
        b = self.client(requests.exceptions.ConnectionError("Connection aborted: RemoteDisconnected"))
        out = b._run_batch([{"type": "REGULAR", "regular": "rank(close)", "settings": {}}])
        self.assertEqual(out[0]["status"], "UNCERTAIN")
        self.assertIn("before simulating this again", out[0]["error"])
        self.assertEqual(len(b.s.calls), 1)

    def test_lost_submission_answer_is_checked_by_reading_the_alpha(self):
        b = self.client(requests.exceptions.ReadTimeout("x"),
                        _Resp(200, payload={"id": "A1", "dateSubmitted": "2026-10-20T10:00:00-04:00"}))
        res = b.submit("A1", confirm="SUBMIT A1")
        self.assertTrue(res["confirmed_after_lost_response"])
        self.assertEqual([m for m, _ in b.s.calls], ["POST", "GET"])                   # never a second POST
        b = self.client(_Resp(500, text="oops"), _Resp(200, payload={"id": "A1", "status": "UNSUBMITTED"}))
        with self.assertRaises(B.UncertainOutcome):
            b.submit("A1", confirm="SUBMIT A1")
        self.assertEqual([m for m, _ in b.s.calls], ["POST", "GET"])


if __name__ == "__main__":
    unittest.main()

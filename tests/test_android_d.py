"""1.17.0, Android phase D: live BRAIN safely from a web page or a tablet.
- pages and jobs never wait on input(): an ended session or a face scan mid-job raise AuthError with a plain message;
- the tablet never keeps the password (not on disk, not in memory after login, not while a face scan is pending);
- "Stop waiting" stops polling only (never a POST, never a re-send) and the simulation stays pending for recovery;
- failed jobs explain themselves in plain words."""
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for k in ("HYPOLAB_LAUNCH_SECRET", "HYPOLAB_PLATFORM", "BRAIN_EMAIL", "BRAIN_PASSWORD"):
    os.environ.pop(k, None)

from starlette.testclient import TestClient  # noqa: E402

from hypolab import brain, config, connect  # noqa: E402
from ideaweb.app import app  # noqa: E402
from ideaweb.jobs import JOBS, explain  # noqa: E402

C = TestClient(app)


def no_input(prompt=""):
    raise AssertionError("input() was called: " + prompt)


class Resp:
    def __init__(self, status=200, headers=None, js=None, text="", url="https://api.example/authentication"):
        self.status_code, self.headers, self._js, self.text, self.url = status, headers or {}, js, text, url

    def json(self):
        return self._js or {}


class NoPrompt(unittest.TestCase):
    def setUp(self):
        self.assertTrue(brain.NO_PROMPT)          # importing the web app switched it on
        for p in (brain._cred_path(), brain._session_path()):
            if p.exists():
                p.unlink()

    def test_no_credentials_raises_instead_of_asking(self):
        b = brain.BrainClient(verbose=False, input_fn=no_input)
        with self.assertRaises(brain.AuthError) as cm:
            b._credentials()
        self.assertIn("Setup page", str(cm.exception))

    def test_face_scan_mid_job_raises_instead_of_waiting(self):
        b = brain.BrainClient(verbose=False, input_fn=no_input, credentials=("a@b.c", "pw"))
        with mock.patch.object(b, "begin_login", return_value={"status": "biometric", "url": "https://x/scan"}):
            with self.assertRaises(brain.AuthError) as cm:
                b.login(force=True)
        self.assertIn("face scan", str(cm.exception))

    def test_terminal_still_prompts(self):
        with mock.patch.object(brain, "NO_PROMPT", False):
            b = brain.BrainClient(verbose=False, input_fn=lambda p: "me@example.com")
            with mock.patch("getpass.getpass", return_value="pw"):
                self.assertEqual(b._credentials(), ("me@example.com", "pw"))


class TabletPassword(unittest.TestCase):
    def setUp(self):
        os.environ["HYPOLAB_PLATFORM"] = "android"
        if brain._cred_path().exists():
            brain._cred_path().unlink()

    def tearDown(self):
        os.environ.pop("HYPOLAB_PLATFORM", None)
        connect._PENDING = None

    def _client(self):
        b = brain.BrainClient(verbose=False, input_fn=no_input, credentials=("me@example.com", "secret-pw"))
        b.expiry_ts = time.time() + 3600
        return b

    def test_accept_never_saves_nor_keeps_the_password(self):
        b = self._client()
        res = connect._accept(b, "me@example.com", "secret-pw", save=True)
        self.assertFalse(res["saved"])
        self.assertFalse(brain._cred_path().exists())
        self.assertIsNone(b._given_credentials)

    def test_pending_face_scan_does_not_hold_the_password(self):
        with mock.patch.object(brain.BrainClient, "begin_login",
                               return_value={"status": "biometric", "url": "https://x/scan"}):
            res = connect.begin_login("me@example.com", "secret-pw", save=True)
        self.assertEqual(res["status"], "biometric")
        self.assertIsNone(connect._PENDING["password"])

    def test_laptop_unchanged(self):
        os.environ.pop("HYPOLAB_PLATFORM", None)
        b = self._client()
        connect._accept(b, "me@example.com", "secret-pw", save=True)
        self.assertTrue(brain._cred_path().exists())
        brain._cred_path().unlink()


class StopWaiting(unittest.TestCase):
    def tearDown(self):
        brain.CANCEL.clear()

    def test_poll_stops_within_a_second_and_never_posts(self):
        b = brain.BrainClient(verbose=False, input_fn=no_input)
        calls = []

        def req(method, path, **kw):
            calls.append(method)
            return Resp(headers={"Retry-After": "30"})
        b._req = req
        threading.Timer(0.3, brain.CANCEL.set).start()
        t0 = time.time()
        with self.assertRaises(brain.BrainError) as cm:
            b._poll("/simulations/xyz")
        self.assertLess(time.time() - t0, 2.0)
        self.assertIn("Fetch them from BRAIN", str(cm.exception))
        self.assertEqual(set(calls), {"GET"})

    def test_button_route_and_new_job_releases_it(self):
        JOBS.start("a slow wait", "/lab", lambda: time.sleep(0.6))
        r = C.post("/jobs/stop", data={"back": "/lab"}, follow_redirects=False)
        self.assertIn("Stopping+the+wait", r.headers["location"])
        self.assertTrue(brain.CANCEL.is_set())
        JOBS.wait(5)
        JOBS.start("next", "/lab", lambda: None)
        self.assertFalse(brain.CANCEL.is_set())
        JOBS.wait(5)
        r = C.post("/jobs/stop", data={"back": "//evil.example"}, follow_redirects=False)
        self.assertTrue(r.headers["location"].startswith("/lab"))


class Explain(unittest.TestCase):
    def test_messages(self):
        import requests
        m, k = explain("1 simulation", brain.AuthError(brain.SESSION_ENDED))
        self.assertIn("Setup page", m)
        m, k = explain("1 simulation", requests.ConnectionError("Max retries exceeded"))
        self.assertIn("no connection to BRAIN", m)
        self.assertIn("Nothing was sent again", m)
        m, k = explain("1 simulation", brain.BrainError(brain.STOPPED_WAITING))
        self.assertEqual(k, "warn")


class SessionBanner(unittest.TestCase):
    def test_banner_when_live_session_ended(self):
        from ideaweb.lab import LAB
        fake = mock.Mock()
        fake.brain.is_mock = False
        fake.brain.seconds_left.return_value = 0
        with mock.patch.object(config, "sandbox_mode", return_value=False), mock.patch.object(LAB, "R", fake):
            from ideaweb.app import _session_ended
            self.assertTrue(_session_ended())
        self.assertFalse(_session_ended())         # sandbox: never


if __name__ == "__main__":
    unittest.main()

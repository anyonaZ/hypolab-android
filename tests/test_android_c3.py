"""1.15.0, Android phase C3: Data (with explore/scan), Account and Setup as shared web pages."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for k in ("HYPOLAB_LAUNCH_SECRET", "HYPOLAB_PLATFORM", "BRAIN_EMAIL", "BRAIN_PASSWORD"):
    os.environ.pop(k, None)
os.environ.setdefault("HYPOLAB_SANDBOX_STOCKS", "150")

from starlette.testclient import TestClient  # noqa: E402

from hypolab import config, connect  # noqa: E402
from ideaweb.app import app  # noqa: E402
from ideaweb.jobs import JOBS  # noqa: E402
from ideaweb.lab import LAB  # noqa: E402

C = TestClient(app)


def post(path, data=None):
    r = C.post(path, data=data or {}, follow_redirects=False)
    assert r.status_code in (200, 303), (path, r.status_code, r.text[:300])
    return r


class Data(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config.save_settings(mode="sandbox")
        LAB.mode_key = None

    def test_1_catalog_browse(self):
        r = C.get("/data")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Datasets in this region", r.text)
        self.assertIn("SBX", r.text)
        ds = LAB.researcher().catalog.datasets("SBX", "SANDBOX", 1)["id"].tolist()[0]
        r = C.get(f"/data?ds={ds}")
        self.assertIn(f"What each field of <code>{ds}</code> measures", r.text)
        r = C.get("/data?concept=cfo&q=cash")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("Traceback", r.text)

    def test_2_explore_is_free_scan_is_a_job(self):
        before = len(LAB.researcher().journal.experiments())
        post("/data/learn", {"ds": "sbx_analyst", "explore_n": "3", "scan_n": "4", "min_cov": "0.5", "go": "explore"})
        self.assertEqual(len(LAB.researcher().journal.experiments()), before)        # explore is free
        page = C.get("/data").text
        self.assertIn("Lens cards for", page)
        lid = LAB.explore["cards"][0].hypothesis.id
        self.assertIn(lid, C.get(f"/data?lens={lid}").text)
        post("/data/learn", {"ds": "sbx_analyst", "explore_n": "3", "scan_n": "4", "min_cov": "0.5", "go": "scan"})
        JOBS.wait(300)
        page = C.get("/data").text
        self.assertIn("Noise bar for", page)
        self.assertGreater(len(LAB.researcher().journal.experiments()), before)       # the scan simulated

    def test_3_download_refused_in_sandbox(self):
        r = post("/data/download", {"region": "USA"})
        self.assertIn("needs+live+mode", r.headers["location"])


class Account(unittest.TestCase):
    def test_page_and_sync_refused_in_sandbox(self):
        config.save_settings(mode="sandbox")
        r = C.get("/account")
        self.assertEqual(r.status_code, 200)
        for h in ("Counts", "Genius tie-breakers", "Osmosis check", "Operators by category"):
            self.assertIn(h, r.text)
        r = post("/account/sync")
        self.assertIn("switch+to+Live", r.headers["location"])
        r = post("/account/rerun", {"alpha": "nope"})
        self.assertIn("Pick+a+submitted+alpha", r.headers["location"])


class Setup(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("HYPOLAB_PLATFORM", None)
        config.save_settings(mode="sandbox")
        LAB.mode_key = None

    def test_page(self):
        r = C.get("/setup")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Where you stand", r.text)
        self.assertIn("Remember on this laptop", r.text)
        self.assertIn("Operators you may use", r.text)

    def test_mode_switch_reopens_the_researcher(self):
        LAB.researcher()
        post("/setup/mode", {"mode": "live", "region": config.account_regions()[0]})
        self.assertFalse(config.sandbox_mode())
        page = C.get("/lab").text
        self.assertIn("not logged in", page.lower())
        post("/setup/mode", {"mode": "sandbox"})
        self.assertTrue(config.sandbox_mode())
        self.assertIsNotNone(LAB.researcher())

    def test_login_face_scan_logout(self):
        calls = {}
        orig = (connect.begin_login, connect.finish_login, connect.logout)

        def fake_begin(email, pw, save=True):
            calls["begin"] = (email, save)
            return {"status": "biometric", "url": "https://example.invalid/scan"}
        try:
            connect.begin_login = fake_begin
            connect.finish_login = lambda: {"status": "ok", "hours_left": 6, "saved": False}
            connect.logout = lambda *a, **k: calls.setdefault("logout", True)
            post("/setup/login", {"email": "me@example.com", "password": "pw", "save": "1"})
            page = C.get("/setup").text
            self.assertIn("Face scan required", page)
            self.assertIn("https://example.invalid/scan", page)
            r_before = LAB.researcher()
            post("/setup/scan-done")
            self.assertIsNone(LAB.mode_key)            # the Researcher is opened again on the next page
            self.assertIn("Logged in.", C.get("/setup").text)
            self.assertIsNot(LAB.researcher(), r_before)
            post("/setup/logout")
            self.assertTrue(calls.get("logout"))
            self.assertEqual(calls["begin"], ("me@example.com", True))
        finally:
            connect.begin_login, connect.finish_login, connect.logout = orig

    def test_tablet_never_saves_the_password_before_phase_d(self):
        os.environ["HYPOLAB_PLATFORM"] = "android"
        calls = {}
        orig = connect.begin_login
        try:
            connect.begin_login = lambda e, p, save=True: calls.setdefault("save", save) and {"status": "error",
                                                                                            "detail": "x"} or {
                "status": "error", "detail": "x"}
            self.assertIn("waits for phase D", C.get("/setup").text)
            post("/setup/login", {"email": "me@example.com", "password": "pw", "save": "1"})
            self.assertIs(calls["save"], False)
        finally:
            connect.begin_login = orig

    def test_empty_login_refused(self):
        r = post("/setup/login", {"email": "", "password": ""})
        self.assertIn("Type+your+BRAIN", r.headers["location"])


class Nav(unittest.TestCase):
    def test_links(self):
        page = C.get("/week").text
        for href in ('href="/data"', 'href="/account"', 'href="/setup"'):
            self.assertIn(href, page)


if __name__ == "__main__":
    unittest.main()

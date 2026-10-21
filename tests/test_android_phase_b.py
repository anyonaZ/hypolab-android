"""1.12.0, Android phase B: the launcher that runs the Ideas app inside the tablet app, the per-launch secret,
local fonts, the platform switch and the smaller practice market. Runs on the laptop (no Android needed)."""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "android" / "app" / "src" / "main" / "python"))

import requests  # noqa: E402

import hl_android  # noqa: E402   (does not import hypolab at module level)

FILES = tempfile.mkdtemp(prefix="hl_android_")
URL = hl_android.start(FILES)
ORIGIN = hl_android.origin()


class Launcher(unittest.TestCase):
    def test_home_and_platform(self):
        from hypolab import config
        self.assertEqual(str(config.HOME), os.path.join(FILES, "hypolab"))
        self.assertEqual(config.platform(), "android")
        self.assertEqual(config.sandbox_stocks(), 250)

    def test_start_twice_same_server(self):
        self.assertEqual(hl_android.start(FILES), URL)

    def test_listens_on_loopback_only(self):
        self.assertTrue(URL.startswith("http://127.0.0.1:"))

    def test_secret_required(self):
        r = requests.get(ORIGIN + "/week", allow_redirects=False, timeout=30)
        self.assertEqual(r.status_code, 403)
        r = requests.get(ORIGIN + "/?k=wrong", allow_redirects=False, timeout=30)
        self.assertEqual(r.status_code, 403)
        r = requests.get(ORIGIN + "/static/ideas.css", timeout=30)
        self.assertEqual(r.status_code, 403)
        r = requests.get(ORIGIN + "/week", cookies={"hl_k": "nope"}, timeout=30)
        self.assertEqual(r.status_code, 403)

    def test_first_url_sets_cookie_and_pages_render(self):
        s = requests.Session()
        r = s.get(URL, allow_redirects=False, timeout=30)
        self.assertEqual(r.status_code, 303)
        self.assertIn("httponly", r.headers.get("set-cookie", "").lower())
        self.assertIn("samesite=strict", r.headers.get("set-cookie", "").lower())
        for path in ("/week", "/leads", "/cards", "/drafts", "/drafts/new"):
            p = s.get(ORIGIN + path, timeout=120)
            self.assertEqual(p.status_code, 200, path)
            self.assertNotIn("fonts.googleapis", p.text, path)
            self.assertIn("/static/fonts/fonts.css", p.text, path)
            self.assertIn('class="android"', p.text, path)
            self.assertNotIn("127.0.0.1:2718", p.text, path)          # no cockpit link on the tablet
        self.assertEqual(s.get(ORIGIN + "/static/fonts/fonts.css", timeout=30).status_code, 200)

    def test_paste_boxes_marked(self):
        s = requests.Session()
        s.get(URL, timeout=30)
        self.assertIn("data-paste", s.get(ORIGIN + "/drafts", timeout=120).text)
        self.assertIn("data-paste", s.get(ORIGIN + "/week", timeout=120).text)

    def test_post_from_the_app_works_other_origin_refused(self):
        s = requests.Session()
        s.get(URL, timeout=30)
        r = s.post(ORIGIN + "/api/check", data={"region": "USA"}, headers={"Origin": ORIGIN}, timeout=120)
        self.assertNotEqual(r.status_code, 403)
        r = s.post(ORIGIN + "/api/check", data={}, headers={"Origin": "https://evil.example"}, timeout=30)
        self.assertEqual(r.status_code, 403)


class Fonts(unittest.TestCase):
    def test_every_font_file_exists_with_license(self):
        d = ROOT / "ideaweb" / "static" / "fonts"
        css = (d / "fonts.css").read_text()
        files = re.findall(r"url\(([^)]+)\)", css)
        self.assertGreaterEqual(len(files), 9)
        for f in files:
            self.assertTrue((d / f).exists(), f)
        self.assertEqual(len(list(d.glob("OFL-*.txt"))), 3)

    def test_css_families_are_bundled(self):
        css = (ROOT / "ideaweb" / "static" / "fonts" / "fonts.css").read_text()
        for fam in ("IBM Plex Sans", "IBM Plex Mono", "Newsreader"):
            self.assertIn(f'"{fam}"', css)


if __name__ == "__main__":
    unittest.main()

"""1.12.0: on the laptop nothing changes - no launch secret, the cockpit link stays, 500 stocks."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for k in ("HYPOLAB_LAUNCH_SECRET", "HYPOLAB_PLATFORM", "HYPOLAB_SANDBOX_STOCKS"):
    os.environ.pop(k, None)

from starlette.testclient import TestClient  # noqa: E402

from hypolab import config  # noqa: E402
from ideaweb.app import app  # noqa: E402


class Desktop(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(config.platform(), "desktop")
        self.assertEqual(config.sandbox_stocks(), 500)

    def test_pages_open_without_secret_and_keep_cockpit_link(self):
        c = TestClient(app)
        r = c.get("/week")
        self.assertEqual(r.status_code, 200)
        self.assertIn("127.0.0.1:2718", r.text)
        self.assertIn('class="desktop"', r.text)
        self.assertNotIn("fonts.googleapis", r.text)

    def test_setting_changes_market_size(self):
        config.save_settings(sandbox_stocks=120)
        try:
            from hypolab.mock import MockBrain
            self.assertEqual(MockBrain(seed=7).data.N, 120)
        finally:
            config.save_settings(sandbox_stocks=500)


if __name__ == "__main__":
    unittest.main()

"""1.11.0: HYPOLAB's own normal/skew/kurtosis helpers must match scipy (skipped where scipy is absent)."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypolab import _stats as S  # noqa: E402

try:
    import scipy.special as sps
    import scipy.stats as sst
except Exception:  # pragma: no cover
    sps = sst = None


class NoScipyImports(unittest.TestCase):
    def test_engine_does_not_import_scipy(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        for pkg in ("hypolab", "ideaengine", "ideaweb", "apps"):
            for dp, _, fs in os.walk(os.path.join(root, pkg)):
                for f in fs:
                    if f.endswith(".py"):
                        with open(os.path.join(dp, f), encoding="utf-8") as fh:
                            txt = fh.read()
                        self.assertNotIn("import scipy", txt, f)
                        self.assertNotIn("from scipy", txt, f)

    def test_ndtri_edges(self):
        out = S.ndtri(np.array([0.0, 1.0, np.nan, -0.1, 0.5]))
        self.assertEqual(out[0], -np.inf)
        self.assertEqual(out[1], np.inf)
        self.assertTrue(np.isnan(out[2]) and np.isnan(out[3]))
        self.assertEqual(out[4], 0.0)


@unittest.skipIf(sps is None, "scipy not installed")
class MatchesScipy(unittest.TestCase):
    def test_ndtri(self):
        p = np.concatenate([np.linspace(1e-12, 1 - 1e-12, 20001), [1e-300, 1e-50, 1e-6, 0.001, 0.999, 1 - 1e-6],
                            np.random.default_rng(0).random(5000)])
        np.testing.assert_allclose(S.ndtri(p), sps.ndtri(p), rtol=1e-12, atol=1e-12)
        m = np.random.default_rng(1).random((40, 30))
        m[3, 4] = np.nan
        np.testing.assert_allclose(S.ndtri(m), sps.ndtri(m), rtol=1e-12, atol=1e-12, equal_nan=True)

    def test_norm(self):
        for x in np.linspace(-8, 8, 161):
            self.assertAlmostEqual(S.norm_cdf(x), float(sst.norm.cdf(x)), places=12)
        for p in [1e-9, 0.001, 0.02, 0.3, 0.5, 0.9, 0.99, 1 - 1e-9]:
            self.assertTrue(math.isclose(S.norm_ppf(p), float(sst.norm.ppf(p)), rel_tol=1e-10, abs_tol=1e-12))

    def test_moments(self):
        rng = np.random.default_rng(2)
        for x in (rng.standard_normal(500), rng.standard_t(3, 800), rng.exponential(size=300)):
            self.assertAlmostEqual(S.skew(x), float(sst.skew(x)), places=10)
            self.assertAlmostEqual(S.kurtosis(x, fisher=False), float(sst.kurtosis(x, fisher=False)), places=10)
            self.assertAlmostEqual(S.kurtosis(x), float(sst.kurtosis(x)), places=10)


if __name__ == "__main__":
    unittest.main()

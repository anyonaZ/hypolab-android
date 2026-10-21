"""Small statistics helpers that replace scipy (1.11.0).

scipy has no current Android (Chaquopy) build, so HYPOLAB keeps its own versions of the five
functions it used. tests/test_stats_noscipy.py checks they match scipy to ~1e-12 wherever scipy
is installed.

- norm_cdf / norm_ppf: scalar standard-normal CDF and inverse CDF (statistics.NormalDist).
- ndtri: vectorised inverse normal CDF for numpy arrays (Wichura's AS241, about 1e-16 accurate);
  NaN in -> NaN out, 0 -> -inf, 1 -> +inf.
- skew / kurtosis: the biased sample estimators scipy uses by default (bias=True);
  kurtosis(fisher=False) is the plain fourth moment ratio (3 for a normal).
"""
from __future__ import annotations

from statistics import NormalDist

import numpy as np

_N = NormalDist()


def norm_cdf(x: float) -> float:
    return _N.cdf(float(x))


def norm_ppf(p: float) -> float:
    p = float(p)
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        return float("inf")
    return _N.inv_cdf(p)


# AS241 (PPND16) coefficients
_A = [3.3871328727963666080e0, 1.3314166789178437745e2, 1.9715909503065514427e3, 1.3731693765509461125e4,
      4.5921953931549871457e4, 6.7265770927008700853e4, 3.3430575583588128105e4, 2.5090809287301226727e3]
_B = [1.0, 4.2313330701600911252e1, 6.8718700749205790830e2, 5.3941960214247511077e3,
      2.1213794301586595867e4, 3.9307895800092710610e4, 2.8729085735721942674e4, 5.2264952788528545610e3]
_C = [1.42343711074968357734e0, 4.63033784615654529590e0, 5.76949722146069140550e0, 3.64784832476320460504e0,
      1.27045825245236838258e0, 2.41780725177450611770e-1, 2.27238449892691845833e-2, 7.74545014278341407640e-4]
_D = [1.0, 2.05319162663775882187e0, 1.67638483018380384940e0, 6.89767334985100004550e-1,
      1.48103976427480074590e-1, 1.51986665636164571966e-2, 5.47593808499534494600e-4, 1.05075007164441684324e-9]
_E = [6.65790464350110377720e0, 5.46378491116411436990e0, 1.78482653991729133580e0, 2.96560571828504891230e-1,
      2.65321895265761230930e-2, 1.24266094738807843860e-3, 2.71155556874348757815e-5, 2.01033439929228813265e-7]
_F = [1.0, 5.99832206555887937690e-1, 1.36929880922735805310e-1, 1.48753612908506148525e-2,
      7.86869131145613259100e-4, 1.84631831751005468180e-5, 1.42151175831644588870e-7, 2.04426310338993978564e-15]


def _poly(c, x):
    out = np.zeros_like(x)
    for k in reversed(c):
        out = out * x + k
    return out


def ndtri(p):
    p = np.asarray(p, dtype=float)
    out = np.full(p.shape, np.nan)
    ok = np.isfinite(p) & (p >= 0) & (p <= 1)
    q = p - 0.5
    central = ok & (np.abs(q) <= 0.425)
    if central.any():
        qc = q[central]
        r = 0.180625 - qc * qc
        out[central] = qc * _poly(_A, r) / _poly(_B, r)
    tail = ok & ~central
    if tail.any():
        pt = p[tail]
        r = np.where(q[tail] < 0, pt, 1.0 - pt)
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.sqrt(-np.log(r))
            near = r <= 5.0
            rn = r - 1.6
            rf = r - 5.0
            val = np.where(near, _poly(_C, rn) / _poly(_D, rn), _poly(_E, rf) / _poly(_F, rf))
        val = np.where(np.isinf(r), np.inf, val)
        out[tail] = np.where(q[tail] < 0, -val, val)
    return out if out.ndim else float(out)


def skew(x) -> float:
    x = np.asarray(x, dtype=float)
    d = x - x.mean()
    m2 = np.mean(d ** 2)
    if m2 == 0:
        return float("nan")
    return float(np.mean(d ** 3) / m2 ** 1.5)


def kurtosis(x, fisher: bool = True) -> float:
    x = np.asarray(x, dtype=float)
    d = x - x.mean()
    m2 = np.mean(d ** 2)
    if m2 == 0:
        return float("nan")
    k = float(np.mean(d ** 4) / m2 ** 2)
    return k - 3.0 if fisher else k

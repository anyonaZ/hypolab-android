"""Production / self correlation, handled with evidence (1.6.0).

What BRAIN does (Zacc's screenshots, 2026-10-11): right after a simulation the alpha page shows the production
correlation (maximum and minimum against the production pool) and the IS checks, where SELF_CORRELATION,
PROD_CORRELATION and the Power Pool correlation stay PENDING until "Check Submission". BRAIN's own check is the
authority: it may let an alpha above 0.7 through (BRAIN's self-correlation rule passes an alpha whose Sharpe is
clearly higher than the correlated one's; whether the production check does the same is NOT confirmed), so HYPOLAB
never blocks on its own reading when BRAIN's check has answered.

Three jobs:
1. read  - `corr_status(checks, prod)` tells PASS / FAIL / PENDING / UNKNOWN per correlation check, BRAIN first.
2. hint  - `theme_hints(checks)` reads BRAIN's theme warnings ("Theme GLB/D1 Risk Handled Crowding Factors/Fast
           Factors Theme does not match with multiplier of 2.5") and turns them into the neutralization that would
           match (CROWDING / FAST ...). Risk-handled neutralizations also remove crowded style exposure, so the same
           change can lower production correlation AND earn a theme multiplier.
3. fix   - `variants(...)` proposes at most a handful of principled changes that keep the idea (BRAIN_RULES R1:
           equivalent field, similar operator, meaningful grouping; N1/N2/N5: risk sets; H3: horizon), each with
           its reason. Researcher.decorrelate() simulates them, measures production correlation and Sharpe kept,
           and recommends the best trade-off - never just the lowest correlation.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import pandas as pd

from . import config

CORR_CHECKS = {"SELF_CORRELATION": "self", "PROD_CORRELATION": "prod", "POWER_POOL_CORRELATION": "power_pool"}

# Textbook families: many consultants have submitted them, so production correlation is the expected obstacle.
# (Learned numbers from the journal override this prior once you have measured a few.)
CROWDED_FAMILIES = {
    "pv_reversal": "short-term reversal", "pv_momentum": "momentum", "fnd_value": "value", "anl_value": "value",
    "fnd_quality": "quality / profitability", "pv_lowrisk": "low volatility", "rsk_lowrisk": "low risk",
    "corp_finance": "issuance / buybacks", "ern_surprise": "post-earnings drift", "anl_revision": "estimate revisions",
}

# Crowded styles as Gold-only expressions on the standard fields every region has.
STYLE_PROXIES = {
    "momentum": "rank(ts_sum(ts_delay(returns, 21), 231))",
    "reversal": "rank(-ts_sum(returns, 5))",
    "size": "rank(-log(cap))",
    "low_volatility": "rank(-ts_std_dev(returns, 252))",
    "value_proxy": "rank(-close / ts_max(close, 252))",
}

# Words in a BRAIN theme name -> the neutralization that matches it (longest first).
THEME_NEUTRALIZATION = [
    ("reversion and momentum", "REVERSION_AND_MOMENTUM"), ("slow and fast", "SLOW_AND_FAST"),
    ("crowding", "CROWDING"), ("fast factor", "FAST"), ("slow factor", "SLOW"), ("statistical", "STATISTICAL"),
]
RISK_SETS = ["CROWDING", "SLOW_AND_FAST", "FAST", "SLOW", "REVERSION_AND_MOMENTUM", "STATISTICAL"]

_THEME_RE = re.compile(r"(?<!Pyramid )Theme\s+(?P<theme>.+?)\s+(?P<match>does not match|matches)\s+with\s+multiplier\s+of\s+"
                       r"(?P<mult>[0-9]+(?:\.[0-9]+)?)", re.I)


def _rows(checks) -> List[dict]:
    if checks is None:
        return []
    if isinstance(checks, pd.DataFrame):
        return checks.to_dict("records")
    return [c for c in checks if isinstance(c, dict)]


def corr_status(checks=None, prod: Optional[dict] = None, self_corr: Optional[dict] = None) -> Dict[str, dict]:
    """Per correlation check: {"result": PASS|FAIL|PENDING|UNKNOWN, "value", "limit", "source"}.
    BRAIN's check row wins; HYPOLAB's own reading (max vs the settings limit) is used only when there is no row."""
    st = config.settings()
    limits = {"self": st.get("max_self_corr", 0.7), "prod": st.get("max_prod_corr", 0.7), "power_pool": 0.7}
    out = {k: {"result": "UNKNOWN", "value": None, "limit": limits[k], "source": "none"} for k in limits}
    for r in _rows(checks):
        kind = CORR_CHECKS.get(str(r.get("name", "")).upper())
        if kind:
            res = str(r.get("result", "UNKNOWN")).upper()
            out[kind] = {"result": res, "value": r.get("value"), "limit": r.get("limit") or limits[kind],
                         "source": "BRAIN check"}
    for kind, reading in (("prod", prod), ("self", self_corr)):
        mx = (reading or {}).get("max")
        if mx is None:
            continue
        if out[kind]["value"] is None:
            out[kind]["value"] = mx
        if out[kind]["source"] == "none" or out[kind]["result"] == "PENDING":
            if out[kind]["source"] == "none":
                out[kind]["result"] = "FAIL?" if mx >= limits[kind] else "PASS?"
                out[kind]["source"] = "HYPOLAB reading (BRAIN's check not run)"
            out[kind]["reading"] = mx
    return out


def status_line(status: Dict[str, dict]) -> str:
    parts = []
    for kind, label in (("prod", "production"), ("self", "self"), ("power_pool", "Power Pool")):
        s = status.get(kind) or {}
        if s.get("result") == "UNKNOWN" and s.get("value") is None:
            continue
        v = s.get("value")
        parts.append(f"{label} {s.get('result')}" + (f" ({float(v):.2f} vs {s.get('limit')})" if v is not None else ""))
    return "; ".join(parts) or "no correlation numbers yet"


def theme_hints(checks=None, offered: Optional[Sequence[str]] = None, current: Optional[str] = None) -> List[dict]:
    """BRAIN's theme lines -> [{"theme", "multiplier", "matches", "neutralization"}]; neutralization is set only
    for themes that do NOT match yet and name a risk set the region offers."""
    out, seen = [], set()
    for r in _rows(checks):
        text = json.dumps(r, default=str)
        for m in _THEME_RE.finditer(text.replace("\\n", " ")):
            theme = m.group("theme").strip(" .\"'")
            if theme in seen:
                continue
            seen.add(theme)
            low = theme.lower()
            neut = next((n for w, n in THEME_NEUTRALIZATION if w in low), None)
            if neut and offered is not None and neut not in offered:
                neut = None
            matches = m.group("match").lower() == "matches"
            out.append({"theme": theme, "multiplier": float(m.group("mult")), "matches": matches,
                        "neutralization": None if matches or neut == current else neut})
    return out


def crowding_prior(card, journal=None) -> dict:
    """How taken an idea probably is, before simulating: family prior, learned family numbers, field crowding."""
    notes, score = [], 0.0
    fam = getattr(card, "family", None) or getattr(getattr(card, "hypothesis", None), "family", None)
    if fam in CROWDED_FAMILIES:
        score += 0.4
        notes.append(f"textbook idea ({CROWDED_FAMILIES[fam]}) - many alphas in the pool hold it")
    learned = family_prod_corr(journal).get(fam) if journal is not None and fam else None
    if learned:
        notes.append(f"your measured production correlation in this family: median {learned['median']:.2f} over "
                     f"{learned['n']} alpha(s)")
        score = max(score, min(1.0, learned["median"]))
    for b in (getattr(card, "bindings", None) or {}).values():
        ac = b.alpha_count
        if ac is not None and ac == ac and ac >= 1000:
            score += 0.2
            notes.append(f"field {b.field_id} is already in {int(ac)} alphas")
    return {"score": round(min(score, 1.0), 2), "notes": notes}


def family_prod_corr(journal) -> Dict[str, dict]:
    """Measured production correlation per family (from the journal's correlations table)."""
    if journal is None:
        return {}
    try:
        df = pd.read_sql_query(
            "SELECT i.family, c.max FROM correlations c JOIN experiments e ON e.alpha_id = c.alpha_id "
            "JOIN ideas i ON i.id = e.idea_id WHERE c.kind = 'prod' AND c.max IS NOT NULL", journal.db)
    except Exception:  # noqa: BLE001
        return {}
    if df.empty:
        return {}
    g = df.drop_duplicates().groupby("family")["max"]
    return {f: {"median": float(s.median()), "max": float(s.max()), "n": int(s.size)} for f, s in g}


# ------------------------------------------------------------------------------------------------- variants
@dataclass
class Variant:
    name: str
    why: str
    expression: str
    settings: Dict[str, object] = field(default_factory=dict)
    kind: str = ""          # risk_set | residual | field | horizon | grouping | own_residual


def _windows(expr: str):
    """(start, end, value, enclosing function) for each integer literal in the expression."""
    out, stack, i = [], [], 0
    name = ""
    while i < len(expr):
        ch = expr[i]
        if ch.isalpha() or ch == "_":
            j = i
            while j < len(expr) and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            name, i = expr[i:j], j
            continue
        if ch == "(":
            stack.append(name)
            name = ""
        elif ch == ")":
            if stack:
                stack.pop()
        elif ch.isdigit() and (i == 0 or not (expr[i - 1].isalnum() or expr[i - 1] in "._")):
            j = i
            while j < len(expr) and (expr[j].isdigit() or expr[j] == "."):
                j += 1
            tok = expr[i:j]
            if tok.isdigit() and not (j < len(expr) and (expr[j].isalpha() or expr[j] == "_")):
                out.append((i, j, int(tok), stack[-1] if stack else ""))
            i = j
            name = ""
            continue
        elif not ch.isspace():
            name = ""
        i += 1
    return out


def _shorter_horizon(expr: str) -> Optional[str]:
    """Shorten the LONGEST look-back (>= 126 days) to the next shorter economic window (504 -> 252 ...).
    ts_backfill windows are not horizons (they only carry sparse data forward) and are left alone."""
    wins = sorted(w for w in config.ECONOMIC_WINDOWS if w >= 63)
    found = [w for w in _windows(expr) if w[2] in wins and w[2] >= 126 and w[3] != "ts_backfill"]
    if not found:
        return None
    longest = max(w[2] for w in found)
    shorter = max(w for w in wins if w < longest)
    out = expr
    for a, b, v, _ in sorted(found, reverse=True):
        if v == longest:
            out = out[:a] + str(shorter) + out[b:]
    return out


def _residual(expr: str, proxy: str) -> str:
    """Gold-only residualization: neutralize the alpha within deciles of the crowded style, so only the part the
    style does not explain is traded (vector_neut is a Genius operator). 1.8.1: applied to the FINAL value of a
    multi-statement expression (wrapping the whole text broke boosted alphas and any alpha with variables)."""
    from .diagnose import wrap_result
    return wrap_result(expr, 'group_neutralize({}, bucket(' + proxy + ', range="0,1,0.1"))')


def _other_grouping(expr: str) -> Optional[str]:
    for a, b in (("subindustry", "industry"), ("industry", "sector"), ("sector", "industry")):
        if re.search(rf"\b{a}\b", expr):
            return re.sub(rf"\b{a}\b", b, expr, count=1)
    return None


def variants(expression: str, settings: dict, *, checks=None, style_corr: Optional[Dict[str, float]] = None,
             own_corr: Optional[List[dict]] = None, field_swaps: Optional[List[dict]] = None, k: int = 4,
             turnover: float = 0.0) -> List[Variant]:
    """Candidate changes, best first, at most k. Each keeps the idea and changes ONE thing for a stated reason."""
    region = settings.get("region", "")
    offered = config.region_neutralizations(region)
    cur = settings.get("neutralization")
    out: List[Variant] = []
    used_neut = set()
    # 1. risk set named by a theme BRAIN says does not match yet (correlation + multiplier in one change)
    for h in theme_hints(checks, offered, cur):
        n = h["neutralization"]
        if n and n not in used_neut:
            used_neut.add(n)
            out.append(Variant(f"neutralization {n}", f"BRAIN's theme '{h['theme']}' would match (x{h['multiplier']:g})"
                               " and this risk set removes crowded style exposure", expression,
                               {"neutralization": n}, "risk_set"))
    # 2. residual against the crowded style the alpha resembles most (measured PnL correlation)
    if style_corr:
        name, rho = max(style_corr.items(), key=lambda kv: abs(kv[1]))
        if abs(rho) >= 0.3:
            out.append(Variant(f"remove {name} exposure", f"PnL correlation {rho:+.2f} with a {name} proxy: trade only "
                               f"what {name} does not explain", _residual(expression, STYLE_PROXIES[name]), {},
                               "residual"))
    # 3. equivalent field from a less crowded dataset (R1 step 1)
    for sw in (field_swaps or [])[:1]:
        out.append(Variant(f"field {sw['old']} -> {sw['new']}", sw.get("why", "equivalent field, fewer alphas on it"),
                           sw["expression"], {}, "field"))
    # 4. the general crowding risk set when no theme pointed to one
    for n in ("CROWDING", "SLOW_AND_FAST" if (turnover or 0) >= 0.2 else "SLOW"):
        if n in offered and n != cur and n not in used_neut:
            used_neut.add(n)
            out.append(Variant(f"neutralization {n}", "BRAIN_RULES N5: re-simulating with a risk set often keeps the "
                               "Sharpe and lowers correlation with the pool", expression, {"neutralization": n},
                               "risk_set"))
            break
    # 5. shorter horizon (H3: short-horizon alphas correlate less with the pool, which sits at 20+ days)
    sh = _shorter_horizon(expression)
    if sh and sh != expression:
        out.append(Variant("shorter horizon", "most of the pool holds 20+ days; a shorter look-back is a different "
                           "bet on the same mechanism (BRAIN_RULES H3)", sh, {}, "horizon"))
    # 6. residual against your own most correlated alpha (self-correlation)
    for o in (own_corr or [])[:1]:
        code = str(o.get("code") or "")
        if o.get("corr", 0) >= 0.5 and code and ";" not in code and "=" not in code.replace("==", ""):
            # a multi-statement alpha cannot sit inside rank(...): only single-expression alphas are used here
            out.append(Variant(f"remove overlap with {o['alpha_id']}", f"PnL correlation {o['corr']:.2f} with your own "
                               "submitted alpha", _residual(expression, f"rank({code})"), {}, "own_residual"))
    # 7. a different meaningful grouping (R1 step 3)
    g = _other_grouping(expression)
    if g:
        out.append(Variant("different peer group", "BRAIN_RULES R1 step 3: a meaningful grouping changes who the "
                           "alpha is compared with", g, {}, "grouping"))
    seen, uniq = set(), []
    for v in out:
        key = (v.expression, json.dumps(v.settings, sort_keys=True))
        if key not in seen:
            seen.add(key)
            uniq.append(v)
    return uniq[:k]


def recommend(rows: pd.DataFrame, base_sharpe: float, limit: float = 0.7) -> Optional[int]:
    """Index of the best variant: the highest Sharpe among those under the limit that keep >= 60% of the Sharpe.
    None when nothing qualifies."""
    if rows is None or rows.empty:
        return None
    ok = rows.dropna(subset=["sharpe"])
    ok = ok[ok["sharpe"] > 0]
    if ok.empty:
        return None
    keep = ok["sharpe"] / max(abs(base_sharpe), 1e-9)
    under = ok[(ok["prod_corr"].notna()) & (ok["prod_corr"] < limit) & (keep >= 0.6)]
    if not under.empty:
        return int(under["sharpe"].idxmax())
    return None          # nothing under the limit that keeps the signal: say so, never recommend a copy


def lesson(rows: pd.DataFrame, base_corr: Optional[float], base_sharpe: float) -> str:
    """What the attempt teaches (shown under the table)."""
    if rows is None or rows.empty:
        return "No variant could be built."
    done = rows.dropna(subset=["sharpe"])
    if done.empty:
        return "No variant produced a result."
    best_keep = (done["sharpe"] / max(abs(base_sharpe), 1e-9)).max()
    if best_keep < 0.5:
        return ("Every change that lowers the overlap also removes most of the Sharpe: the signal IS the crowded "
                "part. Submitting a copy would not help your combined performance - move to another idea or dataset.")
    if base_corr is not None and done["prod_corr"].notna().any() and done["prod_corr"].min() >= base_corr - 0.05:
        return ("Correlation barely moved: it comes from the data itself. An equivalent field from a less used dataset "
                "or a different mechanism is the next step, not more settings.")
    return "Some changes kept the signal and lowered the overlap - the unique part of the idea is real."

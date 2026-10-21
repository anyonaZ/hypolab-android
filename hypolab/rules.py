"""BRAIN's own rules, in one place (see docs/BRAIN_RULES.md for the source of every number).

* Single Dataset Alphas  - fields from one dataset only (grouping fields don't count) skip the
  IS-ladder Sharpe test and must instead clear a last-2-year Sharpe cutoff.        [S1]
* Sub-universe test      - sub_sharpe >= 0.75 * sqrt(sub_size / size) * sharpe.     [S9]
* Fitness rating labels  - Spectacular / Excellent / Good / Average / Needs Improvement. [S18]
* BRAIN's day            - simulation quota and daily counts reset at midnight New York time. [S2]
"""
from __future__ import annotations

import datetime as _dt
import math
from typing import Callable, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from . import fastexpr as fx

BRAIN_TZ = ZoneInfo("America/New_York")

_KEYWORDS = {"true", "false", "nan", "NaN", "inf"}

# Grouping fields that never count as a dataset or a Pyramid category. The Single Dataset page lists six [S1];
# the newer "Clear these tests" page (ATOM and Pyramid Alphas) adds currency, split and adjfactor [S26].
GROUPING_FIELDS = {"country", "exchange", "market", "sector", "industry", "subindustry", "currency", "split",
                   "adjfactor"}
# Operators that read pv1 data under the hood [S1].
PV1_OPERATORS = {"inst_pnl", "convert"}
# Last-2-year IS Sharpe a Single Dataset Alpha must clear, by delay [S1].
SINGLE_DATASET_2Y_SHARPE = {1: 2.38, 0: 3.96}
# BRAIN multiplies IS-ladder thresholds by 0.85 when turnover < 30%. Whether that also applies to the
# single-dataset cutoffs is not stated (BRAIN_RULES T2), so we only mention it.
LOW_TURNOVER_FACTOR = 0.85
LOW_TURNOVER_BELOW = 0.30

FITNESS_LABELS = {  # (label, D1 lower bound, D0 lower bound) - strictly greater than [S18]
    "Spectacular": (2.5, 3.25),
    "Excellent": (2.0, 2.6),
    "Good": (1.5, 1.95),
    "Average": (1.0, 1.3),
}


# ----------------------------------------------------------- single dataset
def fields_in(expression: str) -> List[str]:
    """Identifiers in an expression that are data fields (not operators, not assigned variables)."""
    try:
        prog = fx.parse(expression)
    except fx.ParseError:
        return []
    assigned = {n.target for n in fx.walk(prog) if isinstance(n, fx.Assign)} | _KEYWORDS
    out = []
    for n in fx.walk(prog):
        if isinstance(n, fx.Name) and n.id not in assigned and n.id not in out:
            out.append(n.id)
    return out


def dataset_profile(expression: str, dataset_of: Callable[[str], Optional[str]], delay: int = 1) -> Dict:
    """Which datasets an expression draws on, and which IS Sharpe test applies.

    ``dataset_of(field_id)`` returns the field's dataset id, or None if unknown (e.g. no catalog yet).
    Returns {"datasets": [...], "unknown": [...], "single": bool | None, "test": str, "cutoff": float | None}.
    ``single`` is None when some fields could not be looked up.
    """
    try:
        ops = set(fx.operators_used(fx.parse(expression)))
    except fx.ParseError:
        ops = set()
    datasets, unknown = set(), []
    for f in fields_in(expression):
        if f in GROUPING_FIELDS:
            continue
        ds = dataset_of(f)
        if ds:
            datasets.add(ds)
        else:
            unknown.append(f)
    if ops & PV1_OPERATORS:
        datasets.add("pv1")
    if unknown:
        single = None
    else:
        single = len(datasets) == 1
    cutoff = SINGLE_DATASET_2Y_SHARPE.get(int(delay)) if single else None
    if single:
        test = f"single dataset ({next(iter(datasets))}): last-2-year Sharpe >= {cutoff} instead of the IS ladder"
    elif single is None:
        test = f"unknown - no catalog entry for {', '.join(unknown)}"
    else:
        test = f"{len(datasets)} datasets ({', '.join(sorted(datasets))}): regular IS-ladder Sharpe test"
    return {"datasets": sorted(datasets), "unknown": unknown, "single": single, "test": test, "cutoff": cutoff}


def catalog_lookup(catalog, region: str, universe: Optional[str], delay: int) -> Callable[[str], Optional[str]]:
    """dataset_of() backed by HYPOLAB's catalog (one query, then a dict)."""
    try:
        if hasattr(catalog, "lookup_map"):
            return catalog.lookup_map(region, universe, delay).get      # cached per context (1.4.3)
        df = catalog.fields(region, universe, delay, enrich=False)
    except Exception:  # noqa: BLE001
        df = None
    m = {} if df is None or df.empty else dict(zip(df["id"], df["dataset"]))
    return m.get


# ------------------------------------------------------------ other tests
def sub_universe_cutoff(alpha_sharpe: float, sub_size: float, size: float) -> float:
    """BRAIN's sub-universe threshold [S9], e.g. TOP3000 -> TOP1000: 0.433 x Sharpe."""
    if not size:
        return 0.0
    return 0.75 * math.sqrt(sub_size / size) * alpha_sharpe


def fitness_label(fitness: Optional[float], delay: int = 1) -> str:
    if fitness is None or (isinstance(fitness, float) and math.isnan(fitness)):
        return ""
    col = 0 if int(delay) == 1 else 1
    for label, bounds in FITNESS_LABELS.items():
        if fitness > bounds[col]:
            return label
    return "Needs Improvement"


# --------------------------------------------------------------- BRAIN day
def brain_day_start(now: Optional[_dt.datetime] = None) -> float:
    """Unix time of the last midnight in New York - when BRAIN's daily simulation quota resets [S2]."""
    now = now or _dt.datetime.now(tz=_dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_dt.timezone.utc)
    ny = now.astimezone(BRAIN_TZ)
    midnight = _dt.datetime.combine(ny.date(), _dt.time(), tzinfo=BRAIN_TZ)
    return midnight.timestamp()


def quarter_bounds(day: Optional[_dt.date] = None) -> tuple:
    """(start, end) dates of the calendar quarter - Genius counts signals and Pyramids per quarter [S14]."""
    day = day or _dt.date.today()
    q0 = 3 * ((day.month - 1) // 3) + 1
    start = _dt.date(day.year, q0, 1)
    end = _dt.date(day.year + (q0 == 10), 1 if q0 == 10 else q0 + 3, 1) - _dt.timedelta(days=1)
    return start, end


def osmosis_lock_deadline(quarter_end: _dt.date, weeks_needed: int = 6) -> _dt.date:
    """Last Sunday whose locked allocation still gives ``weeks_needed`` used weeks by quarter end [S10].

    Points lock Sunday 23:59 New York time and are used from the Monday 8 days later.
    """
    d = quarter_end
    while d.weekday() != 6:
        d -= _dt.timedelta(days=1)
    while True:
        first_used = d + _dt.timedelta(days=8)
        weeks = (quarter_end - first_used).days // 7 + 1
        if weeks >= weeks_needed:
            return d
        d -= _dt.timedelta(days=7)


def delay_of(value, default: int = 1) -> int:
    """A delay from settings / BRAIN rows. 1.8.1: `int(x or 1)` turned delay 0 into delay 1 (0 is falsy), so D0
    alphas were re-run, diagnosed and counted as D1."""
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)) or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def split_names(items: Iterable[str]) -> str:
    return ", ".join(sorted(set(items)))


# ------------------------------------------------------------- 1.6.0: rules read on 2026-10-19 (batch 5)
# Pyramid Alphas: an alpha contributes to at most 2 Pyramids (region x delay x category) [S26].
MAX_PYRAMIDS_PER_ALPHA = 2


def pyramid_check(categories: Iterable[str]) -> Dict:
    """Does an alpha with these data categories still count as a Pyramid Alpha? (grouping fields excluded)."""
    cats = sorted({str(c) for c in categories if c})
    ok = len(cats) <= MAX_PYRAMIDS_PER_ALPHA
    note = "" if ok else (f"touches {len(cats)} data categories ({', '.join(cats)}): BRAIN counts an alpha toward at most "
                          f"{MAX_PYRAMIDS_PER_ALPHA} Pyramids, so the extra categories add nothing (and it may not "
                          "count as a Pyramid Alpha). Keep it to 1-2 categories.")
    return {"categories": cats, "ok": ok, "note": note}


# Power Pool Alphas [S27]: Sharpe >= 1.0, <= 8 operators in total (repeats counted, ts_backfill / group_backfill not),
# <= 3 unique data fields (grouping fields excluded), Power Pool correlation < 0.5, turnover + sub-universe tests pass,
# and a description of at least 100 characters (Idea / Rationale for data / Rationale for operators).
POWER_POOL = {"min_sharpe": 1.0, "max_operators": 8, "max_fields": 3, "max_pp_corr": 0.5, "min_description": 100}
_NOT_COUNTED = {"ts_backfill", "group_backfill"}


def power_pool_shape(expression: str) -> Dict:
    """The parts of the Power Pool criteria an expression decides by itself (operators and fields)."""
    try:
        prog = fx.parse(expression)
    except fx.ParseError:
        return {"operators": None, "fields": None, "ok": False, "note": "expression does not parse"}
    ops = [o for o in fx.operators_used(prog) if o not in _NOT_COUNTED]
    flds = [f for f in fields_in(expression) if f not in GROUPING_FIELDS]
    ok = len(ops) <= POWER_POOL["max_operators"] and len(flds) <= POWER_POOL["max_fields"]
    note = (f"{len(ops)} operators (max {POWER_POOL['max_operators']}), {len(flds)} fields (max "
            f"{POWER_POOL['max_fields']})")
    return {"operators": len(ops), "fields": len(flds), "ok": ok, "note": note}


# BRAIN's recommended neutralization per data category [S28]. The first entry is the default to try.
RECOMMENDED_NEUTRALIZATION = {
    "fundamental": ["INDUSTRY"], "analyst": ["INDUSTRY"], "earnings": ["INDUSTRY"], "shortinterest": ["INDUSTRY"],
    "news": ["SUBINDUSTRY"], "option": ["SECTOR", "MARKET"], "pv": ["MARKET", "SECTOR"],
    "socialmedia": ["SUBINDUSTRY", "INDUSTRY"], "institutions": ["SECTOR", "INDUSTRY"],
    "insiders": ["INDUSTRY", "SUBINDUSTRY"], "sentiment": ["INDUSTRY", "SUBINDUSTRY"],
    "macro": ["SECTOR", "MARKET", "INDUSTRY"], "model": ["MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY"],
}


def recommended_neutralization(categories: Iterable[str]) -> List[str]:
    """Neutralizations BRAIN suggests for the data an alpha uses (the non-pv category decides when there is one)."""
    cats = [c for c in categories if c]
    main = [c for c in cats if c != "pv"] or cats
    out: List[str] = []
    for c in main:
        for n in RECOMMENDED_NEUTRALIZATION.get(c, []):
            if n not in out:
                out.append(n)
    return out


def self_corr_exception(alpha_sharpe: Optional[float], table, cutoff: float = 0.7) -> Optional[bool]:
    """BRAIN accepts self-correlation above the cutoff when the alpha's Sharpe is >= 10% higher than every alpha it
    correlates with above the cutoff [S26]. table: BRAIN's self-correlation records (columns incl. correlation, sharpe).
    Returns True/False, or None when the table lacks the columns to decide."""
    try:
        if alpha_sharpe is None or table is None or table.empty:
            return None
        cols = {c.lower(): c for c in table.columns}
        cc, sc = cols.get("correlation"), cols.get("sharpe")
        if not cc or not sc:
            return None
        hi = table[table[cc].astype(float) >= cutoff]
        if hi.empty:
            return True
        return bool((float(alpha_sharpe) >= 1.1 * hi[sc].astype(float)).all())
    except Exception:  # noqa: BLE001
        return None


# Region Agnostic Alphas [S29]: one simulation across GLB, USA, EUR, ASI (D1 only) on special RA universes.
RA_UNIVERSES = {
    "LARGE": {"ASI": "MINVOL1M", "EUR": "TOP2500", "GLB": "MINVOL1M", "USA": "TOP3000"},
    "MEDIUM": {"ASI": "MINVOL10M", "EUR": "TOP1200", "GLB": "MINVOL10M", "USA": "TOP1000"},
    "SMALL": {"ASI": "TOP500", "EUR": "TOP800", "GLB": "TOPDIV3000", "USA": "TOP500"},
}
RA_REGIONS = ("USA", "EUR", "ASI", "GLB")
RA_NOTE = ("Region Agnostic Alpha: simulate once across USA/EUR/ASI/GLB (D1, RA universe SMALL/MEDIUM/LARGE). It is "
           "submittable when 2+ regions pass Sharpe >= 1.58, Fitness >= 1.0, 2Y Sharpe >= 1.58, sub-universe and "
           "self-correlation; it uses ONE submission but every passing region counts as a signal and in its Pyramid.")


_THEMES_CACHE: Dict = {}


def themes(day: Optional[_dt.date] = None) -> List[Dict]:
    """Active BRAIN themes (data/themes.json), e.g. the EUR/D1 TOP800 theme of Oct-Nov 2026."""
    import json
    from . import config
    day = day or _dt.date.today()
    path = config.BUNDLED_DATA / "themes.json"
    try:
        sig = (path.stat().st_mtime_ns, path.stat().st_size)
        if _THEMES_CACHE.get("sig") != sig:                 # 1.8.1: parsed once, not once per card
            _THEMES_CACHE.update(sig=sig, rows=json.loads(path.read_text()).get("themes", []))
        rows = _THEMES_CACHE["rows"]
    except (OSError, ValueError):
        return []
    out = []
    for t in rows:
        try:
            start, end = _dt.date.fromisoformat(t["start"]), _dt.date.fromisoformat(t["end"])
        except (KeyError, ValueError):
            continue
        if start <= day <= end:
            out.append(dict(t, days_left=(end - day).days))
    return out


def last_month_warning(day: Optional[_dt.date] = None) -> str:
    """Genius G8: alphas submitted in a quarter's last month may not count toward that quarter's combined performance."""
    day = day or _dt.date.today()
    _, end = quarter_bounds(day)
    if day.month == end.month:
        return ("Last month of the quarter: new submissions still count for signals and Pyramids, but may not count "
                "toward this quarter's combined alpha performance (Genius G8).")
    return ""

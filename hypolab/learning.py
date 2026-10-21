"""What the journal has learned (phase 5, 1.7.0).

Pure reads of ``journal.sqlite``: near misses, inverted results, dead ends, scan candidates, failed-check
patterns and transfers between regions. The Idea Engine (``ideaengine/learn.py``) turns these facts into
inbox items, drafts and the weekly digest; the card ranking (``ideas._score``) uses ``card_adjustments``.

Sandbox (practice) rows never count, except in the sandbox's own in-memory journal, so practice runs can be
used to learn the screens.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from hypolab import config
from hypolab.overfit import noise_bar

VERDICT_RANK = {"PASS": 5, "NEAR": 4, "WEAK": 3, "INVERTED": 2, "NOISE": 1, "ERROR": 0, "BLOCKED": 0, "BUDGET": 0}
SIGNAL = ("PASS", "NEAR", "WEAK")
# The tries on a card's idea: what the trial budget and the gate count (journal.trials also counts play, but Play
# rows have their own play:... idea ids). 1.10.1: every "tries" count in HYPOLAB uses this.
TRY_PURPOSES = ("explore", "boost", "decorr")


def _budget(budget: Optional[int] = None) -> int:
    return int(budget or config.settings().get("max_sims_per_idea", 10))


def hypothesis_of(idea_id: str) -> str:
    """'ERN_PEAD@USA' -> 'ERN_PEAD'; 'play:ERN_PEAD@USA' -> 'ERN_PEAD'; 'rerun:abc' stays as it is."""
    i = str(idea_id or "")
    if i.startswith("play:") and not i.startswith("play:wild:"):
        i = i[5:]
    return i.rsplit("@", 1)[0] if "@" in i else i


def is_card_idea(idea_id: str) -> bool:
    """True for ideas built from a hypothesis card (not lens/scan probes, play rolls or re-runs)."""
    i = str(idea_id or "")
    return not i.startswith(("play:", "rerun:", "LENS_"))


def _journal_version(journal):
    """Changes whenever anything was committed to the journal, by this connection or another (the cockpit writes
    while the Ideas app reads). None = unknown, no caching."""
    try:
        return (journal.db.execute("PRAGMA data_version").fetchone()[0], journal.db.total_changes)
    except Exception:  # noqa: BLE001
        return None


def live_experiments(journal, purposes: Optional[Iterable[str]] = None) -> pd.DataFrame:
    """The journal's experiments joined to their idea (family, categories, hypothesis), sandbox rows dropped
    unless this IS the in-memory sandbox journal. 1.10.1: cached on the journal object until the journal changes
    (the Week page asked for it a dozen times per load)."""
    ver = _journal_version(journal)
    key = (ver, tuple(purposes) if purposes else None)
    cache = getattr(journal, "_live_cache", None)
    if ver is not None and isinstance(cache, dict) and key in cache:
        return cache[key].copy()
    out = _live_experiments(journal, purposes)
    if ver is not None:
        if not isinstance(cache, dict) or len(cache) > 8 or any(k[0] != ver for k in cache):
            cache = {}
        cache[key] = out
        try:
            journal._live_cache = cache
        except AttributeError:
            return out
        return out.copy()
    return out


def _live_experiments(journal, purposes: Optional[Iterable[str]] = None) -> pd.DataFrame:
    ex = journal.experiments()
    if ex.empty:
        return ex.assign(family=[], categories=[], hypothesis_id=[])
    if getattr(journal, "path", None) != ":memory:":
        ex = ex[ex["backend"].fillna("") != "sandbox"]
    if purposes:
        ex = ex[ex["purpose"].isin(list(purposes))]
    try:
        ideas = pd.read_sql_query("SELECT id AS idea_id, hypothesis_id, family, categories FROM ideas", journal.db)
    except Exception:  # noqa: BLE001
        ideas = pd.DataFrame(columns=["idea_id", "hypothesis_id", "family", "categories"])
    ex = ex.merge(ideas, on="idea_id", how="left")
    ex["hypothesis_id"] = ex["hypothesis_id"].fillna(ex["idea_id"].map(hypothesis_of))
    ex["family"] = ex["family"].fillna("")
    ex["categories"] = ex["categories"].fillna("")
    ex["verdict"] = ex["verdict"].fillna("")
    return ex.sort_values("created").reset_index(drop=True)


def idea_summary(journal, budget: Optional[int] = None) -> pd.DataFrame:
    """One row per idea (its tries: TRY_PURPOSES): tries, best verdict, best Sharpe, the rung that got there."""
    b = _budget(budget)
    ex = live_experiments(journal, TRY_PURPOSES)
    cols = ["idea_id", "hypothesis_id", "family", "region", "categories", "tries", "tries_left", "best_verdict",
            "best_sharpe", "best_fitness", "best_rung", "best_failed", "last"]
    if ex.empty:
        return pd.DataFrame(columns=cols)
    ex = ex.assign(_rank=ex["verdict"].map(lambda v: VERDICT_RANK.get(v, 0)), _sh=ex["sharpe"].fillna(-99))
    best = ex.sort_values(["_rank", "_sh"], ascending=False).drop_duplicates("idea_id")
    g = ex.groupby("idea_id").agg(tries=("id", "count"), last=("created", "max"))
    out = best.merge(g, left_on="idea_id", right_index=True)
    out = out.rename(columns={"verdict": "best_verdict", "sharpe": "best_sharpe", "fitness": "best_fitness",
                              "rung": "best_rung", "failed": "best_failed"})
    out["tries_left"] = (b - out["tries"]).clip(lower=0)
    return out[cols].sort_values("last", ascending=False).reset_index(drop=True)


def near_misses(journal, budget: Optional[int] = None) -> pd.DataFrame:
    """Ideas whose best result is NEAR (or WEAK with Sharpe >= 1.0). ``at_budget`` = no tries left: the
    honest next step is a sibling card, not an 11th rung."""
    s = idea_summary(journal, budget)
    if s.empty:
        return s.assign(at_budget=[])
    s = s[(s["best_verdict"] == "NEAR") | ((s["best_verdict"] == "WEAK") & (s["best_sharpe"].fillna(0) >= 1.0))]
    s = s.assign(at_budget=s["tries_left"] <= 0)
    return s.sort_values("best_sharpe", ascending=False).reset_index(drop=True)


def inverted(journal) -> pd.DataFrame:
    """INVERTED results with no later positive result on the same idea (the flip was never tried or never
    worked). Each needs a decision: does the reverse mechanism make economic sense?"""
    ex = live_experiments(journal, TRY_PURPOSES + ("play",))
    cols = ["idea_id", "hypothesis_id", "family", "region", "rung", "expression", "sharpe", "created"]
    if ex.empty:
        return pd.DataFrame(columns=cols)
    inv = ex[ex["verdict"] == "INVERTED"].drop_duplicates("idea_id", keep="last")
    rows = []
    for r in inv.itertuples(index=False):
        later = ex[(ex["idea_id"] == r.idea_id) & (ex["created"] > r.created)]
        if not later.empty and (later["verdict"].isin(SIGNAL) & (later["sharpe"].fillna(0) > 0)).any():
            continue
        rows.append({c: getattr(r, c) for c in cols})
    return pd.DataFrame(rows, columns=cols)


def dead_end_families(journal, min_tries: int = 5) -> pd.DataFrame:
    """Families with ``min_tries``+ live tries and nothing WEAK or better (the rule of 07_dead_ends.md)."""
    ex = live_experiments(journal, TRY_PURPOSES)
    cols = ["family", "tries", "regions", "best_sharpe"]
    if ex.empty:
        return pd.DataFrame(columns=cols)
    ex = ex[ex["family"] != ""]
    rows = []
    for fam, g in ex.groupby("family"):
        if len(g) >= min_tries and not g["verdict"].isin(SIGNAL).any():
            rows.append({"family": fam, "tries": len(g), "regions": ", ".join(sorted(g["region"].dropna().unique())),
                         "best_sharpe": None if g["sharpe"].isna().all() else round(float(g["sharpe"].max()), 2)})
    return pd.DataFrame(rows, columns=cols).sort_values("tries", ascending=False).reset_index(drop=True)


def _field_used_elsewhere(ex_other: pd.DataFrame, field: str) -> bool:
    if ex_other.empty:
        return False
    pat = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(field)}(?![A-Za-z0-9_])")
    return bool(ex_other["expression"].fillna("").map(lambda e: bool(pat.search(e))).any())


def scan_candidates(journal) -> pd.DataFrame:
    """Scanned fields whose |Sharpe| clears the scan's noise bar and that no card has used since.

    Each one says: "this field carries information; write the mechanism, or skip it". The bar is recomputed
    from the journal per (dataset, region, universe, delay) scan, exactly as ``Researcher.scan`` does."""
    ex = live_experiments(journal)
    cols = ["dataset", "field", "region", "universe", "delay", "lens", "sharpe", "fitness", "turnover", "noise_bar",
            "n_probes", "expression", "alpha_id", "idea_id"]
    if ex.empty:
        return pd.DataFrame(columns=cols)
    scans = ex[(ex["purpose"] == "scan") & ex["sharpe"].notna()]
    if scans.empty:
        return pd.DataFrame(columns=cols)
    other = ex[ex["purpose"] != "scan"]
    rows = []
    for (fam, reg, uni, dly), g in scans.groupby(["family", "region", "universe", "delay"], dropna=False):
        g = g.drop_duplicates("idea_id", keep="last")
        bar = noise_bar(len(g), g["sharpe"].tolist())
        ds = fam[5:] if str(fam).startswith("lens_") else str(fam)
        for r in g[g["sharpe"].abs() > bar].itertuples(index=False):
            field = str(r.hypothesis_id)[5:] if str(r.hypothesis_id).startswith("LENS_") else str(r.hypothesis_id)
            if _field_used_elsewhere(other, field):
                continue
            rows.append({"dataset": ds, "field": field, "region": reg, "universe": uni, "delay": dly,
                         "lens": r.rung, "sharpe": round(float(r.sharpe), 2),
                         "fitness": None if pd.isna(r.fitness) else round(float(r.fitness), 2),
                         "turnover": None if pd.isna(r.turnover) else round(float(r.turnover), 3),
                         "noise_bar": round(bar, 2), "n_probes": len(g), "expression": r.expression,
                         "alpha_id": r.alpha_id, "idea_id": r.idea_id})
    out = pd.DataFrame(rows, columns=cols)
    if out.empty:
        return out
    out = out.assign(_m=(out["sharpe"].abs() / out["noise_bar"])).sort_values("_m", ascending=False)
    return out.drop(columns="_m").reset_index(drop=True)


def check_failures(journal, min_count: int = 3) -> pd.DataFrame:
    """How often each BRAIN check fails, by region and data category (simulations with a result)."""
    ex = live_experiments(journal, TRY_PURPOSES + ("play",))      # scan probes are crude lenses: left out
    cols = ["region", "category", "check", "failed", "of", "share"]
    if ex.empty:
        return pd.DataFrame(columns=cols)
    ex = ex[ex["status"].isin(["COMPLETE", "WARNING"])]
    if ex.empty:
        return pd.DataFrame(columns=cols)
    ex = ex.assign(category=ex["categories"].replace("", "unknown").str.split(",")).explode("category")
    tot = ex.groupby(["region", "category"]).size()
    f = ex.assign(check=ex["failed"].fillna("").str.split(",")).explode("check")
    f = f[f["check"].fillna("").str.strip() != ""]
    if f.empty:
        return pd.DataFrame(columns=cols)
    g = f.groupby(["region", "category", "check"]).size().rename("failed").reset_index()
    g["of"] = [int(tot.get((r, c), 0)) for r, c in zip(g["region"], g["category"])]
    g["share"] = (g["failed"] / g["of"]).round(2)
    g = g[g["failed"] >= min_count]
    return g.sort_values(["failed", "share"], ascending=False).reset_index(drop=True)[cols]


def transfers(journal, regions: Optional[Iterable[str]] = None) -> pd.DataFrame:
    """Cards at NEAR or PASS in one region and never tried in another: the cheapest next experiments.

    regions: where to look (default: the regions your journal already has results in). Practice (SBX) results
    are never a reason to try a real region."""
    s = idea_summary(journal)
    cols = ["hypothesis_id", "family", "from_region", "best_verdict", "best_sharpe", "to_region"]
    if s.empty:
        return pd.DataFrame(columns=cols)
    s = s[s["idea_id"].map(is_card_idea)]
    s = s[s["region"].fillna("SBX") != "SBX"]              # the practice market is no evidence for a real region
    if s.empty:
        return pd.DataFrame(columns=cols)
    tried = s.groupby("hypothesis_id")["region"].apply(set).to_dict()
    good = s[s["best_verdict"].isin(["PASS", "NEAR"])].sort_values("best_sharpe", ascending=False)
    if regions is None:                                     # default: the regions you already work in
        regions = sorted(s["region"].dropna().unique())
    targets = [r for r in regions if r != "SBX"]
    rows, seen = [], set()
    for r in good.itertuples(index=False):
        for to in targets:
            if to in tried.get(r.hypothesis_id, set()) or (r.hypothesis_id, to) in seen:
                continue
            seen.add((r.hypothesis_id, to))
            rows.append({"hypothesis_id": r.hypothesis_id, "family": r.family, "from_region": r.region,
                         "best_verdict": r.best_verdict, "best_sharpe": round(float(r.best_sharpe), 2),
                         "to_region": to})
    return pd.DataFrame(rows, columns=cols)


def card_adjustments(journal, region: str, budget: Optional[int] = None) -> Dict[str, Tuple[float, str]]:
    """Score changes for the Cards ranking in ``region``, keyed by hypothesis id, plus ``family:<name>`` keys
    for dead-end families. What the journal learned moves cards; it never hides them."""
    adj: Dict[str, Tuple[float, str]] = {}
    try:
        for r in dead_end_families(journal).itertuples(index=False):
            adj[f"family:{r.family}"] = (-2.0, f"dead end: {r.tries} live tries in this family, nothing WEAK or "
                                               "better - only a genuinely new mechanism or dataset")
        s = idea_summary(journal, budget)
        if not s.empty:
            s = s[s["idea_id"].map(is_card_idea)]
            here = s[s["region"] == region]
            for r in here.itertuples(index=False):
                if r.best_verdict in ("NEAR",) or (r.best_verdict == "WEAK" and (r.best_sharpe or 0) >= 1.0):
                    if r.tries_left > 0:
                        adj[r.hypothesis_id] = (0.5, f"near miss here (Sharpe {r.best_sharpe:.2f}): "
                                                     f"{int(r.tries_left)} tries left - one rung or one boost")
            for t in transfers(journal, [region]).itertuples(index=False):
                if t.hypothesis_id not in adj:
                    adj[t.hypothesis_id] = (1.0, f"{t.best_verdict} in {t.from_region} (Sharpe {t.best_sharpe:.2f}) "
                                                 "and untried here - a transfer")
    except Exception:  # noqa: BLE001 - learning is advice; a broken journal never breaks the ranking
        return adj
    return adj


def card_warnings(journal, region: str, categories: Iterable[str], min_share: float = 0.4,
                  min_count: int = 3) -> List[str]:
    """Checks your own results fail often for this region and these data categories (for drafts)."""
    cats = {c for c in categories if c}
    try:
        cf = check_failures(journal, min_count=min_count)
    except Exception:  # noqa: BLE001
        return []
    if cf.empty:
        return []
    cf = cf[(cf["region"] == region) & (cf["category"].isin(cats)) & (cf["share"] >= min_share)]
    return [f"In {r.region} {r.category}, {r.failed} of your {r.of} results failed {r.check} - plan for it"
            for r in cf.itertuples(index=False)]


# ------------------------------------------------------------------------- 1.10.3: the Weekly Reviewer's decisions
_DEAD_DECL = "dead end: stop the family "
_REVIEW_TAG = re.compile(r"^\[(\d{4}-W\d{2}) review\]\s*")


def declared_dead_ends(journal) -> pd.DataFrame:
    """Families the Weekly Reviewer's PLAN declared dead ends (stored as journal lessons by ``apply_plan``), newest
    first, one row per family. Measured dead ends (``dead_end_families``) need 5 tries; these need none."""
    cols = ["family", "week", "date"]
    try:
        rows = journal.db.execute("SELECT created, family, text FROM lessons WHERE text LIKE ? ORDER BY created DESC",
                                  (f"%{_DEAD_DECL}%",)).fetchall()
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=cols)
    out, seen = [], set()
    for created, fam, text in rows:
        fam = (fam or str(text).split(_DEAD_DECL, 1)[-1]).strip()
        if not fam or fam in seen:
            continue
        seen.add(fam)
        m = _REVIEW_TAG.match(str(text))
        out.append({"family": fam, "week": m.group(1) if m else "", "date": pd.to_datetime(created, unit="s").date()})
    return pd.DataFrame(out, columns=cols)


def recent_lessons(journal, n: int = 15) -> pd.DataFrame:
    """The newest lessons (weekly reviews and your own), dead-end declarations left out (see declared_dead_ends)."""
    cols = ["week", "family", "text", "date"]
    try:
        rows = journal.db.execute("SELECT created, family, text FROM lessons WHERE text NOT LIKE ? "
                                  "ORDER BY created DESC LIMIT ?", (f"%{_DEAD_DECL}%", int(n))).fetchall()
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=cols)
    out = []
    for created, fam, text in rows:
        m = _REVIEW_TAG.match(str(text))
        out.append({"week": m.group(1) if m else "", "family": fam or "",
                    "text": _REVIEW_TAG.sub("", str(text)).strip(), "date": pd.to_datetime(created, unit="s").date()})
    return pd.DataFrame(out, columns=cols)

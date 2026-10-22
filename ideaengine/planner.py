"""The weekly layer on top of HYPOLAB's PyramidTracker.

HYPOLAB already knows WHICH Pyramid cells are empty (tracker.plan()). This module decides what to do
THIS week: one region, one or two categories, one dataset to read closely - and measures the week
against the quarter's goals.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Dict, List, Optional

import pandas as pd

from hypolab import config
from hypolab.catalog import CATEGORY_NAMES
from hypolab.pyramids import GUIDE_DATASETS, TIERS

# Starting plan. 1.6.1 (Zacc, 19 Oct): EUR first while the EUR/D1 TOP800 theme runs (12 Oct - 8 Nov, 2x, 3x for Python
# alphas), then USA and GLB - which still cover all five tier-1 categories in both regions (the 10 Pyramids of the
# Expert bar) before December, whose submissions may not count toward Q4 combined performance (G8).
STARTING_PLAN = {
    "2026-W42": ("USA", ["analyst", "fundamental"]),
    "2026-W43": ("EUR", ["analyst", "model"]),
    "2026-W44": ("EUR", ["fundamental", "analyst"]),
    "2026-W45": ("EUR", ["model", "pv", "risk"]),
    "2026-W46": ("USA", ["analyst", "fundamental"]),
    "2026-W47": ("USA", ["pv", "model", "risk"]),
    "2026-W48": ("GLB", ["analyst", "fundamental"]),
    "2026-W49": ("GLB", ["pv", "model", "risk"]),
}

CATEGORY_IDS = [c for t in (1, 2, 3) for c in TIERS[t]]


def category_name(cid: str) -> str:
    return CATEGORY_NAMES.get(cid, cid)


def iso_week(day: Optional[dt.date] = None) -> str:
    y, w, _ = (day or dt.date.today()).isocalendar()
    return f"{y}-W{w:02d}"


def week_start(week: str) -> dt.date:
    y, w = week.split("-W")
    return dt.date.fromisocalendar(int(y), int(w), 1)


def next_week(week: str) -> str:
    return iso_week(week_start(week) + dt.timedelta(days=7))


def quarter_bounds(quarter: str) -> tuple:
    """'2026-Q4' -> (date(2026,10,1), date(2026,12,31))."""
    y, q = quarter.split("-Q")
    y, q = int(y), int(q)
    start = dt.date(y, 3 * (q - 1) + 1, 1)
    end = (dt.date(y + (q == 4), (3 * q) % 12 + 1, 1)) - dt.timedelta(days=1)
    return start, end


def guide_dataset(category: str) -> str:
    """First dataset the Pyramids guide recommends for a category (without the shape note)."""
    for d in GUIDE_DATASETS.get(category, []):
        if not d.upper().startswith("NOT "):
            return d.split(" (")[0].split(" /")[0].strip()
    return ""


def propose(week: str, tracker=None, saved: Optional[dict] = None) -> dict:
    """A plan for `week`: the saved one if any, else the starting plan, else the top empty cells."""
    if saved:
        return saved
    if week in STARTING_PLAN:
        region, cats = STARTING_PLAN[week]
    else:
        region, cats = config.live_region(), ["analyst", "fundamental"]
        if tracker is not None:
            plan = tracker.plan(n=30)
            if not plan.empty:
                region = plan.iloc[0]["region"]
                names = plan[plan["region"] == region]["category"].tolist()[:2]
                rev = {v: k for k, v in CATEGORY_NAMES.items()}
                cats = [rev.get(n, n.lower()) for n in names]
    universe = config.REGION_DEFAULTS.get(region, {}).get("universe", "TOP3000")
    focus = guide_dataset(cats[0]) if cats else ""
    # 1.6.1: a BRAIN theme active that week in this region sets the universe and the dataset to read first
    for t in sorted(themes_in_week(week), key=lambda x: x.get("priority", 9)):
        if t.get("region") == region:
            universe = t.get("universe") or universe
            prio = [d for d in t.get("priority_datasets") or [] if d.get("ai")] or t.get("priority_datasets") or []
            if prio:
                focus = prio[0].get("id") or prio[0].get("name")
            break
    return {"week": week, "region": region, "universe": universe, "delay": 1, "categories": cats,
            "dataset_focus": focus, "card_target": 5,
            "submit_target": DEFAULT_WEEKLY_SUBMISSIONS, "review_note": ""}


# ------------------------------------------------------------------- submissions: daily cap + SuperAlpha unlock
# BRAIN expects up to 4 alphas + 1 SuperAlpha a day. 4 is the CEILING. The default weekly target is 2 a working
# day: it unlocks SuperAlphas in about five weeks while leaving room to submit only what clears the gate
# (combined alpha performance is a Genius bar, so weak filler hurts).
DEFAULT_WEEKLY_SUBMISSIONS = 10
WORKDAYS_PER_WEEK = 5


def _workdays_needed(n: int, per_day: float) -> int:
    return 0 if n <= 0 else math.ceil(n / max(per_day, 1e-9))


def _add_workdays(start: dt.date, n: int) -> dt.date:
    d = start
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def lifetime_submitted(store, journal=None) -> int:
    """The count you entered from BRAIN, plus every alpha submitted through HYPOLAB since (live journal only)."""
    lt = store.lifetime()
    extra, downloaded = 0, 0
    if journal is not None and getattr(journal, "path", None) != ":memory:":
        sub = journal.submissions()
        if not sub.empty:
            # 1.10.0: SuperAlphas do not count toward the 100 alpha submissions that unlock them
            sub = sub[sub["family"].fillna("") != "superalpha"]
            extra = int((sub["submitted"] > lt["since"]).sum())
        # 1.10.1: BRAIN's own count (Account tab download) plus HYPOLAB's submissions since; the larger one wins, so
        # the Week page, the SuperAlpha tab, the DIGEST and the state doc all show the same number
        try:
            from hypolab import account
            last = account.last_sync(journal)
            if last:
                downloaded = int(account.counts(journal)["lifetime_regular"])
                if not sub.empty:
                    downloaded += int((sub["submitted"] > last).sum())
        except Exception:  # noqa: BLE001
            downloaded = 0
    return max(int(lt["base"]) + extra, downloaded)


def submission_status(store, journal=None, today: Optional[dt.date] = None,
                      weekly_target: Optional[int] = None) -> Dict[str, object]:
    """Today's submissions against the daily cap, and the road to the SuperAlpha unlock."""
    st = config.settings()
    cap = int(st.get("max_submissions_per_day", 4))
    unlock = int(store.lifetime()["unlock"] or st.get("superalpha_unlock_after", 100))
    today = today or dt.date.today()
    done_today = journal.submissions_today() if journal is not None else 0
    lifetime = lifetime_submitted(store, journal)
    to_unlock = max(0, unlock - lifetime)
    left_today = max(0, cap - done_today)
    weekly = int(weekly_target or DEFAULT_WEEKLY_SUBMISSIONS)

    def unlock_date(per_day: float) -> Optional[dt.date]:
        if to_unlock == 0:
            return today
        rest = to_unlock - min(left_today, per_day) if today.weekday() < 5 else to_unlock
        return today if rest <= 0 else _add_workdays(today, _workdays_needed(rest, per_day))

    super_today = journal.super_submissions_today() if journal is not None and \
        hasattr(journal, "super_submissions_today") else 0
    return {"cap": cap, "submitted_today": done_today, "left_today": left_today, "lifetime": lifetime,
            "unlock_at": unlock, "to_unlock": to_unlock, "superalpha_unlocked": to_unlock == 0,
            "super_today": super_today, "super_cap": 1,
            "weekly_target": weekly,
            "unlock_at_cap": unlock_date(cap),
            "unlock_at_target": unlock_date(weekly / WORKDAYS_PER_WEEK)}


def submission_summary(status: Dict[str, object]) -> str:
    s = status
    head = (f"**Today:** {s['submitted_today']}/{s['cap']} alphas submitted ({s['left_today']} left). ")
    if s["superalpha_unlocked"]:
        return head + (f"**SuperAlpha: unlocked** - {s.get('super_today', 0)}/{s.get('super_cap', 1)} today; build it "
                       "on the SuperAlpha page from pools of 10+ submitted alphas.")
    fmt = lambda d: d.strftime("%a %d %b") if d else "-"   # noqa: E731
    return (head + f"**SuperAlpha: locked** - {s['lifetime']}/{s['unlock_at']} lifetime alphas, "
            f"{s['to_unlock']} to go. At this week's target ({s['weekly_target']} a week) it unlocks around "
            f"{fmt(s['unlock_at_target'])}; at the full {s['cap']} a day (working days) around "
            f"{fmt(s['unlock_at_cap'])}. The cap is a ceiling: submit only what clears the gate.")


def week_progress(journal, week: str) -> Dict[str, object]:
    """What happened in the journal during one ISO week (simulations, ideas, verdicts)."""
    start = dt.datetime.combine(week_start(week), dt.time())
    end = start + dt.timedelta(days=7)
    sub = journal.submissions()
    submitted = supers = 0
    if not sub.empty:
        wk = sub[(sub["submitted"] >= start.timestamp()) & (sub["submitted"] < end.timestamp())]
        is_super = wk["family"].fillna("") == "superalpha"
        submitted, supers = int((~is_super).sum()), int(is_super.sum())     # 1.10.1: the weekly target is alphas
    ex = journal.experiments()
    if ex.empty:
        return {"simulations": 0, "ideas_tested": 0, "verdicts": {}, "best_sharpe": None, "submitted": submitted,
                "super_submitted": supers}
    ex = ex[(ex["created"] >= start.timestamp()) & (ex["created"] < end.timestamp())]
    return {"simulations": int(len(ex)), "ideas_tested": int(ex["idea_id"].nunique()),
            "verdicts": ex["verdict"].replace("", "-").value_counts().to_dict(),
            "best_sharpe": None if ex["sharpe"].dropna().empty else round(float(ex["sharpe"].max()), 2),
            "submitted": submitted, "super_submitted": supers}


def submissions_in_quarter(journal, quarter: str) -> int:
    start, end = quarter_bounds(quarter)
    sub = journal.submissions()
    if sub.empty:
        return 0
    t0 = dt.datetime.combine(start, dt.time()).timestamp()
    t1 = dt.datetime.combine(end + dt.timedelta(days=1), dt.time()).timestamp()
    return int(((sub["submitted"] >= t0) & (sub["submitted"] < t1)).sum())


def weeks_left(quarter: str, today: Optional[dt.date] = None) -> float:
    _, end = quarter_bounds(quarter)
    return max(0.0, round(((end - (today or dt.date.today())).days + 1) / 7, 1))


def goals_view(store, journal=None, today: Optional[dt.date] = None) -> pd.DataFrame:
    """Goals with the weekly pace needed to reach each bar by the end of the quarter."""
    g = store.goals()
    if g.empty:
        return g
    left = weeks_left(g["quarter"].iloc[0], today)
    g["weeks_left"] = left
    g["per_week_needed"] = (g["still_needed"] / left).round(2) if left else None
    # a pace only makes sense for counts; combined performance is a level, not something you add weekly
    g.loc[g["key"] == "combined_perf", "per_week_needed"] = None
    if journal is not None:
        g["journal_hint"] = ""
        g.loc[g["key"] == "signals", "journal_hint"] = (
            f"{submissions_in_quarter(journal, g['quarter'].iloc[0])} submitted through HYPOLAB this quarter")
    return g


# ------------------------------------------------------------------- phase 4 (1.6.0): the Friday review
def _week_bounds_ts(week: str) -> tuple:
    start = dt.datetime.combine(week_start(week), dt.time())
    return start.timestamp(), (start + dt.timedelta(days=7)).timestamp()


def previous_plan(store, week: str) -> Optional[dict]:
    """The most recent saved plan strictly before `week`."""
    earlier = [w for w in store.weeks_planned() if w < week]
    return store.plan(earlier[-1]) if earlier else None


def near_misses(journal, budget: Optional[int] = None, limit: int = 8) -> pd.DataFrame:
    """Ideas whose best live result is NEAR (or WEAK with Sharpe >= 1.0) and that still have tries left.
    1.7.0: one rule for the whole system - hypolab.learning.near_misses."""
    from hypolab import learning
    cols = ["idea_id", "best_verdict", "best_sharpe", "tries", "tries_left"]
    nm = learning.near_misses(journal, budget)
    if nm.empty:
        return pd.DataFrame(columns=cols)
    nm = nm[~nm["at_budget"]].assign(best_sharpe=lambda d: d["best_sharpe"].astype(float).round(2))
    return nm[cols].head(limit).reset_index(drop=True)


def dead_end_families(journal, min_tries: int = 5) -> List[str]:
    """Families with min_tries+ live explore/boost tries and nothing WEAK or better (same rule as 07_dead_ends)."""
    from hypolab import learning
    try:
        return sorted(learning.dead_end_families(journal, min_tries)["family"].tolist())
    except Exception:  # noqa: BLE001
        return []


def themes_in_week(week: str) -> List[dict]:
    """BRAIN themes active on any day of the week."""
    from hypolab import rules
    seen, out = set(), []
    for i in range(7):
        for t in rules.themes(week_start(week) + dt.timedelta(days=i)):
            if t["name"] not in seen:
                seen.add(t["name"])
                out.append(t)
    return out


def warnings_for(week: str) -> List[str]:
    """Dated warnings the week's plan must respect (Genius G8, the Osmosis lock deadline)."""
    from hypolab import rules
    out = []
    day = week_start(week)
    w = rules.last_month_warning(day + dt.timedelta(days=4))
    if w:
        out.append(w)
    _, q_end = rules.quarter_bounds(day)
    lock = rules.osmosis_lock_deadline(q_end)
    if 0 <= (lock - day).days <= 28:
        out.append(f"Osmosis: the last Sunday to lock a valid allocation for this quarter is {lock:%a %d %b} "
                   "(3+ scopes, each exactly 100,000 points over 10+ alphas).")
    return out


def evidence(journal, store, week: str, tracker=None) -> Dict[str, object]:
    """What the journal, the last PLAN, the Pyramid tracker and the calendar say about `week` (phase 4)."""
    prev = previous_plan(store, week) or {}
    px = prev.get("extra") or {}
    nm = near_misses(journal) if journal is not None else pd.DataFrame()
    retry = list(dict.fromkeys(list(px.get("retry") or []) + nm["idea_id"].tolist()))
    dead = list(dict.fromkeys(list(px.get("dead_ends") or []) + (dead_end_families(journal) if journal is not None
                                                                   else [])))
    cells = []
    if tracker is not None:
        try:
            plan = tracker.plan(n=30)
            if not plan.empty:
                plan = plan.sort_values(["need", "tier"], kind="stable")
                cells = [f"{r.region} D{r.delay} {r.category} ({r.have}/{tracker.k})" for r in plan.head(6).itertuples()]
        except Exception:  # noqa: BLE001
            cells = []
    warns = warnings_for(week)
    try:                                   # 1.8.1: the goals table is per quarter and does not roll over by itself
        q = store.goals()["quarter"].iloc[0]
        d = week_start(week)
        cur = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        if q and q != cur:
            warns.append(f"The quarter goals on the Week page are for {q}, not {cur}: enter this quarter's numbers "
                         "from your Genius page (Update the numbers).")
    except Exception:  # noqa: BLE001
        pass
    return {"retry": retry, "near_misses": nm, "dead_ends": dead, "themes": themes_in_week(week),
            "warnings": warns, "next_cells": cells, "previous_week": prev.get("week")}


def propose_from_evidence(week: str, journal, store, tracker=None) -> dict:
    """propose() plus the evidence in `extra` (retry, dead ends, themes, warnings, next cells). A saved plan is
    returned as saved, its evidence attached under extra['evidence']. Never pushes filler: submit_target stays the
    ceiling-respecting default unless a plan says otherwise."""
    saved = store.plan(week)
    p = propose(week, tracker, saved)
    ev = evidence(journal, store, week, tracker)
    extra = dict(p.get("extra") or {})
    extra["evidence"] = {k: (v.to_dict("records") if isinstance(v, pd.DataFrame) else v) for k, v in ev.items()}
    if not saved:
        extra.setdefault("retry", ev["retry"])
        extra.setdefault("dead_ends", ev["dead_ends"])
    p["extra"] = extra
    return p


def week_pyramid_moves(journal, catalog, week: str) -> pd.DataFrame:
    """Pyramid cells that gained alphas during `week`, from the Account tab download (this quarter's submissions)."""
    from hypolab import account
    cols = ["region", "delay", "category", "added this week", "total this quarter"]
    try:
        df = account.quarter_alphas(journal)
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=cols)
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    t0, t1 = _week_bounds_ts(week)
    sub = pd.to_datetime(df["date_submitted"], utc=True, errors="coerce")
    ts = sub.map(lambda x: x.timestamp() if pd.notna(x) else None)
    total, _ = account.quarter_pyramids(journal, catalog)
    if total.empty:
        return pd.DataFrame(columns=cols)
    in_week = df[(ts >= t0) & (ts < t1)]
    if in_week.empty:
        return pd.DataFrame(columns=cols)
    week_counts, _ = account.quarter_pyramids(journal, catalog, alpha_ids=set(in_week["alpha_id"]))
    if week_counts.empty:
        return pd.DataFrame(columns=cols)
    tot = total.rename(columns={"alphas": "total this quarter"})
    out = week_counts.merge(tot, on=["region", "delay", "category"], how="left").rename(
        columns={"alphas": "added this week"})
    return out[cols].sort_values("added this week", ascending=False).reset_index(drop=True)


def friday_checklist(journal, store, week: str) -> List[dict]:
    """The Friday routine, each step with a done flag where HYPOLAB can tell."""
    from hypolab import account
    t0, t1 = _week_bounds_ts(week)
    synced = account.last_sync(journal) if journal is not None else None
    nxt = next_week(week)
    pack = config.PROJECT_DIR / "claude_projects" / "knowledge" / "INDEX.md"     # 1.10.1: stamped at every rebuild
    pack_ts = pack.stat().st_mtime if pack.exists() else 0
    return [
        {"step": "Download your account (Account page)", "done": bool(synced and synced >= t0),
         "why": "fresh submissions, Pyramid counts and operator usage for the review"},
        {"step": "Update the goal numbers from your Genius page (Week, above)", "done": None,
         "why": "BRAIN's own signals / Pyramids / combined performance"},
        {"step": "Rebuild the knowledge pack (Ideas › Drafts) and re-upload changed files", "done": pack_ts >= t0,
         "why": "the Claude Projects see this week's cards, dead ends and operator usage"},
        {"step": "Copy the DIGEST into the Weekly Reviewer", "done": None, "why": "the honest review of the week"},
        {"step": f"Paste the Reviewer's PLAN (for {nxt})", "done": store.plan(nxt) is not None,
         "why": "saved for its week; lessons and dead ends go to the journal"},
        {"step": "Copy the state text into the HYPOLAB state doc", "done": None,
         "why": "the daily alpha brief reads it, so next week's ideas follow the plan"},
    ]

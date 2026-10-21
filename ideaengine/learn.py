"""The learning loop (phase 5, 1.7.0): what the journal learned, turned into things to do.

``hypolab.learning`` finds the facts (near misses, inverted results, dead ends, scan candidates, check failures,
transfers). This module turns them into:

- **inbox items** (``items``), each with one suggested action, that you can skip or turn into a draft. Skipped and
  drafted items stay hidden (table ``inbox`` in ``ideas.sqlite``) until the evidence behind them changes;
- **drafts**: a sibling of a near miss that used its budget (``sibling_draft``) or a card for a scanned field that
  beat the noise bar (``scan_draft``). Drafts go through the normal checks and need your approval;
- **source quality** (``source_quality``): which source of cards (built-in, the daily brief, your own, inbox,
  lens probes ...) reaches NEAR or PASS within the trial budget - the honest test of whether AI drafts help;
- the **learning digest** (``digest`` / ``digest_json``): ~1-2 KB of counts and top items for the Friday review.

Nothing here simulates, approves or submits.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd

from hypolab import learning
from hypolab import hypotheses as hyp

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inbox (
  key TEXT PRIMARY KEY, kind TEXT, subject TEXT, state TEXT, evidence TEXT, note TEXT DEFAULT '',
  draft_id TEXT DEFAULT '', updated REAL);
"""
KINDS = {
    "near_miss": "Near miss with tries left",
    "sibling": "Near miss at the trial budget",
    "scan": "Scanned field above the noise bar",
    "inverted": "Inverted result",
    "transfer": "Works elsewhere, untried here",
}
ACTIONS = {
    "near_miss": "One rung or one independent boost left: open the card in the Lab.",
    "sibling": "The budget is spent: draft a sibling card that changes ONE thing for an economic reason.",
    "scan": "This field beats luck: write the mechanism as a card, or skip it.",
    "inverted": "Does the reverse mechanism make economic sense? If yes, flip it in the Lab; if not, skip.",
    "transfer": "Try the same card in this region (same rung first).",
}
PRIORITY = {"sibling": 5, "near_miss": 4, "scan": 3, "transfer": 2, "inverted": 1}
STATES = ("new", "skipped", "drafted")


def _ensure(store) -> None:
    store.db.executescript(_SCHEMA)
    store.db.commit()


def _key(kind: str, subject: str, region: str = "") -> str:
    return f"{kind}:{subject}" + (f"@{region}" if region and "@" not in subject else "")


def _evidence_hash(ev: dict) -> str:
    return hashlib.sha1(json.dumps(ev, sort_keys=True, default=str).encode()).hexdigest()[:10]


# ------------------------------------------------------------------------------------------------ inbox
def items(journal, store, regions: Optional[Sequence[str]] = None, show: str = "new",
          budget: Optional[int] = None) -> pd.DataFrame:
    """Everything the journal suggests doing next, most valuable first.

    show: "new" (default; hides skipped/drafted items whose evidence has not changed), or "all"."""
    _ensure(store)
    rows: List[dict] = []
    # 1.8.1: only ideas built from a card in your library can be sent to the Lab or copied as a sibling (lens probes,
    # wild play rolls, re-runs and manual expressions have no card: the Lab could not open them)
    lib = set(hyp_ids())
    for r in learning.near_misses(journal, budget).itertuples(index=False):
        kind = "sibling" if r.at_budget else "near_miss"
        hid = learning.hypothesis_of(r.idea_id)
        if hid not in lib:
            continue
        ev = {"sharpe": r.best_sharpe, "verdict": r.best_verdict, "tries": int(r.tries)}
        rows.append({"kind": kind, "subject": r.idea_id, "region": r.region, "hypothesis_id": hid,
                     "detail": f"{r.best_verdict} at rung '{r.best_rung}': Sharpe {_f(r.best_sharpe)}, fitness "
                               f"{_f(r.best_fitness)}; {int(r.tries)} tries, {int(r.tries_left)} left"
                               + (f"; failed {r.best_failed}" if r.best_failed else ""),
                     "score": abs(r.best_sharpe or 0), "evidence": ev})
    for r in learning.scan_candidates(journal).itertuples(index=False):
        ev = {"sharpe": r.sharpe, "bar": r.noise_bar}
        rows.append({"kind": "scan", "subject": f"{r.dataset}.{r.field}", "region": r.region,
                     "hypothesis_id": f"LENS_{r.field}",
                     "detail": f"{r.field} ({r.dataset}, lens '{r.lens}'): Sharpe {_f(r.sharpe)} vs noise bar "
                               f"{_f(r.noise_bar)} of {r.n_probes} probes"
                               + (" - negative: the opposite sign works" if r.sharpe < 0 else ""),
                     "score": abs(r.sharpe) / max(r.noise_bar, 0.01), "evidence": ev, "_row": r._asdict()})
    for r in learning.inverted(journal).itertuples(index=False):
        hid = learning.hypothesis_of(r.idea_id)
        if hid not in lib:
            continue
        ev = {"sharpe": None if pd.isna(r.sharpe) else round(float(r.sharpe), 2)}
        rows.append({"kind": "inverted", "subject": r.idea_id, "region": r.region, "hypothesis_id": hid,
                     "detail": f"rung '{r.rung}': Sharpe {_f(r.sharpe)} - strongly the wrong way round",
                     "score": abs(r.sharpe or 0), "evidence": ev})
    tr = learning.transfers(journal, regions)
    for r in tr.itertuples(index=False):
        if r.hypothesis_id not in lib:
            continue
        ev = {"from": r.from_region, "sharpe": r.best_sharpe}
        rows.append({"kind": "transfer", "subject": f"{r.hypothesis_id}@{r.to_region}", "region": r.to_region,
                     "hypothesis_id": r.hypothesis_id,
                     "detail": f"{r.best_verdict} in {r.from_region} (Sharpe {_f(r.best_sharpe)}), never tried in "
                               f"{r.to_region}", "score": r.best_sharpe or 0, "evidence": ev})
    cols = ["key", "kind", "what", "subject", "region", "detail", "action", "state", "hypothesis_id", "draft_id"]
    if not rows:
        return pd.DataFrame(columns=cols + ["_evidence", "_row"])
    saved = {k: (s, e, d) for k, s, e, d in store.db.execute("SELECT key, state, evidence, draft_id FROM inbox")}
    out = []
    for r in rows:
        key = _key(r["kind"], r["subject"], r["region"])
        h = _evidence_hash(r["evidence"])
        state, draft_id = "new", ""
        if key in saved:
            s, e, d = saved[key]
            if e == h:                      # same evidence as when you decided: keep your decision
                state, draft_id = s, d or ""
        if show == "new" and state != "new":
            continue
        out.append({"key": key, "kind": r["kind"], "what": KINDS[r["kind"]], "subject": r["subject"],
                    "region": r["region"], "detail": r["detail"], "action": ACTIONS[r["kind"]], "state": state,
                    "hypothesis_id": r["hypothesis_id"], "draft_id": draft_id, "_prio": PRIORITY[r["kind"]],
                    "_score": r["score"], "_evidence": h, "_row": r.get("_row")})
    df = pd.DataFrame(out)
    if df.empty:
        return pd.DataFrame(columns=cols + ["_evidence", "_row"])
    df = df.sort_values(["_prio", "_score"], ascending=False).reset_index(drop=True)
    return df[cols + ["_evidence", "_row"]]


def _set_state(store, key: str, state: str, evidence: str, note: str = "", draft_id: str = "") -> None:
    _ensure(store)
    kind, _, subject = key.partition(":")
    store.db.execute("INSERT OR REPLACE INTO inbox (key, kind, subject, state, evidence, note, draft_id, updated) "
                     "VALUES (?,?,?,?,?,?,?,?)", (key, kind, subject, state, evidence, note, draft_id, time.time()))
    store.db.commit()


def skip(store, item: dict, note: str = "") -> None:
    """Hide an inbox item until its evidence changes (e.g. a new result on the same idea)."""
    _set_state(store, item["key"], "skipped", item.get("_evidence", ""), note)


def reopen(store, key: str) -> None:
    _ensure(store)
    store.db.execute("DELETE FROM inbox WHERE key=?", (key,))
    store.db.commit()


def mark_drafted(store, item: dict, draft_id: str) -> None:
    _set_state(store, item["key"], "drafted", item.get("_evidence", ""), draft_id=draft_id)


def decisions(store) -> pd.DataFrame:
    _ensure(store)
    df = pd.read_sql_query("SELECT key, kind, subject, state, note, draft_id, updated FROM inbox "
                           "ORDER BY updated DESC", store.db)
    if not df.empty:
        df["updated"] = pd.to_datetime(df["updated"], unit="s").dt.strftime("%Y-%m-%d %H:%M")
    return df


# ------------------------------------------------------------------------------------------------ drafts
def _free_id(base: str, taken: Iterable[str]) -> str:
    base = re.sub(r"[^A-Z0-9_]", "_", base.upper()).strip("_")[:40] or "CARD"
    used = set(taken) | set(hyp_ids())
    cid, n = f"IE_{base}", 2
    while cid in used:
        cid, n = f"IE_{base}_{n}", n + 1
    return cid


def hyp_ids() -> List[str]:
    try:
        return [h.id for h in hyp.load_library()]
    except Exception:  # noqa: BLE001
        return []


def sibling_draft(journal, idea_id: str, taken: Iterable[str] = (), budget: Optional[int] = None) -> dict:
    """A new card from a near miss that used its budget: the same card under a new id, with the evidence written
    into the story and watch_out. You change ONE thing (data, mechanism, horizon or the second leg)."""
    from ideaengine import drafts as idea_drafts
    hid = learning.hypothesis_of(idea_id)
    s = learning.idea_summary(journal, budget)
    row = s[s["idea_id"] == idea_id]
    ev = row.iloc[0] if not row.empty else None
    raw = idea_drafts.library_raw()
    if hid not in raw:
        raise KeyError(f"{hid} is not a card in your library - nothing to copy")
    c = copy.deepcopy(raw[hid][0])
    c.pop("beginner", None)
    c["id"] = _free_id(re.sub(r"^IE_", "", hid) + "_SIB", taken)
    c["title"] = f"{c.get('title', hid)} (sibling)"
    if ev is not None:
        note = (f"Sibling of {hid}: its best result in {ev['region']} was {ev['best_verdict']} at rung "
                f"'{ev['best_rung']}' (Sharpe {_f(ev['best_sharpe'])}, fitness {_f(ev['best_fitness'])}"
                + (f", failed {ev['best_failed']}" if ev['best_failed'] else "") + f") after {int(ev['tries'])} "
                "tries. Change ONE thing for an economic reason - other data for the same concept, a different "
                "horizon, a conditioning event, or an independent second leg - and say which here.")
    else:
        note = f"Sibling of {hid}. Change ONE thing for an economic reason and say which here."
    c["story"] = note + "\n\n" + str(c.get("story", "")).strip()
    wo = list(c.get("watch_out") or [])
    wo.insert(0, f"Same family as {hid}: the gate counts this card's tries separately, but production correlation "
                 "with the original is likely - check it before submitting both.")
    c["watch_out"] = wo
    return c


def scan_draft(row: dict, taken: Iterable[str] = ()) -> dict:
    """A card skeleton for a scanned field that beat the noise bar. The story is yours to write: if you can't
    say who is wrong and why, skip the field (a lucky field without a mechanism is the overfitting trap)."""
    from ideaengine import drafts as idea_drafts
    from hypolab.concepts import match_concepts
    field, ds = str(row["field"]), str(row["dataset"])
    expr = str(row.get("expression") or "rank({x})")
    expr = re.sub(rf"vec_avg\(\s*{re.escape(field)}\s*\)", "{x}", expr)
    expr = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(field)}(?![A-Za-z0-9_])", "{x}", expr)
    if (row.get("sharpe") or 0) < 0:
        expr = expr[1:].strip() if expr.startswith("-") else f"reverse({expr})"
    try:
        m = match_concepts(field, "")
        concept = m[0].concept if m else "vendor_score"
    except Exception:  # noqa: BLE001
        concept = "vendor_score"
    c = idea_drafts.template()
    c.update({
        "id": _free_id(f"SCAN_{field}", taken),
        "title": f"{field} ({ds}) - mechanism wanted",
        "family": re.sub(r"[^a-z0-9_]", "_", f"scan_{ds}".lower()),
        "horizon": "medium", "strength": 1, "sign": "-1" if (row.get("sharpe") or 0) < 0 else "+1",
        "story": (f"A scan of {ds} in {row.get('region')} found {field} above the noise bar (Sharpe "
                  f"{_f(row.get('sharpe'))} vs {_f(row.get('noise_bar'))} for {row.get('n_probes')} probes). "
                  "Write here who makes the mistake, why prices adjust slowly, and why this field measures it. "
                  "If you can't, skip the field."),
        "why_persists": "",
        "references": [],
        "roles": {"x": {"concept": concept, "note": f"field {field} in {ds}; check the concept fits"}},
        "ladder": [{"name": "core", "expr": expr, "teaches": "the scan's probe, now with a stated mechanism"}],
        "expected_turnover": [0.02, 0.3],
        "watch_out": [f"Picked from a scan of {row.get('n_probes')} fields: the gate deflates the Sharpe for that "
                      "selection, so it needs to be clearly above the bar.",
                      "Check the direction in the field's description before the first simulation."],
    })
    if concept not in _concepts():
        c["roles"]["x"]["concept"] = "vendor_score"
    return c


def _concepts():
    from hypolab.concepts import CONCEPTS
    return CONCEPTS


# --------------------------------------------------------------------------------------------- source quality
def _bucket(hypothesis_id: str, idea_id: str, lib_source: Dict[str, str], draft_source: Dict[str, str]) -> str:
    if idea_id.startswith("play:"):
        return "play rolls"
    if idea_id.startswith("rerun:"):
        return "re-runs"
    if hypothesis_id.startswith("LENS_"):
        return "lens probes"
    src = lib_source.get(hypothesis_id)
    if src == "library":
        return "built-in cards"
    d = (draft_source.get(hypothesis_id) or "").lower()
    m = re.search(r"\bs-(osap|arxiv|news|dataset|manual)-", d)      # 1.9.0: the collectors' SOURCE ids
    if m:
        kind = "outside: " + {"osap": "published predictors (OSAP)", "arxiv": "arXiv papers", "news": "news themes",
                              "dataset": "under-used datasets", "manual": "sources you added"}[m.group(1)]
        # 1.10.3: `# from: daily brief <date> via S-...` keeps the writer visible next to the source
        return f"daily brief + {kind}" if "daily brief" in d else kind
    if "daily brief" in d:
        return "daily brief"
    if d.startswith("inbox"):
        return "inbox (learning loop)"
    if d.startswith("copy of"):
        return "your copies"
    if re.search(r"\bb-\d{8}|scout|writer", d):
        return "Scout & Writer"
    if src == "mine" or hypothesis_id.startswith("IE_"):
        return "your own cards"
    return "other"


def source_quality(journal, store=None, budget: Optional[int] = None) -> pd.DataFrame:
    """Per source of cards: ideas tried, how many reached NEAR or PASS within the trial budget, submitted."""
    b = learning._budget(budget)
    ex = learning.live_experiments(journal, learning.TRY_PURPOSES + ("play",))
    cols = ["source", "ideas_tried", "near_or_pass", "rate", "pass", "submitted", "tries"]
    if ex.empty:
        return pd.DataFrame(columns=cols)
    try:
        lib_source = {h.id: h.source for h in hyp.load_library()}
    except Exception:  # noqa: BLE001
        lib_source = {}
    draft_source = {}
    if store is not None:
        try:
            draft_source = {i: s or "" for i, s in store.db.execute("SELECT id, source FROM drafts")}
        except Exception:  # noqa: BLE001
            draft_source = {}
    ex = ex.assign(_n=ex.groupby("idea_id").cumcount() + 1)
    within = ex[ex["_n"] <= b]
    subs = set()
    try:
        subs = {r[0] for r in journal.db.execute("SELECT idea_id FROM submissions")}
    except Exception:  # noqa: BLE001
        pass
    rows = []
    for idea, g in within.groupby("idea_id"):
        hid = str(g["hypothesis_id"].iloc[0])
        rows.append({"source": _bucket(hid, str(idea), lib_source, draft_source),
                     "hit": bool(g["verdict"].isin(["NEAR", "PASS"]).any()), "pass": bool((g["verdict"] == "PASS").any()),
                     "sub": idea in subs, "tries": int(len(ex[ex["idea_id"] == idea]))})
    d = pd.DataFrame(rows)
    out = d.groupby("source").agg(ideas_tried=("hit", "size"), near_or_pass=("hit", "sum"), **{"pass": ("pass", "sum")},
                                  submitted=("sub", "sum"), tries=("tries", "sum")).reset_index()
    out["rate"] = (out["near_or_pass"] / out["ideas_tried"]).round(2)
    return out.sort_values(["rate", "ideas_tried"], ascending=False).reset_index(drop=True)[cols]


def critic_calibration(journal, store, budget: Optional[int] = None) -> pd.DataFrame:
    """1.10.3: is the Critic right? Per latest Critic decision on a draft (keep / rewrite / bin, or no verdict): how
    many of those cards were tested live and how many reached NEAR or PASS within the trial budget. A card the Critic
    binned is only measured if you approved and tested it anyway - do that now and then, or its misses stay invisible."""
    cols = ["decision", "cards", "tested", "near_or_pass", "rate", "avg_scores"]
    if store is None:
        return pd.DataFrame(columns=cols)
    try:
        drafts_rows = store.db.execute("SELECT id, decision FROM drafts").fetchall()
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=cols)
    latest, scores = {i: (d or "") for i, d in drafts_rows}, {}
    try:
        for did, dec, sc in store.db.execute("SELECT draft_id, decision, scores FROM verdicts ORDER BY n"):
            latest[did] = dec                   # the last verdict wins, even after a rewrite cleared the draft's copy
            try:
                scores[did] = {k: float(v) for k, v in (json.loads(sc or "{}") or {}).items()
                               if isinstance(v, (int, float))}
            except (ValueError, TypeError):
                pass
    except Exception:  # noqa: BLE001
        pass
    if not latest:
        return pd.DataFrame(columns=cols)
    b = learning._budget(budget)
    ex = learning.live_experiments(journal, learning.TRY_PURPOSES)
    hit, tested = {}, set()
    if not ex.empty:
        ex = ex.assign(_n=ex.groupby("idea_id").cumcount() + 1)
        for idea, g in ex[ex["_n"] <= b].groupby("idea_id"):
            hid = str(g["hypothesis_id"].iloc[0])
            if hid in latest:
                tested.add(hid)
                hit[hid] = hit.get(hid, False) or bool(g["verdict"].isin(["NEAR", "PASS"]).any())
    rows = []
    for dec in ("keep", "rewrite", "bin", ""):
        ids = [i for i, d in latest.items() if (d or "") == dec]
        if not ids:
            continue
        t = [i for i in ids if i in tested]
        n_hit = sum(1 for i in t if hit.get(i))
        sc = pd.DataFrame([scores[i] for i in ids if i in scores])
        avg = ", ".join(f"{k} {v:.1f}" for k, v in sc.mean().items()) if not sc.empty else ""
        rows.append({"decision": dec or "no verdict", "cards": len(ids), "tested": len(t), "near_or_pass": n_hit,
                     "rate": round(n_hit / len(t), 2) if t else None, "avg_scores": avg})
    return pd.DataFrame(rows, columns=cols)


# ------------------------------------------------------------------------------------------------ digest
def digest(journal, store=None, since: Optional[float] = None, until: Optional[float] = None,
           budget: Optional[int] = None, top: int = 5) -> dict:
    """Counts, rates and the top items of the learning loop (what the Weekly Reviewer reads; ~1-2 KB)."""
    ex = learning.live_experiments(journal)
    if since is not None and not ex.empty:
        ex = ex[ex["created"] >= since]
    if until is not None and not ex.empty:
        ex = ex[ex["created"] < until]
    out: Dict[str, object] = {"sims": int(len(ex))}
    if not ex.empty:
        out["verdicts"] = {k: int(v) for k, v in ex["verdict"].replace("", "-").value_counts().items()}
    nm = learning.near_misses(journal, budget)
    out["near_misses"] = [f"{r.idea_id} {r.best_verdict} {_f(r.best_sharpe)} ({int(r.tries_left)} left)"
                          for r in nm.head(top).itertuples(index=False)]
    sc = learning.scan_candidates(journal)
    out["scan_candidates"] = [f"{r.region} {r.dataset}.{r.field} {_f(r.sharpe)} (bar {_f(r.noise_bar)})"
                              for r in sc.head(top).itertuples(index=False)]
    inv = learning.inverted(journal)
    out["inverted"] = [f"{r.idea_id} {_f(r.sharpe)}" for r in inv.head(top).itertuples(index=False)]
    de = learning.dead_end_families(journal)
    out["dead_ends"] = [f"{r.family} ({r.tries} tries)" for r in de.head(top).itertuples(index=False)]
    tr = learning.transfers(journal)
    out["transfers"] = [f"{r.hypothesis_id} {r.from_region}->{r.to_region} {_f(r.best_sharpe)}"
                        for r in tr.head(top).itertuples(index=False)]
    try:                                             # production correlation you measured, per family (decorr)
        from hypolab.decorr import family_prod_corr
        fp = family_prod_corr(journal)
        out["crowded_families"] = [f"{k} median {v['median']:.2f} (n={v['n']})" for k, v in
                                   sorted(fp.items(), key=lambda kv: -kv[1]["median"]) if v["median"] >= 0.7][:top]
    except Exception:  # noqa: BLE001
        out["crowded_families"] = []
    cf = learning.check_failures(journal)
    out["check_failures"] = [f"{r.region} {r.category} {r.check} {r.failed}/{r.of}"
                             for r in cf.head(top).itertuples(index=False)]
    sq = source_quality(journal, store, budget)
    out["source_quality"] = [f"{r.source}: {int(r.near_or_pass)}/{int(r.ideas_tried)} NEAR+ ({r.rate:.0%}), "
                             f"{int(r.submitted)} submitted" for r in sq.itertuples(index=False)]
    try:                                             # 1.10.3: the Critic measured against results
        cc = critic_calibration(journal, store, budget)
        out["critic_calibration"] = [f"{r.decision}: {r.cards} cards, {r.tested} tested, {r.near_or_pass} NEAR+"
                                     for r in cc.itertuples(index=False)]
    except Exception:  # noqa: BLE001
        out["critic_calibration"] = []
    try:
        les = journal.db.execute("SELECT text FROM lessons ORDER BY created DESC LIMIT ?", (top,)).fetchall()
        out["lessons"] = [t[0][:160] for t in les]
    except Exception:  # noqa: BLE001
        out["lessons"] = []
    if store is not None:
        try:
            _ensure(store)
            st = dict(store.db.execute("SELECT state, COUNT(*) FROM inbox GROUP BY state").fetchall())
            out["inbox_decisions"] = {k: int(v) for k, v in st.items()}
        except Exception:  # noqa: BLE001
            pass
        try:                                         # 1.9.0: outside sources (collectors)
            from ideaengine import sources
            out["outside_sources"] = sources.digest(store)["sources"]
        except Exception:  # noqa: BLE001
            pass
    return out


def digest_json(journal, store=None, since=None, until=None, max_bytes: int = 2200) -> str:
    """The digest as compact JSON, trimmed (fewest items dropped first from the longest lists) to max_bytes."""
    d = digest(journal, store, since, until)
    s = json.dumps(d, separators=(",", ":"))
    while len(s.encode()) > max_bytes:
        lists = [(k, v) for k, v in d.items() if isinstance(v, list) and v]
        if not lists:
            break
        k, v = max(lists, key=lambda kv: len(json.dumps(kv[1])))
        d[k] = v[:-1]
        s = json.dumps(d, separators=(",", ":"))
    return s


def _f(x, nd: int = 2) -> str:
    try:
        if x is None or pd.isna(x):
            return "-"
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return str(x)

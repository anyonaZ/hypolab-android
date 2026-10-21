"""Phase 7 (1.9.0): the inbox of outside sources - stored, ranked, and turned into work.

The collectors (``ideaengine.collectors``) read Open Source Asset Pricing, arXiv, news RSS and your own field lists
into ``SourceItem``s. This module keeps them in ``ideas.sqlite`` (table ``sources``, one row per item, your
decision kept when the same item is collected again), tags each with the HYPOLAB concepts and BRAIN data categories
it mentions, notes when one of your cards already cites the same paper, ranks them for this week's plan, and offers
two actions - the same split as everywhere else in HYPOLAB (decision 1: HYPOLAB never calls an AI):

* **Copy for Scout & Writer** (``writer_message``): a SOURCE block for the Scout & Writer project, which finds the
  mechanism and writes the card. Its cards come back with ``# from: S-<kind>-<key>``, so Source quality measures
  outside sources separately from the built-in cards and the daily brief.
* **Make a draft** (``source_draft``): a card skeleton with the source as its reference and the concepts as roles;
  the story, ``why_persists`` and rung 1 are yours to write (the checks keep it a draft until you do) - a source never
  becomes a card without a written mechanism.

Most items should produce no card; skipping is the normal outcome.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import time
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd

from hypolab import hypotheses as hyp
from hypolab.concepts import CONCEPTS
from ideaengine.collectors import OSAP_CITE, SourceItem

KINDS = {"osap": "Published predictor (Open Source Asset Pricing)", "arxiv": "New paper (arXiv q-fin)",
         "news": "News theme (many firms)", "dataset": "Under-used dataset", "manual": "Added by hand"}
KIND_SHORT = {"osap": "OSAP", "arxiv": "arXiv", "news": "news", "dataset": "dataset", "manual": "by hand"}
STATES = ("new", "skipped", "drafted")
COLLECTORS = ("osap", "arxiv", "news", "datasets")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, kind TEXT, title TEXT, summary TEXT, url TEXT, authors TEXT, year INTEGER,
  published TEXT, first_seen REAL, last_seen REAL, concepts TEXT DEFAULT '[]', categories TEXT DEFAULT '[]',
  covered_by TEXT DEFAULT '[]', score REAL, state TEXT DEFAULT 'new', note TEXT DEFAULT '', draft_id TEXT DEFAULT '',
  extra TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS collector_runs (
  kind TEXT, ran REAL, found INTEGER, added INTEGER, error TEXT DEFAULT '', origin TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS sources_meta (key TEXT PRIMARY KEY, value TEXT);
"""

NEWS_FRESH_DAYS = 14        # 1.9.1: a news theme older than this leaves the "new" list (it stays under "all")
DATASET_USED_NOTE = "used in your journal since it was collected"

# Concepts whose patterns fire on almost any finance abstract ("expected return", "signal", "peer"): not used to tag
# free text (they still bind fields as usual).
TEXT_SKIP = {"vendor_score", "predicted_return", "relationship_group", "returns", "close", "open", "high", "low",
             "vwap", "volume", "adv", "cap", "sharesout",
             # vendor-score concepts: "quality", "valuation" or "momentum" in prose names the idea, not a model dataset
             "value_score", "quality_score", "momentum_score", "revision_score", "dividend_score"}

# Concept -> the BRAIN data category its fields usually come from (a hint for the plan, never a binding).
CONCEPT_CATEGORY = {
    **{c: "pv" for c in ("returns", "close", "open", "high", "low", "vwap", "volume", "adv", "cap", "sharesout")},
    **{c: "risk" for c in ("specific_return", "beta", "volatility", "specific_risk", "credit_risk")},
    **{c: "fundamental" for c in ("sales", "cogs", "gross_profit", "operating_income", "ebitda", "net_income", "eps",
                                  "cfo", "capex", "fcf", "assets", "liabilities", "debt", "equity", "bvps",
                                  "current_assets", "current_liabilities", "inventory", "receivables", "rnd", "sga",
                                  "dividend", "enterprise_value", "roe", "roa", "pretax_income", "income_tax")},
    **{c: "analyst" for c in ("est_eps", "est_sales", "est_ltg", "est_dispersion", "num_estimates", "rev_up",
                              "rev_down", "recommendation", "target_price")},
    **{c: "earnings" for c in ("surprise", "call_tone", "guidance", "earnings_date")},
    **{c: "sentiment" for c in ("sentiment", "sentiment_pos", "sentiment_neg", "sentiment_dispersion")},
    "news_volume": "news", "short_interest": "shortinterest",
    **{c: "institutions" for c in ("inst_ownership", "inst_buyers", "inst_sellers", "inst_holders")},
    "insider_buy": "insiders", "insider_sell": "insiders",
    **{c: "option" for c in ("implied_vol", "implied_vol_call", "implied_vol_put", "iv_skew", "put_call")},
    "realized_vol": "pv",
    **{c: "model" for c in ("value_score", "quality_score", "momentum_score", "revision_score", "dividend_score",
                            "predicted_return", "vendor_score")},
    "esg_score": "other", "credit_spread": "risk", "management_change": "other", "order_imbalance": "imbalance",
    "relationship_group": "other", "macro_series": "macro", "rate_sensitivity": "macro",
}


def ensure(store) -> None:
    store.db.executescript(_SCHEMA)
    store.db.commit()


# ------------------------------------------------------------------------------------------------- tagging
def text_concepts(text: str, limit: int = 4) -> List[str]:
    """HYPOLAB concepts a piece of prose mentions, strongest first (heuristic, shown as 'mentions')."""
    t = " ".join(str(text or "").lower().split())
    if not t:
        return []
    hits = []
    for name, c in CONCEPTS.items():
        if name in TEXT_SKIP:
            continue
        s, _ = c.match_text("", t)
        if s > 0:
            hits.append((s, name))
    hits.sort(key=lambda x: -x[0])
    return [n for _, n in hits[:limit]]


def _refs(library) -> List[tuple]:
    out = []
    for h in library:
        for ref in h.references or []:
            out.append((h.id, str(ref)))
    return out


def _surnames(authors: str) -> List[str]:
    """'Cooper, Gulen and Schill' -> ['cooper', 'gulen', 'schill']; 'Ang et al.' -> ['ang']."""
    parts = re.split(r",|\band\b|&|\bet al\b\.?", str(authors or ""))
    return [p.split()[-1].lower().strip(".") for p in parts if p.strip() and p.split()]


_REF = re.compile(r"^\s*(?P<authors>[^()]{2,120}?)\s*\((?P<year>\d{4})\)")


def covered_by(item: SourceItem, library=None) -> List[str]:
    """Cards in your library that cite the same paper: same first author, same second author when both name one,
    same year (card references are written 'Author, Author & Author (Year) Title')."""
    if item.kind not in ("osap", "arxiv", "manual") or not item.year or not item.authors:
        return []
    mine = _surnames(item.authors)
    if not mine or len(mine[0]) < 3:
        return []
    lib = library if library is not None else _library()
    out = set()
    for cid, ref in _refs(lib):
        m = _REF.match(ref)
        if not m or int(m.group("year")) != int(item.year):
            continue
        theirs = _surnames(m.group("authors"))
        if not theirs or theirs[0] != mine[0]:
            continue
        if len(mine) > 1 and len(theirs) > 1 and mine[1] != theirs[1]:
            continue
        out.add(cid)
    return sorted(out)


def _library():
    try:
        return hyp.load_library()
    except Exception:  # noqa: BLE001
        return []


def _library_sig(library) -> str:
    return hashlib.sha1(json.dumps(_refs(library)).encode()).hexdigest()[:16]


def refresh_covered(store, library=None) -> int:
    """1.9.1: recompute "same paper as" for papers when your library changed since the last look (a card you approved
    later now covers its paper). Cheap when nothing changed. Returns the number of items whose answer changed."""
    ensure(store)
    lib = library if library is not None else _library()
    sig = _library_sig(lib)
    row = store.db.execute("SELECT value FROM sources_meta WHERE key='library_sig'").fetchone()
    if row and row[0] == sig:
        return 0
    changed = 0
    for sid, kind, title, authors, year, cov, score in store.db.execute(
            "SELECT id, kind, title, authors, year, covered_by, score FROM sources "
            "WHERE kind IN ('osap','arxiv','manual')").fetchall():
        y = _f(year)
        new = covered_by(SourceItem(id=sid, kind=kind, title=title or "", authors=authors or "",
                                    year=int(y) if y else None), lib)
        try:
            old = json.loads(cov or "[]")
        except ValueError:
            old = []
        if new != old:
            sc = (score or 0.0) + (1.5 if old else 0.0) - (1.5 if new else 0.0)
            store.db.execute("UPDATE sources SET covered_by=?, score=? WHERE id=?", (json.dumps(new), round(sc, 3), sid))
            changed += 1
    store.db.execute("INSERT OR REPLACE INTO sources_meta VALUES ('library_sig', ?)", (sig,))
    store.db.commit()
    return changed


def tag(item: SourceItem, library=None) -> dict:
    """concepts, categories and covered_by for an item."""
    ex = item.extra or {}
    if item.kind == "news":
        concepts = list(ex.get("concepts") or [])
    elif item.kind == "dataset":
        concepts = []
    else:
        concepts = text_concepts(f"{item.title}. {item.summary}")
    cats = [ex["category"]] if ex.get("category") else []
    for c in concepts:
        k = CONCEPT_CATEGORY.get(c)
        if k and k not in cats:
            cats.append(k)
    return {"concepts": concepts, "categories": cats[:3], "covered_by": covered_by(item, library)}


def base_score(item: SourceItem, tags: dict) -> float:
    """How promising an item is before this week's plan is known (higher first)."""
    ex = item.extra or {}
    s = 0.3 * min(len(tags["concepts"]), 4)
    if item.kind == "osap":
        s += 1.0 + min(_f(ex.get("t_stat")) or 0.0, 8.0) / 4.0
        s += {"1_clear": 0.5, "2_likely": 0.2}.get(str(ex.get("predictability")), -0.5)
        s += {"1_good": 0.3, "2_fair": 0.1}.get(str(ex.get("replication")), 0.0)
    elif item.kind == "arxiv":
        s += 0.5 + 0.25 * min(_f(ex.get("relevance")) or 0.0, 6.0)
    elif item.kind == "news":
        s += 0.5 + math.log1p(int(ex.get("count") or 0))
    elif item.kind == "dataset":
        vs = _f(ex.get("value_score")) or 0.0
        ac = _f(ex.get("alpha_count"))
        s += 0.6 * vs - (0.25 * math.log10(1 + ac) if ac is not None else 0.0) + (1.0 if ex.get("theme") else 0.0)
    elif item.kind == "manual":
        s += 2.0                                         # you chose it: it comes first
    if tags["covered_by"]:
        s -= 1.5
    return round(s, 3)


def _f(x) -> Optional[float]:
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------ the store
def upsert(store, items: Iterable[SourceItem], origin: str = "", library=None) -> Dict[str, int]:
    """Add new items and refresh the ones seen before. Your decision (skipped / drafted, note, draft) is kept."""
    ensure(store)
    lib = library if library is not None else _library()
    now = time.time()
    have = {r[0] for r in store.db.execute("SELECT id FROM sources")}
    found = added = 0
    for it in items:
        found += 1
        if it.kind == "news" and it.id in have:
            it = _merge_news(store, it)
        tags = tag(it, lib)
        vals = (it.kind, it.title, it.summary, it.url, it.authors, it.year, it.published, now,
                json.dumps(tags["concepts"]), json.dumps(tags["categories"]), json.dumps(tags["covered_by"]),
                base_score(it, tags), json.dumps(it.extra, default=str))
        if it.id in have:
            store.db.execute("UPDATE sources SET kind=?, title=?, summary=?, url=?, authors=?, year=?, published=?, "
                             "last_seen=?, concepts=?, categories=?, covered_by=?, score=?, extra=? WHERE id=?",
                             vals + (it.id,))
        else:
            store.db.execute("INSERT INTO sources (kind, title, summary, url, authors, year, published, last_seen, "
                             "concepts, categories, covered_by, score, extra, id, first_seen, state) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'new')", vals + (it.id, now))
            have.add(it.id)
            added += 1
    store.db.execute("INSERT OR REPLACE INTO sources_meta VALUES ('library_sig', ?)", (_library_sig(lib),))
    store.db.commit()
    return {"found": found, "added": added}


def _merge_news(store, it: SourceItem) -> SourceItem:
    """A news theme collected again in the same week keeps the headlines it already had (feeds only show the last
    few dozen items, so each fetch sees a different slice of the week)."""
    from ideaengine.collectors import NEWS_THEMES, _short
    old = get(store, it.id) or {}
    heads = {}
    for h in list((old.get("extra") or {}).get("headlines") or []) + list(it.extra.get("headlines") or []):
        heads.setdefault(h.get("link") or h.get("title"), h)
    hs = sorted(heads.values(), key=lambda h: h.get("date") or "", reverse=True)
    th = next((t for t in NEWS_THEMES if t.key == it.extra.get("theme")), None)
    label = th.label if th else it.extra.get("theme")
    extra = dict(it.extra, headlines=hs[:30], count=len(hs))
    week = extra.get("week")
    return SourceItem(id=it.id, kind="news", title=f"{label}: {len(hs)} headline{'s' * (len(hs) != 1)} in {week}",
                      summary=_short(f"{extra.get('idea', '')} Headlines: " + "; ".join(h['title'] for h in hs[:5])),
                      url=hs[0].get("link") if hs else it.url, published=max(it.published or "", old.get("published") or ""),
                      extra=extra)


def log_run(store, kind: str, found: int = 0, added: int = 0, error: str = "", origin: str = "") -> None:
    ensure(store)
    store.db.execute("INSERT INTO collector_runs VALUES (?,?,?,?,?,?)",
                     (kind, time.time(), int(found), int(added), error[:500], origin[:200]))
    store.db.commit()


def last_runs(store) -> Dict[str, dict]:
    ensure(store)
    out = {}
    for kind, ran, found, added, err, origin in store.db.execute(
            "SELECT kind, ran, found, added, error, origin FROM collector_runs ORDER BY ran"):
        out[kind] = {"ran": ran, "found": found, "added": added, "error": err, "origin": origin,
                     "when": time.strftime("%d %b %H:%M", time.localtime(ran)),
                     "days_ago": round((time.time() - ran) / 86400, 1)}
    return out


def get(store, sid: str) -> Optional[dict]:
    ensure(store)
    cur = store.db.execute("SELECT * FROM sources WHERE id=?", (sid,))
    row = cur.fetchone()
    return None if row is None else _row(dict(zip([c[0] for c in cur.description], row)))


def _row(d: dict) -> dict:
    for k in ("concepts", "categories", "covered_by"):
        try:
            d[k] = json.loads(d.get(k) or "[]")
        except ValueError:
            d[k] = []
    try:
        d["extra"] = json.loads(d.get("extra") or "{}")
    except ValueError:
        d["extra"] = {}
    y = _f(d.get("year"))
    d["year"] = int(y) if y else None
    d["what"] = KINDS.get(d["kind"], d["kind"])
    d["tag"] = source_tag(d)
    return d


def source_tag(d) -> str:
    """The id Scout & Writer writes after `# from:` - S-<kind>-<key> (short, no spaces)."""
    sid = d["id"] if isinstance(d, dict) else d
    kind, _, key = str(sid).partition(":")
    key = re.sub(r"[^A-Za-z0-9._-]+", "-", key.replace(":", "-")).strip("-")
    return f"S-{kind}-{key}"


def _news_age_days(r: dict, today: dt.date) -> int:
    pub = str(r.get("published") or "")[:10]
    try:
        d = dt.date.fromisoformat(pub)
    except ValueError:
        d = dt.date.fromtimestamp(r.get("first_seen") or r.get("last_seen") or time.time())
    return (today - d).days


def news_listed(r: dict, show: str = "new", min_news: int = 2, today: Optional[dt.date] = None,
                muted: Optional[Iterable[str]] = None) -> bool:
    """Whether a news theme shows: >= min_news headlines in its week; on the "new" list also not older than
    NEWS_FRESH_DAYS and not a muted theme (1.9.1)."""
    ex = r.get("extra") or {}
    if min_news and int(ex.get("count") or 0) < min_news:
        return False
    if show == "new":
        from ideaengine.collectors import muted_themes
        if ex.get("theme") in set(muted_themes() if muted is None else muted):
            return False
        if _news_age_days(r, today or dt.date.today()) > NEWS_FRESH_DAYS:
            return False
    return True


def _balance(rows: List[dict]) -> List[dict]:
    """1.9.1: best of each kind first, then the second of each kind, ... (relevance decides inside a round). Without
    it the 212 published predictors filled every top slot and a new paper ranked about 145th."""
    seen: Dict[str, int] = {}
    for r in rows:                                   # rows arrive best first
        r["_round"] = seen.get(r["kind"], 0)
        seen[r["kind"]] = r["_round"] + 1
    rows.sort(key=lambda r: (r["_round"], -r["relevance"], -(r["last_seen"] or 0)))
    for r in rows:
        r.pop("_round", None)
    return rows


def items(store, kinds: Optional[Sequence[str]] = None, show: str = "new", plan: Optional[dict] = None,
          limit: int = 40, offset: int = 0, query: str = "", min_news: int = 2, balance: bool = True,
          today: Optional[dt.date] = None) -> pd.DataFrame:
    """Source items, best first for this week's plan (its categories add +2.0, its region +0.5 for datasets).

    show: "new" (default), "all", "skipped" or "drafted". A news theme needs `min_news` headlines in its week to be
    listed: one headline is one company's story, not a pattern; on "new" it also leaves after NEWS_FRESH_DAYS and
    when its theme is muted. balance: mix the kinds (the best of each first) when more than one kind is listed."""
    ensure(store)
    q, args = "SELECT * FROM sources WHERE 1=1", []
    if kinds:
        q += f" AND kind IN ({','.join('?' * len(kinds))})"
        args += list(kinds)
    if show in STATES:
        q += " AND state=?"
        args.append(show)
    if query:
        q += " AND (title LIKE ? OR summary LIKE ? OR authors LIKE ?)"
        args += [f"%{query}%"] * 3
    cur = store.db.execute(q, args)
    cols = [c[0] for c in cur.description]
    rows = [_row(dict(zip(cols, r))) for r in cur.fetchall()]
    if any(r["kind"] == "news" for r in rows):
        from ideaengine.collectors import muted_themes
        muted = muted_themes()
        rows = [r for r in rows if r["kind"] != "news" or news_listed(r, show, min_news, today, muted)]
    cats = set((plan or {}).get("categories") or [])
    region = (plan or {}).get("region")
    for r in rows:
        bonus, why = 0.0, []
        if cats and set(r["categories"]) & cats:
            bonus += 2.0
            why.append("fits this week's categories")
        if r["kind"] == "dataset" and region and r["extra"].get("region") == region:
            bonus += 0.5
            why.append(f"in this week's region {region}")
        r["relevance"] = round((r["score"] or 0) + bonus, 2)
        r["plan_note"] = "; ".join(why)
    rows.sort(key=lambda r: (-r["relevance"], -(r["last_seen"] or 0)))
    if balance and (not kinds or len(kinds) > 1):
        rows = _balance(rows)
    df = pd.DataFrame(rows[offset: offset + limit] if limit else rows[offset:])
    df.attrs["total"] = len(rows)
    return df


def _news_rows(store, state: Optional[str] = None) -> List[dict]:
    q = "SELECT state, published, first_seen, last_seen, extra FROM sources WHERE kind='news'"
    args: list = []
    if state:
        q += " AND state=?"
        args.append(state)
    out = []
    for st, pub, fs, ls, ex in store.db.execute(q, args):
        try:
            e = json.loads(ex or "{}")
        except ValueError:
            e = {}
        out.append({"state": st, "published": pub, "first_seen": fs, "last_seen": ls, "extra": e})
    return out


def counts(store, today: Optional[dt.date] = None) -> Dict[str, Dict[str, int]]:
    """{kind: {state: n}}, counted the way the list shows them (1.9.1: news themes the list hides - one headline,
    stale, muted - are not counted)."""
    ensure(store)
    out: Dict[str, Dict[str, int]] = {}
    for kind, state, n in store.db.execute("SELECT kind, state, COUNT(*) FROM sources WHERE kind != 'news' "
                                           "GROUP BY kind, state"):
        out.setdefault(kind, {})[state] = int(n)
    from ideaengine.collectors import muted_themes
    muted = muted_themes()
    for r in _news_rows(store):
        if news_listed(r, r["state"], 2, today, muted):
            d = out.setdefault("news", {})
            d[r["state"]] = d.get(r["state"], 0) + 1
    return out


def new_count(store, today: Optional[dt.date] = None) -> int:
    """New items as the list shows them, for the menu badge. 1.9.1: a count in the database (it built and decoded the
    whole list on every page view); only news rows are read, to apply the list's rules."""
    try:
        ensure(store)
        n = store.db.execute("SELECT COUNT(*) FROM sources WHERE state='new' AND kind != 'news'").fetchone()[0]
        from ideaengine.collectors import muted_themes
        muted = muted_themes()
        return int(n) + sum(1 for r in _news_rows(store, "new") if news_listed(r, "new", 2, today, muted))
    except Exception:  # noqa: BLE001
        return 0


def set_state(store, sid: str, state: str, note: str = "", draft_id: str = "") -> None:
    if state not in STATES:
        raise ValueError(f"unknown state {state!r}")
    ensure(store)
    store.db.execute("UPDATE sources SET state=?, note=CASE WHEN ?='' THEN note ELSE ? END, "
                     "draft_id=CASE WHEN ?='' THEN draft_id ELSE ? END WHERE id=?",
                     (state, note, note, draft_id, draft_id, sid))
    store.db.commit()


def skip(store, sid: str, note: str = "") -> None:
    set_state(store, sid, "skipped", note)


def reopen(store, sid: str) -> None:
    ensure(store)
    store.db.execute("UPDATE sources SET state='new' WHERE id=?", (sid,))
    store.db.commit()


def mute_theme(store, theme: str) -> int:
    """Leave a news theme out from now on (settings.json `news_muted_themes`); its new items are skipped. Returns
    how many were skipped."""
    from hypolab import config
    from ideaengine.collectors import NEWS_THEMES, muted_themes
    if theme not in {t.key for t in NEWS_THEMES}:
        raise ValueError(f"unknown news theme {theme!r}")
    cur = muted_themes()
    if theme not in cur:
        config.save_settings(news_muted_themes=cur + [theme])
    ensure(store)
    n = 0
    for (sid,) in store.db.execute("SELECT id FROM sources WHERE kind='news' AND state='new' AND id LIKE ?",
                                   (f"news:{theme}:%",)).fetchall():
        set_state(store, sid, "skipped", note="theme muted")
        n += 1
    return n


def unmute_theme(theme: str) -> None:
    from hypolab import config
    from ideaengine.collectors import muted_themes
    config.save_settings(news_muted_themes=[t for t in muted_themes() if t != theme])


def find_by_tag(store, text: str) -> Optional[dict]:
    """The source item named in a `# from:` line (S-osap-Accruals ...), if any."""
    m = re.search(r"\bS-(osap|arxiv|news|dataset|manual)-([A-Za-z0-9._-]+)", str(text or ""), re.I)
    if not m:
        return None
    want = m.group(0).lower()                         # 1.9.1: "S-osap-accruals" finds S-osap-Accruals too
    ensure(store)
    for (sid,) in store.db.execute("SELECT id FROM sources WHERE kind=?", (m.group(1).lower(),)):
        if source_tag(sid).lower() == want:
            return get(store, sid)
    return None


def link_draft(store, source_text: str, draft_id: str) -> Optional[str]:
    """A card imported with `# from: S-...` marks its source item as drafted. Returns the source id or None."""
    it = find_by_tag(store, source_text)
    if it is None:
        return None
    set_state(store, it["id"], "drafted", draft_id=draft_id)
    return it["id"]


def add_manual(store, title: str, url: str = "", text: str = "", authors: str = "", year=None) -> str:
    """A source you found yourself (an SSRN abstract, a BRAIN forum post ...). Stored short: the first 600 characters."""
    import hashlib
    from ideaengine.collectors import _short
    title = " ".join(str(title or "").split())
    if not title:
        raise ValueError("a source needs a title")
    key = hashlib.sha1(f"{title}|{url}".encode()).hexdigest()[:10]
    y = None
    try:
        y = int(year) if year else None
    except (TypeError, ValueError):
        y = None
    it = SourceItem(id=f"manual:{key}", kind="manual", title=title, summary=_short(text), url=str(url or "").strip(),
                    authors=" ".join(str(authors or "").split()), year=y,
                    published=time.strftime("%Y-%m-%d"))
    upsert(store, [it], origin="by hand")
    return it.id


# ------------------------------------------------------------------------------------------------ collecting
NETWORK = ("osap", "arxiv", "news")


def fetch(kind: str, origin: str = "") -> Dict[str, object]:
    """The download part of a collector, alone (1.9.1): no database, so the Ideas app runs it in a worker thread and
    the page stays responsive. Returns {"text" or "texts", "errors", "origin"} for collect(fetched=...)."""
    from ideaengine import collectors as C
    if kind == "osap":
        return {"text": C.fetch_osap(), "errors": [], "origin": origin or "download"}
    if kind == "arxiv":
        return {"text": C.fetch_arxiv(), "errors": [], "origin": origin or "arXiv API"}
    if kind == "news":
        texts, errors = C.fetch_feeds()
        if not texts:
            raise RuntimeError("no feed could be read: " + "; ".join(errors))
        return {"texts": texts, "errors": errors, "origin": origin or f"{len(texts)} feed(s)"}
    raise ValueError(f"{kind} needs no download")


def retire_used_datasets(store, used: Dict[str, set]) -> int:
    """1.9.1: an under-used dataset that your journal has used since it was collected leaves the new list."""
    ensure(store)
    n = 0
    for sid, ex in store.db.execute("SELECT id, extra FROM sources WHERE kind='dataset' AND state='new'").fetchall():
        try:
            e = json.loads(ex or "{}")
        except ValueError:
            continue
        if e.get("dataset") in used.get(e.get("region"), set()):
            set_state(store, sid, "skipped", note=DATASET_USED_NOTE)
            n += 1
    return n


def collect(store, kind: str, text=None, catalog=None, journal=None, origin: str = "",
            regions: Optional[Sequence[str]] = None, fetched: Optional[dict] = None,
            today: Optional[dt.date] = None) -> Dict[str, object]:
    """Run one collector and store its items. text: a document you saved (else the bundled OSAP list / a download);
    fetched: what fetch() downloaded already (the Ideas app downloads in a worker thread).

    Returns {"kind", "found", "added", "errors", "retired"}; a failure is logged with the run and raised again."""
    from ideaengine import collectors as C
    errors: List[str] = []
    retired = 0
    used: Dict[str, set] = {}
    try:
        if fetched is None and text is None and (kind in ("arxiv", "news") or (kind == "osap" and origin == "download")):
            fetched = fetch(kind, origin)
        if fetched is not None:
            text = fetched.get("text")
            errors = list(fetched.get("errors") or [])
            origin = str(fetched.get("origin") or origin)
        if kind == "osap":
            if isinstance(text, bytes):
                text = text.decode("utf-8-sig", errors="replace")
            origin = origin or ("bundled list" if text is None else "file")
            got = C.read_osap(text)
        elif kind == "arxiv":
            got = C.read_arxiv(text)
        elif kind == "news":
            texts = list(fetched.get("texts") or []) if fetched is not None else [text]
            got = C.read_news(texts, today=today)
        elif kind == "datasets":
            if catalog is None:
                raise ValueError("the datasets collector needs the field lists (catalog)")
            got = C.read_datasets(catalog, journal, regions, used_out=used)
            origin = origin or "your downloaded field lists"
        else:
            raise ValueError(f"unknown collector {kind!r}; one of {', '.join(COLLECTORS)}")
    except Exception as e:  # noqa: BLE001
        log_run(store, kind, error=f"{type(e).__name__}: {e}", origin=origin)
        raise
    res = upsert(store, got, origin)
    if kind == "datasets":
        retired = retire_used_datasets(store, used)
    log_run(store, kind, res["found"], res["added"], "; ".join(errors), origin)
    return {"kind": kind, **res, "errors": errors, "retired": retired}


# --------------------------------------------------------------------------------------------------- actions
def citation(d: dict) -> str:
    ex = d.get("extra") or {}
    if d["kind"] == "osap":
        return (f"{d.get('authors')} ({d.get('year')}), {ex.get('journal') or 'journal not stated'} - via "
                f"{OSAP_CITE}, signal {ex.get('acronym')}")
    if d["kind"] == "arxiv":
        return f"{d.get('authors')} ({d.get('year')}) {d['title']}, arXiv {d['id'].split(':', 1)[1]}"
    if d["kind"] == "news":
        return f"News theme {ex.get('theme')} in {ex.get('week')} ({ex.get('count')} headlines)"
    if d["kind"] == "dataset":
        return f"BRAIN dataset {ex.get('dataset')} ({ex.get('region')})"
    return f"{d.get('authors') + ' ' if d.get('authors') else ''}{'(' + str(d['year']) + ') ' if d.get('year') else ''}" \
           f"{d['title']}" + (f", {d['url']}" if d.get("url") else "")


def evidence_line(d: dict) -> str:
    ex = d.get("extra") or {}
    if d["kind"] == "osap":
        parts = [f"sign {ex.get('sign'):+d}" if isinstance(ex.get("sign"), int) else "sign not stated"]
        if ex.get("t_stat") is not None:
            parts.append(f"t-stat {ex['t_stat']:.2f}")
        if ex.get("return_pct_month") is not None:
            parts.append(f"long-short {ex['return_pct_month']:.2f}% a month")
        if ex.get("sample"):
            parts.append(f"sample {ex['sample']}")
        if ex.get("holding_months"):
            parts.append(f"rebalanced every {int(ex['holding_months'])} month(s)")
        parts.append(f"OSAP: predictability {ex.get('predictability') or '?'}, replication "
                     f"{ex.get('replication') or 'not rated'}")
        return "; ".join(parts)
    if d["kind"] == "arxiv":
        return f"submitted {d.get('published') or '?'}; categories {', '.join(ex.get('categories') or [])}"
    if d["kind"] == "news":
        return f"{ex.get('count')} headlines in {ex.get('week')}"
    if d["kind"] == "dataset":
        vs, ac, cov = ex.get("value_score"), ex.get("alpha_count"), ex.get("coverage")
        return (f"value score {vs:g}" if vs is not None else "value score ?") + \
               (f", {int(ac)} alphas" if ac is not None else "") + (f", coverage {cov:.0%}" if cov is not None else "") + \
               (f", {ex.get('fields')} fields known" if ex.get("fields") else "") + \
               (f"; priority dataset of '{ex['theme']}'" if ex.get("theme") else "") + \
               "; none of your simulations has used it yet"
    return f"added by hand {d.get('published') or ''}".strip()


def writer_message(d: dict, plan: Optional[dict] = None, catalog=None) -> str:
    """The SOURCE block for Scout & Writer (format in claude_projects/README.md)."""
    ex = d.get("extra") or {}
    lines = [f"### SOURCE {d['tag']}: {d['title']}", f"kind: {KINDS.get(d['kind'], d['kind'])}",
             f"cite: {citation(d)}"]
    if d.get("url"):
        lines.append(f"link: {d['url']}")
    lines.append(f"evidence: {evidence_line(d)}")
    if d.get("summary"):
        label = {"osap": "what it measures", "arxiv": "abstract (shortened)", "news": "the pattern",
                 "dataset": "description"}.get(d["kind"], "notes")
        lines.append(f"{label}: {d['summary']}")
    if d["kind"] == "news":
        for h in (ex.get("headlines") or [])[:8]:
            lines.append(f"- {h.get('date') or ''} {h.get('title')}")
    if d["kind"] == "dataset" and catalog is not None:
        try:
            cm = catalog.concept_map(ex.get("dataset"), ex.get("region"), ex.get("universe"), int(ex.get("delay", 1)))
            if cm is not None and not cm.empty:
                cm = cm[~cm["nature"].isin(["identifier", "date", "group"])].sort_values("coverage", ascending=False)
                lines.append("fields (id | nature | concepts | coverage | alphas | description):")
                for r in cm.head(12).itertuples(index=False):
                    cov = "?" if r.coverage is None or r.coverage != r.coverage else f"{r.coverage:.0%}"
                    ac = "?" if r.alpha_count is None or r.alpha_count != r.alpha_count else int(r.alpha_count)
                    lines.append(f"- {r.id} | {r.nature} | {r.concepts or '-'} | {cov} | {ac} | "
                                 f"{str(r.description or '')[:90]}")
        except Exception:  # noqa: BLE001
            pass
    lines.append(f"concepts it mentions: {', '.join(d.get('concepts') or []) or 'none matched - say which data is needed'}")
    lines.append(f"BRAIN data categories it likely touches: {', '.join(d.get('categories') or []) or 'unclear'}")
    if d.get("covered_by"):
        lines.append(f"already in the library: {', '.join(d['covered_by'])} cite(s) the same paper - write a card only "
                     "if the mechanism or the data genuinely differs, and say how")
    if plan:
        lines.append(f"this week: {plan.get('region')} D{plan.get('delay', 1)} {plan.get('universe') or ''} - "
                     f"categories {', '.join(plan.get('categories') or [])}".replace("  ", " "))
    if d["kind"] == "osap":
        lines.append("note: published anomalies lose about a third of their power after publication (McLean & Pontiff "
                     "2016) and the paper's sample is US stocks - expect less, and check the data exists in the region.")
    lines.append(f"ask: SCOUT the mechanism (who is wrong, why prices adjust slowly). Write a card only if it predicts "
                 f"RELATIVE returns of many stocks and its data maps to concepts; otherwise answer \"no card\". "
                 f"Put `# from: {d['tag']}` above the card.")
    return "\n".join(lines) + "\n"


def _snake(s: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", str(s).lower())).strip("_") or "src"


def source_draft(d: dict, taken: Iterable[str] = ()) -> dict:
    """A card skeleton from a source item. The mechanism (story, why_persists) and rung 1 are left for you: the checks
    keep it a draft until they are written."""
    from ideaengine import drafts as idea_drafts
    from ideaengine.learn import _free_id
    ex = d.get("extra") or {}
    key = ex.get("acronym") or ex.get("theme") or ex.get("dataset") or d["id"].split(":", 1)[-1]
    c = idea_drafts.template()
    roles = {}
    for con in (d.get("concepts") or [])[:3]:
        if con in CONCEPTS:
            roles[con] = {"concept": con, "note": "suggested by the source text - keep it only if the mechanism needs it"}
    hold = _f(ex.get("holding_months"))
    horizon = "fast" if d["kind"] == "news" else ("slow" if hold and hold >= 12 else "medium")
    strong = d["kind"] == "osap" and ex.get("predictability") == "1_clear" and (_f(ex.get("t_stat")) or 0) >= 3
    sign = ex.get("sign")
    c.update({
        "id": _free_id(f"SRC_{key}", taken),
        "title": f"{d['title'][:80]} - mechanism wanted",
        "family": _snake(f"src_{d['kind']}_{key}")[:40],
        "horizon": horizon, "strength": 2 if strong else 1,
        "sign": f"{int(sign):+d}" if isinstance(sign, int) and sign else "+1",
        "story": (f"From {citation(d)}. {evidence_line(d)}. "
                  + (f"{ex.get('idea')} " if ex.get("idea") else "")
                  + "Write here, in your own words, who makes the mistake, why prices adjust slowly, and which data "
                    "measures it - or bin the draft."),
        "why_persists": "",
        "references": [citation(d) + (f" ({d['url']})" if d.get("url") and d["kind"] != "osap" else "")],
        "roles": roles,
        "ladder": [{"name": "core", "expr": "", "teaches": "the plainest test of the mechanism (write it)"}],
        "expected_turnover": [0.05, 0.4] if d["kind"] == "news" else [0.02, 0.2],
        "watch_out": [],
    })
    wo = []
    if d.get("covered_by"):
        wo.append(f"{', '.join(d['covered_by'])} already cite(s) this paper: make the card genuinely different or bin it.")
    if d["kind"] == "osap":
        wo.append("Published anomalies lose about a third of their power after publication (McLean & Pontiff 2016); the "
                  "paper used US stocks.")
    if d["kind"] == "news":
        wo.append("Built from headlines: test a pattern across many firms, never one company's story.")
    if d["kind"] == "dataset":
        wo.append(f"Read the field descriptions of {ex.get('dataset')} on the cockpit's Data tab first; a scan in the "
                  "Dataset scan app shows which fields carry information (the gate deflates for every field scanned).")
    c["watch_out"] = wo
    return c


# ------------------------------------------------------------------------------------------------ hand-offs
def digest(store) -> Dict[str, object]:
    """Small counts for the Friday digest."""
    c = counts(store)
    out = {k: {s: n for s, n in v.items()} for k, v in c.items()}
    runs = last_runs(store)
    return {"sources": out, "last_collected": {k: v["when"] for k, v in runs.items()}}


def digest_line(store) -> str:
    c = counts(store)
    if not c:
        return "outside sources: none collected yet (Leads > From outside)"
    parts = []
    for kind in ("osap", "arxiv", "news", "dataset", "manual"):
        v = c.get(kind)
        if v:
            parts.append(f"{KIND_SHORT[kind]} {v.get('new', 0)} new / {v.get('drafted', 0)} drafted / "
                         f"{v.get('skipped', 0)} skipped")
    return "outside sources: " + "; ".join(parts)


def state_rows(store, plan: Optional[dict] = None, n: int = 5) -> List[str]:
    """Markdown rows for the state doc's "Fresh outside sources" table.

    1.9.1: the kinds are mixed (the best of each first) and news is left out (the doc is refreshed on Fridays, news
    is stale by the time the brief reads it). Rows are numbered 1-5: the daily brief, which remembers nothing between
    days, uses row N on weekday N (Monday = 1), so the week sees five different sources."""
    refresh_covered(store)
    try:
        df = items(store, kinds=["osap", "arxiv", "dataset", "manual"], show="new", plan=plan, limit=n)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for k, r in enumerate(df.to_dict("records") if not df.empty else [], start=1):
        note = evidence_line(r)
        if r.get("covered_by"):
            note += f"; same paper as {', '.join(r['covered_by'])}"
        title = str(r["title"]).replace("|", "/")
        out.append(f"| {k} | {KIND_SHORT.get(r['kind'], r['kind'])} | {r['tag']} | {title[:70]} | "
                   f"{note.replace('|', '/')[:120]} |")
    return out

"""Phase 7 (1.9.0): collectors - outside sources of ideas, read into plain items.

Four collectors, each turning one kind of outside material into ``SourceItem``s (``ideaengine.sources`` stores them,
scores them and puts them on the Ideas app's Leads > From outside tab):

* ``osap``     - Open Source Asset Pricing (Chen & Zimmermann): ~210 published cross-sectional predictors with their
                 paper, sign and t-stat. The signal list is bundled (``data/osap_SignalDoc.csv.gz``), so it works
                 offline; ``fetch_osap()`` downloads the current one from GitHub.
* ``arxiv``    - the newest q-fin papers (PM, ST, TR, GN) from arXiv's API, kept only when they look cross-sectional
                 (stock returns, anomalies, analysts, earnings ...), not option pricing, crypto or market making.
* ``news``     - business-news RSS headlines, never stored one by one: they are grouped into weekly THEMES that hit
                 many firms at once (guidance cuts, downgrades, buybacks, CEO exits, credit stress ...). One company's
                 story is not an idea; a pattern across hundreds of companies might be (Design v2).
* ``datasets`` - under-used datasets in the field lists you downloaded (value score >= 3, few alphas) that your
                 journal has never touched.

Nothing here simulates, writes a card or calls an AI. Parsing is separate from fetching, so every collector also
reads a file you saved by hand (``python -m ideaengine.collect arxiv --file saved.xml``) and the tests need no
network.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import html
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence
from urllib.parse import quote_plus

from hypolab import config

USER_AGENT = "HYPOLAB-collector/1.9.1 (personal research tool)"
TIMEOUT = 20

OSAP_FILE = config.BUNDLED_DATA / "osap_SignalDoc.csv.gz"
OSAP_URL = "https://raw.githubusercontent.com/OpenSourceAP/CrossSection/master/SignalDoc.csv"
OSAP_CITE = "Chen & Zimmermann (2022) Open Source Cross-Sectional Asset Pricing, Critical Finance Review"

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_CATEGORIES = ["q-fin.PM", "q-fin.ST", "q-fin.TR", "q-fin.GN"]

# Checked on 2026-10-20: all answered with an RSS 2.0 feed. The last two are European (1.9.1: the plan is EUR until
# 8 Nov; Euronews business = EU-wide, City AM = London-listed companies). Edit `collector_feeds` in
# ~/.hypolab/settings.json to change them (any RSS 2.0 or Atom feed works).
DEFAULT_FEEDS = [
    "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "https://www.nasdaq.com/feed/rssoutbound?category=Earnings",
    "https://finance.yahoo.com/news/rssindex",
    "https://www.euronews.com/rss?level=vertical&name=business",
    "https://www.cityam.com/feed/",
]
FEEDS_190 = DEFAULT_FEEDS[:3]          # 1.9.0's defaults: a settings.json that still holds exactly these gets the new list

# News themes that fire on almost every day's headlines and say little about one stock against another; muted unless
# you unmute them (settings.json `news_muted_themes`, or Leads > From outside > Collect).
DEFAULT_MUTED_THEMES = ["rates_inflation"]

SUMMARY_MAX = 600          # stored text stays short: a pointer to the source, never a copy of it


@dataclass
class SourceItem:
    id: str                         # stable: osap:<acronym>, arxiv:<id>, news:<theme>:<week>, dataset:<region>:<id>
    kind: str                       # osap | arxiv | news | dataset | manual
    title: str
    summary: str = ""
    url: str = ""
    authors: str = ""
    year: Optional[int] = None
    published: str = ""             # ISO date
    extra: Dict[str, object] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return self.id.split(":", 1)[1] if ":" in self.id else self.id


def _short(text: str, n: int = SUMMARY_MAX) -> str:
    t = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(text or ""))).split())
    return t if len(t) <= n else t[: n - 3].rsplit(" ", 1)[0] + " ..."


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------ network
def http_get(url: str, timeout: float = TIMEOUT, params: Optional[dict] = None, raw: bool = False):
    """One GET with a plain user agent. Raises on a network error or an HTTP error (the caller says what failed).

    raw=True returns the bytes: feeds are XML and declare their own encoding (1.9.1 - requests guesses ISO-8859-1
    for a `text/xml` reply without a charset, which garbled quotes and euro signs)."""
    import requests
    r = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    if raw:
        return r.content
    r.encoding = r.encoding or "utf-8"
    return r.text


# --------------------------------------------------------------------------------- Open Source Asset Pricing
# OSAP's Cat.Data -> BRAIN's data category (the paper's data, not necessarily the field BRAIN would use)
OSAP_CATEGORY = {"accounting": "fundamental", "analyst": "analyst", "price": "pv", "trading": "pv",
                 "options": "option", "13f": "institutions", "event": "other", "other": "other"}


def read_osap(text: Optional[str] = None, include_placebos: bool = False) -> List[SourceItem]:
    """Predictors from OSAP's SignalDoc.csv (the bundled copy when `text` is None).

    Placebos (signals the original paper did not find significant) and dropped signals are left out unless
    include_placebos=True."""
    if text is None:
        with gzip.open(OSAP_FILE, "rt", encoding="utf-8-sig") as fh:
            text = fh.read()
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if rows and "Acronym" not in rows[0]:
        raise ValueError("not OSAP's SignalDoc.csv: no 'Acronym' column")
    out = []
    for r in rows:
        kind = (r.get("Cat.Signal") or "").strip()
        if kind == "Drop" or (kind != "Predictor" and not include_placebos):
            continue
        acr = (r.get("Acronym") or "").strip()
        if not acr:
            continue
        authors, year = (r.get("Authors") or "").strip(), _num(r.get("Year"))
        desc = (r.get("LongDescription") or acr).strip()
        cat = OSAP_CATEGORY.get((r.get("Cat.Data") or "").strip().lower(), "other")
        sign = _num(r.get("Sign"))
        q = quote_plus(f"{authors} {int(year) if year else ''} {desc}".strip())
        out.append(SourceItem(
            id=f"osap:{acr}", kind="osap", title=desc, summary=_short(r.get("Detailed Definition") or ""),
            url=f"https://scholar.google.com/scholar?q={q}", authors=authors, year=int(year) if year else None,
            extra={"acronym": acr, "journal": (r.get("Journal") or "").strip(), "signal": kind,
                   "osap_data": (r.get("Cat.Data") or "").strip(), "category": cat,
                   "economic": (r.get("Cat.Economic") or "").strip(),
                   "sign": None if sign is None else int(sign), "t_stat": _num(r.get("T-Stat")),
                   "return_pct_month": _num(r.get("Return")),
                   "predictability": (r.get("Predictability in OP") or "").strip(),
                   "replication": (r.get("Signal Rep Quality") or "").strip(),
                   "sample": "-".join(x for x in ((r.get("SampleStartYear") or "").strip(),
                                                  (r.get("SampleEndYear") or "").strip()) if x),
                   "holding_months": _num(r.get("Portfolio Period")),
                   "evidence": _short(r.get("Evidence Summary") or "", 200)}))
    return out


def fetch_osap() -> str:
    """The current SignalDoc.csv from OSAP's GitHub repository (GPL-2.0, see data/OSAP_NOTICE.md)."""
    return http_get(OSAP_URL)


# ---------------------------------------------------------------------------------------------- RSS / Atom
_ATOM = "{http://www.w3.org/2005/Atom}"
_ARX = "{http://arxiv.org/schemas/atom}"
_DC = "{http://purl.org/dc/elements/1.1/}"


def _date(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(s).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def parse_feed(text) -> List[dict]:
    """Entries of an RSS 2.0 or Atom document (bytes as downloaded, or text): {title, link, summary, published,
    authors, categories, id}. Bytes are decoded by the XML parser from the document's own declaration."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"not an RSS or Atom feed ({e})") from None
    out = []
    if root.tag == f"{_ATOM}feed":
        for e in root.findall(f"{_ATOM}entry"):
            link = next((lk.get("href") for lk in e.findall(f"{_ATOM}link")
                         if lk.get("rel") in (None, "alternate") and lk.get("href")), "")
            cats = [c.get("term") for c in e.findall(f"{_ATOM}category") if c.get("term")]
            pc = e.find(f"{_ARX}primary_category")
            out.append({"id": (e.findtext(f"{_ATOM}id") or "").strip(), "title": _short(e.findtext(f"{_ATOM}title"), 300),
                        "link": link, "summary": e.findtext(f"{_ATOM}summary") or e.findtext(f"{_ATOM}content") or "",
                        "published": _date(e.findtext(f"{_ATOM}published") or e.findtext(f"{_ATOM}updated") or ""),
                        "authors": [a.findtext(f"{_ATOM}name") or "" for a in e.findall(f"{_ATOM}author")],
                        "categories": cats, "primary": pc.get("term") if pc is not None else (cats[0] if cats else "")})
        return out
    chan = root.find("channel")
    for it in (chan.findall("item") if chan is not None else root.iter("item")):
        cats = [c.text for c in it.findall("category") if c.text]
        creators = [c.text for c in it.findall(f"{_DC}creator") if c.text]
        out.append({"id": (it.findtext("guid") or it.findtext("link") or "").strip(),
                    "title": _short(it.findtext("title"), 300), "link": (it.findtext("link") or "").strip(),
                    "summary": it.findtext("description") or "", "published": _date(it.findtext("pubDate") or
                                                                                   it.findtext(f"{_DC}date") or ""),
                    "authors": creators, "categories": cats, "primary": cats[0] if cats else ""})
    return out


# ------------------------------------------------------------------------------------------------------ arXiv
# A paper is kept when it talks about the cross-section of stock returns; these push it out.
ARXIV_KEEP = [r"cross[- ]section", r"anomal", r"stock returns?", r"equity returns?", r"return predictab", r"predict\w* "
              r"(stock|equity|asset) returns?", r"mispricing", r"factor (model|zoo|premi|investing)", r"\bfactors?\b.{0,40}"
              r"returns", r"analysts?", r"earnings", r"investor (attention|sentiment)", r"institutional",
              r"short (selling|sellers|interest)", r"insider", r"momentum", r"reversal", r"value (premium|investing)",
              r"profitability", r"accrual", r"liquidity", r"firm characteristics", r"stock selection", r"alpha"]
ARXIV_DROP = [r"option pricing", r"black[- ]scholes", r"crypto", r"bitcoin", r"blockchain", r"defi\b", r"market[- ]making",
              r"limit order book", r"high[- ]frequency", r"insurance", r"pension", r"mortgage", r"credit default swap",
              r"interest rate model", r"term structure", r"stochastic volatility model", r"rough volatility",
              r"hedging", r"optimal execution", r"exchange rate", r"commodit"]


def arxiv_relevance(title: str, abstract: str) -> float:
    """How much an abstract looks like a cross-sectional stock-return idea (0 = not at all)."""
    t = f"{title} {abstract}".lower()
    keep = sum(1 for p in ARXIV_KEEP if re.search(p, t))
    drop = sum(1 for p in ARXIV_DROP if re.search(p, t))
    return max(0.0, keep - 2.0 * drop)


def read_arxiv(text: str, min_relevance: float = 2.0) -> List[SourceItem]:
    out = []
    for e in parse_feed(text):
        abstract = _short(e["summary"])
        rel = arxiv_relevance(e["title"], abstract)
        if rel < min_relevance:
            continue
        aid = re.sub(r"v\d+$", "", e["id"].rsplit("/abs/", 1)[-1].rsplit("/", 1)[-1]) or \
            hashlib.sha1(e["title"].encode()).hexdigest()[:10]
        authors = [a for a in e["authors"] if a]
        au = authors[0].split()[-1] + (" et al." if len(authors) > 2 else
                                       (f" & {authors[1].split()[-1]}" if len(authors) == 2 else "")) if authors else ""
        year = int(e["published"][:4]) if e["published"][:4].isdigit() else None
        out.append(SourceItem(id=f"arxiv:{aid}", kind="arxiv", title=e["title"], summary=abstract,
                              url=e["link"] or f"https://arxiv.org/abs/{aid}", authors=au, year=year,
                              published=e["published"],
                              extra={"categories": e["categories"], "primary": e["primary"], "relevance": rel}))
    return out


def fetch_arxiv(categories: Optional[Sequence[str]] = None, max_results: int = 100) -> str:
    """The newest papers in the q-fin categories (one API call; arXiv asks for no more than one every 3 seconds)."""
    cats = list(categories or config.settings().get("arxiv_categories") or ARXIV_CATEGORIES)
    q = " OR ".join(f"cat:{c}" for c in cats)
    return http_get(ARXIV_API, params={"search_query": q, "sortBy": "submittedDate", "sortOrder": "descending",
                                       "start": 0, "max_results": int(max_results)}, raw=True)


# ------------------------------------------------------------------------------------------------------- news
@dataclass
class NewsTheme:
    key: str
    label: str
    patterns: List[str]
    concepts: List[str]
    category: str
    idea: str                        # the cross-sectional question the theme raises


NEWS_THEMES: List[NewsTheme] = [
    NewsTheme("guidance_cut", "Guidance cuts and profit warnings",
              [r"\b(cut|cuts|lower|lowers|lowered|slash|slashes|withdraw|withdraws|pull|pulls)\b.{0,25}"
               r"\b(guidance|outlook|forecast)", r"profit warning", r"warns? (on|of) (profit|earnings|sales)"],
              ["guidance", "est_eps"], "earnings",
              "Do firms that cut guidance keep drifting down while analysts revise slowly? Measured across many firms."),
    NewsTheme("guidance_raise", "Guidance raised",
              [r"\b(raise|raises|raised|lift|lifts|boost|boosts|hike|hikes)\b.{0,25}\b(guidance|outlook|forecast)"],
              ["guidance", "est_eps"], "earnings", "Do upward guidance changes lead estimate revisions and returns?"),
    NewsTheme("earnings_surprise", "Earnings beats and misses",
              [r"\b(beat|beats|top|tops|miss|misses|surpass|surpasses)\b.{0,25}\b(estimates|expectations|forecasts|"
               r"consensus)", r"earnings (surprise|beat|miss)"],
              ["surprise"], "earnings", "Is the drift after surprises stronger where attention is low this season?"),
    NewsTheme("analyst_rating", "Analyst upgrades, downgrades and target changes",
              [r"\bupgrade[sd]?\b", r"\bdowngrade[sd]?\b", r"price target", r"initiat\w+ coverage"],
              ["recommendation", "target_price", "num_estimates"], "analyst",
              "Do rating changes keep paying off after the announcement day, and which analysts move prices?"),
    NewsTheme("buyback_dividend", "Buybacks and dividend changes",
              [r"buy ?back", r"share repurchase", r"repurchase program", r"dividend (hike|increase|cut|raise|boost|"
               r"suspen)", r"(raises|cuts|suspends) (its )?dividend"],
              ["sharesout", "dividend"], "fundamental",
              "Do buybacks and dividend changes signal undervaluation that prices absorb slowly?"),
    NewsTheme("equity_issuance", "Share sales and convertible issuance",
              [r"secondary offering", r"(share|stock|equity) (sale|offering)", r"convertible (notes|bonds|offering)",
               r"raises? \$[\d.]+ ?(billion|million) in (a )?(share|stock)"],
              ["sharesout"], "fundamental", "Do issuers underperform after raising equity (net issuance)?"),
    NewsTheme("mna", "Mergers and acquisitions",
              [r"\bto acquire\b", r"\bacquires?\b", r"\bmerger\b", r"takeover", r"deal to buy", r"\bbid for\b"],
              [], "other", "Do acquirers underperform and targets' peers re-rate? Which side is slow?"),
    NewsTheme("short_sellers", "Short-seller reports and short interest",
              [r"short[- ]sell(er|ing)", r"short report", r"short interest", r"\bshorted\b"],
              ["short_interest"], "shortinterest", "Is short interest rising before bad news across firms?"),
    NewsTheme("insiders", "Insider buying and selling",
              [r"insider (buying|selling|purchase|sale)s?", r"\b(ceo|cfo|director|chairman)\b.{0,20}\b(buys|bought|"
               r"sells|sold) (shares|stock)"],
              ["insider_buy", "insider_sell"], "insiders", "Do clustered insider purchases predict returns?"),
    NewsTheme("management_change", "CEO and CFO changes",
              [r"\b(ceo|cfo|chief executive|chief financial officer)\b.{0,30}\b(steps? down|resigns?|to step down|"
               r"ousted|departs?|exit|leaves?|retire)", r"(names|appoints|hires) (a )?new (ceo|cfo|chief)"],
              ["management_change"], "other", "Do abrupt executive departures precede weak results?"),
    NewsTheme("rates_inflation", "Rates and inflation",
              [r"\b(rate|rates) (hike|cut|increase|decision)", r"\binflation\b", r"\b(fed|ecb|central bank)\b",
               r"bond yields?", r"treasury yields?"],
              ["rate_sensitivity", "macro_series"], "macro",
              "Which stocks are most exposed to rate moves, and is that exposure priced slowly?"),
    NewsTheme("supply_chain", "Tariffs, supply chains and shortages",
              [r"\btariffs?\b", r"supply[- ]chain", r"shortages?", r"export (ban|controls?|curbs?)"],
              ["cogs", "inventory", "relationship_group"], "fundamental",
              "Do shocks to suppliers or customers reach linked firms' prices with a delay?"),
    NewsTheme("credit_stress", "Credit downgrades, defaults and bankruptcies",
              [r"\bjunk\b", r"credit rating", r"\bdefaults?\b", r"bankrupt", r"chapter 11", r"\bdistress"],
              ["credit_risk", "credit_spread"], "risk", "Does credit-market stress reach the stock price late?"),
    NewsTheme("cost_cuts", "Layoffs and restructuring",
              [r"layoffs?", r"job cuts", r"cut(s|ting)? \d[\d,]* jobs", r"restructuring", r"cost[- ]cutting"],
              ["sga", "operating_income"], "fundamental", "Do cost cuts lift margins before analysts revise?"),
    NewsTheme("capex_ai", "Capital spending plans",
              [r"\bcapex\b", r"capital (spending|expenditure)", r"data cent(er|re)s?", r"\binvest(s|ing)? \$[\d.]+ ?"
               r"billion"],
              ["capex"], "fundamental", "Is over-investment (capex growth) still followed by lower returns?"),
    NewsTheme("index_changes", "Index additions and deletions",
              [r"(added|join|joins|added to|removed from|dropped from) the (s&p|nasdaq|stoxx|ftse|msci)",
               r"index (inclusion|rebalanc)"],
              ["adv", "volume"], "pv", "Do index changes create temporary price pressure that reverses?"),
]


def news_themes(title: str, summary: str = "") -> List[NewsTheme]:
    t = f"{title} {summary}".lower()
    return [th for th in NEWS_THEMES if any(re.search(p, t) for p in th.patterns)]


def iso_week(day: Optional[dt.date] = None) -> str:
    y, w, _ = (day or dt.date.today()).isocalendar()
    return f"{y}-W{w:02d}"


def muted_themes() -> List[str]:
    """News themes you muted (settings.json `news_muted_themes`; rates and inflation by default)."""
    v = config.settings().get("news_muted_themes")
    return list(DEFAULT_MUTED_THEMES if v is None else v)


def read_news(texts: Iterable, today: Optional[dt.date] = None, max_age_days: int = 14,
              muted: Optional[Iterable[str]] = None) -> List[SourceItem]:
    """Headlines from one or more RSS/Atom documents, grouped by theme and ISO week. Headlines that match no theme
    are dropped (a single company's story is not a cross-sectional idea), and so are muted themes."""
    today = today or dt.date.today()
    mute = set(muted_themes() if muted is None else muted)
    groups: Dict[tuple, dict] = {}
    for text in texts:
        try:
            entries = parse_feed(text)
        except ValueError:
            continue
        for e in entries:
            pub = e["published"]
            try:
                d = dt.date.fromisoformat(pub) if pub else today
            except ValueError:
                d = today
            if (today - d).days > max_age_days:
                continue
            for th in news_themes(e["title"], _short(e["summary"], 300)):
                if th.key in mute:
                    continue
                g = groups.setdefault((th.key, iso_week(d)), {"theme": th, "heads": {}, "latest": ""})
                link = e["link"] or e["id"] or e["title"]
                g["heads"].setdefault(link, {"title": e["title"], "link": e["link"], "date": pub})
                g["latest"] = max(g["latest"], pub or "")
    out = []
    for (key, week), g in groups.items():
        th, heads = g["theme"], list(g["heads"].values())
        heads.sort(key=lambda h: h["date"] or "", reverse=True)
        lines = "; ".join(h["title"] for h in heads[:5])
        out.append(SourceItem(id=f"news:{key}:{week}", kind="news",
                              title=f"{th.label}: {len(heads)} headline{'s' * (len(heads) != 1)} in {week}",
                              summary=_short(f"{th.idea} Headlines: {lines}"), url=heads[0]["link"] if heads else "",
                              published=g["latest"],
                              extra={"theme": key, "week": week, "count": len(heads), "concepts": th.concepts,
                                     "category": th.category, "idea": th.idea,
                                     "headlines": [{"title": h["title"], "link": h["link"], "date": h["date"]}
                                                   for h in heads[:12]]}))
    return out


def feed_urls() -> List[str]:
    urls = list(config.settings().get("collector_feeds") or DEFAULT_FEEDS)
    return list(DEFAULT_FEEDS) if urls == FEEDS_190 else urls        # 1.9.0's untouched defaults -> today's


def fetch_feeds(urls: Optional[Sequence[str]] = None) -> tuple:
    """(documents, errors) for the configured RSS feeds; a feed that fails to download or is not RSS/Atom is
    reported, the others still count."""
    urls = list(urls or feed_urls())
    texts, errors = [], []
    for u in urls:
        try:
            body = http_get(u, raw=True)
            parse_feed(body)                                   # 1.9.1: a page that is not a feed is reported too
            texts.append(body)
        except Exception as e:  # noqa: BLE001 - one dead feed must not stop the rest
            errors.append(f"{u}: {type(e).__name__}: {str(e)[:120]}")
    return texts, errors


# ---------------------------------------------------------------------------------------------------- datasets
def read_datasets(catalog, journal=None, regions: Optional[Sequence[str]] = None, min_value: float = 3.0,
                  max_alphas: float = 2000.0, used_out: Optional[Dict[str, set]] = None) -> List[SourceItem]:
    """Under-used datasets in the field lists you downloaded: BRAIN's value score >= min_value and not too crowded,
    that no simulation in your journal has touched yet. Theme priority datasets are flagged.

    1.9.1: one item per region and dataset (Delay-1 preferred; `delays` lists every delay it was seen at), and
    `used_out`, when given, receives {region: dataset ids your journal has used} for the regions read."""
    from hypolab import rules
    try:
        ctx = catalog.contexts()
    except Exception:  # noqa: BLE001
        return []
    if ctx is None or ctx.empty:
        return []
    if regions:
        ctx = ctx[ctx["region"].isin(list(regions))]
    ctx = ctx[ctx["region"] != "SBX"]
    used: Dict[str, set] = {}
    exprs = []
    if journal is not None:
        try:
            exprs = [(r, e) for r, e in journal.db.execute("SELECT region, expression FROM experiments "
                                                           "WHERE backend != 'sandbox'")]
        except Exception:  # noqa: BLE001
            exprs = []
    prio = {}
    for t in rules.themes():
        for d in t.get("priority_datasets") or []:
            if d.get("id"):
                prio[(t.get("region"), d["id"])] = t["name"]
    out: Dict[tuple, SourceItem] = {}
    seen = set()
    ctx = ctx.assign(_d1=(ctx["delay"].astype(int) == 1).astype(int)).sort_values(["_d1", "fields"], ascending=False)
    for c in ctx.itertuples(index=False):
        region, universe, delay = c.region, c.universe, int(c.delay)
        if (region, delay) in seen:                    # one field list per region and delay is enough
            continue
        seen.add((region, delay))
        ds = catalog.datasets(region, universe, delay)
        if ds is None or ds.empty or "value_score" not in ds.columns:
            continue
        if region not in used:
            look = catalog.lookup_map(region, universe, delay)
            u = set()
            for reg, e in exprs:
                if reg != region:
                    continue
                for f in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", e or ""):
                    if f in look:
                        u.add(look[f])
            used[region] = u
            if used_out is not None:
                used_out[region] = u
        for r in ds.itertuples(index=False):
            vs = _num(getattr(r, "value_score", None))
            ac = _num(getattr(r, "alpha_count", None))
            if vs is None or vs < min_value or (ac is not None and ac > max_alphas) or r.id in used[region]:
                continue
            cov = _num(getattr(r, "coverage", None))
            if cov is not None and cov < 0.3:
                continue
            if (region, r.id) in out:                  # already listed at Delay-1 (or another field list)
                ds_delays = out[(region, r.id)].extra["delays"]
                if delay not in ds_delays:
                    ds_delays.append(delay)
                continue
            theme = prio.get((region, r.id))
            out[(region, r.id)] = (SourceItem(
                id=f"dataset:{region}:{r.id}", kind="dataset", title=f"{r.name if isinstance(r.name, str) and r.name else r.id} ({r.id}, {region} D{delay})",
                summary=_short(r.description if isinstance(r.description, str) else ""), url="",
                extra={"region": region, "universe": universe, "delay": delay, "delays": [delay], "dataset": r.id,
                       "category": r.category, "value_score": vs, "alpha_count": ac, "coverage": cov,
                       "fields": int(getattr(r, "fields_known", 0) or 0),
                       "multiplier": _num(getattr(r, "pyramid_multiplier", None)), "theme": theme}))
    return list(out.values())


def osap_notice() -> str:
    p = config.BUNDLED_DATA / "OSAP_NOTICE.md"
    return p.read_text() if p.exists() else OSAP_CITE


def load_file(path, binary: bool = False):
    """A file Zacc saved by hand (gz allowed). binary=True for feeds: the XML parser reads the encoding itself."""
    p = Path(path)
    if p.suffix == ".gz":
        if binary:
            with gzip.open(p, "rb") as fh:
                return fh.read()
        with gzip.open(p, "rt", encoding="utf-8-sig") as fh:
            return fh.read()
    if binary:
        return p.read_bytes()
    return p.read_text(encoding="utf-8-sig", errors="replace")

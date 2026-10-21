"""Paths and research defaults. Override anything with environment variables or by adding the setting to
``~/.hypolab/settings.json`` (created on first run; it holds only your own choices since 1.10.1 - the defaults are
listed in ``~/.hypolab/settings.defaults.json``)."""
from __future__ import annotations

import json
import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
BUNDLED_DATA = PROJECT_DIR / "data"
LIBRARY_DIR = PACKAGE_DIR / "library"

HOME = Path(os.environ.get("HYPOLAB_HOME", Path.home() / ".hypolab"))

DEFAULTS = {
    # "sandbox" = offline practice market; "live" = your BRAIN account. Every marimo app follows this switch.
    # Change it on the cockpit's Setup tab, or `python -m hypolab live` / `python -m hypolab sandbox`.
    "mode": "sandbox",
    "live_region": "USA",             # the region the apps use in live mode (change per session if you like)
    # Simulation discipline. BRAIN wants VOLUME (1000+ simulations is normal for a consultant who builds
    # ideas from scratch). Volume is not the problem; picking the best of many variants of ONE idea is.
    # So: spend freely ACROSS ideas and datasets, stay disciplined WITHIN one idea, and let the journal
    # count every try so the gate can deflate the Sharpe honestly.
    "max_sims_per_idea": 10,          # per hypothesis: past this, rethink the idea (force=True overrides)
    "max_sims_per_day": 500,          # only a runaway-loop guard; raise it freely
    # Submissions. BRAIN expects up to 4 regular alphas and 1 SuperAlpha a day; SuperAlphas unlock after
    # 100 submitted alphas (lifetime). The 4 is a ceiling, not a quota: weak submissions pull down your
    # combined alpha performance, which is one of the Genius bars.
    "max_submissions_per_day": 4,
    "superalpha_unlock_after": 100,
    "max_super_sims_per_pool": 10,
    "gate_max_age_minutes": 30,         # 1.10.2: submit only from a READY gate report issued this recently      # 1.10.0: SuperAlpha simulations per pool (region, delay) per quarter
    # How long an app keeps running after the browser loses its connection (laptop asleep, Wi-Fi blip). marimo's own
    # default is 120 s, after which the tab shows "kernel not found". Each kept session holds ~0.8 GB on a T470s.
    "session_ttl_seconds": 900,
    "scan_max_fields": 40,            # fields probed per dataset scan (R.scan)
    "concurrent_simulations": 2,      # gentle on a T470s and on the API; 3 is the safe maximum
    "multi_sim_batch": 5,             # alphas per multi-simulation request (BRAIN allows 2..10)
    # Submission gate used for "is this worth your time" - BRAIN's own /check is the authority,
    # and its limits are read live from each simulation's checks.
    "min_sharpe_d1": 1.58, "min_fitness_d1": 1.0,
    "min_sharpe_d0": 2.69, "min_fitness_d0": 1.5,
    "max_self_corr": 0.7,
    "max_prod_corr": 0.7,             # vs BRAIN's production pool = "is this idea already taken?"
    "target_turnover": [0.05, 0.40],
    # Pyramids: alphas you must submit in one (region, delay, category) cell for it to count.
    # Check the Genius page on BRAIN and set the number you see there.
    # Confirmed by BRAIN's Genius page: a Pyramid needs 3 submitted alphas in the cell (BRAIN_RULES G3).
    "alphas_per_pyramid": 3,
    # Regions YOUR account can simulate (BRAIN's Simulate > Region dropdown; Zacc, 10 Oct 2026).
    # The Pyramid planner, Osmosis check and region pickers use this list. Edit it if BRAIN changes yours.
    "account_regions": ["USA", "GLB", "EUR", "ASI", "CHN", "JPN", "AMR", "IND", "DEU", "GBR"],
    # 1.9.0 collectors (Ideas app, Leads > From outside; python -m hypolab collect). Any RSS 2.0 / Atom feed works;
    # these three answered on 2026-10-20. arXiv categories: q-fin portfolio management, statistical finance, trading
    # and market microstructure, general finance.
    "collector_feeds": ["https://feeds.content.dowjones.io/public/rss/mw_topstories",
                        "https://www.nasdaq.com/feed/rssoutbound?category=Earnings",
                        "https://finance.yahoo.com/news/rssindex",
                        "https://www.euronews.com/rss?level=vertical&name=business",
                        "https://www.cityam.com/feed/"],
    "news_muted_themes": ["rates_inflation"],          # 1.9.1: news themes Leads > From outside leaves out
    "arxiv_categories": ["q-fin.PM", "q-fin.ST", "q-fin.TR", "q-fin.GN"],
    # 1.10.1: the "HYPOLAB state" doc the daily brief reads (the Week page links to it)
    "state_doc_url": "https://claude.ai/code/artifact/edd2818c-6d1d-45b5-ac48-c32324a9c8ff",
}

# 1.10.1: settings.json holds only YOUR choices. Before, every save wrote all of DEFAULTS into it, so a default
# changed in a later release never reached you (the 1.4.2 session_ttl and the 1.9.0 feed list needed special code).
SETTINGS_VERSION = 2
OBSOLETE_KEYS = {"pyramid_regions", "single_country_region"}      # before 1.3.2; account_regions replaced them
_MARK = "_settings_version"
_ABOUT = ("Only the settings you changed. Every other setting uses HYPOLAB's default: see settings.defaults.json "
          "next to this file (rewritten at each start, so editing it does nothing). Copy a line here to change it.")


def _own_keys(user: dict) -> dict:
    """The keys a settings.json really sets. A file without the 1.10.1 mark was written whole by older releases:
    keys equal to today's default (or obsolete ones) are dropped, so later defaults reach you."""
    if user.get(_MARK, 0) >= SETTINGS_VERSION:
        return {k: v for k, v in user.items() if k not in OBSOLETE_KEYS and not k.startswith("_")}
    return {k: v for k, v in user.items() if k not in OBSOLETE_KEYS and not k.startswith("_")
            and (k not in DEFAULTS or DEFAULTS[k] != v)}


def _write_settings(own: dict) -> None:
    body = {"_about": _ABOUT, _MARK: SETTINGS_VERSION}
    body.update({k: v for k, v in own.items() if not k.startswith("_")})
    path = HOME / "settings.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(body, indent=2))
    os.replace(tmp, path)


def _write_defaults_reference() -> None:
    try:
        ref = HOME / "settings.defaults.json"
        text = json.dumps(DEFAULTS, indent=2)
        if not ref.exists() or ref.read_text() != text:
            ref.write_text(text)
    except OSError:
        pass


def ensure_home() -> Path:
    HOME.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(HOME, 0o700)
    except OSError:
        pass
    return HOME


_SETTINGS_CACHE: dict = {}


def settings() -> dict:
    """DEFAULTS merged with ~/.hypolab/settings.json. 1.8.1: re-read only when the file changes (it was read from
    disk on every call - dozens of times per Cards ranking)."""
    path = HOME / "settings.json"
    try:
        st = path.stat()
        sig = (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        sig = None
    if sig is not None and _SETTINGS_CACHE.get("sig") == sig:
        return dict(_SETTINGS_CACHE["value"])
    ensure_home()
    if _SETTINGS_CACHE.get("ref") != str(HOME):
        _write_defaults_reference()
        _SETTINGS_CACHE["ref"] = str(HOME)
    if not path.exists():
        _write_settings({"mode": "sandbox"})
        return settings()
    try:
        user = json.loads(path.read_text())
    except json.JSONDecodeError:
        user = {}
    if not isinstance(user, dict):
        user = {}
    if user and user.get(_MARK, 0) < SETTINGS_VERSION:      # an older, whole-defaults file: keep only your choices
        try:
            _write_settings(_own_keys(user))
            return settings()
        except OSError:
            pass
    merged = dict(DEFAULTS)
    merged.update(_own_keys(user))
    try:
        st = path.stat()
        _SETTINGS_CACHE.update(sig=(str(path), st.st_mtime_ns, st.st_size), value=dict(merged))
    except OSError:
        pass
    return merged


def save_settings(**changes) -> dict:
    """Change some settings in ~/.hypolab/settings.json (keeps your other choices; never writes the defaults)."""
    settings()                                     # creates or migrates the file first
    path = HOME / "settings.json"
    try:
        own = _own_keys(json.loads(path.read_text()))
    except (OSError, json.JSONDecodeError, AttributeError):
        own = {}
    own.update(changes)
    _write_settings(own)
    _SETTINGS_CACHE.pop("sig", None)
    _SETTINGS_CACHE.pop("value", None)
    return settings()


def sandbox_mode() -> bool:
    """True unless you switched to live mode. The apps use: SANDBOX = config.sandbox_mode()."""
    return settings().get("mode", "sandbox") != "live"


def live_region() -> str:
    return settings().get("live_region", "USA")


# Default universes and simulation constraints per region (documented / measured).
# These are starting points; `BrainClient.simulation_options()` reads the live truth.
REGION_DEFAULTS = {
    "USA": {"universe": "TOP3000", "delays": [1, 0], "max_trade": "OFF", "neutralization": "SUBINDUSTRY"},
    "GLB": {"universe": "MINVOL1M", "delays": [1], "max_trade": "OFF", "neutralization": "STATISTICAL"},
    "EUR": {"universe": "TOP2500", "delays": [1, 0], "max_trade": "OFF", "neutralization": "SUBINDUSTRY"},
    "ASI": {"universe": "MINVOL1M", "delays": [1], "max_trade": "ON", "neutralization": "SUBINDUSTRY"},
    "CHN": {"universe": "TOP2000U", "delays": [1, 0], "max_trade": "ON", "neutralization": "SUBINDUSTRY"},
    "KOR": {"universe": "TOP600", "delays": [1], "max_trade": "ON", "neutralization": "SUBINDUSTRY"},
    "TWN": {"universe": "TOP500", "delays": [1], "max_trade": "ON", "neutralization": "SUBINDUSTRY"},
    "HKG": {"universe": "TOP800", "delays": [1], "max_trade": "ON", "neutralization": "SUBINDUSTRY"},
    "JPN": {"universe": "TOP1600", "delays": [1, 0], "max_trade": "ON", "neutralization": "SUBINDUSTRY"},
    "AMR": {"universe": "TOP600", "delays": [1, 0], "max_trade": "OFF", "neutralization": "SUBINDUSTRY"},
    # DEU and GBR: offered on Zacc's account with D1 and D0 (Genius page). Their universe names are not
    # documented anywhere we have; they are filled in from BRAIN by sync_simulation_options() (Account tab).
    "DEU": {"universe": None, "delays": [1, 0], "max_trade": "ON", "neutralization": "SUBINDUSTRY"},
    "GBR": {"universe": None, "delays": [1, 0], "max_trade": "ON", "neutralization": "SUBINDUSTRY"},
    "IND": {"universe": "TOP500", "delays": [1], "max_trade": "ON", "neutralization": "SUBINDUSTRY"},
    # offline sandbox (synthetic data, see hypolab/sandbox)
    "SBX": {"universe": "SANDBOX", "delays": [1], "max_trade": "OFF", "neutralization": "SUBINDUSTRY"},
}

# Economically meaningful look-back windows in trading days (WorldQuant webinar:
# "days should reflect the alpha idea").
ECONOMIC_WINDOWS = {
    1: "one day", 2: "two days", 3: "three days", 5: "one week", 10: "two weeks", 21: "one month",
    42: "two months", 63: "one quarter", 126: "half a year", 189: "three quarters", 252: "one year",
    504: "two years", 756: "three years",
}


def account_regions() -> list:
    """Regions this account can simulate, in the order of the setting."""
    regs = settings().get("account_regions") or DEFAULTS["account_regions"]
    return [r for r in regs if r != "SBX"]


def universe_for(region: str):
    """Default universe for a region, or None if unknown (sync the simulation options first)."""
    return REGION_DEFAULTS.get(region, {}).get("universe")


def region_neutralizations(region: str) -> list:
    """Neutralizations BRAIN offers in this region (from the synced options), else the classic five."""
    return REGION_DEFAULTS.get(region, {}).get("neutralizations") or \
        ["MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY", "NONE"]


def _pick_universe(current, universes):
    if current in universes or not universes:
        return current
    tops = [u for u in universes if u.startswith("TOP") and u[3:].isdigit()]
    return max(tops, key=lambda u: int(u[3:])) if tops else universes[0]


def apply_sim_options(rows=None) -> int:
    """Merge BRAIN's OPTIONS /simulations answer (cached in ~/.hypolab/sim_options.json) into REGION_DEFAULTS.

    BRAIN is the authority on which delays, universes and neutralizations each region offers.
    """
    if rows is None:
        try:
            rows = json.loads((HOME / "sim_options.json").read_text())
        except (OSError, ValueError):
            return 0
    n = 0
    for r in rows or []:
        reg = r.get("region")
        if not reg:
            continue
        e = REGION_DEFAULTS.setdefault(reg, {"universe": None, "delays": [1], "max_trade": "OFF",
                                             "neutralization": "SUBINDUSTRY"})
        delays = [int(d) for d in (r.get("delays") or []) if str(d).lstrip("-").isdigit()]
        if delays:
            e["delays"] = sorted(set(delays), reverse=True)
        univs = list(r.get("universes") or [])
        if univs:
            e["universes"] = univs
            e["universe"] = _pick_universe(e.get("universe"), univs)
        neuts = list(r.get("neutralizations") or [])
        if neuts:
            e["neutralizations"] = neuts
            if e.get("neutralization") not in neuts:
                e["neutralization"] = "SUBINDUSTRY" if "SUBINDUSTRY" in neuts else neuts[0]
        n += 1
    return n


def save_sim_options(rows) -> int:
    ensure_home()
    (HOME / "sim_options.json").write_text(json.dumps(rows, indent=1))
    return apply_sim_options(rows)


apply_sim_options()


def apply_themes(day=None) -> list:
    """1.6.1: while a BRAIN theme is active (data/themes.json), its universe becomes the region's default - e.g. EUR
    TOP800 during the EUR/D1 TOP800 theme - unless the synced options say the region does not offer it, or
    settings.json has "follow_themes": false. Returns the regions changed."""
    try:                                    # read without creating ~/.hypolab at import time
        follow = json.loads((HOME / "settings.json").read_text()).get("follow_themes", True)
    except (OSError, ValueError):
        follow = True
    if not follow:
        return []
    try:
        from . import rules
        active = rules.themes(day)
    except Exception:  # noqa: BLE001
        return []
    # 1.8.1: a theme that has ended gives the region its usual universe back (the apps run for days, and before
    # this the EUR default stayed TOP800 after 8 Nov until a restart)
    live_regions = {t.get("region") for t in active}
    for reg, e in REGION_DEFAULTS.items():
        if "base_universe" in e and reg not in live_regions:
            e["universe"] = e.pop("base_universe")
    changed = []
    for t in sorted(active, key=lambda x: x.get("priority", 9)):
        reg, uni = t.get("region"), t.get("universe")
        e = REGION_DEFAULTS.get(reg)
        if not e or not uni or (e.get("universes") and uni not in e["universes"]):
            continue
        if reg not in changed:
            e.setdefault("base_universe", e.get("universe"))
            e["universe"] = uni
            changed.append(reg)
    return changed


apply_themes()

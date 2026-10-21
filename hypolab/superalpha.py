"""Phase 8 (HYPOLAB 1.10.0): the SuperAlpha builder.

A SuperAlpha combines alphas you have already SUBMITTED in one region and delay. It is two expressions:

* a **selection** expression, evaluated once per submitted alpha on that alpha's properties (turnover, correlations,
  operator count, data categories ...). BRAIN ranks the alphas by it and keeps the top ``selectionLimit``;
  ``selectionHandling`` says which scores count (``POSITIVE``: only scores > 0, so a gate written as a product of
  conditions drops an alpha by scoring it 0).
* a **combo** expression, evaluated every day per kept alpha, that weights it (``1`` = equal weight; ``stats =
  generate_stats(alpha); ...`` reads each alpha's own return history).

BRAIN unlocks SuperAlphas after 100 submitted alphas and accepts at most one SuperAlpha a day (BRAIN_RULES G11).
Where the facts come from: the unlock and the daily limit are BRAIN's own documentation. The request format
(``type: SUPER``, top-level ``selection`` and ``combo``, settings ``selectionLimit`` >= 10, ``selectionHandling``,
``componentActivation`` IS/OS), the 8,000-operator ceiling across the kept alphas, the 2%-40% turnover band and
three SuperAlpha simulations at a time come from Alpha Harness (github.com/residual-lab/alpha-harness, MIT licence,
built against the live API, read 20 Oct 2026); the selection and combo vocabulary also from wqbkit (PyPI 0.4.7).
They are community sources: BRAIN_RULES marks them "verify live", and BRAIN's own checks stay the authority.
The recipes are adapted from Alpha Harness under its MIT licence: copyright notice in data/THIRD_PARTY_NOTICES.md.

HYPOLAB's rules carry over: nothing simulates without a button, a small library of recipes with a reason each
instead of a sweep, ONE change per try, 10 tries per pool per quarter (the gate's deflated Sharpe counts them all),
and a typed confirmation to submit.
"""
from __future__ import annotations

import ast
import datetime as dt
import math
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd

from . import config

FAMILY = "superalpha"
PURPOSE = "super"

MIN_SELECTION = 10                  # BRAIN refuses a smaller selectionLimit (community source)
MAX_SELECTION = 200
OPERATOR_LIMIT = 8000               # operators across every kept alpha; BRAIN drops what does not fit
TURNOVER_BAND = (0.02, 0.40)        # a SuperAlpha's turnover must sit inside this band (community source)
SELECTION_HANDLING = ("POSITIVE", "NON_ZERO", "NON_NAN")
COMPONENT_ACTIVATION = ("IS", "OS")
DEFAULT_DECAY = 4
DEFAULT_TRUNCATION = 0.05           # lower than an alpha's 0.08: a combination concentrates more easily
SUPER_PER_DAY = 1                   # BRAIN_RULES G11
SHARPE_BAR = 1.58                   # the regular D1 bar, used only to word a diagnosis; BRAIN's checks decide

# Names seen in BRAIN's own examples and the community sources above. Anything else only gets a warning: Gold may
# see a different list, and BRAIN's error message is the authority.
SELECTION_VARIABLES = {
    "own", "color", "self_correlation", "prod_correlation", "turnover", "long_count", "short_count",
    "operator_count", "datacategory_count", "datacategories", "decay", "universe", "region", "delay",
    "neutralization", "sharpe", "fitness", "returns", "drawdown", "margin", "true", "false"}
SELECTION_FUNCTIONS = {"in", "not", "sqrt", "abs", "log", "min", "max", "universe_size", "if_else"}
COMBO_VARIABLES = {"alpha", "stats", "returns", "pnl", "nan", "true", "false"}
COMBO_FUNCTIONS = {
    "generate_stats", "combo_a", "ts_ir", "ts_std_dev", "ts_sum", "ts_mean", "ts_rank", "ts_zscore", "ts_delay",
    "self_corr", "reduce_max", "reduce_min", "reduce_avg", "reduce_sum", "reduce_powersum", "reduce_count",
    "if_else", "max", "min", "sqrt", "abs", "log", "sign", "rank", "is_nan"}


# ------------------------------------------------------------------------------------------------------ recipes
@dataclass(frozen=True)
class Recipe:
    key: str
    name: str
    code: str
    why: str


def _cap(limit: int) -> int:
    return OPERATOR_LIMIT // max(int(limit or MIN_SELECTION), MIN_SELECTION)


def selections(limit: int = 30) -> List[Recipe]:
    """Rankings over alpha properties, each keeping the pool diverse in its own way. Every one caps an alpha's
    operators at 8,000 / limit so the kept alphas never pass BRAIN's ceiling together; a failed condition scores 0,
    which POSITIVE drops. Structure after Alpha Harness (MIT); the reasons are HYPOLAB's."""
    budget = f"(operator_count <= {_cap(limit)})"
    return [
        Recipe("least_corr", "Least correlated",
               f"{budget} * (self_correlation < 0.7) * (1 - prod_correlation)",
               "A combination only beats its parts when the parts disagree: keep the alphas least like each other "
               "and least like the production pool. The safe first try."),
        Recipe("tradeable", "Tradeable turnover",
               f"{budget} * (turnover >= 0.02) * (turnover < 0.35) * (1 - self_correlation)",
               "Very slow alphas add little day to day and very fast ones push the combination past the 40% "
               "turnover ceiling: keep the middle, least correlated first."),
        Recipe("many_sources", "Many data sources",
               f"{budget} * (1 + datacategory_count) * (1 - prod_correlation)",
               "Alphas built on different data fail at different times; favour those that touch more categories "
               "and are least like the production pool."),
        Recipe("slow_core", "Slow core",
               f"{budget} * (turnover < 0.25) / (turnover + 0.05)",
               "Slow alphas keep their edge after costs and correlate less with the fast pool: build a calm, "
               "low-turnover core."),
        Recipe("broad_books", "Broad books",
               f"{budget} * (long_count + short_count) / sqrt(universe_size(universe))",
               "Alphas that hold many stocks spread risk; a few concentrated books dominate a combination's "
               "drawdowns."),
    ]


COMBOS: List[Recipe] = [
    Recipe("equal", "Equal weight", "1",
           "No estimation, nothing to overfit: every kept alpha counts the same. The baseline every other weighting "
           "must beat."),
    Recipe("inv_vol", "Inverse volatility",
           "stats = generate_stats(alpha);\n1 / (ts_std_dev(stats.returns, 120) + 0.0001)",
           "Each alpha contributes about the same risk, so one volatile alpha cannot drive the combination."),
    Recipe("rolling_ir", "Rolling IR (positive only)",
           "stats = generate_stats(alpha);\nmax(ts_ir(stats.returns, 250), 0)",
           "Lean on alphas that have earned their keep over the last year; one that stopped working gets 0. "
           "Chases recent winners, so check the test period."),
    Recipe("least_crowded", "Least crowded",
           "stats = generate_stats(alpha);\ninnerCorr = self_corr(stats.returns, 500);\n"
           "ic = if_else(innerCorr == 1.0, nan, innerCorr);\nmaxCorr = reduce_max(ic);\nmax(1 - maxCorr, 0.05)",
           "Down-weight an alpha that moves with another kept alpha: two copies of one idea should not count "
           "twice."),
    Recipe("combo_a", "BRAIN's combo_a",
           "combo_a(alpha)",
           "BRAIN's own built-in weighting (seen in BRAIN examples; how it weights is not documented here). Try it "
           "once the others give a baseline."),
]


def recipe(kind: str, key: str, limit: int = 30) -> Optional[Recipe]:
    pool = selections(limit) if kind == "selection" else COMBOS
    return next((r for r in pool if r.key == key), None)


def match_recipe(kind: str, code: str, limit: int = 30) -> Optional[Recipe]:
    """The library recipe a piece of code is (whitespace and the operator cap ignored), if any."""
    norm = _norm(code)
    pool = selections(limit) if kind == "selection" else COMBOS
    for r in pool:
        if _norm(r.code) == norm:
            return r
    if kind == "selection":                    # the same recipe at another limit (another operator cap)
        bare = re.sub(r"\(operator_count <= \d+\)", "(operator_count <= N)", norm)
        for r in pool:
            if re.sub(r"\(operator_count <= \d+\)", "(operator_count <= N)", _norm(r.code)) == bare:
                return r
    return None


def _norm(code: str) -> str:
    return " ".join(str(code or "").replace(";", "; ").split()).replace(" ;", ";")


# ---------------------------------------------------------------------------------------------------- payload
def make_payload(selection: str, combo: str, region: str, universe: Optional[str] = None, delay: int = 1,
                 decay: int = DEFAULT_DECAY, neutralization: str = "SUBINDUSTRY",
                 truncation: float = DEFAULT_TRUNCATION, selection_limit: int = 30,
                 selection_handling: str = "POSITIVE", component_activation: str = "IS",
                 test_period: str = "P2Y", max_trade: Optional[str] = None) -> dict:
    """The body of POST /simulations for one SuperAlpha (shape from Alpha Harness: expressions at the top level,
    the three SuperAlpha settings inside `settings`)."""
    reg = config.REGION_DEFAULTS.get(region, {})
    universe = universe or reg.get("universe") or "TOP3000"
    return {
        "type": "SUPER",
        "settings": {
            "instrumentType": "EQUITY", "region": region, "universe": universe, "delay": int(delay),
            "decay": int(decay), "neutralization": neutralization, "truncation": float(truncation),
            "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
            "maxTrade": max_trade or reg.get("max_trade", "OFF"), "language": "FASTEXPR", "visualization": False,
            "testPeriod": test_period, "selectionLimit": int(selection_limit),
            "selectionHandling": selection_handling, "componentActivation": component_activation,
        },
        "selection": selection.strip(),
        "combo": combo.strip(),
    }


def journal_text(selection: str, combo: str, settings: dict) -> str:
    """What the journal stores as the experiment's expression: both expressions and the SuperAlpha settings, so the
    duplicate check (expression + settings fingerprint) tells two SuperAlphas apart."""
    return (f"SELECTION (limit {settings.get('selectionLimit')}, {settings.get('selectionHandling')}, "
            f"{settings.get('componentActivation')}): {_norm(selection)}\nCOMBO: {_norm(combo)}")


def split_journal_text(text: str) -> Dict[str, str]:
    m = re.match(r"SELECTION \([^)]*\): (.*)\nCOMBO: (.*)", str(text or ""), re.S)
    return {"selection": m.group(1), "combo": m.group(2)} if m else {"selection": "", "combo": str(text or "")}


def pool_id(region: str, delay: int, day: Optional[dt.date] = None) -> str:
    """The journal idea a SuperAlpha try counts against: one pool (region, delay) per quarter."""
    d = day or dt.date.today()
    return f"SUPER@{region}-D{int(delay)}@{d.year}Q{(d.month - 1) // 3 + 1}"


def is_pool_id(idea_id: str) -> bool:
    return str(idea_id or "").startswith("SUPER@")


# ------------------------------------------------------------------------------------------------- the checks
@dataclass
class CheckReport:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def markdown(self) -> str:
        if not self.errors and not self.warnings:
            return "Checks: nothing to fix."
        return "\n".join([f"- **ERROR** {e}" for e in self.errors] + [f"- warning: {w}" for w in self.warnings])


def _syntax(text: str, label: str, errors: List[str]) -> None:
    s = str(text or "")
    if not s.strip():
        errors.append(f"{label}: empty")
        return
    depth = 0
    for ch in s:
        depth += ch == "("
        depth -= ch == ")"
        if depth < 0:
            errors.append(f"{label}: a ')' closes nothing")
            return
    if depth:
        errors.append(f"{label}: {depth} '(' never closed")
    if s.count("'") % 2 or s.count('"') % 2:
        errors.append(f"{label}: a quote is not closed")


def _names(text: str) -> tuple:
    """(called names, other names) in an expression, string literals and number literals left out."""
    s = re.sub(r"'[^']*'|\"[^\"]*\"", " ", str(text or ""))
    called = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", s))
    allnames = set(re.findall(r"(?<![\w.])([A-Za-z_][A-Za-z0-9_]*)", s))
    return called, allnames - called


def check(selection: str, combo: str, selection_limit: int = 30, selection_handling: str = "POSITIVE",
          component_activation: str = "IS", decay: Optional[int] = None,
          truncation: Optional[float] = None) -> CheckReport:
    """Checks before any simulation: syntax, settings, names BRAIN's examples use. Unknown names are warnings."""
    rep = CheckReport()
    _syntax(selection, "selection", rep.errors)
    _syntax(combo, "combo", rep.errors)
    try:
        lim = int(selection_limit)
    except (TypeError, ValueError):
        lim = 0
    if lim < MIN_SELECTION:
        rep.errors.append(f"selection limit {selection_limit}: BRAIN keeps at least {MIN_SELECTION} alphas")
    elif lim > MAX_SELECTION:
        rep.warnings.append(f"selection limit {lim}: more than {MAX_SELECTION} alphas is unusual - check the pool")
    if selection_handling not in SELECTION_HANDLING:
        rep.errors.append(f"selection handling {selection_handling!r}: one of {', '.join(SELECTION_HANDLING)}")
    if component_activation not in COMPONENT_ACTIVATION:
        rep.errors.append(f"component activation {component_activation!r}: IS or OS")
    if decay is not None and (int(decay) < 0 or int(decay) > 512):
        rep.errors.append(f"decay {decay}: 0-512")
    if truncation is not None and not (0 <= float(truncation) <= 1):
        rep.errors.append(f"truncation {truncation}: between 0 and 1")
    if rep.errors:
        return rep
    called, names = _names(selection)
    unknown = sorted((called - SELECTION_FUNCTIONS) | (names - SELECTION_VARIABLES))
    if unknown:
        rep.warnings.append(f"selection uses {', '.join(unknown)}: not in the names BRAIN's examples use - BRAIN "
                            "will say if it does not know them")
    if "operator_count" not in names:
        rep.warnings.append(f"selection has no operator cap: BRAIN drops alphas past {OPERATOR_LIMIT:,} operators "
                            f"in all; add (operator_count <= {_cap(lim)}) * ...")
    if selection_handling == "POSITIVE" and re.fullmatch(r"\s*own\s*", selection or ""):
        rep.warnings.append("selection 'own' scores every alpha the same: the limit then keeps an arbitrary subset")
    statements = [x.strip() for x in re.split(r";|\n", combo or "") if x.strip()]
    assigned = {m.group(1) for x in statements for m in [re.match(r"([A-Za-z_]\w*)\s*=(?!=)", x)] if m}
    called, names = _names(combo)
    unknown = sorted((called - COMBO_FUNCTIONS) | (names - COMBO_VARIABLES - assigned))
    if unknown:
        rep.warnings.append(f"combo uses {', '.join(unknown)}: not in the names BRAIN's examples use - BRAIN will say "
                            "if it does not know them")
    if statements and re.match(r"[A-Za-z_]\w*\s*=(?!=)", statements[-1]):
        rep.errors.append("combo: the last statement must be the weight, not an assignment")
    if "generate_stats" in combo and "stats" not in assigned:
        rep.warnings.append("combo calls generate_stats(alpha) without keeping it (stats = generate_stats(alpha);)")
    return rep


# ---------------------------------------------------------------------------------------- selection evaluator
class SelectionError(ValueError):
    pass


_BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
           ast.Div: lambda a, b: a / b if b else math.nan, ast.Pow: lambda a, b: a ** b}
_CMPS = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b,
         ast.GtE: lambda a, b: a >= b, ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b}


def _to_python(text: str) -> str:
    s = str(text or "").strip()
    s = s.replace("&&", " and ").replace("||", " or ")
    s = re.sub(r"!(?!=)", " not ", s)
    s = re.sub(r"\bin\s*\(", "_in(", s)
    s = re.sub(r"\btrue\b", "True", s)
    s = re.sub(r"\bfalse\b", "False", s)
    return s


def universe_size(universe) -> float:
    m = re.search(r"(\d+)", str(universe or ""))
    return float(m.group(1)) if m else math.nan


def eval_selection(text: str, props: dict) -> float:
    """One alpha's selection score, the way BRAIN would compute it - as far as HYPOLAB knows the language.

    Used by the sandbox (which plays BRAIN) and by the pool preview. Raises SelectionError for a property the
    alpha does not have (the preview cannot know correlations BRAIN has not computed)."""
    try:
        tree = ast.parse(_to_python(text), mode="eval")
    except SyntaxError as e:
        raise SelectionError(f"cannot read the selection ({e.msg})") from None
    funcs: Dict[str, Callable] = {
        "_in": lambda xs, v: float(v in (xs or [])), "not": lambda x: float(not x),
        "sqrt": lambda x: math.sqrt(x) if x >= 0 else math.nan, "abs": abs,
        "log": lambda x: math.log(x) if x > 0 else math.nan, "min": min, "max": max,
        "universe_size": lambda u: props.get("_universe_size") or universe_size(u),
        "if_else": lambda c, a, b: a if c else b}

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            if n.id in ("True", "False"):
                return n.id == "True"
            if n.id not in props or props[n.id] is None:
                raise SelectionError(f"'{n.id}' is not known for this alpha")
            v = props[n.id]
            return v
        if isinstance(n, ast.BoolOp):
            vals = [bool(_num(ev(v))) for v in n.values]
            return float(all(vals) if isinstance(n.op, ast.And) else any(vals))
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            if isinstance(n.op, ast.Not):
                return float(not _num(v))
            return -_num(v) if isinstance(n.op, ast.USub) else _num(v)
        if isinstance(n, ast.BinOp) and type(n.op) in _BINOPS:
            return _BINOPS[type(n.op)](_num(ev(n.left)), _num(ev(n.right)))
        if isinstance(n, ast.Compare):
            left, ok = ev(n.left), True
            for op, right_n in zip(n.ops, n.comparators):
                right = ev(right_n)
                if type(op) not in _CMPS:
                    raise SelectionError("unsupported comparison")
                a, b = (left, right) if isinstance(left, str) or isinstance(right, str) else (_num(left), _num(right))
                ok = ok and bool(_CMPS[type(op)](a, b))
                left = right
            return float(ok)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in funcs:
            return funcs[n.func.id](*[ev(a) for a in n.args])
        raise SelectionError(f"'{ast.unparse(n)[:40]}' is outside what HYPOLAB can evaluate")

    v = ev(tree)
    try:
        return float(v)
    except (TypeError, ValueError):
        raise SelectionError("the selection does not give a number") from None


def _num(v) -> float:
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    raise SelectionError(f"{v!r} is not a number")


def apply_selection(text: str, alphas: Sequence[dict], limit: int, handling: str = "POSITIVE") -> pd.DataFrame:
    """Score every alpha, keep those the handling allows, best first, top `limit` marked `kept`."""
    rows = []
    for a in alphas:
        try:
            s = eval_selection(text, a)
            err = ""
        except SelectionError as e:
            s, err = math.nan, str(e)
        rows.append({"alpha_id": a.get("alpha_id"), "score": s, "error": err})
    df = pd.DataFrame(rows, columns=["alpha_id", "score", "error"])
    if df.empty:
        df["kept"] = []
        return df
    if handling == "POSITIVE":
        ok = df["score"] > 0
    elif handling == "NON_ZERO":
        ok = df["score"].notna() & (df["score"] != 0)
    else:
        ok = df["score"].notna()
    df["eligible"] = ok.fillna(False)
    df = df.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)
    rank = df["eligible"].cumsum()
    df["kept"] = df["eligible"] & (rank <= int(limit))
    return df


# --------------------------------------------------------------------------------------------------- the pools
def pool_alphas(journal=None, catalog=None, brain=None) -> pd.DataFrame:
    """Your submitted REGULAR alphas with the properties a selection can read: from the Account download (live) or
    the sandbox's own submissions. Correlations are only known in the sandbox (BRAIN computes them itself)."""
    cols = ["alpha_id", "region", "delay", "universe", "turnover", "sharpe", "fitness", "decay", "operator_count",
            "datacategories", "datacategory_count", "neutralization"]
    if brain is not None and getattr(brain, "is_mock", False):
        return pd.DataFrame(brain.super_pool_props(), columns=cols + ["self_correlation", "prod_correlation",
                                                                      "long_count", "short_count", "_universe_size"])
    if journal is None:
        return pd.DataFrame(columns=cols)
    from . import account
    from .rules import GROUPING_FIELDS, delay_of
    df = account.account_alphas(journal)
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = df[(df["type"].fillna("REGULAR") == "REGULAR") & df["date_submitted"].notna()]
    maps: Dict[tuple, dict] = {}
    out = []
    for r in df.itertuples(index=False):
        d = delay_of(r.delay)
        key = (r.region, d)
        if key not in maps:
            maps[key] = {}
            if catalog is not None:
                try:
                    f = catalog.fields(r.region, None, d, enrich=False)
                    maps[key] = dict(zip(f["id"], f["category"])) if not f.empty else {}
                except Exception:  # noqa: BLE001
                    maps[key] = {}
        cats = sorted({account._norm_cat(maps[key][x]) for x in (r.fields or []) if x in maps[key]
                       and x not in GROUPING_FIELDS})
        out.append({"alpha_id": r.alpha_id, "region": r.region, "delay": d, "universe": r.universe,
                    "turnover": r.turnover, "sharpe": r.sharpe, "fitness": r.fitness, "decay": r.decay,
                    "operator_count": len(r.operators or []), "datacategories": cats,
                    "datacategory_count": len(cats) if cats else None, "neutralization": r.neutralization})
    return pd.DataFrame(out, columns=cols)


def suggested_limit(n: int) -> Optional[int]:
    """About two thirds of the pool, at least BRAIN's 10, at most 60: room for the selection to choose."""
    if n < MIN_SELECTION:
        return None
    return int(max(MIN_SELECTION, min(60, round(n * 2 / 3))))


def pools(alphas: pd.DataFrame) -> pd.DataFrame:
    """One row per region and delay: how many submitted alphas, how varied, whether a SuperAlpha can be built."""
    cols = ["region", "delay", "alphas", "categories", "median_turnover", "median_sharpe", "ready", "limit"]
    if alphas is None or alphas.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for (region, delay), g in alphas.groupby(["region", "delay"]):
        cats = sorted({c for cs in g["datacategories"] for c in (cs or [])})
        n = len(g)
        rows.append({"region": region, "delay": int(delay), "alphas": n, "categories": ", ".join(cats) or "?",
                     "median_turnover": round(float(g["turnover"].median()), 3) if g["turnover"].notna().any() else None,
                     "median_sharpe": round(float(g["sharpe"].median()), 2) if g["sharpe"].notna().any() else None,
                     "ready": n >= MIN_SELECTION, "limit": suggested_limit(n)})
    return pd.DataFrame(rows, columns=cols).sort_values(["ready", "alphas"], ascending=False).reset_index(drop=True)


def preview(selection: str, alphas: pd.DataFrame, region: str, delay: int, limit: int,
            handling: str = "POSITIVE") -> Dict[str, object]:
    """Which of your alphas a selection would keep - before spending a simulation. Live, BRAIN knows properties
    HYPOLAB does not (correlations, long/short counts): then the preview says so instead of guessing."""
    if alphas is None or alphas.empty:
        return {"ok": False, "note": "no submitted alphas known: download your account (cockpit > Account)",
                "table": pd.DataFrame()}
    pool = alphas[(alphas["region"] == region) & (alphas["delay"].astype(int) == int(delay))]
    recs = []
    for r in pool.to_dict("records"):
        recs.append({k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()}
                    | {"own": True, "color": "NONE"})
    sel = apply_selection(selection, recs, limit, handling)
    unknown = sorted({e.split("'")[1] for e in sel["error"] if e and "'" in e}) if not sel.empty else []
    if unknown:
        return {"ok": False, "note": f"the preview needs {', '.join(unknown)}, which only BRAIN knows for your "
                                     "alphas - the simulation will apply it", "table": sel}
    kept = int(sel["kept"].sum()) if not sel.empty else 0
    note = f"{kept} of {len(pool)} alphas kept"
    if kept < MIN_SELECTION:
        note += f" - fewer than {MIN_SELECTION}: loosen the selection or wait for more submissions"
    return {"ok": True, "note": note, "kept": kept, "table": sel}


# ------------------------------------------------------------------------------------------------- the unlock
def unlock_status(store=None, journal=None, sandbox: bool = False) -> Dict[str, object]:
    """Lifetime REGULAR submissions against the 100 that unlock SuperAlphas, and today's SuperAlpha count."""
    st = config.settings()
    unlock = int(st.get("superalpha_unlock_after", 100))
    lifetime, source = 0, "none"
    if journal is not None:
        try:
            from . import account
            if account.last_sync(journal):
                lifetime, source = int(account.counts(journal)["lifetime_regular"]), "account download"
        except Exception:  # noqa: BLE001
            pass
    if store is not None:
        try:
            from ideaengine import planner
            lt = planner.lifetime_submitted(store, journal)
            if lt > lifetime:
                lifetime, source = lt, ("account download + HYPOLAB's submissions since" if source != "none"
                                        else "Week page count")
            unlock = int(store.lifetime().get("unlock") or unlock)
        except Exception:  # noqa: BLE001
            pass
    today = journal.super_submissions_today() if journal is not None and hasattr(journal, "super_submissions_today") \
        else 0
    unlocked = sandbox or lifetime >= unlock
    return {"lifetime": lifetime, "unlock_at": unlock, "to_unlock": max(0, unlock - lifetime), "unlocked": unlocked,
            "source": source, "sandbox": sandbox, "today": today, "cap": SUPER_PER_DAY,
            "left_today": max(0, SUPER_PER_DAY - today)}


def unlock_line(s: dict) -> str:
    if s["sandbox"]:
        return (f"Sandbox: SuperAlphas are open for practice (BRAIN unlocks them after 100 submitted alphas). "
                f"SuperAlphas today: {s['today']}/{s['cap']}.")
    if s["unlocked"]:
        return (f"**Unlocked** ({s['lifetime']} lifetime alphas). SuperAlphas today: {s['today']}/{s['cap']}.")
    return (f"**Locked**: {s['lifetime']}/{s['unlock_at']} lifetime alphas ({s['to_unlock']} to go; count from the "
            f"{s['source']}). Plan and preview now; simulating waits for the unlock.")


# ------------------------------------------------------------------------------------------------- diagnosis
CORR_CHECKS = {"SELF_CORRELATION", "PROD_CORRELATION", "POWER_POOL_CORRELATION"}


def diagnose(summary: dict, settings: dict, trials_so_far: int = 0):
    """One verdict and the next ONE change for a SuperAlpha (BRAIN's checks decide; this words them)."""
    from .diagnose import Action, Diagnosis
    from .rules import fitness_label
    status = summary.get("status")
    if status in ("ERROR", "REJECTED", "FAIL", "GONE") or not summary.get("alpha_id"):
        msg = str(summary.get("error") or "BRAIN did not return a SuperAlpha")[:400]
        return Diagnosis("ERROR", "BRAIN refused this SuperAlpha", [msg],
                         [Action("Fix what BRAIN says", "usually a name BRAIN does not know in the selection or combo, "
                                 "or a setting outside its range - nothing else changes", kind="fix")], {})
    s = summary.get("is_sharpe")
    s = float(s) if s is not None else 0.0
    t = summary.get("is_turnover")
    fit = summary.get("is_fitness")
    metrics = {"sharpe": s, "fitness": fit, "turnover": t, "returns": summary.get("is_returns"),
               "drawdown": summary.get("is_drawdown"), "train_sharpe": summary.get("train_sharpe"),
               "test_sharpe": summary.get("test_sharpe"),
               "fitness_label": fitness_label(fit, int(settings.get("delay", 1) or 1)) if fit is not None else ""}
    failed = set(summary.get("failed") or [])
    findings, actions = [], []
    lo, hi = TURNOVER_BAND
    if t is not None and t > hi:
        findings.append(f"Turnover {t:.1%} is above the {hi:.0%} a SuperAlpha must stay under.")
        actions.append(Action("Raise the decay", f"decay {settings.get('decay')} -> {max(10, int(settings.get('decay') or 0) * 2)}: "
                              "smooths the daily weights; nothing else changes", kind="climb",
                              settings={"decay": max(10, int(settings.get("decay") or 0) * 2)}))
    elif t is not None and t < lo:
        findings.append(f"Turnover {t:.1%} is below the {lo:.0%} floor.")
        actions.append(Action("Lower the decay, or select 'Tradeable turnover'", "a combination of very slow alphas "
                              "barely trades; one change only", kind="climb"))
    if failed & CORR_CHECKS:
        findings.append(f"Correlation check fails: {', '.join(sorted(failed & CORR_CHECKS))}.")
        actions.append(Action("Select 'Least correlated' (or weight 'Least crowded')", "the combination looks like "
                              "alphas already in the pool; keep the selection that drops them", kind="climb"))
    trs, tes = summary.get("train_sharpe"), summary.get("test_sharpe")
    if trs and tes is not None and tes < 0.5 * trs:
        findings.append(f"Test-period Sharpe {tes:.2f} vs train {trs:.2f}: the weighting may chase the past.")
        actions.append(Action("Go back to Equal weight", "estimated weights (Rolling IR) can fit the train years; "
                              "equal weight cannot", kind="climb"))
    other = sorted(failed - CORR_CHECKS - {"HIGH_TURNOVER", "LOW_TURNOVER"})
    if other:
        findings.append(f"BRAIN checks failing: {', '.join(other)}.")
    if abs(s) < 0.5:
        verdict, head = "NOISE", f"the combination shows no reliable signal (Sharpe {s:.2f})"
        actions.append(Action("Stop on this pool for now", "more tries buy luck; the pool needs better or more "
                              "varied alphas first", kind="stop"))
    elif not failed and s > 0:
        verdict, head = "PASS", f"BRAIN's checks pass (Sharpe {s:.2f})"
        _n = max(1, trials_so_far + 1)
        actions.insert(0, Action("Run the SuperAlpha gate", "checks, correlations and the deflated Sharpe over "
                                 f"{_n} tr{'y' if _n == 1 else 'ies'} on this pool", kind="accept"))
    elif s >= 0.75 * SHARPE_BAR and len(failed) <= 1:
        verdict, head = "NEAR", f"one check stands in the way (Sharpe {s:.2f})"
    else:
        verdict, head = "WEAK", f"some signal, short of the bar (Sharpe {s:.2f})"
        if "LOW_SHARPE" in failed or "LOW_FITNESS" in failed or not actions:
            actions.append(Action("Try ONE other weighting: Inverse volatility", "equal weight lets a volatile alpha "
                                  "dominate; one change, then re-read", kind="climb"))
    if s < 0:
        findings.append("A negative SuperAlpha from submitted alphas usually means the weighting fights the alphas "
                        "(e.g. a combo that can turn negative).")
    findings.append(f"{trials_so_far + 1} SuperAlpha tr{'y' if trials_so_far == 0 else 'ies'} on this pool this "
                    "quarter; the gate deflates the Sharpe for every one.")
    return Diagnosis(verdict, head, findings, actions, metrics)


def recipe_names(selection: str, combo: str, limit: int) -> str:
    s = match_recipe("selection", selection, limit)
    c = match_recipe("combo", combo, limit)
    return f"{s.name if s else 'custom selection'} x {c.name if c else 'custom combo'}"


def ladder_note() -> str:
    return ("Start with **Least correlated x Equal weight** at decay 4. Then change ONE thing per try - the "
            "weighting, OR the selection, OR the decay - and only for the reason the diagnosis gives.")


def sources_note() -> str:
    return ("Facts behind this tab: BRAIN's Genius page (unlock at 100 alphas, 1 SuperAlpha a day); the request "
            "format, the 10-alpha minimum, the 8,000-operator ceiling and the 2%-40% turnover band from Alpha Harness "
            "(MIT, built against the live API); selection/combo names from BRAIN examples quoted in wqbkit. BRAIN's "
            "own checks are the authority.")


__all__ = ["FAMILY", "PURPOSE", "Recipe", "selections", "COMBOS", "make_payload", "check", "eval_selection",
           "apply_selection", "pool_alphas", "pools", "preview", "unlock_status", "diagnose", "pool_id"]

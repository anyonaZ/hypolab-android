"""The research workflow in one object - what the cockpit's Lab calls.

    from hypolab.research import Researcher
    R = Researcher.sandbox()          # offline practice (synthetic data)
    R = Researcher.live()             # your BRAIN account

    cards = R.ideas("USA")            # economics-first idea cards for a region
    R.show(cards[0])                  # story, data, ladder, settings
    t = R.test(cards[0])              # lint -> budget -> dedupe -> simulate -> diagnose -> journal
    t2 = R.test(cards[0], rung=1)     # climb one rung, OR:
    t2 = R.follow(t, 0)               # apply the diagnosis' first suggested action
    rb = R.robustness(t2)             # WorldQuant's robustness battery
    g = R.gate(t2, rb)                # submission gate report (+ written description)
    R.submit(g, confirm="SUBMIT <alpha_id>")   # only you can do this

Guard rails that the zip's notebooks lacked: every expression is linted
before it can cost a simulation; every simulation is journaled; the same
expression+settings is never simulated twice; each idea has a simulation
budget; the count of tries feeds the deflated-Sharpe check at the gate.
"""
from __future__ import annotations

import json

import math
import re
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from . import config, decorr, robustness as rob, rules
from .brain import make_payload, quota as brain_quota, summarize_alpha
from .catalog import Catalog
from .diagnose import Diagnosis, diagnose, flip, split_statements, wrap_result
from .hypotheses import load_library
from .ideas import IdeaCard, _score, build_card, explore_dataset, generate_ideas, ideas_table
from .journal import Journal
from .linter import Linter
from .overfit import deflated_sharpe, noise_bar, verdict as dsr_verdict
from .pyramids import PyramidTracker


def display_md(text: str):
    try:
        from IPython.display import Markdown, display
        display(Markdown(text))
    except ImportError:
        print(text)


@dataclass
class TestResult:
    card: Optional[IdeaCard]
    rung: str
    expression: str
    settings: dict
    summary: dict
    diagnosis: Diagnosis
    cached: bool = False
    idea_id: Optional[str] = None      # journal idea the try counts against (set for re-runs of submitted alphas)

    @property
    def key(self) -> str:
        return self.idea_id or (self.card.id if self.card else f"manual@{self.settings.get('region')}")

    @property
    def alpha_id(self) -> Optional[str]:
        return self.summary.get("alpha_id")

    def markdown(self) -> str:
        head = f"**{self.card.hypothesis.id if self.card else (self.idea_id or 'manual')} / {self.rung}**"
        if self.cached:
            head += " (from journal - not re-simulated)"
        s = self.settings
        return (f"{head}  alpha `{self.alpha_id}`\n```\n{self.expression}\n```\n"
                f"`{s.get('region')} {s.get('universe')} D{s.get('delay')} | neut {s.get('neutralization')} | "
                f"decay {s.get('decay')} | trunc {s.get('truncation')}`\n\n" + self.diagnosis.markdown())


@dataclass
class GateReport:
    alpha_id: str
    ready: bool
    reasons: List[str]
    table: pd.DataFrame
    description: str
    dsr: dict = field(default_factory=dict)
    # 1.10.2: set when the Researcher issues the report; submit() accepts only a report it issued, READY when issued,
    # for the same alpha and kind, and recent (changing `ready` on the object changes nothing)
    token: str = ""
    issued_at: float = 0.0
    kind: str = "alpha"

    def markdown(self) -> str:
        status = ('<span class="hl-verdict hl-v-ready">READY TO SUBMIT</span> (your decision)' if self.ready
                  else '<span class="hl-verdict hl-v-notready">NOT READY</span>')
        lines = [f"### Submission gate for `{self.alpha_id}`: {status}", ""]
        lines += [f"- {r}" for r in self.reasons]
        lines += ["", "**Description to store with the alpha:**", "", "```", self.description, "```"]
        return "\n".join(lines)


_NO_EVIDENCE = ("{label}: no evidence - BRAIN's check has no row for it and HYPOLAB could not read it. The gate never "
                "passes without it: press Check Submission on the platform, then run the gate again")
_NO_DSR = ("could not compute the deflated Sharpe (PnL unavailable) - the gate never passes without the overfitting "
           "check: run it again when BRAIN returns the PnL")


def _platform_checks(checks: pd.DataFrame, reasons: List[str]) -> bool:
    """BRAIN's /check rows -> pass? (1.10.2: an empty answer is missing evidence, never a pass)."""
    if checks is None or checks.empty or "result" not in checks.columns:
        if not any(r.startswith("could not fetch /check") for r in reasons):
            reasons.append("BRAIN returned no platform checks for this alpha - the gate never passes without them: "
                           "run it again in a minute (or open the alpha on the platform)")
        return False
    fails = checks[checks["result"] == "FAIL"]["name"].tolist()
    pend = checks[checks["result"] == "PENDING"]["name"].tolist()
    if fails:
        reasons.append(f"platform checks FAIL: {', '.join(fails)}")
    if pend:
        reasons.append(f"platform checks PENDING: {', '.join(pend)} - re-run the gate later")
    if not fails and not pend:
        reasons.append("all platform checks pass")
    return not fails and not pend


def _holdout(summary: dict, reasons: List[str]) -> bool:
    """Train vs test Sharpe (BRAIN's 2-year test period). 1.10.2: a missing split blocks; a train Sharpe of 0 is
    no longer skipped as if it were missing."""
    trs, tes = summary.get("train_sharpe"), summary.get("test_sharpe")
    if trs is None or tes is None or trs != trs or tes != tes:
        reasons.append("no train/test split in this result - the gate never passes without the out-of-sample check: "
                       "simulate it again (HYPOLAB always asks BRAIN for a 2-year test period)")
        return False
    if trs <= 0:
        reasons.append(f"train Sharpe {trs:.2f}: no positive edge in the selection window")
        return False
    if tes < 0.5 * trs:
        reasons.append(f"test-period Sharpe {tes:.2f} vs train {trs:.2f}: weak out of the selection window")
        return False
    reasons.append(f"test-period Sharpe {tes:.2f} vs train {trs:.2f}: holds up")
    return True


def _combine(base: str, booster: str, mode: str = "add") -> str:
    """Two (possibly multi-statement) expressions -> one FastExpression, variables kept apart."""
    def as_var(expr: str, name: str) -> List[str]:
        parts = split_statements(expr)
        assigned = [m.group(1) for p in parts[:-1] for m in [re.match(r"^([A-Za-z_]\w*)\s*=(?!=)", p)] if m]
        out = []
        for p in parts:
            for v in assigned:
                p = re.sub(rf"\b{re.escape(v)}\b", f"{name}_{v}", p)
            out.append(p)
        last = out[-1]
        m = re.match(r"^([A-Za-z_]\w*)\s*=(?!=)\s*(.+)$", last, re.S)
        out[-1] = f"{name} = {m.group(2) if m else last}"
        return out
    lines = as_var(base, "base_sig") + as_var(booster, "boost_sig")
    final = "min(rank(base_sig), rank(boost_sig))" if mode == "and" else "rank(base_sig) + rank(boost_sig)"
    return ";\n".join(lines + [final])


@dataclass
class BoostReport:
    base: "TestResult"
    base_sharpe: float
    table: pd.DataFrame
    results: dict
    best: Optional["TestResult"]
    notes: List[str]
    boosters: dict = field(default_factory=dict)     # booster card id -> its solo TestResult (1.4.3)

    def lab_results(self) -> List["TestResult"]:
        """What the Lab adds to its results list: each booster alone, then the combinations, the best LAST
        (so it is the one selected and shown, with its PnL)."""
        combos = [r for r in self.results.values() if r is not self.best]
        out = [b for b in self.boosters.values() if b.alpha_id] + combos
        return out + ([self.best] if self.best is not None else [])

    def alpha_ids(self) -> set:
        ids = {self.base.alpha_id} | {r.alpha_id for r in self.results.values()} | \
            {b.alpha_id for b in self.boosters.values()}
        return {a for a in ids if a}

    def markdown(self) -> str:
        b = self.base
        lines = [f"### Boosting `{b.card.hypothesis.id if b.card else 'manual'}` (Sharpe {self.base_sharpe:.2f})", ""]
        lines += [f"- {n}" for n in self.notes]
        lines.append("Predicted combined Sharpe = (S1 + S2) / sqrt(2 x (1 + correlation)). A booster helps when it has "
                     "its own signal AND low correlation with your alpha.")
        if self.best is not None:
            s = self.best.summary
            lines += ["", f"**Best combination:** {self.best.rung} - Sharpe {s.get('is_sharpe')}, fitness "
                      f"{s.get('is_fitness')}, verdict **{self.best.diagnosis.verdict}**", "```",
                      self.best.expression, "```",
                      "Next: `R.robustness(...)` and `R.gate(...)` on `report.best`. Don't also submit the booster "
                      "alone - the two would be correlated."]
        else:
            lines += ["", "No combination was worth simulating or none improved the alpha. That is information: "
                      "this idea may need a better construction (next rung), not a partner."]
        return "\n".join(lines)


@dataclass
class DecorrReport:
    """Researcher.decorrelate(): what was tried to lower correlation, and what it cost in Sharpe (1.6.0)."""
    base: "TestResult"
    base_sharpe: float
    base_prod: Optional[float]
    table: pd.DataFrame
    results: List["TestResult"]
    best: Optional["TestResult"]
    style_corr: dict
    own_corr: List[dict]
    lesson: str
    notes: List[str] = field(default_factory=list)

    def lab_results(self) -> List["TestResult"]:
        rest = [r for r in self.results if r is not self.best and r.alpha_id]
        return rest + ([self.best] if self.best is not None else [])

    def alpha_ids(self) -> set:
        return {a for a in [self.base.alpha_id] + [r.alpha_id for r in self.results] if a}

    def markdown(self) -> str:
        bp = "?" if self.base_prod is None else f"{self.base_prod:.2f}"
        lines = [f"### Lowering correlation (base Sharpe {self.base_sharpe:.2f}, production correlation {bp})", ""]
        lines += [f"- {n}" for n in self.notes]
        if self.style_corr:
            lines.append("- PnL correlation with crowded styles: " + ", ".join(
                f"{k} {v:+.2f}" for k, v in sorted(self.style_corr.items(), key=lambda kv: -abs(kv[1]))))
        if self.own_corr:
            lines.append("- Your most similar submitted alphas: " + ", ".join(
                f"{o['alpha_id']} {o['corr']:.2f}" for o in self.own_corr[:3]))
        if self.best is not None:
            s = self.best.summary
            lines += ["", f"**Recommended:** {self.best.rung} - Sharpe {s.get('is_sharpe')}, verdict "
                      f"**{self.best.diagnosis.verdict}**", "```", self.best.expression, "```",
                      "Next: robustness, then the gate - BRAIN's Check Submission gives the final production-"
                      "correlation verdict."]
        lines += ["", f"_{self.lesson}_"]
        return "\n".join(lines)


_CARRY = ("region", "universe", "delay", "decay", "neutralization", "truncation")


def _carry_settings(settings: dict) -> dict:
    """The settings a follow-up test must keep from the result it builds on (payload keys -> payload() keys)."""
    st = settings or {}
    out = {k: st[k] for k in _CARRY if st.get(k) is not None}
    if st.get("maxTrade"):
        out["max_trade"] = st["maxTrade"]
    return out


def card_of_idea(idea_id: Optional[str]) -> Optional[str]:
    """The idea card behind a journal idea id: "ERN_PEAD@USA" and "play:ERN_PEAD@USA" -> "ERN_PEAD";
    wild rolls and manual expressions have none."""
    if not idea_id:
        return None
    i = str(idea_id)
    if i.startswith("play:"):
        i = i[5:]
    if i.startswith(("wild:", "manual")):
        return None
    return i.split("@", 1)[0] or None


class Researcher:
    def __init__(self, brain=None, catalog: Optional[Catalog] = None, journal: Optional[Journal] = None,
                 region: str = "USA"):
        self.brain = brain
        self.catalog = catalog or Catalog()
        self.journal = journal or Journal()
        self.region = region
        self._cards = {}

    # ------------------------------------------------------- constructors
    @classmethod
    def sandbox(cls, seed: int = 7, home_suffix: str = "") -> "Researcher":
        from .mock import MockBrain, sandbox_catalog_payload
        brain = MockBrain(seed=seed)
        # in memory: the practice market's fields must never land in your real ~/.hypolab/catalog.sqlite
        cat = Catalog(":memory:")
        cat.ingest_payload(sandbox_catalog_payload(brain.data))
        # in-memory journal: sandbox alpha ids only live for this Python session
        return cls(brain=brain, catalog=cat, journal=Journal(":memory:"), region="SBX")

    @classmethod
    def live(cls, region: Optional[str] = None, login: bool = True, sync: bool = True) -> "Researcher":
        """Your BRAIN account. Region defaults to the one set with connect.go_live(...)."""
        from . import connect
        region = (region or config.live_region()).upper()
        brain = connect.client(login_now=login)     # same session as the Setup tab login: no repeated face scan
        cat = Catalog()
        if not cat.has_context("GLB", "MINVOL1M", 1):
            cat.load_bundled()             # the GLB snapshot shipped in data/ (earlier versions skipped it
                                           # whenever the sandbox had written its fields into this file)
        cat.db.execute("DELETE FROM fields WHERE region='SBX'")   # clean up sandbox fields left by v1.0/1.1
        cat.db.execute("DELETE FROM datasets WHERE region='SBX'")
        cat.db.commit()
        cat._cache.clear()
        cat._concepts_disk.clear()
        universe = config.REGION_DEFAULTS.get(region, {}).get("universe", "TOP3000")
        if sync and login and not cat.has_context(region, universe, 1):
            print(f"First time in {region} {universe}: downloading the list of datasets and fields from BRAIN "
                  "(metadata only - no simulations). This takes a few minutes once and is reused for 7 days.")
            cat.sync_from_brain(brain, region, universe, 1)
        return cls(brain=brain, catalog=cat, region=region)

    @classmethod
    def start(cls, sandbox: Optional[bool] = None, region: Optional[str] = None) -> "Researcher":
        """Sandbox or live, following the switch on the cockpit's Setup tab
        (or `python -m hypolab live USA`). Pass sandbox=True/False to override it once."""
        use_sandbox = config.sandbox_mode() if sandbox is None else sandbox
        if use_sandbox:
            print("SANDBOX mode: offline practice market (region SBX). Go live on the Setup page.")
            return cls.sandbox()
        print(f"LIVE mode: your BRAIN account, region {(region or config.live_region()).upper()}.")
        return cls.live(region)

    @property
    def is_sandbox(self) -> bool:
        return getattr(self.brain, "is_mock", False)

    # ------------------------------------------------------------- ideas
    def pyramids(self) -> PyramidTracker:
        """Pyramid counts for ranking ideas. Genius counts the QUARTER, so this quarter's submitted alphas
        (Account tab download) come first; BRAIN's diversity counts are all-time and only a fallback."""
        if self.is_sandbox:
            return PyramidTracker(self.brain.diversity(), regions=["SBX"])
        import time as _time
        hit = getattr(self, "_pyr_cache", None)
        if hit and _time.time() - hit[0] < 600:          # 1.8.1: the Lab asked BRAIN on every card it opened
            return hit[1]
        tracker = self._pyramids_uncached()
        self._pyr_cache = (_time.time(), tracker)
        return tracker

    def _pyramids_uncached(self) -> PyramidTracker:
        from . import account
        if account.last_sync(self.journal):
            counts, _ = account.quarter_pyramids(self.journal, self.catalog)
            return PyramidTracker(counts)
        if self.brain is not None:
            try:
                return PyramidTracker.from_brain(self.brain)
            except Exception as e:  # noqa: BLE001
                print(f"(could not read pyramids from BRAIN: {e}; using the journal)")
        return PyramidTracker.from_journal(self.journal)

    def ideas(self, region: Optional[str] = None, universe: Optional[str] = None, categories=None, n: int = 10,
              beginner: bool = True, use_pyramids: bool = True, one_per_family: bool = True) -> List[IdeaCard]:
        region = region or self.region
        need = {}
        if use_pyramids:
            try:
                need = self.pyramids().need(region)
            except Exception:  # noqa: BLE001
                need = {}
        binned = self.journal.binned_ids()
        lib = [h for h in load_library() if h.id not in binned]          # binned cards never come back (1.4.3)
        cards = generate_ideas(self.catalog, region, universe, categories=categories, n=n, journal=self.journal,
                               pyramid_need=need, beginner=beginner, one_per_family=one_per_family, library=lib)
        for c in cards:
            self._cards[c.hypothesis.id] = c
        return cards

    def card(self, hypothesis_id: str, region: Optional[str] = None, universe: Optional[str] = None,
             delay: int = 1) -> IdeaCard:
        """ONE idea card by its id (built-in or yours), bound to your fields in a region.

        Unlike R.ideas(), it keeps every rung - including rungs you already simulated (re-testing one is
        served from the journal, not simulated again). This is what the cockpit's "send to lab" uses."""
        region = region or self.region
        h = next((x for x in load_library() if x.id == hypothesis_id), None)
        if h is None:
            raise KeyError(f"no idea card with id {hypothesis_id!r}")
        universe = universe or config.REGION_DEFAULTS.get(region, {}).get("universe", "TOP3000")
        c = build_card(h, self.catalog, region, universe, delay)
        if c is None:
            raise ValueError(f"{hypothesis_id}: its data roles could not be bound to fields in {region} {universe} "
                             f"D{delay} (sync the catalog for this region, or the data does not exist there)")
        need = {}
        try:
            need = self.pyramids().need(region, delay)
        except Exception:  # noqa: BLE001
            pass
        _score(c, need, journal=None)
        self._cards[h.id] = c
        return c

    def explore(self, dataset: str, region: Optional[str] = None, universe: Optional[str] = None, **kw) -> List[IdeaCard]:
        cards = explore_dataset(self.catalog, dataset, region or self.region, universe, journal=self.journal, **kw)
        for c in cards:
            self._cards[c.hypothesis.id] = c
        return cards

    def scan(self, dataset: str, region: Optional[str] = None, universe: Optional[str] = None,
             max_fields: Optional[int] = None, min_coverage: float = 0.5) -> pd.DataFrame:
        """Probe every usable field of one dataset with ONE sensible expression each - in bulk.

        This is where simulation volume pays off: you learn which fields of a dataset carry
        information, which sign they have, and how fast they trade - before you write a hypothesis.
        Every probe is journaled under the dataset's family, so if you later build an alpha from a
        scanned field, the gate deflates its Sharpe by the number of fields you scanned (picking the
        best of 40 fields IS a 40-way selection).

        The returned table has a ``noise_bar``: the |Sharpe| that the best of that many pure-noise
        probes would beat only 5% of the time. Fields below it are indistinguishable from luck; fields
        above it are CANDIDATES that still need a mechanism (a hypothesis card) before you build on them.
        """
        region = region or self.region
        cfg = config.settings()
        n = int(max_fields or cfg["scan_max_fields"])
        # 1.8.1: no journal here - with it, rungs already simulated were dropped from each card, so a second scan
        # probed a DIFFERENT lens (new simulations) and lost every field whose lenses were all done. The scan
        # serves repeats from the journal itself (already_run below).
        cards = explore_dataset(self.catalog, dataset, region, universe, journal=None,
                                max_fields=n, min_coverage=min_coverage, dedupe_siblings=False)
        if not cards:
            print(f"no usable numeric fields in {dataset} for {region} (sync the catalog for this context?)")
            return pd.DataFrame()
        todo, rows = [], []
        for c in cards:
            self._cards[c.hypothesis.id] = c
            self.journal.log_idea(c)
            p = self.payload(c.steps[0].expression, c)
            prev = self.journal.already_run(c.steps[0].expression, p["settings"])
            if prev:
                rows.append((c, prev["alpha_id"], {"is_sharpe": prev["sharpe"], "is_fitness": prev["fitness"],
                                                   "is_turnover": prev["turnover"], "status": prev["status"],
                                                   "failed": [f for f in (prev["failed"] or "").split(",") if f]}, True))
            else:
                todo.append((c, p))
        if todo and not self.is_sandbox:
            left = cfg["max_sims_per_day"] - self.journal.sims_today()
            if left < len(todo):
                print(f"daily guard: {left} simulations left today, {len(todo)} needed - scanning the first {max(left, 0)}"
                      " (raise max_sims_per_day in ~/.hypolab/settings.json if you mean it)")
                todo = todo[:max(left, 0)]
        if todo:
            print(f"scanning {len(todo)} field(s) of {dataset} ({len(rows)} already in the journal) ...")
            results = self.brain.simulate([p for _, p in todo], progress=None if self.is_sandbox else print)
            for (c, p), res in zip(todo, results):
                if res["ok"]:
                    summary = summarize_alpha(self.brain.alpha(res["alpha_id"]))
                    summary["status"] = res["status"]
                else:
                    summary = {"status": res.get("status", "ERROR"), "error": res.get("error", ""), "alpha_id": None}
                dg = diagnose(summary, c.steps[0].expression, p["settings"], delay=p["settings"]["delay"])
                self.journal.record(c.id, c.steps[0].name, "scan", c.steps[0].expression, p["settings"], summary,
                                    dg.verdict, backend="sandbox" if self.is_sandbox else "brain")
                rows.append((c, summary.get("alpha_id"), summary, False))
        bar = round(noise_bar(len(rows), [sm.get("is_sharpe") for _, _, sm, _ in rows]), 2)
        out = []
        for c, aid, sm, cached in rows:
            b = c.bindings["x"]
            sh = sm.get("is_sharpe")
            out.append({"field": b.field_id, "description": (b.description or "")[:60], "nature": b.nature,
                        "lens": c.steps[0].name, "sharpe": sh, "fitness": sm.get("is_fitness"),
                        "turnover": sm.get("is_turnover"), "alpha_id": aid, "status": sm.get("status"),
                        "above_noise_bar": bool(sh is not None and abs(sh) > bar),
                        "idea": c.hypothesis.id, "cached": cached})
        df = pd.DataFrame(out)
        df = df.reindex(df["sharpe"].abs().sort_values(ascending=False).index).reset_index(drop=True)
        df.attrs["noise_bar"] = bar
        df.attrs["dataset"] = dataset
        print(f"noise bar for {len(df)} probes: |Sharpe| > {bar} separates a candidate from luck "
              f"(95% level). {int(df['above_noise_bar'].sum())} field(s) clear it. Negative Sharpe = opposite sign. "
              "Below the bar is not proof of nothing - a field with a clear mechanism may still deserve a card.")
        return df

    @staticmethod
    def table(cards: List[IdeaCard]) -> pd.DataFrame:
        return ideas_table(cards)

    @staticmethod
    def show(obj):
        display_md(obj.markdown() if hasattr(obj, "markdown") else str(obj))

    # -------------------------------------------------------------- test
    def _linter(self, region, universe, delay):
        return Linter.for_context(self.catalog, region, universe, delay) if self.catalog.has_context(region, universe, delay) \
            else Linter()

    def dataset_profile(self, expression: str, settings: dict) -> dict:
        """Datasets an expression uses and the IS Sharpe test BRAIN will apply (BRAIN_RULES T1)."""
        if self.is_sandbox and hasattr(self.brain, "_dataset_of"):
            look = self.brain._dataset_of
        else:
            look = rules.catalog_lookup(self.catalog, settings["region"], settings.get("universe"),
                                        int(settings.get("delay", 1)))
        return rules.dataset_profile(expression, look, int(settings.get("delay", 1)))

    def payload(self, expression: str, card: Optional[IdeaCard] = None, settings: Optional[dict] = None) -> dict:
        s = dict(card.settings) if card else {}
        s.update(settings or {})
        region = s.pop("region", None) or (card.region if card else self.region)
        explicit_universe = (settings or {}).get("universe")
        universe = s.pop("universe", None) or (card.universe if card else None)
        delay = int(s.pop("delay", card.delay if card else 1))
        if delay == 0 and region == "USA" and not explicit_universe:
            universe = "TOP1000"       # 1.6.0: D0 trades near the close - BRAIN's D0 page says USA TOP1000 (S-8)
        return make_payload(expression, region=region, universe=universe, delay=delay,
                            decay=int(s.get("decay", 0)), neutralization=s.get("neutralization", "SUBINDUSTRY"),
                            truncation=float(s.get("truncation", 0.08)), max_trade=s.get("max_trade"),
                            nan_handling=s.get("nan_handling", "OFF"), test_period=s.get("test_period", "P2Y"))

    def test(self, card: Optional[IdeaCard] = None, rung: int = 0, expression: Optional[str] = None,
             settings: Optional[dict] = None, purpose: str = "explore", force: bool = False,
             idea_id: Optional[str] = None, rung_name: Optional[str] = None) -> TestResult:
        """Simulate ONE rung (or your own expression) with all guard rails.

        rung_name: the label stored in the journal (default: the rung's name, or "custom" for an expression) -
        boosts are stored as "<rung> + boost:<card>" so they are recognisable after a restart."""
        label = rung_name
        if self.brain is None:
            raise RuntimeError("No BRAIN connection. Use Researcher.live() or Researcher.sandbox().")
        if expression is None:
            if card is None:
                raise ValueError("give an idea card or an expression")
            if rung >= len(card.steps):
                raise IndexError(f"this card has {len(card.steps)} rung(s)")
            expression, rung_name = card.steps[rung].expression, card.steps[rung].name
        else:
            rung_name = "custom"
        rung_name = label or rung_name
        p = self.payload(expression, card, settings)
        st = p["settings"]
        idea_id = idea_id or (card.id if card else f"manual@{st['region']}")
        lint = self._linter(st["region"], st["universe"], st["delay"]).lint(expression)
        if not lint.ok:
            d = Diagnosis("BLOCKED", "the linter stopped this expression before it cost a simulation",
                          [str(i) for i in lint.errors()], [], {})
            return TestResult(card, rung_name, expression, st, {"status": "BLOCKED"}, d)
        if card:
            self.journal.log_idea(card)
        cfg = config.settings()
        profile = self.dataset_profile(expression, st)
        prev = self.journal.already_run(expression, st)
        if prev and not force:
            summary = {"alpha_id": prev["alpha_id"], "is_sharpe": prev["sharpe"], "is_fitness": prev["fitness"],
                       "is_turnover": prev["turnover"], "is_returns": prev["returns"], "is_drawdown": prev["drawdown"],
                       "train_sharpe": prev["train_sharpe"], "test_sharpe": prev["test_sharpe"],
                       "failed": [f for f in (prev["failed"] or "").split(",") if f], "status": prev["status"],
                       "dataset_profile": profile}
            dg = diagnose(summary, expression, st, expected_turnover=card.hypothesis.expected_turnover if card else None,
                          delay=st["delay"], trials_so_far=self.journal.trials(idea_id))
            return TestResult(card, rung_name, expression, st, summary, dg, cached=True, idea_id=idea_id)
        trials = self.journal.trials(idea_id)
        if purpose in ("explore", "boost") and trials >= cfg["max_sims_per_idea"] and not force:
            d = Diagnosis("BUDGET", f"this idea already used {trials} simulations (budget {cfg['max_sims_per_idea']})",
                          ["More tries on the same idea mostly buy luck, not evidence (see overfit.noise_table())."],
                          [], {})
            return TestResult(card, rung_name, expression, st, {"status": "BUDGET"}, d, idea_id=idea_id)
        if not self.is_sandbox and self.journal.sims_today() >= cfg["max_sims_per_day"] and not force:
            d = Diagnosis("BUDGET", "daily simulation guard reached (settings.json: max_sims_per_day)", [], [], {})
            return TestResult(card, rung_name, expression, st, {"status": "BUDGET"}, d, idea_id=idea_id)
        q = None if self.is_sandbox else brain_quota()
        if q is not None and q["remaining"] <= 0:
            d = Diagnosis("BUDGET", f"BRAIN's daily simulation limit ({q['limit']}) is used up",
                          ["It resets at midnight New York time (07:00/08:00 in Nairobi)."], [], {})
            return TestResult(card, rung_name, expression, st, {"status": "BUDGET"}, d, idea_id=idea_id)
        locs: List[str] = []

        def _remember(payloads, loc):
            locs.append(loc)
            self.journal.add_pending(loc, idea_id, rung_name, purpose, expression, st, payloads[0])

        res = self.brain.simulate([p], progress=None, on_submitted=_remember)[0]
        out = self._finish(card, rung_name, expression, st, res, idea_id, purpose, trials, profile)
        for loc in locs:
            self.journal.clear_pending(loc)
        return out

    def _finish(self, card, rung_name: str, expression: str, st: dict, res: dict, idea_id: str, purpose: str,
                trials: int, profile: dict) -> TestResult:
        """Read a finished simulation back from BRAIN, diagnose it and journal it."""
        if not res["ok"]:
            summary = {"status": res.get("status", "ERROR"), "error": res.get("error", ""), "alpha_id": None}
        else:
            summary = summarize_alpha(self.brain.alpha(res["alpha_id"]))
            summary["status"] = res["status"]
        yearly = None
        if summary.get("alpha_id"):
            try:
                yearly = self.brain.yearly_stats(summary["alpha_id"])
            except Exception:  # noqa: BLE001
                yearly = None
            if card and not self.is_sandbox:
                try:
                    self.brain.set_properties(summary["alpha_id"], name=card.hypothesis.id[:30],
                                              tags=["hypolab", card.family],
                                              description=self.description(card, expression))
                except Exception:  # noqa: BLE001
                    pass
        summary["dataset_profile"] = profile
        dg = diagnose(summary, expression, st, yearly, card.hypothesis.expected_turnover if card else None,
                      delay=st["delay"], trials_so_far=trials)
        self.journal.record(idea_id, rung_name, purpose, expression, st, summary, dg.verdict,
                            backend="sandbox" if self.is_sandbox else "brain")
        return TestResult(card, rung_name, expression, st, summary, dg, idea_id=idea_id)

    # ------------------------------------------------------------ resume (1.4.1)
    def pending(self) -> List[dict]:
        """Simulations BRAIN accepted that HYPOLAB never read back (e.g. the laptop was shut down mid-run)."""
        return self.journal.pending()

    def recover_pending(self) -> dict:
        """Fetch finished results for interrupted simulations - from BRAIN, without simulating again.

        Returns {"recovered": [TestResult], "running": n, "gone": n}. Still-running ones stay pending.
        """
        out = {"recovered": [], "running": 0, "gone": 0}
        for row in self.journal.pending():
            loc, st = row["location"], row["settings"]
            if not hasattr(self.brain, "peek") or str(loc).startswith("sandbox://"):
                self.journal.clear_pending(loc)        # the sandbox finishes instantly; nothing to fetch
                out["gone"] += 1
                continue
            try:
                res = self.brain.peek(loc, [row["payload"]])
            except Exception:  # noqa: BLE001 - BRAIN unreachable: try again later
                out["running"] += 1
                continue
            if res is None:
                out["running"] += 1
                continue
            r = res[0]
            if r.get("status") == "GONE":
                self.journal.clear_pending(loc)
                out["gone"] += 1
                continue
            if row["purpose"] == "super":            # 1.10.0: a SuperAlpha interrupted mid-simulation
                t = self._finish_super(row["rung"], row["expression"], st, r, row["idea_id"],
                                       self.journal.trials(row["idea_id"], purpose=("super",)))
                t.rung = f"{row['rung']} (recovered)"
                self.journal.clear_pending(loc)
                out["recovered"].append(t)
                continue
            card = self._card_for(row["idea_id"])
            prof = self.dataset_profile(row["expression"], st)
            t = self._finish(card, row["rung"], row["expression"], st, r, row["idea_id"], row["purpose"],
                             self.journal.trials(row["idea_id"]), prof)
            t.rung = f"{row['rung']} (recovered)"
            self.journal.clear_pending(loc)
            out["recovered"].append(t)
        return out

    def _card_for(self, idea_id: str):
        """The idea card behind a journal idea id like 'FND_ACCRUALS@USA' (None for play/rerun/manual ids)."""
        if not idea_id or "@" not in idea_id or ":" in idea_id:
            return None
        hid, region = idea_id.rsplit("@", 1)
        try:
            return self.card(hid, region)
        except Exception:  # noqa: BLE001
            return None

    def recent_results(self, n: int = 10, purposes=("explore", "boost", "play", "decorr")) -> List[TestResult]:
        """Your last ``n`` simulations rebuilt from the journal (diagnosis recomputed, nothing re-simulated) -
        to pick up where you left off after closing HYPOLAB."""
        ex = self.journal.experiments()
        if ex.empty:
            return []
        ex = ex[ex["purpose"].isin(purposes) & ex["status"].isin(["COMPLETE", "WARNING"])]
        binned = self.journal.binned_ids()
        if binned:                       # results of binned cards stay in the journal but not in the Lab list
            ex = ex[~ex["idea_id"].map(lambda i: card_of_idea(i) in binned)]
        out = []
        for row in ex.sort_values("created").tail(n).to_dict("records"):
            try:
                st = json.loads(row.get("settings") or "{}")
            except ValueError:
                st = {}
            summary = {"alpha_id": row["alpha_id"], "is_sharpe": row["sharpe"], "is_fitness": row["fitness"],
                       "is_turnover": row["turnover"], "is_returns": row["returns"], "is_drawdown": row["drawdown"],
                       "train_sharpe": row["train_sharpe"], "test_sharpe": row["test_sharpe"],
                       "failed": [f for f in (row["failed"] or "").split(",") if f], "status": row["status"]}
            card = self._card_for(row["idea_id"])
            if st.get("region"):
                summary["dataset_profile"] = self.dataset_profile(row["expression"], st)
            dg = diagnose(summary, row["expression"], st,
                          expected_turnover=card.hypothesis.expected_turnover if card else None,
                          delay=rules.delay_of(st.get("delay")), trials_so_far=self.journal.trials(row["idea_id"]))
            out.append(TestResult(card, row["rung"], row["expression"], st, summary, dg, cached=True,
                                  idea_id=row["idea_id"]))
        return out

    def follow(self, result: TestResult, action: int = 0) -> TestResult:
        """Apply the diagnosis' suggested action #action (expression and/or settings change) and test it."""
        acts = result.diagnosis.actions
        if not acts or action >= len(acts):
            raise ValueError("no such action")
        a = acts[action]
        if a.kind == "stop":
            raise ValueError(f"the suggested action is to STOP: {a.why}")
        if a.expression is None and not a.settings:
            raise ValueError(f"'{a.title}' is a research step, not an automatic change: {a.why}")
        expr = a.expression or result.expression
        # 1.6.0: keep WHERE the result was simulated (region, universe, delay) - before, a D0 result or a manual
        # expression in another region was followed at the card's / session's defaults (D1, default universe).
        s = _carry_settings(result.settings)
        s.update(a.settings or {})
        out = self.test(result.card, expression=expr, settings={k: v for k, v in s.items() if v is not None},
                        idea_id=result.idea_id)
        out.rung = f"{result.rung} + {a.title}"
        return out

    # ---------------------------------------------- re-run submitted alphas
    RISK_SETS = ("SLOW", "FAST", "SLOW_AND_FAST", "REVERSION_AND_MOMENTUM", "STATISTICAL", "CROWDING")

    def rerun_variants(self, alpha: dict) -> List[dict]:
        """Settings worth re-simulating for an already-submitted alpha (BRAIN_RULES N5, S-8).

        * each risk-neutralization set BRAIN offers in its region (the alpha's own neutralization excluded);
        * delay 0, if the region offers it and the alpha is delay 1 (the D0 page's tip).
        Returns [{"label", "settings"}]; nothing is simulated here.
        """
        region, delay = alpha.get("region"), rules.delay_of(alpha.get("delay"))
        current = alpha.get("neutralization")
        offered = config.region_neutralizations(region)
        out = [{"label": f"neutralization {n}", "settings": {"neutralization": n, "delay": delay}}
               for n in self.RISK_SETS if n in offered and n != current]
        if delay == 1 and 0 in config.REGION_DEFAULTS.get(region, {}).get("delays", []):
            out.append({"label": "delay 0 (same settings)", "settings": {"neutralization": current, "delay": 0}})
        return out

    def rerun(self, alpha: dict, variants: List[dict], force: bool = False) -> List[TestResult]:
        """Re-simulate a submitted alpha with other settings; every try counts against `rerun:<alpha_id>`.

        ``alpha``: a row of account.account_alphas() (code, region, universe, delay, neutralization, decay,
        truncation). The results go through the same linter, budget, journal and diagnosis as any test, and a
        good one still has to pass the gate - including self-correlation with the original.
        """
        code = alpha.get("code") or ""
        idea = f"rerun:{alpha.get('alpha_id')}"
        region = alpha.get("region")
        try:
            f = self.catalog.fields(region, None, rules.delay_of(alpha.get("delay")), enrich=False)
            cat_of = dict(zip(f["id"], f["category"])) if not f.empty else {}
        except Exception:  # noqa: BLE001
            cat_of = {}
        cats = sorted({str(cat_of[x]) for x in rules.fields_in(code) if x in cat_of and x not in rules.GROUPING_FIELDS})
        self.journal.log_manual_idea(idea, region, "rerun", f"Re-run of submitted alpha {alpha.get('alpha_id')}",
                                     cats)
        out = []
        for v in variants:
            st = {"region": region, "universe": alpha.get("universe") or config.universe_for(region),
                  "delay": rules.delay_of(alpha.get("delay")), "decay": int(alpha.get("decay") or 0),
                  "neutralization": alpha.get("neutralization") or "SUBINDUSTRY",
                  "truncation": float(alpha.get("truncation") or 0.08)}
            st.update(v.get("settings") or {})
            t = self.test(expression=code, settings=st, idea_id=idea, force=force)
            t.rung = v.get("label", "re-run")
            out.append(t)
        return out

    # ------------------------------------------------------------ playground
    def roll(self, n: int = 5, mode: str = "mix", region: Optional[str] = None, seed: Optional[int] = None,
             shuffle_settings: bool = True):
        """Random alphas from random cards / random fields, ignoring the Pyramid plan (free; see hypolab.play)."""
        from .play import roll
        return roll(self.catalog, region or self.region, n=n, mode=mode, seed=seed, shuffle_settings=shuffle_settings,
                    exclude=self.journal.binned_ids())

    def play(self, items) -> List[TestResult]:
        """Simulate rolled play items. Journaled as purpose "play" under `play:<card>` / `play:wild:<dataset>`;
        the per-idea budget does not stop play, BRAIN's daily quota does, and every roll counts as a try."""
        out = []
        for it in items:
            if not it.lint_ok:
                continue
            self.journal.log_manual_idea(it.idea_id, it.settings.get("region"), "play", it.title or it.name,
                                         it.categories)
            t = self.test(it.card, expression=it.expression, settings=dict(it.settings), purpose="play",
                          idea_id=it.idea_id, rung_name=f"play: {it.name}")
            out.append(t)
        return out

    # -------------------------------------------------------- validation
    def robustness(self, result: TestResult) -> pd.DataFrame:
        base = result.summary.get("is_sharpe") or 0.0
        idea_id = result.key

        def sim(variants):
            # 1.8.1: every variant that needs a simulation goes to BRAIN in ONE multi-simulation request (it used to
            # be one request after another); blocked variants are marked "not run" instead of counting as failures
            out, todo = [], []
            for v in variants:
                st = dict(v.settings)
                p = make_payload(v.expression, region=st["region"], universe=st["universe"], delay=st["delay"],
                                 decay=st["decay"], neutralization=st["neutralization"], truncation=st["truncation"],
                                 max_trade=st.get("maxTrade"), test_period=st.get("testPeriod", "P2Y"))
                lint = self._linter(st["region"], st["universe"], st["delay"]).lint(v.expression)
                if not lint.ok:
                    out.append({"status": "BLOCKED", "error": "; ".join(str(i) for i in lint.errors())[:200]})
                    continue
                prev = self.journal.already_run(v.expression, p["settings"])
                if prev:
                    out.append({"is_sharpe": prev["sharpe"], "is_fitness": prev["fitness"], "is_turnover": prev["turnover"]})
                    continue
                out.append(None)
                todo.append((len(out) - 1, v, p))
            if todo:
                results = self.brain.simulate([p for _, _, p in todo], progress=None)
                for (i, v, p), r in zip(todo, results):
                    sm = summarize_alpha(self.brain.alpha(r["alpha_id"])) if r["ok"] else \
                        {"status": "ERROR", "error": r.get("error", "")}
                    self.journal.record(idea_id, f"robust:{v.name}", "robustness", v.expression, p["settings"], sm,
                                        backend="sandbox" if self.is_sandbox else "brain")
                    out[i] = sm
            return out
        return rob.run(result.expression, result.settings, base, sim)

    # ------------------------------------------------------------- boost
    # ------------------------------------------------------------ bin (1.4.3)
    def bin(self, hypothesis_id: str, reason: str = "") -> None:
        """Bin a noise card: hidden from ideas(), the Ideas app's Cards page, the Lab's list, Play and boosters."""
        self.journal.bin_card(hypothesis_id, reason)

    def restore(self, hypothesis_id: str) -> None:
        self.journal.restore_card(hypothesis_id)

    def binned(self) -> pd.DataFrame:
        return self.journal.binned()

    # ------------------------------------------------------------ performance (1.4.3)
    def performance(self, result: "TestResult", compare: Optional[dict] = None) -> dict:
        """What the alpha earned: cumulative PnL (BRAIN's pnl recordset) and the yearly table.

        compare: {label: alpha_id} drawn next to it (the Lab uses it for a boost: base, booster, combination).
        Costs API reads only - never a simulation. Returns {"pnl": DataFrame (one column per line),
        "yearly": DataFrame, "error": str}."""
        out = {"pnl": pd.DataFrame(), "yearly": pd.DataFrame(), "error": ""}
        if not result.alpha_id:
            out["error"] = "this result has no alpha id (blocked, budget or an error) - nothing to draw"
            return out
        lines = {"this alpha": result.alpha_id}
        for k, v in (compare or {}).items():
            if v and v != result.alpha_id:
                lines[k] = v
        cols = {}
        for label, aid in lines.items():
            try:
                cols[f"{label} ({aid})"] = self._daily_pnl(aid).cumsum()
            except Exception as e:  # noqa: BLE001
                if label == "this alpha":
                    out["error"] = f"PnL not available from BRAIN yet ({e})"
        if cols:
            out["pnl"] = pd.concat(cols, axis=1).sort_index().ffill()
        try:
            out["yearly"] = self.brain.yearly_stats(result.alpha_id)
        except Exception:  # noqa: BLE001
            pass
        return out

    def _daily_pnl(self, alpha_id: str) -> pd.Series:
        if hasattr(self.brain, "daily_pnl"):
            return self.brain.daily_pnl(alpha_id)
        return self.brain.pnl(alpha_id).diff().dropna()       # BRAIN's pnl recordset is cumulative

    def boost(self, result: TestResult, k: int = 4, mode: str = "add", candidates: Optional[List[IdeaCard]] = None,
              min_booster_sharpe: float = 0.5) -> "BoostReport":
        """Strengthen a weak-but-real alpha with ONE independent second signal.

        Why it works: two signals with Sharpe S1, S2 and correlation rho, combined with equal risk, give about
            S = (S1 + S2) / sqrt(2 * (1 + rho))
        so two unrelated 1.0 signals make ~1.41, but a 1.0 plus a near-copy (rho ~ 1) stays 1.0.

        Steps: pick k booster candidates from OTHER idea families (different data category first), test each
        alone (rung 1 of its own card - a normal, journaled test of that idea), measure the PnL correlation with
        your alpha, PREDICT the combined Sharpe, and simulate the combination only where the prediction is a
        real improvement. Every combination counts as a try on your base idea, so the gate stays honest.

        mode: "add"  -> rank(base) + rank(booster)          (diversify: two views averaged)
              "and"  -> min(rank(base), rank(booster))      (conjunction: only stocks both like)
        """
        S1 = result.summary.get("is_sharpe")
        if not result.alpha_id or S1 is None:
            raise ValueError("boost needs a simulated alpha (run R.test first)")
        base_expr = result.expression
        notes = []
        if S1 < 0:
            base_expr, S1 = flip(base_expr), -S1
            notes.append("Your alpha had a negative Sharpe; it is used FLIPPED (opposite sign) - make sure the "
                         "reversed story makes sense.")
        if S1 < min_booster_sharpe:
            raise ValueError(f"Sharpe {S1:.2f} is too weak to boost - the booster would be doing all the work. "
                             "Climb the ladder or move to another idea.")
        base_pnl = self._daily_pnl(result.alpha_id)
        if result.summary.get("is_sharpe", 0) < 0:
            base_pnl = -base_pnl
        base_card = result.card
        base_fam = base_card.family if base_card else None
        base_cats = set(base_card.categories) if base_card else set()
        if candidates is None:
            pool = self.ideas(result.settings.get("region", self.region), n=40, one_per_family=True)
            pool = [c for c in pool if c.family != base_fam]
            # independent DATA first: a different pyramid category is the best guess for low correlation
            pool.sort(key=lambda c: (bool(set(c.categories) & base_cats), -c.score))
            candidates = pool[:k]
        rows, results, boosters = [], {}, {}
        for c in candidates:
            row = {"booster": c.hypothesis.id, "category": ",".join(c.categories), "booster_sharpe": None,
                   "correlation": None, "predicted": None, "combined_sharpe": None, "combined_fitness": None,
                   "combined_turnover": None, "verdict": "", "why": ""}
            bt = self.test(c, rung=0)
            bt.rung = f"booster alone: {bt.rung}"
            boosters[c.hypothesis.id] = bt
            S2 = bt.summary.get("is_sharpe")
            row["booster_sharpe"] = S2
            if not bt.alpha_id or S2 is None:
                row["why"] = f"booster could not be tested ({bt.diagnosis.verdict})"
                rows.append(row)
                continue
            if S2 < min_booster_sharpe:
                row["why"] = ("works only inverted - test that card on its own first" if S2 <= -min_booster_sharpe
                              else "no signal of its own - nothing to add")
                rows.append(row)
                continue
            bp = self._daily_pnl(bt.alpha_id)
            both = pd.concat([base_pnl, bp], axis=1, join="inner").dropna()
            rho = float(both.corr().iloc[0, 1]) if len(both) > 60 else 0.0
            pred = (S1 + S2) / math.sqrt(max(2 * (1 + rho), 1e-6))
            row.update(correlation=round(rho, 2), predicted=round(pred, 2))
            if rho > 0.7:
                row["why"] = "too correlated with your alpha - same information, no boost"
            elif pred < S1 * 1.1:
                row["why"] = "predicted gain under 10% - not worth a simulation"
            elif S2 >= pred:
                row["why"] = ("the booster is better ON ITS OWN than the combination - work on that idea instead "
                              "(a combination would mostly be the booster's alpha)")
            else:
                booster_expr = bt.expression
                t1 = result.summary.get("is_turnover") or 0.0
                t2 = bt.summary.get("is_turnover") or 0.0
                if t2 > 2 * max(t1, 0.05):
                    # a slow alpha needs a slow partner: otherwise the booster's trading dominates turnover and
                    # kills fitness. One economic choice (a month), not a parameter search.
                    booster_expr = wrap_result(booster_expr, "ts_mean({}, 21)")
                    row["why"] = f"booster smoothed over a month to match your alpha's pace (turnover {t2:.0%} vs {t1:.0%}); "
                combo = _combine(base_expr, booster_expr, mode)
                pc = rules.pyramid_check(self.categories_of(combo, result.settings))
                if not pc["ok"]:          # 1.6.0: a combination over 2 categories adds no Pyramid cell
                    row["why"] += f"note: combination {pc['note'].split(':')[0]} - over BRAIN's 2-Pyramid limit; "
                st = _carry_settings(result.settings)       # 1.6.0: same region / universe / delay as the base
                t = self.test(base_card, expression=combo, settings=st, purpose="boost",
                              idea_id=result.idea_id, rung_name=f"{result.rung} + boost:{c.hypothesis.id}")
                results[c.hypothesis.id] = t
                row.update(combined_sharpe=t.summary.get("is_sharpe"), combined_fitness=t.summary.get("is_fitness"),
                           combined_turnover=t.summary.get("is_turnover"), verdict=t.diagnosis.verdict,
                           why=row["why"] + ("simulated" if t.alpha_id else t.diagnosis.headline))
            rows.append(row)
        table = pd.DataFrame(rows)
        best = None
        done = [r for r in results.values() if r.summary.get("is_sharpe") is not None]
        if done:
            order = {"PASS": 3, "NEAR": 2, "WEAK": 1}
            best = max(done, key=lambda r: (order.get(r.diagnosis.verdict, 0), r.summary.get("is_sharpe") or -9))
        if not table.empty:
            table.insert(1, "booster_alpha", [boosters[b].alpha_id if b in boosters else None for b in table["booster"]])
            table.insert(len(table.columns) - 2, "combined_alpha",
                         [results[b].alpha_id if b in results else None for b in table["booster"]])
        return BoostReport(result, S1, table, results, best, notes, boosters)

    # ------------------------------------------------------------ correlation (1.6.0)
    def correlation(self, alpha_id: str, kind: str = "prod", refresh: bool = False) -> dict:
        """BRAIN's self / production correlation of an alpha: an API read (never a simulation), kept in the
        journal for a day. Returns {"max", "min", "table"} (table only when freshly read)."""
        if not refresh:
            c = self.journal.correlation(alpha_id, kind)
            if c is not None:
                return {"max": c["max"], "min": c["min"], "table": pd.DataFrame(), "cached": True}
        d = self.brain.correlations(alpha_id, kind)
        tab = d.get("table")
        raw = tab.to_dict("records") if isinstance(tab, pd.DataFrame) else None
        try:
            self.journal.save_correlation(alpha_id, kind, d.get("max"), d.get("min"), raw)
        except Exception:  # noqa: BLE001 - read-only journal
            pass
        return d

    def corr_status(self, result: "TestResult", refresh: bool = False) -> dict:
        """Production correlation now (free read) + BRAIN's checks as they stand -> status per check."""
        aid = result.alpha_id
        prod = None
        if aid:
            try:
                prod = self.correlation(aid, "prod", refresh)
            except Exception:  # noqa: BLE001
                prod = None
        return decorr.corr_status(result.summary.get("checks"), prod)

    def _style_corr(self, result: "TestResult", base_pnl: pd.Series) -> dict:
        """PnL correlation of the alpha with each crowded-style proxy. The proxies are simulated once per
        region/universe/delay/neutralization (then served from the journal: same expression = no new simulation)."""
        out = {}
        st = {k: result.settings[k] for k in ("region", "universe", "delay", "neutralization") if k in result.settings}
        st.update(decay=0, truncation=0.08)
        for name, expr in decorr.STYLE_PROXIES.items():
            try:
                t = self.test(None, expression=expr, settings=st, purpose="style",
                              idea_id=f"style:{name}@{st.get('region')}", rung_name=f"style {name}")
                if not t.alpha_id:
                    continue
                both = pd.concat([base_pnl, self._daily_pnl(t.alpha_id)], axis=1, join="inner").dropna()
                if len(both) > 120:
                    out[name] = round(float(both.corr().iloc[0, 1]), 2)
            except Exception:  # noqa: BLE001
                continue
        return out

    def _own_corr(self, result: "TestResult", base_pnl: pd.Series, limit: int = 60) -> List[dict]:
        """PnL correlation with your submitted alphas in the same region and delay (API reads, cached a day)."""
        region, delay = result.settings.get("region"), result.settings.get("delay", 1)
        ids = {}
        try:
            from .account import account_alphas
            acc = account_alphas(self.journal)
            if not acc.empty:
                acc = acc[(acc["region"] == region) & (acc["delay"].fillna(1).astype(int) == int(delay))]
                acc = acc[acc["type"].fillna("REGULAR") == "REGULAR"]       # 1.10.0: SuperAlphas are not alphas here
                ids.update({r.alpha_id: r.code for r in acc.itertuples()})
        except Exception:  # noqa: BLE001
            pass
        sub = self.journal.submissions()
        if not sub.empty:
            sub = sub[sub["family"].fillna("") != "superalpha"]    # 1.10.0: their stored text is not FASTEXPR
            for r in sub[sub["region"] == region].itertuples():
                ids.setdefault(r.alpha_id, None)
        if not ids:
            return []
        codes = {}
        if any(v is None for v in ids.values()):
            ex = self.journal.experiments()
            if not ex.empty:
                codes = dict(zip(ex["alpha_id"], ex["expression"]))
        out = []
        for aid, code in list(ids.items())[:limit]:
            if aid == result.alpha_id:
                continue
            try:
                both = pd.concat([base_pnl, self._daily_pnl(aid)], axis=1, join="inner").dropna()
            except Exception:  # noqa: BLE001
                continue
            if len(both) > 120:
                out.append({"alpha_id": aid, "corr": round(float(both.corr().iloc[0, 1]), 2),
                            "code": code or codes.get(aid)})
        return sorted(out, key=lambda o: -o["corr"])

    def _field_swaps(self, result: "TestResult") -> List[dict]:
        """The same card bound to a less crowded field (R1 step 1): rebuild it avoiding the current fields."""
        card = result.card
        if card is None or not card.bindings:
            return []
        region = result.settings.get("region", self.region)
        out = []
        for role, b in card.bindings.items():
            try:
                alt = build_card(card.hypothesis, self.catalog, region, card.universe, card.delay,
                                 avoid_fields=[b.field_id])
            except Exception:  # noqa: BLE001
                alt = None
            if alt is None or role not in alt.bindings:
                continue
            nb = alt.bindings[role]
            step = next((s for s in alt.steps if s.name == result.rung), None)
            if step is None or not step.lint.ok or step.expression == result.expression:
                continue
            fewer = (nb.alpha_count is not None and b.alpha_count is not None and nb.alpha_count < b.alpha_count)
            why = (f"equivalent field for '{role}' ({nb.dataset})"
                   + (f", {int(nb.alpha_count)} alphas on it vs {int(b.alpha_count)}" if fewer else ""))
            out.append({"old": b.field_id, "new": nb.field_id, "expression": step.expression, "why": why,
                        "fewer": fewer})
        return sorted(out, key=lambda d: not d["fewer"])

    def decorrelate(self, result: "TestResult", k: int = 4, measure_styles: bool = True) -> DecorrReport:
        """Lower production/self correlation while keeping the signal.

        1. measure: production correlation (free read), PnL correlation with crowded-style proxies (simulated once
           per region and neutralization, then cached) and with your own submitted alphas (free reads);
        2. propose at most k changes that keep the idea (decorr.variants: BRAIN's theme hint, residual against the
           style it resembles, a less crowded equivalent field, a risk set, a shorter horizon, your own overlap,
           another peer group) - each with its reason;
        3. simulate them (purpose "decorr": every one counts as a try on this idea, so the gate's deflated Sharpe
           stays honest), read each one's production correlation, and recommend the best trade-off.
        """
        S0 = result.summary.get("is_sharpe")
        if not result.alpha_id or S0 is None:
            raise ValueError("decorrelate needs a simulated alpha")
        notes = []
        base_pnl = self._daily_pnl(result.alpha_id)
        try:
            base_prod = self.correlation(result.alpha_id, "prod").get("max")
        except Exception as e:  # noqa: BLE001
            base_prod = None
            notes.append(f"production correlation not readable yet ({e})")
        style = self._style_corr(result, base_pnl) if measure_styles else {}
        own = self._own_corr(result, base_pnl)
        cands = decorr.variants(result.expression, result.settings, checks=result.summary.get("checks"),
                                style_corr=style, own_corr=own, field_swaps=self._field_swaps(result), k=k,
                                turnover=result.summary.get("is_turnover") or 0.0)
        rows, done = [], []
        lim = config.settings().get("max_prod_corr", 0.7)
        for v in cands:
            st = {kk: result.settings[kk] for kk in ("decay", "neutralization", "truncation") if kk in result.settings}
            st.update(v.settings)
            t = self.test(result.card, expression=v.expression, settings=st, purpose="decorr",
                          idea_id=result.idea_id or result.key, rung_name=f"{result.rung} ~ {v.name}")
            pc = None
            if t.alpha_id:
                try:
                    pc = self.correlation(t.alpha_id, "prod").get("max")
                except Exception:  # noqa: BLE001
                    pc = None
                done.append(t)
            sh = t.summary.get("is_sharpe")
            rows.append({"variant": v.name, "why": v.why, "alpha": t.alpha_id, "sharpe": sh,
                         "sharpe_kept": None if sh is None else round(sh / abs(S0), 2),
                         "fitness": t.summary.get("is_fitness"), "turnover": t.summary.get("is_turnover"),
                         "prod_corr": None if pc is None else round(float(pc), 2),
                         "under_limit": None if pc is None else bool(pc < lim), "verdict": t.diagnosis.verdict})
        table = pd.DataFrame(rows, columns=["variant", "why", "alpha", "sharpe", "sharpe_kept", "fitness", "turnover",
                                            "prod_corr", "under_limit", "verdict"])
        i = decorr.recommend(table, S0, lim)
        best = None
        if i is not None:
            aid = table.loc[i, "alpha"]
            best = next((r for r in done if r.alpha_id == aid), None)
        if not cands:
            notes.append("no principled change applies to this expression")
        if self.is_sandbox:
            notes.append("sandbox: risk-set neutralizations are not offered, and the production pool is three "
                         "textbook alphas")
        return DecorrReport(result, S0, base_prod, table, done, best, style, own,
                            decorr.lesson(table, base_prod, S0), notes)

    def description(self, card: Optional[IdeaCard], expression: str) -> str:
        if card is None:
            return f"Expression: {expression}"
        h = card.hypothesis
        data = "; ".join(f"{b.field_id} = {b.description or b.role}" for b in card.bindings.values()) or \
            "standard price/volume fields"
        return (f"Idea: {h.title}. {h.story}\n"
                f"Rationale for data used: {data}. Expected sign {h.sign}; persists because: {h.why_persists}\n"
                f"Rationale for operators used: built as a ladder rung of {h.id}; "
                f"group/rank operators compare peers, ts_backfill carries sparse updates, smoothing controls turnover.\n"
                f"References: {'; '.join(h.references[:2])}")

    def categories_of(self, expression: str, settings: dict) -> List[str]:
        """BRAIN data categories an expression touches in its region (grouping fields excluded) - its Pyramid cells."""
        try:
            if self.is_sandbox and hasattr(self.brain, "_categories"):
                return self.brain._categories(expression)
            f = self.catalog.fields(settings.get("region"), None, rules.delay_of(settings.get("delay")), enrich=False)
            cat_of = dict(zip(f["id"], f["category"])) if not f.empty else {}
        except Exception:  # noqa: BLE001
            return []
        cats = {str(cat_of[x]) for x in rules.fields_in(expression) if x in cat_of and x not in rules.GROUPING_FIELDS}
        names = set(rules.fields_in(expression)) - rules.GROUPING_FIELDS
        from .ideas import STANDARD_PV
        if names & (STANDARD_PV - rules.GROUPING_FIELDS):
            cats.add("pv")
        return sorted(cats)

    def gate(self, result: TestResult, robustness_table: Optional[pd.DataFrame] = None) -> GateReport:
        aid = result.alpha_id
        if not aid:
            raise ValueError("no alpha id on this result")
        reasons, ready = [], True
        try:
            checks = self.brain.checks(aid)
        except Exception as e:  # noqa: BLE001
            checks = pd.DataFrame()
            reasons.append(f"could not fetch /check ({e}) - check on the platform")
            ready = False
        ready = _platform_checks(checks, reasons) and ready
        # Correlation (1.6.0): BRAIN's own SELF/PROD/Power Pool checks are the authority. HYPOLAB's reading of the
        # maximum is shown, but only blocks when BRAIN's check has not answered (its rule may let a correlated alpha
        # through when its Sharpe is clearly higher - so a 0.75 can still PASS on the platform).
        prod = selfc = None
        try:
            selfc = self.brain.correlations(aid, "self")
        except Exception:  # noqa: BLE001
            pass
        try:
            prod = self.correlation(aid, "prod", refresh=True)
        except Exception:  # noqa: BLE001
            reasons.append("could not read the production correlation - BRAIN's Check Submission still tests it")
        cs = decorr.corr_status(checks, prod, selfc)
        for kind, label in (("self", "self-correlation"), ("prod", "production correlation"),
                            ("power_pool", "Power Pool correlation")):
            s = cs[kind]
            val = "" if s["value"] is None else f" {float(s['value']):.2f} (limit {s['limit']})"
            if s["result"] == "FAIL":
                ready = False
                reasons.append(f"{label} FAILS on BRAIN{val}: too close to existing alphas. Use **Lower correlation** "
                               "in the Lab (keeps the idea, changes one thing), or move to a less used dataset")
            elif s["result"] == "FAIL?" and kind == "self" and rules.self_corr_exception(
                    result.summary.get("is_sharpe"), (selfc or {}).get("table"), s["limit"]):
                # BRAIN accepts a correlated alpha whose Sharpe is >= 10% above every alpha it correlates with (T7)
                reasons.append(f"{label}{val} is above the limit, but the Sharpe is at least 10% above every "
                               "correlated alpha: BRAIN allows it as an improved version (Check Submission confirms)")
            elif s["result"] == "FAIL?":
                ready = False
                reasons.append(f"{label}{val} is above the limit by HYPOLAB's reading; BRAIN's check has not answered "
                               "(press Check Submission on the platform - it can still pass a clearly stronger "
                               "alpha). Lower correlation in the Lab is the safe route")
            elif s["result"] == "PENDING":
                ready = False
                hint = (f" - HYPOLAB reads{val}; above the limit, expect a FAIL unless BRAIN's rule lets a stronger alpha"
                        " through" if s.get("reading") is not None and s["reading"] >= s["limit"] else
                        (f" - HYPOLAB reads{val}" if s.get("reading") is not None else ""))
                reasons.append(f"{label} PENDING on BRAIN: re-run the gate after Check Submission{hint}")
            elif s["result"] in ("PASS", "PASS?") and s["value"] is not None:
                reasons.append(f"{label} {s['result'].rstrip('?')}{val}"
                               + (" - BRAIN's check passes it even above the limit" if s["result"] == "PASS"
                                  and float(s["value"]) >= s["limit"] else ""))
            elif kind != "power_pool" and s["result"] not in ("PASS", "PASS?"):
                # 1.10.2: no evidence is not a pass (Power Pool is optional and stays informational)
                ready = False
                reasons.append(_NO_EVIDENCE.format(label=label))
        idea_id = result.key
        n_trials = max(1, self.journal.trials(idea_id))
        if result.card and result.card.hypothesis.source == "lens":
            # a field picked from a scan was selected among every field scanned in that dataset
            n_trials = max(n_trials, self.journal.family_status(result.card.family,
                                                                result.settings.get("region"))["simulated"])
        dsr = {}
        try:
            pnl = self.brain.daily_pnl(aid) if hasattr(self.brain, "daily_pnl") else self.brain.pnl(aid).diff()
            dsr = deflated_sharpe(pnl, n_trials)
            reasons.append(f"deflated Sharpe after {n_trials} tries on this idea{' (incl. dataset scan)' if result.card and result.card.hypothesis.source == 'lens' else ''}: probability {dsr['dsr']:.2f} that "
                           f"the edge is real ({dsr_verdict(dsr['dsr'])})")
            if not dsr["dsr"] >= 0.5:                 # also False for NaN
                ready = False
        except Exception:  # noqa: BLE001
            ready = False                            # 1.10.2: a gate never passes without the overfitting check
            reasons.append(_NO_DSR)
        ready = _holdout(result.summary, reasons) and ready
        if robustness_table is not None and "score" in robustness_table.attrs:
            sc = robustness_table.attrs["score"]
            reasons.append(f"robustness score {sc['score']:.0%}: {sc['verdict']}")
            if sc["score"] < 0.6:
                ready = False
        else:
            reasons.append("robustness battery not run - run R.robustness(result) first")
            ready = False
        # 1.6.0: Pyramid limit, Power Pool shape (information, never blocking)
        cats = self.categories_of(result.expression, result.settings)
        if cats:
            pc = rules.pyramid_check(cats)
            reasons.append(f"Pyramids: {', '.join(pc['categories'])}" + ("" if pc["ok"] else f" - {pc['note']}"))
        pp = rules.power_pool_shape(result.expression)
        if pp["operators"] is not None:
            s_ok = (result.summary.get("is_sharpe") or 0) >= rules.POWER_POOL["min_sharpe"]
            reasons.append("Power Pool shape: " + pp["note"] + (" - eligible shape (also needs Power Pool correlation "
                           "< 0.5 and a 100+ character description)" if pp["ok"] and s_ok else " - not eligible"))
        if result.card:
            fam = self.journal.family_status(result.card.family, result.settings.get("region"))
            if fam["submitted"]:
                reasons.append(f"you already submitted {fam['submitted']} alpha(s) from family "
                               f"'{result.card.family}' in this region - expect correlation")
        desc = self.description(result.card, result.expression)
        return self._issue(GateReport(aid, ready, reasons, checks, desc, dsr), "alpha")

    # ------------------------------------------------------------ gate reports (1.10.2)
    @property
    def _issued(self) -> dict:
        if not hasattr(self, "_issued_gates"):
            self._issued_gates = {}
        return self._issued_gates

    def _issue(self, gate: GateReport, kind: str) -> GateReport:
        """Record the report as issued: what submit() trusts is this record, not the report object."""
        import time as _time
        import uuid
        gate.token, gate.issued_at, gate.kind = uuid.uuid4().hex, _time.time(), kind
        self._issued[gate.token] = {"alpha_id": gate.alpha_id, "ready": bool(gate.ready), "at": gate.issued_at,
                                    "kind": kind, "reasons": list(gate.reasons)}
        return gate

    def _check_gate(self, gate: GateReport, kind: str) -> None:
        import time as _time
        what = "SuperAlpha gate" if kind == "super" else "gate report"
        rec = self._issued.get(getattr(gate, "token", "") or "")
        if rec is None:
            raise RuntimeError(f"Refusing to submit: this {what} was not issued in this session (or was already used "
                               "for a submission). Run the gate again and submit from its READY report.")
        if rec["kind"] != kind or rec["alpha_id"] != gate.alpha_id:
            raise RuntimeError(f"Refusing to submit: the {what} belongs to another alpha or kind. Run the gate again.")
        if not rec["ready"]:
            raise RuntimeError(f"Refusing to submit {gate.alpha_id}: the {what} said NOT READY ("
                               + "; ".join(rec["reasons"][:3]) + ")")
        age = _time.time() - rec["at"]
        max_age = float(config.settings().get("gate_max_age_minutes", 30)) * 60
        if age > max_age:
            raise RuntimeError(f"Refusing to submit: the {what} is {age / 60:.0f} minutes old (limit "
                               f"{max_age / 60:.0f}). BRAIN's checks and correlations move; run the gate again.")

    def submit(self, gate: GateReport, confirm: str = "", force: bool = False) -> dict:
        """Submit ONE alpha whose gate report this Researcher issued READY in the last `gate_max_age_minutes`.
        `force` only lifts HYPOLAB's daily cap; nothing lifts the gate."""
        self._check_gate(gate, "alpha")
        cap = int(config.settings().get("max_submissions_per_day", 4))
        done = self.journal.submissions_today()
        if done >= cap and not force:
            raise RuntimeError(f"You already submitted {done} alpha(s) today (daily limit {cap}, "
                               "max_submissions_per_day in ~/.hypolab/settings.json). Keep this one for tomorrow.")
        if confirm != f"SUBMIT {gate.alpha_id}":
            raise RuntimeError(f'Refusing to submit. Type "SUBMIT {gate.alpha_id}" to confirm.')
        try:
            res = self.brain.submit(gate.alpha_id, confirm=confirm)
        finally:
            self._issued.pop(gate.token, None)        # one gate report, one submission attempt (also when it failed)
        code = int(res.get("status_code") or 0)
        if code >= 300:
            # 1.8.1: BRAIN refused (e.g. a check failed at submission time): nothing is recorded, so the daily
            # count, the Pyramid fallback and the learning loop never see an alpha that was not submitted
            raise RuntimeError(f"BRAIN did not accept the submission ({code}): {str(res.get('body', ''))[:300]}")
        rows = self.journal.experiments()
        row = rows[rows["alpha_id"] == gate.alpha_id]
        if not row.empty:
            idea = row.iloc[-1]["idea_id"]
            card = next((c for c in self._cards.values() if c.id == idea), None)
            if card is not None:
                family, cats = card.family, list(card.categories)
            else:
                # after a kernel restart the card is no longer in memory: the journal still knows it
                stored = self.journal.idea(idea) or {}
                family = stored.get("family") or "manual"
                cats = [c for c in (stored.get("categories") or "").split(",") if c]
            self.journal.record_submission(gate.alpha_id, idea, family, row.iloc[-1]["region"],
                                           int(row.iloc[-1]["delay"]), cats, row.iloc[-1]["sharpe"],
                                           row.iloc[-1]["fitness"])
        return res

    # ------------------------------------------------------------ SuperAlphas (phase 8, 1.10.0)
    def super_pool(self) -> pd.DataFrame:
        """Your submitted alphas with the properties a selection reads (sandbox: its practice submissions)."""
        from . import superalpha as SA
        return SA.pool_alphas(self.journal, self.catalog, self.brain if self.is_sandbox else None)

    def super_unlock(self, store=None) -> dict:
        from . import superalpha as SA
        return SA.unlock_status(store, self.journal, sandbox=self.is_sandbox)

    def practice_super_pool(self, n: int = 24, seed: int = 11) -> int:
        """Sandbox only: submit `n` practice alphas (rung 1 of the built-in cards) so a SuperAlpha has a pool to
        select from. Nothing is journaled - they are the sandbox's stand-in for your 100 submitted alphas."""
        if not self.is_sandbox:
            raise RuntimeError("the practice pool is for the sandbox; live, your real submissions are the pool")
        payloads = []
        for c in self.ideas("SBX", n=max(n * 3, 60)):
            if c.steps:
                try:
                    payloads.append(self.payload(c.steps[0].expression, c))
                except Exception:  # noqa: BLE001
                    continue
        return self.brain.seed_practice_pool(payloads, n=n, seed=seed)

    def super_test(self, selection: str, combo: str, region: str, universe: Optional[str] = None, delay: int = 1,
                   decay: int = 4, neutralization: str = "SUBINDUSTRY", truncation: float = 0.05,
                   selection_limit: int = 30, selection_handling: str = "POSITIVE",
                   component_activation: str = "IS", store=None, force: bool = False) -> "TestResult":
        """Simulate ONE SuperAlpha with the same guard rails as an alpha: checks, unlock, duplicate, budget (10 per
        pool per quarter), daily guard, quota - then diagnose and journal it (purpose 'super')."""
        from . import superalpha as SA
        if self.brain is None:
            raise RuntimeError("No BRAIN connection. Use Researcher.live() or Researcher.sandbox().")
        p = SA.make_payload(selection, combo, region, universe, delay, decay, neutralization, truncation,
                            selection_limit, selection_handling, component_activation)
        st = dict(p["settings"])
        text = SA.journal_text(selection, combo, st)
        name = SA.recipe_names(selection, combo, selection_limit)
        idea_id = SA.pool_id(region, delay)

        def stop(verdict, head, findings):
            return TestResult(None, name, text, st, {"status": verdict}, Diagnosis(verdict, head, findings, [], {}),
                              idea_id=idea_id)
        rep = SA.check(selection, combo, selection_limit, selection_handling, component_activation, decay, truncation)
        if not rep.ok:
            return stop("BLOCKED", "the checks stopped this SuperAlpha before it cost a simulation", rep.errors)
        lock = SA.unlock_status(store, self.journal, sandbox=self.is_sandbox)
        if not lock["unlocked"] and not force:
            return stop("BLOCKED", "SuperAlphas are still locked on BRAIN",
                        [SA.unlock_line(lock), "BRAIN unlocks them after 100 submitted alphas (BRAIN_RULES G11)."])
        self.journal.log_manual_idea(idea_id, region, SA.FAMILY, f"SuperAlphas {region} D{delay}", ())
        prev = self.journal.already_run(text, st)
        trials = self.journal.trials(idea_id, purpose=(SA.PURPOSE,))
        if prev and not force:
            summary = {"alpha_id": prev["alpha_id"], "is_sharpe": prev["sharpe"], "is_fitness": prev["fitness"],
                       "is_turnover": prev["turnover"], "is_returns": prev["returns"], "is_drawdown": prev["drawdown"],
                       "train_sharpe": prev["train_sharpe"], "test_sharpe": prev["test_sharpe"],
                       "failed": [f for f in (prev["failed"] or "").split(",") if f], "status": prev["status"]}
            return TestResult(None, name, text, st, summary, SA.diagnose(summary, st, max(0, trials - 1)), cached=True,
                              idea_id=idea_id)
        cfg = config.settings()
        cap = int(cfg.get("max_super_sims_per_pool", 10))
        if trials >= cap and not force:
            return stop("BUDGET", f"this pool already used {trials} SuperAlpha simulations this quarter (budget {cap})",
                        ["More combinations of the same alphas mostly buy luck. Add better or more varied alphas to the "
                         "pool, or wait for next quarter's budget."])
        if not self.is_sandbox and self.journal.sims_today() >= cfg["max_sims_per_day"] and not force:
            return stop("BUDGET", "daily simulation guard reached (settings.json: max_sims_per_day)", [])
        q = None if self.is_sandbox else brain_quota()
        if q is not None and q["remaining"] <= 0:
            return stop("BUDGET", f"BRAIN's daily simulation limit ({q['limit']}) is used up",
                        ["It resets at midnight New York time (07:00/08:00 in Nairobi)."])
        locs: List[str] = []

        def _remember(payloads, loc):
            locs.append(loc)
            self.journal.add_pending(loc, idea_id, name, SA.PURPOSE, text, st, payloads[0])

        res = self.brain.simulate([p], batch_size=1, progress=None, on_submitted=_remember)[0]
        out = self._finish_super(name, text, st, res, idea_id, trials)
        for loc in locs:
            self.journal.clear_pending(loc)
        return out

    def _finish_super(self, name: str, text: str, st: dict, res: dict, idea_id: str, trials: int) -> "TestResult":
        from . import superalpha as SA
        if not res.get("ok"):
            summary = {"status": res.get("status", "ERROR"), "error": res.get("error", ""), "alpha_id": None}
        else:
            summary = summarize_alpha(self.brain.alpha(res["alpha_id"]))
            summary["status"] = res.get("status")
            if not self.is_sandbox:
                try:
                    self.brain.set_properties(summary["alpha_id"], name=f"SUPER {name}"[:30],
                                              tags=["hypolab", SA.FAMILY])
                except Exception:  # noqa: BLE001
                    pass
        dg = SA.diagnose(summary, st, trials)
        self.journal.record(idea_id, name, SA.PURPOSE, text, st, summary, dg.verdict,
                            backend="sandbox" if self.is_sandbox else "brain")
        return TestResult(None, name, text, st, summary, dg, idea_id=idea_id)

    def super_results(self, n: int = 20) -> List["TestResult"]:
        """Your last SuperAlpha simulations rebuilt from the journal (nothing re-simulated)."""
        from . import superalpha as SA
        ex = self.journal.experiments()
        if ex.empty:
            return []
        ex = ex[(ex["purpose"] == SA.PURPOSE) & ex["status"].isin(["COMPLETE", "WARNING"])]
        out = []
        for row in ex.sort_values("created").tail(n).to_dict("records"):
            try:
                st = json.loads(row.get("settings") or "{}")
            except ValueError:
                st = {}
            summary = {"alpha_id": row["alpha_id"], "is_sharpe": row["sharpe"], "is_fitness": row["fitness"],
                       "is_turnover": row["turnover"], "is_returns": row["returns"], "is_drawdown": row["drawdown"],
                       "train_sharpe": row["train_sharpe"], "test_sharpe": row["test_sharpe"],
                       "failed": [f for f in (row["failed"] or "").split(",") if f], "status": row["status"]}
            n_before = max(0, self.journal.trials(row["idea_id"], purpose=(SA.PURPOSE,)) - 1)
            out.append(TestResult(None, row["rung"], row["expression"], st, summary,
                                  SA.diagnose(summary, st, n_before), cached=True, idea_id=row["idea_id"]))
        return out

    def super_gate(self, result: "TestResult", store=None) -> GateReport:
        """The SuperAlpha gate: BRAIN's checks (the authority), correlations, the 2%-40% turnover band, the deflated
        Sharpe over every try on this pool this quarter, train vs test, the unlock and today's SuperAlpha."""
        from . import superalpha as SA
        aid = result.alpha_id
        if not aid:
            raise ValueError("no alpha id on this result")
        reasons, ready = [], True
        lock = SA.unlock_status(store, self.journal, sandbox=self.is_sandbox)
        if not lock["unlocked"]:
            ready = False
            reasons.append(SA.unlock_line(lock))
        if lock["left_today"] <= 0:
            ready = False
            reasons.append(f"you already submitted {lock['today']} SuperAlpha today (BRAIN accepts {lock['cap']}): "
                           "keep this one for tomorrow")
        try:
            checks = self.brain.checks(aid)
        except Exception as e:  # noqa: BLE001
            checks = pd.DataFrame()
            reasons.append(f"could not fetch /check ({e}) - check on the platform")
            ready = False
        ready = _platform_checks(checks, reasons) and ready
        selfc = prod = None
        try:
            selfc = self.brain.correlations(aid, "self")
        except Exception:  # noqa: BLE001
            pass
        try:
            prod = self.correlation(aid, "prod", refresh=True)
        except Exception:  # noqa: BLE001
            reasons.append("could not read the production correlation - BRAIN's Check Submission still tests it")
        cs = decorr.corr_status(checks, prod, selfc)
        for kind, label in (("self", "self-correlation"), ("prod", "production correlation")):
            s = cs[kind]
            val = "" if s["value"] is None else f" {float(s['value']):.2f} (limit {s['limit']})"
            if s["result"] in ("FAIL", "FAIL?"):
                ready = False
                reasons.append(f"{label}{val} {'FAILS on BRAIN' if s['result'] == 'FAIL' else 'is above the limit'}: "
                               "select 'Least correlated' or weight 'Least crowded' (one change)")
            elif s["result"] == "PENDING":
                ready = False
                reasons.append(f"{label} PENDING on BRAIN: re-run the gate after Check Submission")
            elif s["result"] in ("PASS", "PASS?"):
                reasons.append(f"{label}{val} passes")
            else:                                        # 1.10.2: no evidence is not a pass
                ready = False
                reasons.append(_NO_EVIDENCE.format(label=label))
        t = result.summary.get("is_turnover")
        lo, hi = SA.TURNOVER_BAND
        if t is not None:
            inside = lo <= float(t) <= hi
            reasons.append(f"turnover {float(t):.1%} {'inside' if inside else 'OUTSIDE'} the {lo:.0%}-{hi:.0%} band")
            ready = ready and inside
        else:
            ready = False
            reasons.append("no turnover in this result: the 2%-40% band cannot be checked - simulate it again")
        n_trials = max(1, self.journal.trials(result.key, purpose=(SA.PURPOSE,)))
        dsr = {}
        try:
            pnl = self.brain.daily_pnl(aid) if hasattr(self.brain, "daily_pnl") else self.brain.pnl(aid).diff()
            dsr = deflated_sharpe(pnl, n_trials)
            reasons.append(f"deflated Sharpe after {n_trials} SuperAlpha tries on this pool: probability "
                           f"{dsr['dsr']:.2f} that the edge is real ({dsr_verdict(dsr['dsr'])})")
            if not dsr["dsr"] >= 0.5:
                ready = False
        except Exception:  # noqa: BLE001
            ready = False
            reasons.append(_NO_DSR)
        ready = _holdout(result.summary, reasons) and ready
        reasons.append("SuperAlphas count as signals for Genius (BRAIN_RULES G2); HYPOLAB does not place them in "
                       "Pyramid cells (unknown how BRAIN counts them)")
        if not self.is_sandbox:
            reasons.append("the description below is NOT sent with the submission (BRAIN's shape for a SuperAlpha "
                           "description is not known yet, BRAIN_RULES SA8): paste it on the platform's alpha page")
        sel = SA.split_journal_text(result.expression)
        desc = (f"SuperAlpha from my submitted {result.settings.get('region')} D{result.settings.get('delay')} alphas. "
                f"{result.rung}. Selection keeps the top {result.settings.get('selectionLimit')} by: "
                f"{sel['selection'][:160]}. Weighting: {sel['combo'][:160]}. Built with HYPOLAB.")
        return self._issue(GateReport(aid, ready, reasons, checks, desc, dsr), "super")

    def super_submit(self, gate: GateReport, confirm: str = "", store=None, force: bool = False) -> dict:
        """Submit ONE SuperAlpha (typed confirmation; 1 a day; never while locked; only with a READY SuperAlpha gate
        this Researcher issued recently - `force` lifts the lock and the daily limit, never the gate)."""
        from . import superalpha as SA
        self._check_gate(gate, "super")
        lock = SA.unlock_status(store, self.journal, sandbox=self.is_sandbox)
        if not lock["unlocked"] and not force:
            raise RuntimeError(SA.unlock_line(lock).replace("**", ""))
        if lock["left_today"] <= 0 and not force:
            raise RuntimeError(f"You already submitted {lock['today']} SuperAlpha today (BRAIN accepts "
                               f"{lock['cap']} a day). Keep this one for tomorrow.")
        if confirm != f"SUBMIT {gate.alpha_id}":
            raise RuntimeError(f'Refusing to submit. Type "SUBMIT {gate.alpha_id}" to confirm.')
        try:
            res = self.brain.submit(gate.alpha_id, confirm=confirm)
        finally:
            self._issued.pop(gate.token, None)
        code = int(res.get("status_code") or 0)
        if code >= 300:
            raise RuntimeError(f"BRAIN did not accept the submission ({code}): {str(res.get('body', ''))[:300]}")
        ex = self.journal.experiments()
        row = ex[ex["alpha_id"] == gate.alpha_id]
        if not row.empty:
            r = row.iloc[-1]
            self.journal.record_submission(gate.alpha_id, r["idea_id"], SA.FAMILY, r["region"], int(r["delay"]), [],
                                           r["sharpe"], r["fitness"])
        return res

"""The cockpit's Lab, Play and Quant basics as plain web pages (1.13.0, Android phase C1).

Shared by the laptop and the tablet. Same engine calls as the marimo cockpit (apps/cockpit.py), same rules:
- every simulation (and every BRAIN read) sits behind its own button and runs as a background job (ideaweb.jobs),
  one at a time, never repeated by itself;
- only a READY gate report that this Researcher issued can submit, with the typed confirmation `SUBMIT <alpha id>`;
  Researcher.submit() does every check (daily cap, freshness, typed confirmation) - this page never bypasses it;
- sandbox mode is the offline practice market; live mode needs a BRAIN login (on the tablet: phase D).

State lives in this process (one user): the Lab's results list, the last boost / lower-correlation / gate reports,
robustness tables, PnL panels, the Play roll and results, and the quant-basics lessons once built.
"""
from __future__ import annotations

import base64
import io
import threading
import time
from typing import Dict, List, Optional

import pandas as pd
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route

from hypolab import config
from hypolab import hypotheses as hyp
from ideaweb.jobs import JOBS

NO_CARD = ""
VERDICT_KIND = {"PASS": "ok", "NEAR": "ok", "WEAK": "warn", "INVERTED": "warn", "NOISE": "err", "ERROR": "err",
                "BLOCKED": "err", "BUDGET": "err"}


# ============================================================================================== charts / tables
def fig_uri(fig) -> str:
    """A matplotlib figure as an inline PNG (data URI); the figure is closed."""
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def table(df: Optional[pd.DataFrame], code_cols=(), index: bool = False) -> str:
    from ideaengine import views
    if df is None:
        return "<p class='empty'>none</p>"
    if index:
        df = df.reset_index()
    return views.html_table(df, code_cols=code_cols)


# ============================================================================================== state
class Lab:
    """One Researcher for the web Lab (sandbox or your BRAIN account), opened again when the mode changes."""

    def __init__(self):
        self.lock = threading.RLock()
        self.R = None
        self.mode_key = None
        self.problem = ""
        self.problem_at = 0.0
        self._serial = 0
        self.login_msg = None          # Setup page: survives the Researcher being reopened after a login
        self.reset()

    def reset(self):
        self.results: List[tuple] = []          # (key, TestResult), oldest first
        self.focus: Optional[int] = None         # key of the result shown (None = newest)
        self.robust: Dict[str, pd.DataFrame] = {}
        self.gate = None
        self.boost = None                        # BoostReport or an error text
        self.decorr = None                       # DecorrReport or an error text
        self.perf: Dict[str, dict] = {}
        self.corr: Dict[str, dict] = {}
        self.submitted: List[tuple] = []
        self.play: List[tuple] = []              # (key, TestResult)
        self.play_focus: Optional[int] = None
        self.roll = None
        self.inbox_note = ""
        self._cards: Dict[tuple, object] = {}
        # 1.14.0 (phase C2): Pyramids counts, SuperAlpha form / results / gate / message
        self.pyr = None
        self.super_form = None
        self.super_results: List[tuple] = []
        self.super_focus: Optional[int] = None
        self.super_gate = None
        self.super_msg = ""
        # 1.15.0 (phase C3): Data page's dataset explore/scan, Account download message
        self.scan_form = None
        self.explore = None
        self.scan = None
        self.acct_msg = None

    # ------------------------------------------------------------------ the Researcher
    def researcher(self):
        key = (config.sandbox_mode(), config.live_region())
        with self.lock:
            if key != self.mode_key:
                self.R, self.problem, self.mode_key = None, "", key
                self.reset()
            if self.R is None and (not self.problem or time.time() - self.problem_at > 30):
                from ideaengine.connection import open_researcher
                self.R, self.problem = open_researcher()
                self.problem_at = time.time()
            return self.R

    @property
    def sandbox(self) -> bool:
        return config.sandbox_mode()

    def journal(self):
        R = self.researcher()
        if R is not None:
            return R.journal
        from hypolab.journal import Journal
        return Journal.open_readonly()

    # ------------------------------------------------------------------ results
    def add(self, results, where: str = "lab") -> None:
        with self.lock:
            for t in results:
                self._serial += 1
                (self.results if where == "lab" else self.play).append((self._serial, t))
            if where == "lab":
                self.focus = None
            else:
                self.play_focus = None

    def current(self):
        with self.lock:
            if not self.results:
                return None
            if self.focus is not None:
                for k, t in self.results:
                    if k == self.focus:
                        return t
            return self.results[-1][1]

    def current_key(self) -> Optional[int]:
        t = self.current()
        return next((k for k, x in self.results if x is t), None)

    def key_of(self, t) -> Optional[int]:
        return next((k for k, x in self.results if x is t), None)

    # ------------------------------------------------------------------ the card in the Lab
    def card_id(self) -> str:
        return config.settings().get("last_lab_card") or NO_CARD

    def region(self) -> str:
        R = self.researcher()
        if self.sandbox:
            return "SBX"
        r = config.settings().get("lab_region") or (R.region if R is not None else config.live_region())
        return r if r in config.account_regions() else config.account_regions()[0]

    def card(self):
        """(IdeaCard or None, error text)."""
        cid, R = self.card_id(), self.researcher()
        if not cid or R is None:
            return None, ""
        key = (cid, self.region(), self.mode_key)
        if key not in self._cards:
            try:
                self._cards = {key: R.card(cid, region=self.region())}
            except Exception as e:  # noqa: BLE001
                return None, str(e)
        return self._cards[key], ""

    def pick_up_inbox(self) -> None:
        """A card sent from the Cards page ("Send to the Lab") lands here once."""
        from ideaengine import handoff
        new = handoff.take_new()
        if new and new.get("card"):
            config.save_settings(last_lab_card=new["card"])
            if new.get("region") and not self.sandbox:
                config.save_settings(lab_region=new["region"])
            self.inbox_note = f"Picked up {new['card']} from the Cards page" + (
                f" (sent for {new['region']})." if new.get("region") else ".")


LAB = Lab()


# ============================================================================================== helpers
def _form_int(f, k, default, lo=None, hi=None):
    try:
        v = int(float(f.get(k, default)))
    except (TypeError, ValueError):
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _form_float(f, k, default, lo=None, hi=None):
    try:
        v = float(f.get(k, default))
    except (TypeError, ValueError):
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def boost_compare(rep, t) -> dict:
    """Lines drawn next to a boost result: the base alpha and the booster alone (as in the cockpit)."""
    if rep is None or isinstance(rep, str):
        return {}
    for k, r in rep.results.items():
        if r is t or (r.alpha_id and r.alpha_id == t.alpha_id):
            b = rep.boosters.get(k)
            return {"base": rep.base.alpha_id, "booster " + k: b.alpha_id if b is not None else None}
    return {}


def result_rows(pairs, focus_key) -> List[dict]:
    from ideaengine import views
    out = []
    for k, t in pairs:
        r = views.result_row(t)
        r["key"] = k
        r["on"] = k == focus_key
        r["kind"] = VERDICT_KIND.get(r["verdict"], "muted")
        out.append(r)
    return out


def _start(request: Request, title: str, fn, page: str):
    """Start a job, or say why not. Always redirect back to the page."""
    from ideaweb.app import go
    if JOBS.busy():
        return go(page, f"Still working on: {JOBS.busy().title}. Wait for it to finish.", "warn")
    JOBS.start(title, page, fn)
    return RedirectResponse(page, status_code=303)


def job_ctx(page: str) -> dict:
    """What every Lab-side page needs to know about jobs."""
    j = JOBS.busy()
    done = JOBS.take_message(page) if j is None else None
    return {"job": j, "job_done": done}


# ============================================================================================== LAB
def lab_routes(page, go):
    async def lab_page(request: Request):
        q = request.query_params
        if q.get("focus"):
            try:
                LAB.focus = int(q["focus"])
            except ValueError:
                pass
        R = await run_in_threadpool(LAB.researcher)
        if R is not None and not JOBS.busy():
            LAB.pick_up_inbox()
        card, card_error = await run_in_threadpool(LAB.card) if R is not None else (None, "")
        cur = LAB.current()
        ctx = dict(job_ctx("/lab"), R=R, problem=LAB.problem, sandbox=LAB.sandbox, card=card, card_error=card_error,
                   card_id=LAB.card_id(), region=LAB.region() if R is not None else "",
                   inbox_note=LAB.inbox_note, cur=cur, cur_key=LAB.current_key())
        LAB.inbox_note = ""
        if R is None:
            return page(request, "lab.html", **ctx)
        binned = R.journal.binned_ids()
        ctx["card_ids"] = [h.id for h in hyp.load_library() if h.id not in binned]
        ctx["regions"] = ["SBX"] if LAB.sandbox else config.account_regions()
        st = card.settings if card is not None else {}
        reg = card.region if card is not None else ctx["region"]
        neut = st.get("neutralization", "SUBINDUSTRY")
        d0 = int(card.delay) if card is not None else 1
        ctx["controls"] = {
            "rungs": [(i, f"{i + 1}. {s.name}") for i, s in enumerate(card.steps)] if card is not None else [],
            "neuts": list(dict.fromkeys(config.region_neutralizations(reg) + [neut])), "neut": neut,
            "delays": list(dict.fromkeys(config.REGION_DEFAULTS.get(reg, {}).get("delays", [1]) + [d0])), "delay": d0,
            "decay": int(st.get("decay", 0) or 0), "trunc": float(st.get("truncation", 0.08) or 0.08)}
        if card is not None:
            ctx["ladder"] = [{"rung": f"{i + 1}. {s.name}", "expression": s.expression,
                              "lint": "ok" if s.lint.ok else "BLOCKED", "is_test": s.is_test, "teaches": s.teaches}
                             for i, s in enumerate(card.steps)]
        ctx["rows"] = result_rows(LAB.results, ctx["cur_key"])
        ctx["sims_today"] = R.journal.sims_today()
        if not LAB.sandbox:
            try:
                from hypolab.brain import quota as brain_quota
                ctx["quota"] = brain_quota()
            except Exception:  # noqa: BLE001
                ctx["quota"] = None
            ctx["pending"] = R.pending()
        if not LAB.results:
            ex = R.journal.experiments()
            n = int(ex["purpose"].isin(["explore", "boost", "decorr", "play"]).sum()) if not ex.empty else 0
            ctx["restorable"] = n
            if n:
                ctx["restore_last"] = pd.Timestamp(ex["created"].max(), unit="s").strftime("%a %d %b %H:%M")
        if cur is not None:
            from ideaengine import views
            ctx["actions"] = views.action_choices(cur)
            aid = cur.alpha_id
            p = LAB.perf.get(aid) if aid else None
            if p is not None:
                if not p.get("error") and "_uri" not in p:
                    from ideaengine import views
                    p["_uri"] = fig_uri(views.pnl_figure(p["pnl"], title=f"Cumulative PnL - {cur.rung}")) \
                        if p.get("pnl") is not None and not p["pnl"].empty else ""
                    y = p.get("yearly")
                    if y is not None and not y.empty:
                        if not isinstance(y.index, pd.RangeIndex):
                            y = y.reset_index()
                        if "year" in y.columns:
                            y = y.assign(year=y["year"].astype(str))
                        p["_yearly"] = table(y)
                    else:
                        p["_yearly"] = ""
                ctx["perf"] = p
            b = LAB.boost
            ctx["boost_err"] = b if isinstance(b, str) else ""
            if b is not None and not isinstance(b, str) and aid in b.alpha_ids():
                ctx["boost_md"] = b.markdown()
                ctx["boost_table"] = table(b.table)
                ctx["boost_links"] = [(LAB.key_of(t), (t.card.hypothesis.id if t.card is not None else
                                                       (t.idea_id or "manual")) + " / " + t.rung,
                                       t.summary.get("is_sharpe"), t.diagnosis.verdict)
                                      for t in b.lab_results() if LAB.key_of(t) is not None]
            if aid:
                from hypolab import decorr
                cs = LAB.corr.get(aid)
                if cs is None:
                    known = R.journal.correlation(aid, "prod")
                    if known is not None:
                        cs = decorr.corr_status(cur.summary.get("checks"), known)
                if cs is not None:
                    ctx["corr_err"] = cs.get("error", "") if "error" in cs else ""
                    if not ctx["corr_err"]:
                        ctx["corr_line"] = decorr.status_line(cs)
                        ctx["corr_bad"] = any(v.get("result") in ("FAIL", "FAIL?") for v in cs.values())
                dc = LAB.decorr
                ctx["decorr_err"] = dc if isinstance(dc, str) else ""
                if dc is not None and not isinstance(dc, str) and aid in dc.alpha_ids():
                    ctx["decorr_md"] = dc.markdown()
                    ctx["decorr_table"] = table(dc.table, code_cols=["alpha"])
                rb = LAB.robust.get(aid)
                if rb is not None:
                    sc = rb.attrs.get("score", {})
                    ctx["robust_line"] = f"{sc.get('score', 0):.0%} - {sc.get('verdict', '')}"
                    ctx["robust_table"] = table(rb.drop(columns=["expression"], errors="ignore"))
                g = LAB.gate
                if g is not None and g.alpha_id == aid:
                    ctx["gate_md"] = g.markdown()
                    cap = int(config.settings().get("max_submissions_per_day", 4))
                    today = R.journal.submissions_today()
                    ctx["gate_ready"] = bool(g.ready)
                    ctx["submit_open"] = bool(g.ready) and today < cap
                    ctx["subs_today"], ctx["subs_cap"] = today, cap
                ctx["submitted"] = [m for a, m in LAB.submitted if a == aid]
        return page(request, "lab.html", **ctx)

    async def lab_card(request: Request):
        f = await request.form()
        cid = (f.get("card") or "").strip()
        config.save_settings(last_lab_card=cid)
        if f.get("region") and not LAB.sandbox:
            config.save_settings(lab_region=f["region"])
        return RedirectResponse("/lab", status_code=303)

    async def lab_card_action(request: Request):
        f = await request.form()
        cid = LAB.card_id()
        if f.get("action") == "bin" and cid and LAB.researcher() is not None:
            LAB.R.bin(cid, "noise - binned from the Lab")
            config.save_settings(last_lab_card="")
            return go("/lab", f"Binned {cid} from the Lab. Restore it from Cards > The bin.")
        config.save_settings(last_lab_card="")
        return go("/lab", f"{cid or 'The card'} left the Lab (its results stay in the list and the journal).")

    async def lab_simulate(request: Request):
        f = await request.form()
        R = LAB.researcher()
        if R is None:
            return go("/lab", LAB.problem or "No BRAIN session.", "err")
        card, err = LAB.card()
        expr = (f.get("expression") or "").strip() or None
        if card is None and not expr:
            return go("/lab", "No card in the Lab: pick one or write your own expression first.", "warn")
        settings = {"decay": _form_int(f, "decay", 0, 0, 512), "neutralization": f.get("neutralization") or "SUBINDUSTRY",
                    "truncation": _form_float(f, "truncation", 0.08, 0.0, 1.0), "delay": _form_int(f, "delay", 1, 0, 1)}
        if card is None:
            reg = LAB.region()
            settings.update(region=reg, universe=config.universe_for(reg))
        rung = _form_int(f, "rung", 0, 0)

        def run():
            t = R.test(card, rung=rung, expression=expr, settings=settings)
            LAB.add([t])
            return (f"Simulated {t.rung}: {t.diagnosis.verdict}.", VERDICT_KIND.get(t.diagnosis.verdict, "ok"))
        return _start(request, "1 simulation", run, "/lab")

    async def lab_results(request: Request):
        f = await request.form()
        with LAB.lock:
            if f.get("action") == "clear":
                LAB.results = []
            elif f.get("action") == "remove":
                k = LAB.current_key()
                LAB.results = [(kk, t) for kk, t in LAB.results if kk != k]
            LAB.focus = None
        return RedirectResponse("/lab", status_code=303)

    def _cur_or_redirect():
        t = LAB.current()
        return t

    async def lab_follow(request: Request):
        f = await request.form()
        t, R = LAB.current(), LAB.researcher()
        if t is None or R is None:
            return go("/lab", "Select a result first.", "warn")
        i = _form_int(f, "action", 0, 0)

        def run():
            n = R.follow(t, i)
            LAB.add([n])
            return f"Applied the suggested change: {n.diagnosis.verdict}."
        return _start(request, "the suggested change (1 simulation)", run, "/lab")

    async def lab_boost(request: Request):
        f = await request.form()
        t, R = LAB.current(), LAB.researcher()
        if t is None or R is None:
            return go("/lab", "Select a result first.", "warn")
        k, mode = _form_int(f, "k", 4, 1, 8), ("and" if f.get("mode") == "and" else "add")

        def run():
            try:
                rep = R.boost(t, k=k, mode=mode)
            except ValueError as e:
                LAB.boost = str(e)
                return (str(e), "warn")
            if rep.best is not None and rep.best.alpha_id:
                LAB.perf[rep.best.alpha_id] = R.performance(rep.best, compare=boost_compare(rep, rep.best))
            LAB.boost = rep
            LAB.add(rep.lab_results())
            return "Boost finished: the best combination is shown."
        return _start(request, f"boosters (up to {2 * k} simulations)", run, "/lab")

    async def lab_perf(request: Request):
        t, R = LAB.current(), LAB.researcher()
        if t is None or R is None or not t.alpha_id:
            return go("/lab", "Select a simulated result first.", "warn")

        def run():
            LAB.perf[t.alpha_id] = R.performance(t, compare=boost_compare(LAB.boost, t))
            return "Performance read (no simulation)."
        return _start(request, "reading the PnL", run, "/lab")

    async def lab_corr(request: Request):
        t, R = LAB.current(), LAB.researcher()
        if t is None or R is None or not t.alpha_id:
            return go("/lab", "Select a simulated result first.", "warn")

        def run():
            try:
                LAB.corr[t.alpha_id] = R.corr_status(t, refresh=True)
            except Exception as e:  # noqa: BLE001
                LAB.corr[t.alpha_id] = {"error": str(e)}
            return "Production correlation read (no simulation)."
        return _start(request, "reading production correlation", run, "/lab")

    async def lab_decorr(request: Request):
        f = await request.form()
        t, R = LAB.current(), LAB.researcher()
        if t is None or R is None or not t.alpha_id:
            return go("/lab", "Select a simulated result first.", "warn")
        k = _form_int(f, "k", 4, 1, 6)

        def run():
            try:
                rep = R.decorrelate(t, k=k)
            except ValueError as e:
                LAB.decorr = str(e)
                return (str(e), "warn")
            LAB.decorr = rep
            LAB.add(rep.lab_results())
            return "Lower correlation finished: the recommended version is shown."
        return _start(request, f"less crowded versions (up to {k} simulations)", run, "/lab")

    async def lab_robust(request: Request):
        t, R = LAB.current(), LAB.researcher()
        if t is None or R is None or not t.alpha_id:
            return go("/lab", "Select a simulated result first.", "warn")

        def run():
            LAB.robust[t.alpha_id] = R.robustness(t)
            return "Robustness battery finished."
        return _start(request, "robustness battery (about 7 simulations)", run, "/lab")

    async def lab_gate(request: Request):
        t, R = LAB.current(), LAB.researcher()
        if t is None or R is None or not t.alpha_id:
            return go("/lab", "Select a simulated result first.", "warn")

        def run():
            LAB.gate = R.gate(t, LAB.robust.get(t.alpha_id))
            return ("Gate: READY - the decision is yours." if LAB.gate.ready else "Gate: NOT READY.",
                    "ok" if LAB.gate.ready else "warn")
        return _start(request, "platform checks, correlations, deflated Sharpe", run, "/lab")

    async def lab_submit(request: Request):
        f = await request.form()
        g, R = LAB.gate, LAB.researcher()
        if g is None or R is None:
            return go("/lab", "Run the gate first.", "warn")
        confirm = (f.get("confirm") or "").strip()

        def run():
            try:
                res = R.submit(g, confirm=confirm)            # every check lives in Researcher.submit()
                LAB.submitted.append((g.alpha_id, str(res)))
                return f"{g.alpha_id}: {res}"
            except Exception as e:  # noqa: BLE001
                LAB.submitted.append((g.alpha_id, f"NOT submitted: {e}"))
                return (f"{g.alpha_id} NOT submitted: {e}", "err")
        return _start(request, "submitting " + str(g.alpha_id), run, "/lab")

    async def lab_restore(request: Request):
        R = LAB.researcher()
        if R is None:
            return go("/lab", LAB.problem, "err")
        with LAB.lock:
            old = list(LAB.results)
            LAB.results = []
        LAB.add(R.recent_results(10))
        with LAB.lock:
            LAB.results += old
        return go("/lab", "Restored your recent results from the journal (no simulation).")

    async def lab_recover(request: Request):
        R = LAB.researcher()
        if R is None:
            return go("/lab", LAB.problem, "err")

        def run():
            r = R.recover_pending()
            LAB.add(r["recovered"])
            return (f"Recovered {len(r['recovered'])} result(s) without simulating again"
                    + (f"; {r['running']} still running on BRAIN - try again in a few minutes" if r["running"] else "")
                    + (f"; {r['gone']} no longer on BRAIN" if r["gone"] else "") + ".")
        return _start(request, "collecting interrupted simulations", run, "/lab")

    return [
        Route("/lab", lab_page),
        Route("/lab/card", lab_card, methods=["POST"]), Route("/lab/card/act", lab_card_action, methods=["POST"]),
        Route("/lab/simulate", lab_simulate, methods=["POST"]), Route("/lab/results", lab_results, methods=["POST"]),
        Route("/lab/follow", lab_follow, methods=["POST"]), Route("/lab/boost", lab_boost, methods=["POST"]),
        Route("/lab/perf", lab_perf, methods=["POST"]), Route("/lab/corr", lab_corr, methods=["POST"]),
        Route("/lab/decorr", lab_decorr, methods=["POST"]), Route("/lab/robust", lab_robust, methods=["POST"]),
        Route("/lab/gate", lab_gate, methods=["POST"]), Route("/lab/submit", lab_submit, methods=["POST"]),
        Route("/lab/restore", lab_restore, methods=["POST"]), Route("/lab/recover", lab_recover, methods=["POST"]),
    ]


# ============================================================================================== PLAY
def play_routes(page, go):
    from hypolab import play as P

    async def play_page(request: Request):
        q = request.query_params
        if q.get("show"):
            try:
                LAB.play_focus = int(q["show"])
            except ValueError:
                pass
        R = await run_in_threadpool(LAB.researcher)
        ctx = dict(job_ctx("/play"), R=R, problem=LAB.problem, sandbox=LAB.sandbox)
        if R is None:
            return page(request, "play.html", **ctx)
        if LAB.roll is None:
            LAB.roll = P.load_roll(LAB.sandbox)
        st = P.play_stats(R.journal)
        ctx["stats"] = st
        ctx["regions"] = ["SBX"] if LAB.sandbox else config.account_regions()
        ctx["region"] = "SBX" if LAB.sandbox else (R.region if R.region in ctx["regions"] else ctx["regions"][0])
        items = LAB.roll or []
        ctx["roll"] = [dict(i=i, **{k: v for k, v in it.row().items()}) for i, it in enumerate(items)]
        ctx["rows"] = result_rows(LAB.play, None)
        sel = None
        if LAB.play:
            sel = next((t for k, t in LAB.play if k == LAB.play_focus), LAB.play[-1][1])
            ctx["sel_key"] = next(k for k, t in LAB.play if t is sel)
            for r in ctx["rows"]:
                r["on"] = r["key"] == ctx["sel_key"]
        ctx["sel"] = sel
        return page(request, "play.html", **ctx)

    async def play_roll(request: Request):
        f = await request.form()
        R = LAB.researcher()
        if R is None:
            return go("/play", LAB.problem, "err")
        mode = f.get("mode") if f.get("mode") in ("mix", "cards", "wild") else "mix"
        seed = _form_int(f, "seed", 0, 0) or None
        region = f.get("region") or R.region
        items = await run_in_threadpool(R.roll, n=_form_int(f, "n", 4, 1, 10), mode=mode, region=region, seed=seed,
                                        shuffle_settings=bool(f.get("shuffle")))
        P.save_roll(items, LAB.sandbox)
        LAB.roll = items
        if not items:
            return go("/play", "Nothing rolled: this region has no field list yet (the Data page comes in phase C3; "
                               "on the laptop use the cockpit's Data tab).", "warn")
        return go("/play", f"Rolled {len(items)} alpha(s). Rolling is free; only Simulate spends simulations.")

    async def play_sim(request: Request):
        f = await request.form()
        R = LAB.researcher()
        items = LAB.roll or []
        if R is None or not items:
            return go("/play", "Roll the dice first.", "warn")
        ticked = {int(x) for x in f.getlist("pick") if str(x).isdigit()}
        chosen = [it for i, it in enumerate(items) if not ticked or i in ticked]

        def run():
            res = R.play(chosen)
            LAB.add(res, where="play")
            return f"The dice brought back {len(res)} result(s)."
        return _start(request, f"{len(chosen)} random alpha(s)", run, "/play")

    async def play_tolab(request: Request):
        f = await request.form()
        k = _form_int(f, "key", -1)
        t = next((t for kk, t in LAB.play if kk == k), None)
        if t is None:
            return go("/play", "Select a result first.", "warn")
        if LAB.key_of(t) is None:
            LAB.add([t])
        else:
            LAB.focus = LAB.key_of(t)
        return go("/lab", "Sent to the Lab: robustness, gate and (your decision) submit are there.")

    return [Route("/play", play_page), Route("/play/roll", play_roll, methods=["POST"]),
            Route("/play/sim", play_sim, methods=["POST"]), Route("/play/tolab", play_tolab, methods=["POST"])]


# ============================================================================================== QUANT BASICS
BASICS: Dict[str, object] = {}

IDEAS = {
    "value (cash yield)": "group_rank(ts_backfill(fnd_cfo, 252) / cap, subindustry)",
    "quality score": "group_rank(ts_backfill(mdl_quality_score, 21), subindustry)",
    "revision breadth (rung 1)": "group_rank((anl_rev_up_30d - anl_rev_down_30d) / "
                                 "(anl_rev_up_30d + anl_rev_down_30d + 1), subindustry)",
    "revision breadth (rung 2)": "ts_mean(group_rank((anl_rev_up_30d - anl_rev_down_30d) / "
                                 "(anl_rev_up_30d + anl_rev_down_30d + 1), subindustry), 21)",
    "earnings drift (PEAD)": "group_rank(ts_backfill(ern_eps_surprise, 63), subindustry)",
    "1-week reversal": "group_rank(-ts_sum(returns, 5), subindustry)",
}
SLOW = "group_rank(ts_backfill(fnd_cfo, 252) / cap, subindustry)"
FAST = "group_rank(-ts_sum(returns, 5), subindustry)"
SWEEP_TEMPLATES = ["rank(ts_rank({x}, 126))", "rank(ts_decay_linear({x}, 126))", "rank(-ts_delta({x}, 21))",
                   "-rank({x})"]


def build_lessons() -> dict:
    """Lessons 1-5 of quant basics on the shared practice market (the same as apps/quant_basics.py)."""
    from hypolab import playground as pg
    from hypolab.sandbox.backtest import backtest
    from hypolab.sandbox.evaluator import Evaluator
    from hypolab.sandbox.market import shared_market
    data = shared_market()
    ev = Evaluator(data)
    out = {"size": f"{data.T} days x {data.N} stocks, {len(data.fields)} fields"}
    out["fields"] = table(pd.Series(data.descriptions, name="description").head(32).reset_index()
                          .rename(columns={"index": "field"}), code_cols=["field"])
    day = -1
    x = ev("rank(-ts_sum(returns, 5))")[day]
    out["l1"] = table(pd.DataFrame({"last_week_return": ev("ts_sum(returns, 5)")[day], "alpha_value": x})
                      .sort_values("alpha_value").head(5).round(4), index=True)
    out["l2_fig"] = fig_uri(pg.plot_distribution(["fnd_cfo", "rank(fnd_cfo)", "zscore(ts_backfill(fnd_cfo, 63))",
                                                  "ts_rank(close, 63)"], data))
    out["l2"] = table(pd.DataFrame({e: pg.describe(e, data) for e in [
        "ts_backfill(fnd_cfo, 63) / cap", "rank(ts_backfill(fnd_cfo, 63) / cap)",
        "winsorize(ts_backfill(fnd_cfo, 63) / cap, std=4)"]}).round(4).reset_index()
        .rename(columns={"index": "statistic"}))
    rows = []
    for d in (0, 3, 6, 10, 15):
        for name, e in (("slow value", SLOW), ("fast reversal", FAST)):
            r = backtest(ev(e), data, decay=d)
            rows.append({"signal": name, "decay": d, **{k: r.stats[k] for k in ("sharpe", "turnover", "returns",
                                                                                 "fitness")}})
    piv = pd.DataFrame(rows).pivot(index="decay", columns="signal", values=["turnover", "fitness"])
    piv.columns = [f"{a} - {b}" for a, b in piv.columns]
    out["l3"] = table(piv.round(3).reset_index())
    out["l4"] = table(pd.concat([pg.run({"value, NONE": SLOW}, data, neutralization="NONE"),
                                 pg.run({"value, SECTOR": SLOW}, data, neutralization="SECTOR"),
                                 pg.run({"value, SUBINDUSTRY": SLOW}, data, neutralization="SUBINDUSTRY")]),
                      index=True)
    out["l5"] = table(pg.run(IDEAS, data, decay=2), index=True)
    out["l5_fig"] = fig_uri(pg.pnl_plot({k: IDEAS[k] for k in ["revision breadth (rung 2)", "earnings drift (PEAD)",
                                                               "value (cash yield)"]}, data, decay=2))
    return out


def run_sweep() -> dict:
    """Lessons 6-7: the brute-force sweep on 40 noise fields, the deflated Sharpe and the robustness battery."""
    from hypolab import playground as pg
    from hypolab.overfit import deflated_sharpe, noise_table
    from hypolab.robustness import variants
    from hypolab.sandbox.backtest import backtest
    from hypolab.sandbox.evaluator import Evaluator
    from hypolab.sandbox.market import shared_market
    data = shared_market()
    ev = Evaluator(data)
    sweep = pg.template_sweep(SWEEP_TEMPLATES, [f"nz_{j:03d}" for j in range(40)], data, decay=4)
    best = sweep.iloc[0]
    r_noise = backtest(ev(best["name"]), data, decay=4)
    r_real = backtest(ev(IDEAS["revision breadth (rung 2)"]), data, decay=2)
    dsr = pd.DataFrame({"best noise alpha": deflated_sharpe(r_noise.pnl, n_trials=len(sweep)),
                        "revision breadth (2 tries)": deflated_sharpe(r_real.pnl, n_trials=2)})

    def battery(expr, decay):
        rows = []
        for v in variants(expr, {"neutralization": "SUBINDUSTRY", "region": "SBX"}):
            r = backtest(ev(v.expression), data, decay=decay, neutralization=v.settings["neutralization"])
            rows.append({"variant": v.name, "sharpe": r.stats["sharpe"]})
        return pd.DataFrame(rows).set_index("variant")["sharpe"]

    rob = pd.DataFrame({"best noise alpha": battery(best["name"], 4),
                        "revision breadth": battery(IDEAS["revision breadth (rung 2)"], 2)})
    return {"n": len(sweep), "best": f"Sharpe {best.sharpe} (train {best.train_sharpe}, test {best.test_sharpe})",
            "top": table(sweep.head(10), code_cols=["name"]), "noise": table(noise_table(years=5)),
            "dsr": table(dsr.reset_index().rename(columns={"index": "statistic"})),
            "robust": table(rob.round(3).reset_index())}


def basics_routes(page, go):
    async def basics_page(request: Request):
        return page(request, "basics.html", **job_ctx("/basics"), b=BASICS.get("lessons"), sweep=BASICS.get("sweep"),
                    mine=BASICS.get("mine"), stocks=config.sandbox_stocks())

    async def basics_build(request: Request):
        def run():
            BASICS["lessons"] = build_lessons()
            return "The lessons are ready."
        return _start(request, "building the lessons on the practice market", run, "/basics")

    async def basics_sweep(request: Request):
        def run():
            BASICS["sweep"] = run_sweep()
            return "The sweep finished: read lesson 6."
        return _start(request, "160 noise alphas", run, "/basics")

    async def basics_try(request: Request):
        f = await request.form()
        expr = (f.get("expression") or "").strip()
        decay = _form_int(f, "decay", 3, 0, 30)

        def work():
            from hypolab import playground as pg
            from hypolab.linter import Linter
            from hypolab.sandbox.market import shared_market
            lint = Linter().lint(expr)
            out = {"expr": expr, "decay": decay, "lint": lint.report(), "ok": lint.ok, "table": "", "error": ""}
            if lint.ok:
                try:
                    out["table"] = table(pg.run({"my alpha": expr}, shared_market(), decay=decay), index=True)
                except Exception as e:  # noqa: BLE001
                    out["error"] = f"Could not evaluate: {e}"
            return out
        if JOBS.busy():
            return go("/basics#try", f"Still working on: {JOBS.busy().title}.", "warn")
        BASICS["mine"] = await run_in_threadpool(work)
        return RedirectResponse("/basics#try", status_code=303)

    return [Route("/basics", basics_page), Route("/basics/build", basics_build, methods=["POST"]),
            Route("/basics/sweep", basics_sweep, methods=["POST"]), Route("/basics/try", basics_try, methods=["POST"])]


def routes(page, go) -> list:
    return lab_routes(page, go) + play_routes(page, go) + basics_routes(page, go)

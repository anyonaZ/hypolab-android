"""The cockpit's Journal, Pyramids and SuperAlpha tabs as web pages (1.14.0, Android phase C2).

Same engine calls and rules as apps/cockpit.py:
- Journal: the Researcher's journal (sandbox = the in-memory practice journal; live without a session = the journal
  file, read-only). Lessons can be added when it is writable.
- Pyramids: counts per QUARTER from your submitted alphas once the Account download exists (BRAIN_RULES S14), else
  BRAIN's all-time diversity counts, else HYPOLAB's journal; sandbox uses the practice market's own counts. Reading
  BRAIN sits behind "Refresh counts" (a job); the result is kept until the next refresh.
- SuperAlpha: a free check + preview first (nothing simulates), then ONE SuperAlpha simulation behind its button,
  the SuperAlpha gate, and a submit that only Researcher.super_submit() can let through (typed confirmation,
  1 a day, unlocked at 100 lifetime alphas, a READY SuperAlpha gate). SuperAlphas are built from HYPOLAB's recipes
  or your own code typed here - never from AI-written selection/combo code (HANDOFF decision).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route

from hypolab import config
from ideaweb.jobs import JOBS
from ideaweb.lab import LAB, _form_float, _form_int, _start, fig_uri, job_ctx, table

VERDICTS = ["PASS", "NEAR", "WEAK", "INVERTED", "NOISE", "ERROR"]


# ============================================================================================== JOURNAL
def journal_routes(page, go):
    async def journal_page(request: Request):
        from ideaengine import views
        q = request.query_params
        await run_in_threadpool(LAB.researcher)
        J = LAB.journal()
        ex = J.experiments()
        regions = sorted(r for r in ex["region"].dropna().unique()) if not ex.empty else []
        region = q.get("region") if q.get("region") in regions else "all"
        verdicts = [v for v in q.getlist("v") if v in VERDICTS]
        n = _form_int(q, "n", 30, 10, 2000)
        budget = int(config.settings()["max_sims_per_idea"])
        real = ex[ex["backend"] != "sandbox"] if not ex.empty and getattr(J, "path", "") != ":memory:" else ex
        exp = views.experiments_view(ex, None if region == "all" else region, verdicts or None)
        writable = not getattr(J, "readonly", False)
        return page(request, "journal.html", **job_ctx("/journal"), sandbox=LAB.sandbox, problem=LAB.problem,
                    total=len(ex), budget=budget, writable=writable, regions=regions, region=region,
                    verdicts=verdicts, all_verdicts=VERDICTS, n=n, more=len(exp) > n,
                    mix=table(views.verdict_mix(real)),
                    tries=table(views.tries_per_idea(ex, budget).head(40)),
                    scoreboard=table(J.scoreboard()),
                    experiments=table(exp.head(n), code_cols=["expression", "alpha_id"]),
                    submissions=table(J.submissions(), code_cols=["alpha_id"]),
                    lessons=table(J.lessons()))

    async def journal_lesson(request: Request):
        f = await request.form()
        J = LAB.journal()
        text = (f.get("text") or "").strip()
        if getattr(J, "readonly", False):
            return go("/journal", "The journal is read-only until you log in.", "warn")
        if not text:
            return go("/journal", "Write the lesson first.", "warn")
        J.add_lesson(text, idea_id=(f.get("idea") or "").strip())
        return go("/journal#lessons", "Lesson added.")

    return [Route("/journal", journal_page), Route("/journal/lesson", journal_lesson, methods=["POST"])]


# ============================================================================================== PYRAMIDS
def compute_pyramids(refresh: bool = False) -> dict:
    """Counts as the cockpit computes them (see the module docstring). BRAIN is read only on refresh=True."""
    from hypolab import account as acct
    from hypolab.pyramids import PyramidTracker, multiplier_table
    R, J = LAB.researcher(), LAB.journal()
    out = {"source": "journal", "notes": [], "raw": [], "totals": None, "mult": multiplier_table()}
    if R is not None and LAB.sandbox:
        out.update(counts=R.brain.diversity(), regions=["SBX"], source="sandbox")
        return out
    base = None
    yq = acct.current_quarter()
    if R is not None and refresh:
        try:
            out["mult"] = multiplier_table(R.brain.pyramid_multipliers())
        except Exception:  # noqa: BLE001
            pass
    if acct.last_sync(J):
        qc, notes = acct.quarter_pyramids(J, R.catalog if R is not None else None, *yq)
        base, out["source"], out["notes"] = PyramidTracker(qc), \
            f"your {yq[0]} Q{yq[1]} submissions (Account download)", list(notes)
    elif R is not None and refresh:
        try:
            div = R.brain.diversity()
            out["raw"] = div.attrs.get("raw_sample", [])
            base = PyramidTracker(div)
            out["source"] = "BRAIN, ALL TIME - Genius counts the quarter only: download your account on the Account page"
        except Exception as e:  # noqa: BLE001
            out["source"] = f"journal (BRAIN unavailable: {e})"
    base = base or PyramidTracker.from_journal(J)
    out.update(counts=base.counts, regions=base.regions, totals=base.totals)
    out["notes"] = list(out["notes"]) + list(base.notes)
    return out


def pyramid_routes(page, go):
    async def pyramids_page(request: Request):
        from hypolab.pyramids import GUIDE_DATASETS, GUIDE_NOTES, PyramidTracker
        from ideaengine import views
        q = request.query_params
        if LAB.pyr is None or LAB.pyr.get("_mode") != LAB.mode_key:
            LAB.pyr = await run_in_threadpool(compute_pyramids, False)
            LAB.pyr["_mode"] = LAB.mode_key
        p = LAB.pyr
        k = int(config.settings()["alphas_per_pyramid"])
        sort = "multiplier" if q.get("sort") == "multiplier" else "guide"
        tracker = PyramidTracker(p["counts"], alphas_per_pyramid=k, regions=p["regions"], multipliers=p["mult"])
        key = (id(p), k)
        if p.get("_figkey") != key:
            # categories down the side, regions across: readable on a portrait screen (1.14.0)
            p["_fig"] = fig_uri(views.pyramid_heatmap(tracker.matrix().T, tracker.k,
                                                      title=f"Alphas per cell (counts from {p['source']})"))
            p["_figkey"] = key
        notes = pd.DataFrame([{"category": c, "guide datasets": ", ".join(GUIDE_DATASETS.get(c, [])),
                               "note": GUIDE_NOTES.get(c, "")} for c in GUIDE_DATASETS])
        mult = ""
        if not LAB.sandbox and p["mult"] is not None and len(p["mult"]):
            mt = p["mult"].pivot_table(index="category", columns=["region", "delay"], values="multiplier")
            mt.columns = [f"{r} D{d}" for r, d in mt.columns]
            mult = table(mt.reset_index())
        return page(request, "pyramids.html", **job_ctx("/pyramids"), sandbox=LAB.sandbox, k=k, sort=sort,
                    summary=tracker.summary(), source=p["source"], notes=p["notes"], fig=p["_fig"],
                    totals=table(p["totals"]) if p["totals"] is not None and len(p["totals"]) else "",
                    plan1=table(tracker.plan(n=15, delay=1, by=sort)),
                    plan0=table(tracker.plan(n=15, delay=0, by=sort)),
                    guide=table(notes), mult=mult, mult_src=(p["mult"].attrs.get("source", "?")
                                                             if p["mult"] is not None else ""),
                    raw=p["raw"])

    async def pyramids_k(request: Request):
        f = await request.form()
        config.save_settings(alphas_per_pyramid=_form_int(f, "k", 3, 1, 50))
        return RedirectResponse("/pyramids", status_code=303)

    async def pyramids_refresh(request: Request):
        def run():
            LAB.pyr = compute_pyramids(refresh=True)
            LAB.pyr["_mode"] = LAB.mode_key
            return "Pyramid counts refreshed."
        return _start(request, "reading the Pyramid counts", run, "/pyramids")

    return [Route("/pyramids", pyramids_page), Route("/pyramids/k", pyramids_k, methods=["POST"]),
            Route("/pyramids/refresh", pyramids_refresh, methods=["POST"])]


# ============================================================================================== SUPERALPHA
def _sa_defaults(SA, store) -> dict:
    regions = ["SBX"] if LAB.sandbox else config.account_regions()
    from ideaengine import planner
    plan = (store.plan(planner.iso_week()) or {}).get("region")
    reg = plan if plan in regions else regions[0]
    return {"region": reg, "delay": 1, "universe": _sa_universe(reg), "neut": "SUBINDUSTRY",
            "decay": SA.DEFAULT_DECAY, "trunc": SA.DEFAULT_TRUNCATION, "limit": 20, "handling": "POSITIVE",
            "activation": "IS", "sel": "least_corr" if any(r.key == "least_corr" for r in SA.selections(30))
            else SA.selections(30)[0].key, "combo": SA.COMBOS[0].key, "sel_own": "", "combo_own": ""}


def _sa_universe(reg: str) -> str:
    if LAB.sandbox:
        return "SANDBOX"
    return config.universe_for(reg) or config.REGION_DEFAULTS.get(reg, {}).get("universe") or ""


def _sa_form(SA, f, base: dict) -> dict:
    regions = ["SBX"] if LAB.sandbox else config.account_regions()
    v = dict(base)
    v["region"] = f.get("region") if f.get("region") in regions else base["region"]
    v["delay"] = _form_int(f, "delay", 1, 0, 1)
    v["universe"] = (f.get("universe") or "").strip() or _sa_universe(v["region"])
    v["neut"] = f.get("neut") or "SUBINDUSTRY"
    v["decay"] = _form_int(f, "decay", SA.DEFAULT_DECAY, 0, 60)
    v["trunc"] = _form_float(f, "trunc", SA.DEFAULT_TRUNCATION, 0.01, 1.0)
    v["limit"] = _form_int(f, "limit", 20, SA.MIN_SELECTION, SA.MAX_SELECTION)
    v["handling"] = f.get("handling") if f.get("handling") in SA.SELECTION_HANDLING else "POSITIVE"
    v["activation"] = "OS" if f.get("activation") == "OS" else "IS"
    v["sel"] = f.get("sel") or base["sel"]
    v["combo"] = f.get("combo") or base["combo"]
    v["sel_own"] = (f.get("sel_own") or "").strip()
    v["combo_own"] = (f.get("combo_own") or "").strip()
    return v


def _sa_check(SA, v: dict, pool) -> dict:
    """The free check and preview of what would be simulated (same as the cockpit)."""
    sr, cr = SA.recipe("selection", v["sel"], v["limit"]), SA.recipe("combo", v["combo"])
    selection = v["sel_own"] or sr.code
    combo = v["combo_own"] or cr.code
    rep = SA.check(selection, combo, v["limit"], v["handling"], v["activation"], v["decay"], v["trunc"])
    why = []
    if not v["sel_own"]:
        why.append(f"**Selection - {sr.name}:** {sr.why}")
    if not v["combo_own"]:
        why.append(f"**Weighting - {cr.name}:** {cr.why}")
    pv = SA.preview(selection, pool, v["region"], v["delay"], v["limit"], v["handling"])
    kept = ""
    tab = pv.get("table")
    if pv.get("ok") and tab is not None and not tab.empty:
        t = tab.head(25).copy()
        t["score"] = t["score"].round(3)
        kept = table(t[["alpha_id", "score", "kept"]], code_cols=("alpha_id",))
    return {"selection": selection, "combo": combo, "ok": rep.ok, "warn": bool(rep.warnings), "md": rep.markdown(),
            "why": "\n\n".join(why), "preview": pv["note"], "kept": kept}


def superalpha_routes(page, go):
    from hypolab import superalpha as SA

    def _store():
        from ideaweb.state import state
        return state().store

    async def sa_page(request: Request):
        q = request.query_params
        R = await run_in_threadpool(LAB.researcher)
        J = LAB.journal()
        store = _store()
        pool = R.super_pool() if R is not None else SA.pool_alphas(J)
        pools = SA.pools(pool)
        lock = SA.unlock_status(store, J, sandbox=LAB.sandbox)
        if LAB.super_form is None or LAB.super_form.get("_mode") != LAB.mode_key:
            LAB.super_form = dict(_sa_defaults(SA, store), _mode=LAB.mode_key)
        v = LAB.super_form
        chk = await run_in_threadpool(_sa_check, SA, v, pool)
        pt = pools.copy()
        if not pt.empty:
            pt["ready"] = pt["ready"].map({True: "yes", False: "not yet (10+)"})
            pt = pt.rename(columns={"limit": "suggested limit"})
        if q.get("show"):
            LAB.super_focus = _form_int(q, "show", -1)
        res = LAB.super_results
        cur = None
        if res:
            cur = next((t for k, t in res if k == LAB.super_focus), res[-1][1])
        cur_key = next((k for k, t in res if t is cur), None)
        g = LAB.super_gate
        gate_here = g is not None and cur is not None and g.alpha_id == cur.alpha_id
        note = None
        if cur is not None and LAB.sandbox and R is not None:
            try:
                note = (R.brain._alphas.get(cur.alpha_id) or {}).get("sandbox_note")
            except Exception:  # noqa: BLE001
                note = None
        regions = ["SBX"] if LAB.sandbox else config.account_regions()
        delays = [1] if LAB.sandbox else list(dict.fromkeys(
            config.REGION_DEFAULTS.get(v["region"], {}).get("delays", [1]) + [1]))
        return page(request, "superalpha.html", **job_ctx("/superalpha"), R=R, sandbox=LAB.sandbox,
                    problem=LAB.problem, lock_line=SA.unlock_line(lock), unlocked=lock["unlocked"],
                    can_submit=lock["unlocked"] and lock["left_today"] > 0, msg_sa=LAB.super_msg,
                    pools=table(pt) if not pt.empty else "", v=v, chk=chk, regions=regions, delays=delays,
                    neuts=config.region_neutralizations(v["region"]) or ["SUBINDUSTRY"],
                    handlings=list(SA.SELECTION_HANDLING), sels=[(r.key, r.name) for r in SA.selections(30)],
                    combos=[(r.key, r.name) for r in SA.COMBOS], ladder=SA.ladder_note(), sources=SA.sources_note(),
                    smin=SA.MIN_SELECTION, smax=SA.MAX_SELECTION,
                    results=[(k, f"{i + 1}. {t.rung} | D{t.settings.get('delay')} decay {t.settings.get('decay')} | "
                                 f"{t.diagnosis.verdict}" + (f" {t.summary.get('is_sharpe'):.2f}"
                                                             if t.summary.get("is_sharpe") is not None else ""))
                             for i, (k, t) in enumerate(res)],
                    cur=cur, cur_key=cur_key, sandbox_note=note, gate_md=g.markdown() if gate_here else "",
                    gate_ready=bool(gate_here and g.ready))

    async def sa_check(request: Request):
        f = await request.form()
        LAB.super_form = dict(_sa_form(SA, f, LAB.super_form or _sa_defaults(SA, _store())), _mode=LAB.mode_key)
        if f.get("go") != "simulate":
            return RedirectResponse("/superalpha#build", status_code=303)
        R = LAB.researcher()
        if R is None:
            return go("/superalpha", LAB.problem or "No BRAIN session.", "err")
        v = LAB.super_form
        pool = R.super_pool()
        chk = _sa_check(SA, v, pool)
        if not chk["ok"]:
            return go("/superalpha#build", "The check found an error: fix it before simulating (nothing was spent).",
                      "err")
        store = _store()

        def run():
            t = R.super_test(chk["selection"], chk["combo"], v["region"], v["universe"] or None, v["delay"],
                             v["decay"], v["neut"], v["trunc"], v["limit"], v["handling"], v["activation"],
                             store=store)
            LAB._serial += 1
            LAB.super_results.append((LAB._serial, t))
            LAB.super_focus = None
            LAB.super_gate = None
            return f"SuperAlpha simulated: {t.diagnosis.verdict}."
        return _start(request, "1 SuperAlpha simulation", run, "/superalpha")

    async def sa_pool(request: Request):
        R = LAB.researcher()
        if R is None or not LAB.sandbox:
            return go("/superalpha", "The practice pool exists only in sandbox mode.", "warn")

        def run():
            n = R.practice_super_pool(24)
            LAB.super_msg = f"Practice pool: {n} sandbox alpha(s) submitted (they stand in for your 100 real ones)."
            return LAB.super_msg
        return _start(request, "building a practice pool", run, "/superalpha")

    async def sa_restore(request: Request):
        R = LAB.researcher()
        if R is None:
            return go("/superalpha", LAB.problem, "err")
        have = {t.alpha_id for _, t in LAB.super_results}
        old = list(LAB.super_results)
        LAB.super_results = []
        for t in R.super_results(20):
            if t.alpha_id not in have:
                LAB._serial += 1
                LAB.super_results.append((LAB._serial, t))
        LAB.super_results += old
        return go("/superalpha", "Restored SuperAlpha results from the journal (no simulation).")

    async def sa_gate(request: Request):
        R = LAB.researcher()
        res = LAB.super_results
        cur = next((t for k, t in res if k == LAB.super_focus), res[-1][1]) if res else None
        if R is None or cur is None or not cur.alpha_id:
            return go("/superalpha", "Simulate a SuperAlpha first.", "warn")
        store = _store()

        def run():
            LAB.super_gate = R.super_gate(cur, store)
            return ("SuperAlpha gate: READY - the decision is yours." if LAB.super_gate.ready else
                    "SuperAlpha gate: NOT READY.", "ok" if LAB.super_gate.ready else "warn")
        return _start(request, "platform checks, correlations, deflated Sharpe", run, "/superalpha")

    async def sa_submit(request: Request):
        f = await request.form()
        R, g = LAB.researcher(), LAB.super_gate
        if R is None or g is None:
            return go("/superalpha", "Run the SuperAlpha gate first.", "warn")
        confirm = (f.get("confirm") or "").strip()
        store = _store()

        def run():
            try:
                res = R.super_submit(g, confirm=confirm, store=store)      # every check lives there
                LAB.super_msg = (f"Submitted SuperAlpha {g.alpha_id} (BRAIN answered {res.get('status_code')}). "
                                 "That was today's one SuperAlpha.")
                return LAB.super_msg
            except Exception as e:  # noqa: BLE001
                LAB.super_msg = f"NOT submitted: {e}"
                return (LAB.super_msg, "err")
        return _start(request, "submitting SuperAlpha " + str(g.alpha_id), run, "/superalpha")

    return [Route("/superalpha", sa_page), Route("/superalpha/check", sa_check, methods=["POST"]),
            Route("/superalpha/pool", sa_pool, methods=["POST"]),
            Route("/superalpha/restore", sa_restore, methods=["POST"]),
            Route("/superalpha/gate", sa_gate, methods=["POST"]),
            Route("/superalpha/submit", sa_submit, methods=["POST"])]


def routes(page, go) -> list:
    return journal_routes(page, go) + pyramid_routes(page, go) + superalpha_routes(page, go)

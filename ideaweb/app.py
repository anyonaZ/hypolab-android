"""HYPOLAB Ideas: the web app for the idea side (1.7.0).

Pages: Week (goals, this week's plan, the Friday review), Leads (the learning loop, 1.8.0), Cards (ranked idea cards: read, send to the Lab, copy
into a draft, bin), Drafts (write or import a card, live checks with a dry-run binding, Critic hand-off, approve to
my_cards.yaml). Plain server-rendered pages; the only script is the draft editor's live check and copy buttons.

The idea pages never simulate and never talk to BRAIN. Writes: ideas.sqlite (plans, goals, drafts), my_cards.yaml (on
approval), the journal's bins and lessons, and lab_inbox.json ("Send to the Lab").

1.13.0 (Android phase C1): the cockpit's Lab, Play and Quant basics are pages here too (``ideaweb/lab.py``), shared by
the laptop and the tablet. Those pages DO simulate - each simulation behind its own button, as a background job.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode

import markdown as md
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

import hypolab
from hypolab import config
from hypolab import hypotheses as hyp
from hypolab.catalog import CATEGORY_NAMES
from hypolab.concepts import CONCEPTS
from hypolab.decorr import crowding_prior
from hypolab.ideas import generate_ideas
from ideaengine import drafts as D
from ideaengine import handoff, learn, planner, sources
from ideaweb.jobs import JOBS
from ideaweb.state import state

HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(HERE / "templates"))
STRENGTH = {1: "speculative", 2: "solid in papers", 3: "replicated in many markets"}
BIN_REASONS_CARDS = ["noise - no real signal", "data missing or too thin here", "weak story - I don't believe it",
                     "duplicate of another card", "crowded - everyone trades it"]


_LIST_LINE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\S")


def _loosen_lists(text: str) -> str:
    """1.13.0: python-markdown needs a blank line before a list; the engine's reports (written for marimo, which does
    not) put lists straight under a sentence. Add the blank line outside code blocks."""
    out, fence, prev = [], False, ""
    for line in (text or "").split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
        if (not fence and _LIST_LINE.match(line) and prev.strip() and not _LIST_LINE.match(prev)
                and not prev.lstrip().startswith("|")):
            out.append("")
        out.append(line)
        prev = line
    return "\n".join(out)


def render_md(text: str) -> str:
    return md.markdown(_loosen_lists(text or ""), extensions=["tables", "fenced_code"])


templates.env.filters["md"] = render_md
templates.env.filters["pct"] = lambda v: "-" if v is None or v != v else f"{float(v):.0%}"
templates.env.filters["num"] = lambda v, nd=2: "-" if v is None or v != v else f"{float(v):.{nd}f}"


def go(path: str, msg: str = "", kind: str = "ok", **extra) -> RedirectResponse:
    q = {k: v for k, v in {"msg": msg, "kind": kind if msg else "", **extra}.items() if v}
    return RedirectResponse(path + (("&" if "?" in path else "?") + urlencode(q) if q else ""), status_code=303)


_LEADS_COUNT = {"at": 0.0, "n": 0}


def _leads_count(st) -> int:
    """The number on the Leads link: rebuilt at most every 30 s (it reads the whole journal)."""
    import time as _t
    if _t.time() - _LEADS_COUNT["at"] > 30:
        try:
            _LEADS_COUNT["n"] = len(learn.items(st.journal, st.store, regions=_lead_regions(st)))
        except Exception:  # noqa: BLE001
            _LEADS_COUNT["n"] = 0
        _LEADS_COUNT["at"] = _t.time()
    return _LEADS_COUNT["n"]


def page(request: Request, name: str, **ctx):
    st = state()
    config.apply_themes()               # 1.8.1: a long-running app follows a theme's start and end dates
    counts = st.drafts.counts()
    n_leads = _leads_count(st)
    ctx.update(request=request, sandbox=st.sandbox, version=hypolab.__version__,
               msg=request.query_params.get("msg", ""), kind=request.query_params.get("kind", "ok"),
               lab_card=request.query_params.get("lab", ""),
               nav={"drafts_waiting": counts.get("draft", 0) + counts.get("checked", 0),
                    "week": planner.iso_week(), "leads": n_leads, "sources": _new_sources(st),
                    "job": JOBS.busy() is not None},
               platform=config.platform(),
               # 1.12.0: the tablet has no marimo cockpit (its pages arrive in Android phase C)
               cockpit_url=None if config.platform() == "android" else "http://127.0.0.1:2718",
               region_default=st.default_region())
    return templates.TemplateResponse(request, name, ctx)


# ============================================================================================== WEEK
async def week_page(request: Request):
    st = state()
    this = planner.iso_week()
    weeks = [this]
    for _ in range(6):
        weeks.append(planner.next_week(weeks[-1]))
    weeks = sorted(set(weeks) | set(st.store.weeks_planned()))
    week = request.query_params.get("week") or (this if st.store.plan(this) or this in planner.STARTING_PLAN else
                                                next((w for w in weeks if w > this), this))
    tracker = st.tracker()
    saved = st.store.plan(week)
    plan = planner.propose(week, tracker, saved)
    this_plan = planner.propose(this, tracker, st.store.plan(this))
    goals = planner.goals_view(st.store, st.journal)
    sub = planner.submission_status(st.store, st.journal, weekly_target=this_plan.get("submit_target"))
    prog = planner.week_progress(st.journal, week)
    try:
        digest = D.digest(st.journal, st.store, week, catalog=None if st.sandbox else st.catalog(), tracker=tracker)
    except Exception as e:  # noqa: BLE001
        digest = f"(digest failed: {e})"
    # phase 4: what the week has to respect, the Friday checklist, and the text for the HYPOLAB state doc
    try:
        ev = planner.evidence(st.journal, st.store, week, tracker)
        nm = ev.get("near_misses")
        ev["near_misses"] = nm.to_dict("records") if nm is not None and not nm.empty else []
    except Exception as e:  # noqa: BLE001
        ev = {"error": str(e)}
    try:
        checklist = planner.friday_checklist(st.journal, st.store, week)
    except Exception:  # noqa: BLE001
        checklist = []
    try:
        state_md = D.state_text(st.journal, st.store, week, tracker, None if st.sandbox else st.catalog())
    except Exception as e:  # noqa: BLE001
        state_md = f"(state text failed: {e})"
    regions = list(dict.fromkeys(st.regions() + [plan["region"]]))
    return page(request, "week.html", week=week, weeks=weeks, plan=plan, saved=saved is not None,
                extra=(saved or {}).get("extra") or {}, goals=goals.to_dict("records"),
                quarter=goals["quarter"].iloc[0] if not goals.empty else "",
                weeks_left=goals["weeks_left"].iloc[0] if not goals.empty else "",
                lifetime=st.store.lifetime(), sub_md=planner.submission_summary(sub), sub=sub, prog=prog,
                digest=digest, regions=regions, ev=ev, checklist=checklist, state_md=state_md,
                state_doc_url=config.settings().get("state_doc_url") or config.DEFAULTS["state_doc_url"],
                submit_cap=_submit_cap(),
                categories=[(c, CATEGORY_NAMES.get(c, c)) for c in planner.CATEGORY_IDS],
                tracker_summary=tracker.summary() if tracker is not None else "")


def _submit_cap() -> int:
    """The weekly submission ceiling: the daily cap x 5 working days (the same cap a pasted PLAN gets)."""
    return int(config.settings().get("max_submissions_per_day", 4)) * 5


async def week_plan(request: Request):
    f = await request.form()
    st = state()
    region = f.get("region")
    st.store.save_plan({"week": f["week"], "region": region,
                        "universe": config.REGION_DEFAULTS.get(region, {}).get("universe") or "TOP3000", "delay": 1,
                        "categories": f.getlist("categories"), "dataset_focus": f.get("dataset_focus", ""),
                        "card_target": int(f.get("card_target") or 0),
                        "submit_target": max(0, min(int(f.get("submit_target") or 0), _submit_cap())),
                        "review_note": f.get("review_note", "")})
    return go(f"/week?week={f['week']}", f"Plan for {f['week']} saved.")


async def week_goals(request: Request):
    f = await request.form()
    st = state()

    def num(k):
        return float(f.get(k) or 0)
    import datetime as _dt
    today = _dt.date.today()
    q = f"{today.year}-Q{(today.month - 1) // 3 + 1}"      # 1.8.1: numbers entered now are this quarter's
    st.store.set_goal("signals", num("signals_now"), num("signals_bar"), quarter=q)
    st.store.set_goal("pyramids", num("pyramids_now"), num("pyramids_bar"), quarter=q)
    st.store.set_goal("combined_perf", num("perf_now"), num("perf_bar"), quarter=q)
    lt = st.store.lifetime()
    if (num("life_now"), num("life_bar")) != (lt["base"], lt["unlock"]):
        st.store.set_goal("lifetime_alphas", num("life_now"), num("life_bar"))
    return go("/week", "Goals updated from your Genius page.")


async def week_review(request: Request):
    f = await request.form()
    st = state()
    regions = (["SBX"] if st.sandbox else []) + config.account_regions()
    plan, probs = D.parse_plan(f.get("plan", ""), regions)
    if plan is None:
        return go("/week", "Plan not saved: " + "; ".join(p.replace("error: ", "") for p in probs), "err")
    res = D.apply_plan(st.store, st.journal, plan)
    note = f"{res['lessons_added']} lesson(s) added to the journal" if res["lessons_added"] else "no new lessons"
    extra = (" Adjusted: " + "; ".join(probs)) if probs else ""
    return go(f"/week?week={plan['week']}", f"Plan for {plan['week']} saved ({plan['region']}, "
                                            f"{', '.join(plan['categories'])}); {note}.{extra}")


# ============================================================================================= LEADS
def _lead_regions(st) -> List[str]:
    """Where transfers may go: the plan's regions plus every region your journal has results in (never SBX)."""
    from hypolab import learning
    regs = {v[0] for v in planner.STARTING_PLAN.values()}
    try:
        ex = learning.live_experiments(st.journal)
        if not ex.empty:
            regs |= set(ex["region"].dropna().unique())
    except Exception:  # noqa: BLE001
        pass
    return sorted(r for r in regs if r and r != "SBX")


def _lead(st, key: str) -> Optional[dict]:
    it = learn.items(st.journal, st.store, regions=_lead_regions(st), show="all")
    m = it[it["key"] == key] if not it.empty else it
    return None if m.empty else m.iloc[0].to_dict()


async def leads_page(request: Request):
    from hypolab import learning
    st = state()
    show = request.query_params.get("show", "new")
    error = ""
    try:
        items = learn.items(st.journal, st.store, regions=_lead_regions(st), show=show)
        rows = items.drop(columns=["_row"]).to_dict("records") if not items.empty else []
    except Exception as e:  # noqa: BLE001
        rows, error = [], f"{type(e).__name__}: {e}"

    def recs(fn):
        try:
            df = fn()
            return df.to_dict("records") if df is not None and not df.empty else []
        except Exception:  # noqa: BLE001
            return []
    try:
        dj = json.dumps(json.loads(learn.digest_json(st.journal, st.store)), indent=1)
    except Exception as e:  # noqa: BLE001
        dj = f"(not available: {e})"
    return page(request, "leads.html", rows=rows, show=show, error=error, kinds=learn.KINDS,
                quality=recs(lambda: learn.source_quality(st.journal, st.store)),
                failures=recs(lambda: learning.check_failures(st.journal)),
                dead=recs(lambda: learning.dead_end_families(st.journal)),
                decisions=recs(lambda: learn.decisions(st.store)), digest_json=dj, sub="journal")


async def lead_action(request: Request):
    f = await request.form()
    st = state()
    _LEADS_COUNT["at"] = 0.0
    action, key = f.get("action", ""), f.get("key", "")
    item = _lead(st, key)
    if item is None:
        return go("/leads", "That lead is gone (new results changed it). The list below is current.", "warn")
    if action == "skip":
        learn.skip(st.store, item, f.get("note", ""))
        return go("/leads", f"Skipped {item['subject']}. It comes back if new results change its evidence.")
    if action == "reopen":
        learn.reopen(st.store, key)
        return go("/leads", f"{item['subject']} is back in the list.")
    if action == "lab":
        handoff.send_to_lab(item["hypothesis_id"], item["region"])
        extra = " Flip it only if you can say why the reverse mechanism is true." if item["kind"] == "inverted" else ""
        return go("/leads", f"{item['hypothesis_id']} sent to the Lab for {item['region']}. In the cockpit's Lab "
                            f"press \"Pick up the card sent from Ideas\".{extra}")
    if action == "draft":
        try:
            if item["kind"] == "sibling":
                card = learn.sibling_draft(st.journal, item["subject"], taken=st.drafts.ids())
            elif item["kind"] == "scan":
                card = learn.scan_draft(item["_row"], taken=st.drafts.ids())
            else:
                return go("/leads", "Only siblings and scanned fields become drafts; send the others to the Lab.",
                          "warn")
            rep = D.check_card(card, st.catalog(), item["region"], journal=st.journal, library=hyp.load_library())
            src = f"inbox{' (practice)' if st.sandbox else ''}: {item['kind']} {item['subject']}"
            cid = st.drafts.save(card, src, report=rep)
            learn.mark_drafted(st.store, item, cid)
        except Exception as e:  # noqa: BLE001
            return go("/leads", f"No draft: {e}", "err")
        tip = ("Write why_persists and the story: who is wrong, and why this field measures it - or bin it."
               if item["kind"] == "scan" else "Change ONE thing for an economic reason and say which in the story.")
        return go(f"/drafts/{cid}", f"Draft {cid} made from the lead ({rep.state}). {tip}",
                  "ok" if rep.ok else "warn")
    return go("/leads", f"Unknown action {action!r}.", "err")


# =================================================================================== LEADS: OUTSIDE SOURCES
def _this_plan(st) -> dict:
    w = planner.iso_week()
    return planner.propose(w, None, st.store.plan(w))


def _new_sources(st) -> int:
    return sources.new_count(st.store)


async def sources_page(request: Request):
    st = state()
    q = request.query_params
    kind = q.get("src", "")                # not "kind": that name carries the flash message's colour
    show = q.get("show", "new")
    text = q.get("q", "").strip()
    n = min(int(q.get("n") or 40), 300)
    plan = _this_plan(st)
    error = ""
    try:
        sources.refresh_covered(st.store)             # 1.9.1: a card approved since then may cover a paper now
        df = sources.items(st.store, kinds=[kind] if kind else None, show=show, plan=plan, limit=n, query=text)
        rows = df.to_dict("records") if not df.empty else []
        total = df.attrs.get("total", len(rows))
    except Exception as e:  # noqa: BLE001
        rows, total, error = [], 0, f"{type(e).__name__}: {e}"
    for r in rows:
        y = r.get("year")
        r["year"] = int(y) if isinstance(y, (int, float)) and y == y and y else None   # pandas made it a float
        r["evidence"] = sources.evidence_line(r)
        r["writer"] = sources.writer_message(r, plan)
    return page(request, "sources.html", rows=rows, total=total, src=kind, show=show, q=text, n=n, kinds=sources.KINDS,
                counts=sources.counts(st.store), runs=sources.last_runs(st.store), plan=plan, error=error,
                feeds=_feed_urls(), muted=_muted_view(), sub="sources")


def _feed_urls() -> list:
    from ideaengine import collectors as C
    return C.feed_urls()


def _muted_view() -> list:
    from ideaengine import collectors as C
    labels = {t.key: t.label for t in C.NEWS_THEMES}
    return [{"key": k, "label": labels.get(k, k)} for k in C.muted_themes()]


async def source_writer(request: Request):
    """The SOURCE block with the dataset's field list (needs the catalog, so it is built on demand)."""
    from starlette.responses import PlainTextResponse
    st = state()
    d = sources.get(st.store, request.path_params["sid"])
    if d is None:
        return PlainTextResponse("No such source.", status_code=404)
    return PlainTextResponse(sources.writer_message(d, _this_plan(st), catalog=st.catalog()))


async def source_fetch(request: Request):
    from starlette.concurrency import run_in_threadpool
    f = await request.form()
    st = state()
    which = f.get("collector", "")
    kind, origin = ("osap", "download") if which == "osap_download" else (which, "")
    try:
        if kind == "datasets":
            res = sources.collect(st.store, "datasets", catalog=st.catalog(), journal=st.journal,
                                  regions=None if st.sandbox else config.account_regions())
        elif kind == "osap" and not origin:
            res = sources.collect(st.store, "osap")                         # the bundled list: no download
        else:
            if kind not in sources.NETWORK:
                raise ValueError(f"unknown collector {kind!r}")
            # 1.9.1: the download runs in a worker thread (it blocked every page of the app for up to a minute);
            # storing stays here, on the app's own database connection
            try:
                fetched = await run_in_threadpool(sources.fetch, kind, origin)
            except Exception as e:  # noqa: BLE001
                sources.log_run(st.store, kind, error=f"{type(e).__name__}: {e}", origin=origin)
                raise
            res = sources.collect(st.store, kind, fetched=fetched)
    except Exception as e:  # noqa: BLE001
        hint = (" From a terminal you can read a page you saved yourself: python -m hypolab collect "
                f"{kind} --file <saved file>." if kind in ("arxiv", "news", "osap") else "")
        return go("/leads/sources", f"{kind}: nothing collected ({type(e).__name__}: {str(e)[:200]}).{hint}", "err")
    warn = f" {len(res['errors'])} feed(s) failed: {'; '.join(res['errors'])[:300]}" if res.get("errors") else ""
    ret = f" {res['retired']} dataset(s) you have used since left the new list." if res.get("retired") else ""
    return go(f"/leads/sources?src={'dataset' if kind == 'datasets' else kind}",
              f"{kind}: {res['found']} item(s) read, {res['added']} new.{ret}{warn}", "warn" if warn else "ok")


async def source_unmute(request: Request):
    f = await request.form()
    theme = f.get("theme", "")
    sources.unmute_theme(theme)
    return go("/leads/sources?src=news", f"{theme} is no longer muted: the next news fetch collects it again.")


async def source_add(request: Request):
    f = await request.form()
    try:
        sid = sources.add_manual(state().store, f.get("title", ""), f.get("url", ""), f.get("text", ""),
                                 f.get("authors", ""), f.get("year") or None)
    except Exception as e:  # noqa: BLE001
        return go("/leads/sources", f"Not added: {e}", "err")
    return go("/leads/sources?src=manual", f"Added {sources.source_tag(sid)}. Copy it for Scout & Writer, or make a draft.")


async def source_action(request: Request):
    f = await request.form()
    st = state()
    sid, action = f.get("id", ""), f.get("action", "")
    d = sources.get(st.store, sid)
    back = _back(request, "/leads/sources")
    if d is None:
        return go(back, "That source is gone.", "warn")
    if action == "skip":
        sources.skip(st.store, sid, f.get("note", ""))
        return go(back, f"Skipped {d['tag']}. Most sources produce no card - that is normal.")
    if action == "reopen":
        sources.reopen(st.store, sid)
        return go(back, f"{d['tag']} is back in the list.")
    if action == "mute" and d["kind"] == "news":
        theme = (d.get("extra") or {}).get("theme", "")
        try:
            n = sources.mute_theme(st.store, theme)
        except Exception as e:  # noqa: BLE001
            return go(back, f"Not muted: {e}", "err")
        return go(back, f"Muted the news theme {theme} ({n} item(s) skipped). Unmute it under Collect.")
    if action == "draft":
        try:
            card = sources.source_draft(d, taken=st.drafts.ids())
            # 1.9.1: a dataset is checked in its own region (it was checked in the week's region)
            region = (d.get("extra") or {}).get("region") if d["kind"] == "dataset" else None
            region = region if region and region in st.regions() else st.default_region()
            rep = D.check_card(card, st.catalog(), region, journal=st.journal, library=hyp.load_library())
            cid = st.drafts.save(card, d["tag"], report=rep)
            sources.set_state(st.store, sid, "drafted", draft_id=cid)
        except Exception as e:  # noqa: BLE001
            return go(back, f"No draft: {e}", "err")
        return go(f"/drafts/{cid}", f"Draft {cid} made from {d['tag']}. Write the mechanism (story, why it persists) "
                                    "and rung 1 in your own words - or bin it.", "warn")
    return go(back, f"Unknown action {action!r}.", "err")


# ============================================================================================= CARDS
def _card_view(c, journal) -> dict:
    h = c.hypothesis
    prior = crowding_prior(c, journal)
    return {"id": h.id, "title": h.title, "story": h.story, "why": h.why_persists, "family": h.family,
            "horizon": h.horizon, "strength": h.strength, "strength_txt": STRENGTH.get(h.strength, ""),
            "source": h.source, "sign": h.sign,
            "pyramid": ", ".join(CATEGORY_NAMES.get(x, x) for x in c.categories),
            "fields": [(b.role, b.field_id, b.dataset) for b in c.bindings.values()],
            "steps": [(s.name, s.expression, s.is_test, s.lint.ok) for s in c.steps],
            "score": round(c.score, 2), "notes": c.score_notes, "crowding": prior,
            "references": h.references, "watch_out": h.watch_out}


async def cards_page(request: Request):
    st = state()
    q = request.query_params
    region = q.get("region") or st.default_region()
    cats = q.getlist("cats")
    if "cats" not in q and not st.sandbox:
        cats = list((st.store.plan(planner.iso_week()) or planner.propose(planner.iso_week())).get("categories") or [])
    source = q.get("source", "all")
    n = int(q.get("n") or 30)
    binned = st.journal.binned_ids()
    lib = [h for h in hyp.load_library() if h.id not in binned]
    if source != "all":
        lib = [h for h in lib if h.source == source]
    catalog = st.catalog()
    uni = config.REGION_DEFAULTS.get(region, {}).get("universe") or "TOP3000"
    has_fields = catalog.has_context(region, uni, 1)
    tracker = st.tracker()
    try:
        need = tracker.need(region) if tracker is not None else {}
    except Exception:  # noqa: BLE001
        need = {}
    cards = generate_ideas(catalog, region, categories=cats or None, n=n, journal=st.journal, pyramid_need=need,
                           beginner=True, library=lib, one_per_family=True) if lib else []
    b = st.journal.binned()
    return page(request, "cards.html", region=region, regions=st.regions(), cats=cats, source=source, n=n,
                categories=[(c, CATEGORY_NAMES.get(c, c)) for c in planner.CATEGORY_IDS],
                cards=[_card_view(c, st.journal) for c in cards], has_fields=has_fields,
                binned=b.to_dict("records") if not b.empty else [], bin_reasons=BIN_REASONS_CARDS,
                warnings=list(hyp.LOAD_WARNINGS))


def _back(request: Request, default: str = "/cards") -> str:
    ref = request.headers.get("referer", "")
    m = re.search(r"//[^/]+(/[^#]*)", ref)
    path = m.group(1) if m else default
    path = re.sub(r"([?&])(msg|kind|lab)=[^&]*", r"\1", path).replace("?&", "?").rstrip("?&")
    return path or default


async def card_lab(request: Request):
    cid = request.path_params["cid"]
    f = await request.form()
    handoff.send_to_lab(cid, f.get("region") or None)
    if config.platform() == "android":          # 1.13.0: the Lab is a page here
        return RedirectResponse("/lab", status_code=303)
    return go(_back(request), f"{cid} sent to the Lab. Open the Lab page (it picks the card up), or in the marimo "
                              "cockpit's Lab press \"Pick up the card sent from Ideas\".")


async def card_bin(request: Request):
    cid = request.path_params["cid"]
    f = await request.form()
    state().journal.bin_card(cid, f.get("reason") or "")
    return go(_back(request), f"Binned {cid}. It is out of the ranking, the Lab list, Play and boosters; "
                              "restore it from the bin below.")


async def card_restore(request: Request):
    cid = request.path_params["cid"]
    state().journal.restore_card(cid)
    return go(_back(request), f"{cid} is back.")


async def card_draft(request: Request):
    cid = request.path_params["cid"]
    st = state()
    c = D.copy_of(cid, taken=st.drafts.ids())
    st.drafts.save(c, f"copy of {cid}", state="draft")
    return go(f"/drafts/{c['id']}", f"Copied {cid} as {c['id']}. Change one thing for an economic reason - data, "
                                    "mechanism or horizon - or it is the same card twice.")


# ============================================================================================ DRAFTS
async def drafts_page(request: Request):
    st = state()
    which = request.query_params.get("show", "waiting")
    sel = {"waiting": ["draft", "checked"], "approved": ["approved"], "binned": ["binned"], "all": None}.get(which)
    df = st.drafts.list(sel)
    return page(request, "drafts.html", show=which, rows=df.to_dict("records") if not df.empty else [],
                counts=st.drafts.counts(), regions=st.regions(), plan=_this_plan(st))


def _values_from_form(f) -> Dict:
    def rows(prefix, keys, n):
        out = []
        for i in range(n):
            r = {k: f.get(f"{prefix}_{k}_{i}", "") for k in keys}
            if "optional" in r:
                r["optional"] = bool(r["optional"])
            out.append(r)
        return out
    nr = int(f.get("n_roles") or D.FORM_ROLES)
    ng = int(f.get("n_rungs") or D.FORM_RUNGS)
    v = {k: f.get(k, "") for k in ("id", "title", "family", "category", "horizon", "sign", "story", "why_persists",
                                   "references", "watch_out", "neutralization")}
    v.update(strength=f.get("strength") or 2, decay=f.get("decay") or 0, truncation=f.get("truncation") or 0.08,
             turnover_low=f.get("turnover_low") or 0, turnover_high=f.get("turnover_high") or 0,
             roles=rows("role", ("name", "concept", "optional", "note"), nr),
             rungs=rows("rung", ("name", "expr", "teaches"), ng))
    return v


def _card_from_form(f) -> dict:
    try:
        base = json.loads(f.get("base") or "{}")
    except ValueError:
        base = {}
    return D.card_from_form(_values_from_form(f), base)


def _check(card: dict, region: str, allow_id: Optional[str] = None):
    st = state()
    return D.check_card(card, st.catalog(), region, journal=st.journal, library=hyp.load_library(), allow_id=allow_id)


def _checks_html(request: Request, rep, card: dict, source: str) -> Dict:
    t = templates.get_template("_checks.html")
    body = t.render(rep=rep, table=rep.table().to_dict("records"))
    return {"html": body, "summary": rep.summary(), "ok": rep.ok, "state": rep.state,
            "yaml": D.card_yaml(card, source), "critic": D.critic_message(card, rep, source, _this_plan(state()))}


def _editor(request: Request, card: dict, row: Optional[dict], source: str, region: str):
    st = state()
    allow = row["id"] if row and row["state"] == "approved" else None
    rep = _check(card, region, allow)
    d = D.form_defaults(card)
    cats = [("auto", "auto (from the data used)")] + [(k, f"{v} ({k})") for k, v in CATEGORY_NAMES.items()]
    if d["category"] not in [c for c, _ in cats]:
        cats.append((d["category"], d["category"]))
    neut = list(dict.fromkeys(sorted(D.NEUTRALIZATIONS) + [d["neutralization"]]))
    return page(request, "editor.html", card=card, d=d, row=row, source=source, region=region, regions=st.regions(),
                base=json.dumps(card, default=str), concepts=sorted(CONCEPTS), concept_notes={
                    k: c.note for k, c in CONCEPTS.items()}, cats=cats, neutralizations=neut,
                horizons=list(dict.fromkeys(list(D.HORIZONS) + [d["horizon"]])), strengths=STRENGTH,
                checks=_checks_html(request, rep, card, source), bin_reasons=D.BIN_REASONS,
                verdict_md=D.verdict_markdown(row["verdict"]) if row and row.get("verdict") else "",
                readonly=bool(row and row["state"] == "approved"))


async def draft_new(request: Request):
    return _editor(request, D.template(), None, "", request.query_params.get("region") or state().default_region())


async def draft_open(request: Request):
    st = state()
    row = st.drafts.get(request.path_params["did"])
    if row is None or row["card"] is None:
        return go("/drafts", f"No draft {request.path_params['did']}.", "err")
    return _editor(request, row["card"], row, row.get("source") or "",
                   request.query_params.get("region") or st.default_region())


async def api_check(request: Request):
    f = await request.form()
    card = _card_from_form(f)
    old = f.get("old_id") or None
    row = state().drafts.get(old) if old else None
    allow = old if row and row["state"] == "approved" else None
    rep = _check(card, f.get("region") or state().default_region(), allow)
    return JSONResponse(_checks_html(request, rep, card, f.get("source", "")))


async def draft_action(request: Request):
    f = await request.form()
    st = state()
    action = f.get("action", "save")
    card = _card_from_form(f)
    source = f.get("source", "")
    old = f.get("old_id") or None
    region = f.get("region") or st.default_region()
    rep = _check(card, region)
    cid = str(card.get("id", "")).strip()
    try:
        if action == "approve":
            if not rep.ok:
                return go(f"/drafts/{old}" if old else "/drafts/new",
                          f"Not approved: {rep.summary()}. The checks say what to fix.", "err")
            had = (hyp.user_library_dir() / D.MY_CARDS).exists()
            cid = st.drafts.save(card, source, report=rep, old_id=old)
            path = st.drafts.approve(cid, rep)
            note = "" if rep.idea is not None or not rep.region else f" It does not bind in {rep.region}: pick a region where its data exists."
            return go("/drafts", f"{cid} approved and added to {path}" + (" (previous file kept as my_cards.yaml.bak)"
                                 if had else "") + f". It is in Cards (source mine) and the Lab's list.{note}",
                      lab=cid)
        cid = st.drafts.save(card, source, report=rep, old_id=old)
        if action == "bin":
            st.drafts.bin(cid, f.get("reason") or "no reason given")
            return go("/drafts", f"Binned {cid} ({f.get('reason')}). Restore it from the binned list.")
        return go(f"/drafts/{cid}", f"Saved {cid} as {rep.state}. {rep.summary()}.", "ok" if rep.ok else "warn")
    except Exception as e:  # noqa: BLE001
        return go(f"/drafts/{old}" if old else "/drafts", f"Not saved: {e}", "err")


async def draft_restore(request: Request):
    did = request.path_params["did"]
    state().drafts.restore(did)
    return go(f"/drafts/{did}", f"{did} is back as a draft.")


async def draft_verdict(request: Request):
    f = await request.form()
    nxt = {"keep": "Approve it when the checks pass, then test rung 1 in the Lab.",
           "rewrite": "Give the fixes to Scout & Writer, then import the rewritten card.",
           "bin": "If you agree, bin it with the reason \"Critic said bin\" - the decision stays yours."}
    try:
        v = state().drafts.attach_verdict(f.get("verdict", ""), f.get("draft_id") or None)
        return go(f"/drafts/{v['id']}", f"Verdict {v['decision']} attached to {v['id']}. {nxt[v['decision']]}")
    except Exception as e:  # noqa: BLE001
        back = f"/drafts/{f.get('draft_id')}" if f.get("draft_id") else "/drafts"
        return go(back, f"Verdict not attached: {e}", "err")


async def draft_import(request: Request):
    f = await request.form()
    st = state()
    region = f.get("region") or st.default_region()
    rewrite = bool(f.get("rewrite"))
    ok, bad, notes = [], [], []
    lib = hyp.load_library()
    for p in D.parse_cards(f.get("cards", "")):
        notes += p.warnings
        if p.card is None:
            bad += p.errors
            continue
        cid = str(p.card.get("id", "")).strip()
        cur = st.drafts.get(cid) if cid else None
        # 1.10.3: an id that is already a draft is never overwritten by accident
        if cur is not None and cur["state"] != "approved" and not rewrite:
            bad.append(f"{cid} already exists as a {cur['state']} draft (\"{cur.get('title') or ''}\"): not imported. "
                       "If this is its rewrite, tick \"This is a rewrite\" and import again; otherwise give the new "
                       "card another id")
            continue
        rep = D.check_card(p.card, st.catalog(), region, journal=st.journal, library=lib)
        try:
            if cur is not None and cur["state"] != "approved":
                cid = st.drafts.replace(p.card, p.source, report=rep)
                what = "rewrite: old verdict cleared"
            else:
                cid = st.drafts.save(p.card, p.source or "imported", report=rep)
                what = ""
            linked = sources.link_draft(st.store, p.source, cid) if p.source else None    # 1.9.0: # from: S-...
            ok.append(f"{p.card['id']} ({rep.state}{', ' + what if what else ''})"
                      + (f" from {sources.source_tag(linked)}" if linked else ""))
        except Exception as e:  # noqa: BLE001
            bad.append(f"{p.card.get('id')}: {e}")
    if not ok:
        return go("/drafts", "Nothing imported: " + "; ".join(bad + notes), "err")
    msg = f"Imported in {region}: " + ", ".join(ok) + (". Problems: " + "; ".join(bad) if bad else "") + \
        (". Check the sources: " + "; ".join(notes) if notes else "") + "."
    first = ok[0].split(" ")[0]
    return go(f"/drafts/{first}", msg, "ok" if not (bad or notes) else "warn")


async def pack(request: Request):
    from hypolab.journal import Journal
    try:
        from ideaengine.knowledge_pack import USED_BY
        files = D.rebuild_knowledge_pack(Journal.open_readonly(), state().store)
        ch = getattr(files, "changed", None)
        if ch is None:
            what = "Re-upload the files that changed to the Claude Projects."
        elif not ch:
            what = "Nothing changed since the last rebuild: no re-upload needed."
        else:          # 1.10.1: say exactly which files changed and where each one goes
            what = "Re-upload: " + "; ".join(f"{n} to {', '.join(USED_BY.get(n, []))}" for n in ch) + "."
        return go(_back(request, "/drafts"), f"Knowledge pack rebuilt in {files[0].parent}. {what}")
    except Exception as e:  # noqa: BLE001
        return go(_back(request, "/drafts"), f"Knowledge pack not rebuilt: {e}", "err")


async def home(request: Request):
    return RedirectResponse("/week", status_code=307)


routes = [
    Route("/", home),
    Route("/week", week_page), Route("/week/plan", week_plan, methods=["POST"]),
    Route("/week/goals", week_goals, methods=["POST"]), Route("/week/review", week_review, methods=["POST"]),
    Route("/leads", leads_page), Route("/leads/act", lead_action, methods=["POST"]),
    Route("/leads/sources", sources_page), Route("/leads/sources/fetch", source_fetch, methods=["POST"]),
    Route("/leads/sources/add", source_add, methods=["POST"]),
    Route("/leads/sources/unmute", source_unmute, methods=["POST"]),
    Route("/leads/sources/act", source_action, methods=["POST"]),
    Route("/leads/sources/{sid}/writer", source_writer),
    Route("/cards", cards_page),
    Route("/cards/{cid}/lab", card_lab, methods=["POST"]), Route("/cards/{cid}/bin", card_bin, methods=["POST"]),
    Route("/cards/{cid}/restore", card_restore, methods=["POST"]),
    Route("/cards/{cid}/draft", card_draft, methods=["POST"]),
    Route("/drafts", drafts_page), Route("/drafts/new", draft_new),
    Route("/drafts/save", draft_action, methods=["POST"]), Route("/drafts/import", draft_import, methods=["POST"]),
    Route("/drafts/verdict", draft_verdict, methods=["POST"]), Route("/pack", pack, methods=["POST"]),
    Route("/drafts/{did}/restore", draft_restore, methods=["POST"]), Route("/drafts/{did}", draft_open),
    Route("/api/check", api_check, methods=["POST"]),
    Mount("/static", StaticFiles(directory=str(HERE / "static")), name="static"),
]
from ideaweb import lab as _lab  # noqa: E402  (1.13.0: Lab, Play, Quant basics)

from ideaweb import records as _records  # noqa: E402  (1.14.0: Journal, Pyramids, SuperAlpha)

routes[-1:-1] = _lab.routes(page, go) + _records.routes(page, go)

class LocalOriginOnly:
    """1.8.1: refuse POSTs that come from another web site. The app listens on 127.0.0.1 only, but any page open in
    the same browser could otherwise send a form here (bin cards, approve drafts, overwrite a plan)."""
    OK_HOSTS = {"127.0.0.1", "localhost", "::1"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST":
            from urllib.parse import urlparse
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            src = headers.get("origin") or headers.get("referer") or ""
            host = urlparse(src).hostname if src and src != "null" else None
            if src and host not in self.OK_HOSTS:
                from starlette.responses import PlainTextResponse
                await PlainTextResponse("Refused: this form did not come from the HYPOLAB Ideas page.",
                                        status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


class LaunchKey:
    """1.12.0 (Android): when HYPOLAB_LAUNCH_SECRET is set, every request needs the cookie that the app's first URL
    (``/?k=<secret>``) sets. Other apps on the tablet can reach 127.0.0.1 too; without the per-launch secret they
    get 403. Not set on the laptop, where nothing changes."""
    COOKIE = "hl_k"

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        import os
        secret = os.environ.get("HYPOLAB_LAUNCH_SECRET", "")
        if not secret or scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        import hmac
        from urllib.parse import parse_qs
        from starlette.responses import PlainTextResponse
        q = parse_qs(scope.get("query_string", b"").decode())
        given = (q.get("k") or [""])[0]
        if given:
            if hmac.compare_digest(given, secret):
                resp = RedirectResponse("/week", status_code=303)
                resp.set_cookie(self.COOKIE, secret, httponly=True, samesite="strict", path="/")
                await resp(scope, receive, send)
                return
        else:
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            jar = {}
            for part in headers.get("cookie", "").split(";"):
                k, _, v = part.strip().partition("=")
                jar[k] = v
            if hmac.compare_digest(jar.get(self.COOKIE, ""), secret):
                await self.app(scope, receive, send)
                return
        await PlainTextResponse("Refused: open HYPOLAB from its own app.", status_code=403)(scope, receive, send)


app = LaunchKey(LocalOriginOnly(Starlette(routes=routes)))


def main(port: Optional[int] = None, open_browser: bool = False) -> None:
    import uvicorn
    port = port or handoff.ideas_port()
    if open_browser:
        import threading
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    # 127.0.0.1 only: nothing outside this laptop can reach it
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()

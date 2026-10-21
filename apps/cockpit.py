import marimo

__generated_with = "0.23.16"
app = marimo.App(width="full", app_title="HYPOLAB cockpit", css_file="hypolab.css", html_head_file="head.html")


@app.cell(hide_code=True)
def _():
    import sys

    import marimo as mo

    _root = mo.notebook_dir().parent if mo.notebook_dir() else None
    if _root is not None and str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    import pandas as pd

    import hypolab
    from hypolab import config, connect, decorr, play, rules, theme
    from hypolab import hypotheses as hyp
    from hypolab.brain import AuthError, BrainClient, quota as brain_quota
    from hypolab import account as acct
    from hypolab.concepts import CONCEPTS
    from hypolab.operators import GOLD
    from hypolab.catalog import CATEGORY_NAMES, Catalog
    from hypolab.ideas import generate_ideas
    from hypolab.journal import Journal
    from hypolab.pyramids import GUIDE_DATASETS, GUIDE_NOTES, TIERS, PyramidTracker, multiplier_table
    from ideaengine import drafts as idea_drafts
    from ideaengine import handoff
    from ideaengine import planner, views
    from ideaengine.connection import LOGIN_HELP, open_researcher
    from ideaengine.store import IdeaStore

    pd.set_option("display.max_colwidth", 200)
    return (acct, AuthError, BrainClient, CATEGORY_NAMES, CONCEPTS, Catalog, GOLD, GUIDE_DATASETS, GUIDE_NOTES, IdeaStore,
            decorr, handoff, idea_drafts, Journal, LOGIN_HELP, PyramidTracker, TIERS, config, connect, generate_ideas, hyp, hypolab, mo,
            brain_quota, multiplier_table, open_researcher, pd, planner, play, rules, theme, views)


@app.cell(hide_code=True)
def _(mo):
    # bumped after a mode switch, a login or a logout: the Researcher below is opened again
    get_conn, set_conn = mo.state(0)
    get_login, set_login = mo.state(None)
    return get_conn, get_login, set_conn, set_login


@app.cell(hide_code=True)
def _(config, get_conn, open_researcher):
    # One Researcher for the whole app: sandbox (offline practice) or your BRAIN account,
    # following the switch on the Setup tab (or `python -m hypolab live USA` / `sandbox`).
    get_conn()
    SANDBOX = config.sandbox_mode()
    R, live_problem = open_researcher()
    return R, SANDBOX, live_problem


@app.cell(hide_code=True)
def _(IdeaStore, Journal, R, planner):
    store = IdeaStore()
    this_week = planner.iso_week()
    # the journal the cockpit shows: the Researcher's (sandbox = in-memory practice journal), else read-only file
    J = R.journal if R is not None else Journal.open_readonly()
    return J, store, this_week


@app.cell(hide_code=True)
def _(mo):
    # shared state: Lab results, the card sent to the Lab, and a counter that refreshes views after saves
    get_results, set_results = mo.state([])
    get_lab_card, set_lab_card = mo.state(None)
    get_version, set_version = mo.state(0)
    get_boost, set_boost = mo.state(None)
    get_decorr, set_decorr = mo.state(None)      # 1.6.0: the last "Lower correlation" report (or an error text)
    get_corr, set_corr = mo.state({})            # 1.6.0: alpha id -> correlation status (BRAIN check first)
    get_robust, set_robust = mo.state({})
    get_gate, set_gate = mo.state(None)
    get_submitted, set_submitted = mo.state([])
    # 1.4.3: which result the Lab shows (None = the newest), PnL/yearly per alpha id, and the bin
    get_focus, set_focus = mo.state(None)
    get_perf, set_perf = mo.state({})
    get_bins, set_bins = mo.state(0)
    get_bin_msg, set_bin_msg = mo.state(None)
    NO_CARD = "(no card: write your own expression)"

    def add_results(new):
        """Append results to the Lab list and show the newest (or the last of `new`)."""
        set_results(get_results() + list(new))
        set_focus(None)
    return (get_corr, get_decorr, set_corr, set_decorr, NO_CARD, add_results, get_bin_msg, get_bins, get_boost, get_focus, get_gate, get_lab_card, get_perf,
            get_results, get_robust, get_submitted, get_version, set_bin_msg, set_bins, set_boost, set_focus,
            set_gate, set_lab_card, set_perf, set_results, set_robust, set_submitted, set_version)


@app.cell(hide_code=True)
def _(R, SANDBOX, config, handoff, hyp, live_problem, mo):
    _mode = ('<span class="hl-pill hl-sandbox">SANDBOX</span> offline practice market (region SBX); nothing here '
             "touches your BRAIN account." if SANDBOX else
             f'<span class="hl-pill hl-live">LIVE</span> your BRAIN account (default region {config.live_region()}).')
    _parts = [mo.md(f"# HYPOLAB cockpit\n{_mode}  Switch and log in on the **Setup** tab.  "
                    f"Week plan, leads, cards and drafts: **[Ideas app]({handoff.ideas_url()})**.")]
    if live_problem:
        _parts.append(mo.callout(mo.md(f"{live_problem}\n\nLog in on the **Setup** tab. Until then: Pyramids and "
                                       "Journal show your journal; the Lab is off."), kind="warn"))
    hyp.load_library()
    if hyp.LOAD_WARNINGS:
        _parts.append(mo.callout(mo.md("**Your card files:**\n\n" + "\n".join(f"- {w}" for w in hyp.LOAD_WARNINGS)),
                                 kind="warn"))
    header = mo.vstack(_parts)
    return (header,)


@app.cell(hide_code=True)
def _(R, SANDBOX, config, mo, store, this_week):
    # The region the Cards and Lab tabs work in. Default: this week's plan.
    _plan = store.plan(this_week)
    _regions = ["SBX"] if SANDBOX else config.account_regions()
    _default = "SBX" if SANDBOX else ((_plan or {}).get("region") or (R.region if R else config.live_region()))
    region_dd = mo.ui.dropdown(options=_regions, value=_default if _default in _regions else _regions[0],
                               label="Region")
    return (region_dd,)


# =============================================================================================== PYRAMIDS
@app.cell(hide_code=True)
def _(mo):
    refresh_pyr = mo.ui.button(label="Refresh counts", value=0, on_click=lambda v: (v or 0) + 1)
    return (refresh_pyr,)


@app.cell(hide_code=True)
def _(J, PyramidTracker, R, SANDBOX, acct, get_submitted, get_version, multiplier_table, refresh_pyr):
    # Genius counts Pyramids PER QUARTER (BRAIN_RULES S14). Order of sources:
    # 1. this quarter's submitted alphas (Account tab download) placed in categories by their fields,
    # 2. BRAIN's diversity counts (ALL TIME - they overstate the quarter), 3. HYPOLAB's own journal.
    refresh_pyr.value, get_submitted(), get_version()
    pyr_source, pyr_notes, pyr_raw, pyr_totals, pyr_mult = "journal", [], [], None, multiplier_table()
    if R is not None and SANDBOX:
        pyr_counts, pyr_regions, pyr_source = R.brain.diversity(), ["SBX"], "sandbox"
    else:
        _base = None
        _yq = acct.current_quarter()
        if R is not None:
            try:
                pyr_mult = multiplier_table(R.brain.pyramid_multipliers())
            except Exception:  # noqa: BLE001
                pass
        if acct.last_sync(J):
            _qc, pyr_notes = acct.quarter_pyramids(J, R.catalog if R is not None else None, *_yq)
            _base, pyr_source = PyramidTracker(_qc), f"your {_yq[0]} Q{_yq[1]} submissions (Account tab download)"
        elif R is not None:
            try:
                _div = R.brain.diversity()
                pyr_raw = _div.attrs.get("raw_sample", [])
                _base = PyramidTracker(_div)
                pyr_source = "BRAIN, ALL TIME - Genius counts the quarter only: download on the Account tab"
            except Exception as _e:  # noqa: BLE001
                pyr_source = f"journal (BRAIN unavailable: {_e})"
        _base = _base or PyramidTracker.from_journal(J)
        pyr_counts, pyr_regions, pyr_totals = _base.counts, _base.regions, _base.totals
        pyr_notes = list(pyr_notes) + list(_base.notes)
    return pyr_counts, pyr_mult, pyr_notes, pyr_raw, pyr_regions, pyr_source, pyr_totals


@app.cell(hide_code=True)
def _(config, mo):
    k_input = mo.ui.number(start=1, stop=50, step=1, value=int(config.settings()["alphas_per_pyramid"]),
                           label="Alphas needed per Pyramid (check the Pyramids page on BRAIN)")
    return (k_input,)


@app.cell(hide_code=True)
def _(PyramidTracker, config, k_input, pyr_counts, pyr_mult, pyr_regions):
    if int(k_input.value) != int(config.settings()["alphas_per_pyramid"]):
        config.save_settings(alphas_per_pyramid=int(k_input.value))
    tracker = PyramidTracker(pyr_counts, alphas_per_pyramid=int(k_input.value), regions=pyr_regions,
                             multipliers=pyr_mult)
    return (tracker,)


@app.cell(hide_code=True)
def _(mo):
    plan_sort = mo.ui.radio(options={"Guide order (tier 1 first, easiest regions)": "guide",
                                     "Highest multiplier first (pays more, usually harder)": "multiplier"},
                            value="Guide order (tier 1 first, easiest regions)", inline=True)
    return (plan_sort,)


@app.cell(hide_code=True)
def _(GUIDE_DATASETS, GUIDE_NOTES, R, SANDBOX, k_input, mo, pd, plan_sort, pyr_mult, pyr_notes, pyr_raw,
      pyr_source, pyr_totals, refresh_pyr, tracker, views):
    _m = tracker.matrix()
    _fig = views.pyramid_heatmap(_m, tracker.k, title=f"Alphas per cell (counts from {pyr_source})")
    _notes = pd.DataFrame([{"category": c, "guide datasets": ", ".join(GUIDE_DATASETS.get(c, [])),
                            "note": GUIDE_NOTES.get(c, "")} for c in GUIDE_DATASETS])
    _mult = mo.md("")
    if not SANDBOX and len(pyr_mult):
        _mt = pyr_mult.pivot_table(index="category", columns=["region", "delay"], values="multiplier")
        _mt.columns = [f"{r} D{d}" for r, d in _mt.columns]
        _mult = mo.accordion({f"Pyramid theme multipliers (source: {pyr_mult.attrs.get('source', '?')})":
                              mo.ui.table(_mt.reset_index(), selection=None, page_size=20)})
    pyramids_view = mo.vstack([
        mo.hstack([mo.md(f"**{tracker.summary()}**"), refresh_pyr], justify="space-between"),
        k_input,
        mo.callout(mo.md("**Cleaned up in BRAIN's counts:** " + " ".join(pyr_notes)), kind="neutral")
        if pyr_notes else mo.md(""),
        _fig,
        mo.vstack([
            mo.md("**Alphas per region (BRAIN's totals).** One alpha counts in every category whose data it uses, "
                  "so the cells above can add up to more than these totals."),
            mo.ui.table(pyr_totals, selection=None, page_size=12, show_column_summaries=False),
        ]) if pyr_totals is not None and len(pyr_totals) else mo.md(""),
        mo.md("### Next cells to work on"), plan_sort,
        mo.ui.tabs({"Delay 1": mo.ui.table(tracker.plan(n=15, delay=1, by=plan_sort.value), selection=None,
                                           page_size=15),
                    "Delay 0": mo.ui.table(tracker.plan(n=15, delay=0, by=plan_sort.value), selection=None,
                                           page_size=15)}),
        mo.accordion({"Datasets the Pyramids guide recommends": mo.ui.table(_notes, selection=None, page_size=12),
                      **({"BRAIN's raw Pyramid rows (first 20, for checking)": mo.json(pyr_raw)} if pyr_raw else {})}),
        _mult,
    ])
    return (pyramids_view,)


# ============================================================================== FIELD LIST (Lab needs it)
# 1.7.0: Week, Cards and Drafts moved to the Ideas web app (ideaweb/, http://127.0.0.1:2719).
# 1.10.1: a region's field list is downloaded on the Data tab (the Lab's own, never-shown button is gone).
@app.cell(hide_code=True)
def _(Catalog, R):
    # The data catalog (the sandbox has its own synthetic one).
    catalog = R.catalog if R is not None else Catalog()
    return (catalog,)


# ==================================================================================================== LAB
@app.cell(hide_code=True)
def _(mo):
    # 1.7.0: cards are chosen in the Ideas web app; "Send to the Lab" there lands here
    inbox_btn = mo.ui.run_button(label="Pick up the card sent from Ideas", kind="neutral")
    return (inbox_btn,)


@app.cell(hide_code=True)
def _(J, NO_CARD, config, get_bins, get_lab_card, handoff, hyp, inbox_btn, mo):
    get_bins(), inbox_btn.value
    _binned = J.binned_ids()
    _ids = [NO_CARD] + [h.id for h in hyp.load_library() if h.id not in _binned]   # re-read: Ideas approves cards
    # order: a card sent from Ideas that the Lab has not picked up yet, then the Lab's own choice, then the card you
    # last worked on (settings.json: last_lab_card; "" = no card)
    _new = handoff.take_new()
    _sent = get_lab_card()
    _sent = _sent[0] if isinstance(_sent, tuple) else _sent
    _saved = config.settings().get("last_lab_card")
    _first = (_new or {}).get("card") or _sent or (NO_CARD if _saved == "" else _saved) or NO_CARD
    lab_card_dd = mo.ui.dropdown(options=_ids, value=_first if _first in _ids else NO_CARD, searchable=True,
                                 label="Idea card")
    lab_inbox_note = (f"Picked up **{_new['card']}** from Ideas" + (f" (sent for {_new['region']})"
                      if _new.get("region") else "") + ".") if _new and _new.get("card") in _ids else ""
    return lab_card_dd, lab_inbox_note


@app.cell(hide_code=True)
def _(NO_CARD, R, config, lab_card_dd, region_dd):
    lab_card, lab_card_error = None, ""
    _keep = "" if lab_card_dd.value in (None, NO_CARD) else lab_card_dd.value
    if config.settings().get("last_lab_card") != _keep:
        config.save_settings(last_lab_card=_keep)
    if R is not None and _keep:
        try:
            lab_card = R.card(lab_card_dd.value, region=region_dd.value)
        except Exception as _e:  # noqa: BLE001
            lab_card_error = str(_e)
    return lab_card, lab_card_error


@app.cell(hide_code=True)
def _(config, lab_card, mo, region_dd):
    _steps = lab_card.steps if lab_card is not None else []
    rung_dd = mo.ui.dropdown(options={f"{i + 1}. {s.name}": i for i, s in enumerate(_steps)},
                             value=f"1. {_steps[0].name}" if _steps else None, label="Rung")
    _st = lab_card.settings if lab_card is not None else {}
    custom_expr = mo.ui.text_area(value="", rows=3, full_width=True,
                                  label="Or your own expression (leave empty to use the rung; still linted, "
                                        "budgeted and counted against this idea)" if lab_card is not None else
                                        "Your expression (linted before it costs a simulation)")
    decay_in = mo.ui.number(start=0, stop=60, step=1, value=int(_st.get("decay", 0) or 0), label="Decay")
    # Every neutralization BRAIN offers in this region (incl. the risk sets SLOW / FAST / SLOW_AND_FAST /
    # REVERSION_AND_MOMENTUM / STATISTICAL / CROWDING once the simulation options are synced) - BRAIN_RULES N1.
    _reg = lab_card.region if lab_card is not None else region_dd.value
    _neut = _st.get("neutralization", "SUBINDUSTRY")
    neut_dd = mo.ui.dropdown(options=list(dict.fromkeys(config.region_neutralizations(_reg) + [_neut])),
                             value=_neut, label="Neutralization")
    _delays = config.REGION_DEFAULTS.get(_reg, {}).get("delays", [1])
    _d0 = int(lab_card.delay) if lab_card is not None else 1
    delay_dd = mo.ui.dropdown(options={f"D{d}": d for d in dict.fromkeys(_delays + [_d0])}, value=f"D{_d0}",
                              label="Delay")
    trunc_in = mo.ui.number(start=0.01, stop=1.0, step=0.01, value=float(_st.get("truncation", 0.08) or 0.08),
                            label="Truncation")
    sim_btn = mo.ui.run_button(label="Simulate", kind="success")
    lab_remove_btn = mo.ui.run_button(label="Remove card from the Lab", kind="neutral", disabled=lab_card is None)
    lab_bin_btn = mo.ui.run_button(label="Bin card (noise)", kind="danger", disabled=lab_card is None)
    return (custom_expr, decay_in, delay_dd, lab_bin_btn, lab_remove_btn, neut_dd, rung_dd, sim_btn, trunc_in)


@app.cell(hide_code=True)
def _(NO_CARD, R, config, get_bins, lab_bin_btn, lab_card, lab_remove_btn, mo, set_bin_msg, set_bins,
      set_lab_card):
    # 1.4.3: take the card out of the Lab (results stay in the list and the journal), or bin it as noise
    mo.stop(not (lab_remove_btn.value or lab_bin_btn.value) or lab_card is None)
    import time as _time
    _id = lab_card.hypothesis.id
    if lab_bin_btn.value and R is not None:
        R.bin(_id, "noise - binned from the Lab")
        set_bin_msg(("lab", f"Binned **{_id}** from the Lab. Restore it from **Cards > The bin**."))
        set_bins(get_bins() + 1)
    config.save_settings(last_lab_card="")
    set_lab_card((NO_CARD, _time.time()))
    return


@app.cell(hide_code=True)
def _(R, add_results, config, custom_expr, decay_in, delay_dd, lab_card, mo, neut_dd, region_dd, rung_dd,
      sim_btn, trunc_in, theme):
    # Spends ONE simulation, and only when you click Simulate (changing a control never simulates).
    _expr = custom_expr.value.strip() or None
    mo.stop(not sim_btn.value or R is None or (lab_card is None and not _expr),
            mo.callout(mo.md("No card in the Lab: write your own expression first."), kind="warn")
            if sim_btn.value and lab_card is None and not _expr else None)
    _settings = {"decay": int(decay_in.value), "neutralization": neut_dd.value, "truncation": float(trunc_in.value),
                 "delay": int(delay_dd.value)}
    if lab_card is None:          # your own expression, no card: counted as manual@<region>
        _settings.update(region=region_dd.value, universe=config.universe_for(region_dd.value))
    with mo.status.spinner(title=theme.loading_line("1 simulation")):
        _t = R.test(lab_card, rung=int(rung_dd.value or 0), expression=_expr, settings=_settings)
    add_results([_t])
    return


@app.cell(hide_code=True)
def _(get_focus, get_results, mo, pd, views):
    _res = get_results()
    _f = get_focus()
    _pick = _f if isinstance(_f, int) and 0 <= _f < len(_res) else len(_res) - 1
    lab_history = mo.ui.table(pd.DataFrame([{"#": i, "": "\u25b6" if i == _pick else "", **views.result_row(t)}
                                            for i, t in enumerate(_res)]),
                              selection="single",
                              initial_selection=[_pick] if _res else None, page_size=8,
                              label="Results this session (select one to work on; \u25b6 = shown below)")
    lab_remove_res = mo.ui.run_button(label="Remove the selected result from this list", kind="neutral",
                                      disabled=not _res)
    lab_clear_res = mo.ui.run_button(label="Clear the list", kind="neutral", disabled=not _res)
    return lab_clear_res, lab_history, lab_remove_res


@app.cell(hide_code=True)
def _(get_focus, get_results, lab_history):
    _res = get_results()
    current = None
    if _res:
        _f = get_focus()
        _idx = _f if isinstance(_f, int) and 0 <= _f < len(_res) else len(_res) - 1
        _sel = lab_history.value
        if _sel is not None and len(_sel):
            _idx = int(_sel.iloc[0]["#"])
        current = _res[_idx]
    return (current,)


@app.cell(hide_code=True)
def _(current, mo, views):
    _choices = views.action_choices(current) if current is not None else {}
    follow_dd = mo.ui.dropdown(options=_choices, value=next(iter(_choices), None), label="Suggested action")
    follow_btn = mo.ui.run_button(label="Apply it (1 simulation)", disabled=not _choices)
    boost_k = mo.ui.number(start=1, stop=8, step=1, value=4, label="Boosters to try")
    boost_mode = mo.ui.dropdown(options={"add: rank(a) + rank(b)": "add", "and: min(rank(a), rank(b))": "and"},
                                value="add: rank(a) + rank(b)", label="Combine")
    boost_btn = mo.ui.run_button(label="Boost (up to 2 x k simulations)")
    robust_btn = mo.ui.run_button(label="Run the robustness battery (about 7 simulations)")
    gate_btn = mo.ui.run_button(label="Gate report")
    corr_btn = mo.ui.run_button(label="Read production correlation (free, no simulation)",
                                disabled=current is None or not current.alpha_id)
    decorr_k = mo.ui.number(start=1, stop=6, step=1, value=4, label="Changes to try")
    decorr_btn = mo.ui.run_button(label="Lower correlation (up to k simulations; style probes once per region)",
                                  disabled=current is None or not current.alpha_id)
    return (boost_btn, boost_k, boost_mode, corr_btn, decorr_btn, decorr_k, follow_btn, follow_dd, gate_btn,
            robust_btn)


@app.cell(hide_code=True)
def _(R, add_results, current, follow_btn, follow_dd, mo, theme):
    mo.stop(not follow_btn.value or current is None or follow_dd.value is None)
    with mo.status.spinner(title=theme.loading_line("the suggested change")):
        _t = R.follow(current, int(follow_dd.value))
    add_results([_t])
    return


@app.cell(hide_code=True)
def _(current, get_results, lab_clear_res, lab_remove_res, mo, set_focus, set_results):
    # 1.4.3: tidy the Lab's list (the journal keeps everything; "Restore results" brings them back)
    mo.stop(not (lab_remove_res.value or lab_clear_res.value))
    if lab_clear_res.value:
        set_results([])
    elif current is not None:
        set_results([t for t in get_results() if t is not current])
    set_focus(None)
    return


@app.cell(hide_code=True)
def _(R, corr_btn, current, get_corr, mo, set_corr):
    # 1.6.0: BRAIN shows production correlation right after a simulation; reading it costs no simulation
    mo.stop(not corr_btn.value or R is None or current is None or not current.alpha_id)
    with mo.status.spinner(title="Reading production correlation ..."):
        try:
            _st = R.corr_status(current, refresh=True)
        except Exception as _e:  # noqa: BLE001
            _st = {"error": str(_e)}
    set_corr({**get_corr(), current.alpha_id: _st})
    return


@app.cell(hide_code=True)
def _(R, add_results, current, decorr_btn, decorr_k, mo, set_decorr, theme):
    mo.stop(not decorr_btn.value or R is None or current is None)
    try:
        with mo.status.spinner(title=theme.loading_line("less crowded versions")):
            _rep = R.decorrelate(current, k=int(decorr_k.value))
        set_decorr(_rep)
        add_results(_rep.lab_results())          # the recommended one last, so it is shown
    except ValueError as _e:
        set_decorr(str(_e))
    return


@app.cell(hide_code=True)
def _(R, add_results, boost_btn, boost_k, boost_mode, boost_compare, current, get_perf, mo, set_boost,
      set_perf, theme):
    mo.stop(not boost_btn.value or current is None)
    try:
        with mo.status.spinner(title=theme.loading_line("boosters")):
            _rep = R.boost(current, k=int(boost_k.value), mode=boost_mode.value)
            _perf = dict(get_perf())
            if _rep.best is not None and _rep.best.alpha_id:      # the boosted alpha's PnL, drawn right away
                _perf[_rep.best.alpha_id] = R.performance(_rep.best, compare=boost_compare(_rep, _rep.best))
        set_boost(_rep)
        set_perf(_perf)
        # each booster alone, then the combinations, the best one LAST so it is selected and shown below
        add_results(_rep.lab_results())
    except ValueError as _e:
        set_boost(str(_e))
    return


@app.cell(hide_code=True)
def _():
    def boost_compare(rep, t):
        """Lines drawn next to a boost result: the base alpha and the booster alone."""
        if rep is None or isinstance(rep, str):
            return {}
        for _k, _r in rep.results.items():
            if _r is t or (_r.alpha_id and _r.alpha_id == t.alpha_id):
                _b = rep.boosters.get(_k)
                return {"base": rep.base.alpha_id, "booster " + _k: _b.alpha_id if _b is not None else None}
        return {}
    return (boost_compare,)


@app.cell(hide_code=True)
def _(get_boost, get_results, mo, set_focus):
    # 1.4.3: jump to any alpha the last boost made (each booster alone and every combination)
    _b = get_boost()
    _opts = {}
    if _b is not None and not isinstance(_b, str):
        _res = get_results()
        for _t in _b.lab_results():
            _i = next((i for i, r in enumerate(_res) if r is _t), None)
            if _i is not None:
                _s = _t.summary.get("is_sharpe")
                _who = _t.card.hypothesis.id if _t.card is not None else (_t.idea_id or "manual")
                _opts[f"#{_i}  {_who} / {_t.rung}  -  Sharpe {_s if _s is not None else '-'}  "
                      f"{_t.diagnosis.verdict}"] = _i
    open_boost_dd = mo.ui.dropdown(options=_opts, label="Open a boosted alpha", on_change=set_focus,
                                   full_width=True)
    return (open_boost_dd,)


@app.cell(hide_code=True)
def _(current, mo):
    perf_btn = mo.ui.run_button(label="Show its performance (PnL chart + yearly table, no simulation)",
                                disabled=current is None or not current.alpha_id)
    return (perf_btn,)


@app.cell(hide_code=True)
def _(R, boost_compare, current, get_boost, get_perf, mo, perf_btn, set_perf):
    mo.stop(not perf_btn.value or R is None or current is None or not current.alpha_id)
    with mo.status.spinner(title="Reading the PnL from BRAIN ..."):
        _p = R.performance(current, compare=boost_compare(get_boost(), current))
    set_perf({**get_perf(), current.alpha_id: _p})
    return


@app.cell(hide_code=True)
def _(current, get_perf, mo, pd, views):
    # the performance panel for the result shown in the Lab
    perf_view = None
    _p = get_perf().get(current.alpha_id) if current is not None and current.alpha_id else None
    if _p is not None:
        if _p["error"]:
            perf_view = mo.callout(mo.md(_p["error"]), kind="warn")
        else:
            import matplotlib.pyplot as _plt
            _parts = []
            if not _p["pnl"].empty:
                _fig = views.pnl_figure(_p["pnl"], title=f"Cumulative PnL - {current.rung}")
                _parts.append(mo.as_html(_fig))
                _plt.close(_fig)
            _y = _p["yearly"]
            if _y is not None and not _y.empty:
                if not isinstance(_y.index, pd.RangeIndex):
                    _y = _y.reset_index()
                if "year" in _y.columns:
                    _y = _y.assign(year=_y["year"].astype(str))
                _parts.append(mo.ui.table(_y, selection=None, page_size=12, show_download=False,
                                          show_column_summaries=False, label="Year by year"))
            perf_view = mo.vstack(_parts) if _parts else mo.md("_BRAIN returned no PnL for this alpha._")
    return (perf_view,)


@app.cell(hide_code=True)
def _(R, current, get_robust, mo, robust_btn, set_robust, theme):
    mo.stop(not robust_btn.value or current is None or not current.alpha_id)
    with mo.status.spinner(title=theme.loading_line("robustness battery")):
        _rb = R.robustness(current)
    set_robust({**get_robust(), current.alpha_id: _rb})
    return


@app.cell(hide_code=True)
def _(R, current, gate_btn, get_robust, mo, set_gate):
    mo.stop(not gate_btn.value or current is None or not current.alpha_id)
    with mo.status.spinner(title="Platform checks, correlations, deflated Sharpe ..."):
        set_gate(R.gate(current, get_robust().get(current.alpha_id)))
    return


@app.cell(hide_code=True)
def _(J, SANDBOX, config, current, get_gate, get_submitted, mo):
    get_submitted()
    _g = get_gate()
    _ready = _g is not None and current is not None and _g.alpha_id == current.alpha_id and _g.ready
    _cap = int(config.settings().get("max_submissions_per_day", 4))
    submissions_today = J.submissions_today()
    _ready = _ready and submissions_today < _cap
    confirm_in = mo.ui.text(value="", placeholder=f"SUBMIT {_g.alpha_id}" if _ready else "",
                            label="Type SUBMIT and the alpha id to confirm", full_width=True)
    submit_btn = mo.ui.run_button(label="Submit to BRAIN (permanent)" if not SANDBOX else "Submit (sandbox practice)",
                                  kind="danger", disabled=not _ready)
    return confirm_in, submissions_today, submit_btn


@app.cell(hide_code=True)
def _(R, confirm_in, get_gate, get_submitted, mo, set_submitted, submit_btn):
    mo.stop(not submit_btn.value)
    _g = get_gate()
    try:
        _res = R.submit(_g, confirm=confirm_in.value.strip())
        set_submitted(get_submitted() + [(_g.alpha_id, str(_res))])
    except Exception as _e:  # noqa: BLE001
        set_submitted(get_submitted() + [(_g.alpha_id, f"NOT submitted: {_e}")])
    return


@app.cell(hide_code=True)
def _(mo):
    # Pick up where you left off (1.4.1): results come back from the journal, interrupted simulations from BRAIN.
    restore_btn = mo.ui.run_button(label="Restore results", kind="neutral")
    recover_btn = mo.ui.run_button(label="Fetch them from BRAIN (no new simulation)", kind="success")
    get_resume_msg, set_resume_msg = mo.state(None)
    return get_resume_msg, recover_btn, restore_btn, set_resume_msg


@app.cell(hide_code=True)
def _(R, get_results, mo, restore_btn, set_focus, set_results):
    mo.stop(not restore_btn.value or R is None)
    set_results(R.recent_results(10) + list(get_results()))
    set_focus(None)
    return


@app.cell(hide_code=True)
def _(R, add_results, mo, recover_btn, set_resume_msg, theme):
    mo.stop(not recover_btn.value or R is None)
    with mo.status.spinner(title=theme.loading_line("collecting interrupted simulations")):
        _r = R.recover_pending()
    add_results(_r["recovered"])
    set_resume_msg(f"Recovered {len(_r['recovered'])} result(s) without simulating again"
                   + (f"; {_r['running']} still running on BRAIN - try again in a few minutes" if _r["running"] else "")
                   + (f"; {_r['gone']} no longer on BRAIN (simulate again if you still want them)" if _r["gone"]
                      else "") + ".")
    return


@app.cell(hide_code=True)
def _(R, SANDBOX, get_play, get_results, get_resume_msg, mo, pd, recover_btn, restore_btn):
    get_play()                      # re-check the journal after Play simulations too
    _parts = []
    if R is not None:
        _pend = R.pending() if not SANDBOX else []
        if _pend:
            _parts.append(mo.callout(mo.vstack([
                mo.md(f"**{len(_pend)} simulation(s) were still running when HYPOLAB last closed.** BRAIN finished "
                      "them (and counted them), so collect the results instead of paying again:"),
                mo.ui.table(pd.DataFrame([{"idea": p["idea_id"], "rung": p["rung"], "expression": p["expression"],
                                           "sent": pd.Timestamp(p["created"], unit="s").strftime("%Y-%m-%d %H:%M")}
                                          for p in _pend]), selection=None, show_download=False),
                recover_btn]), kind="info"))
        if not get_results():
            _ex = R.journal.experiments()
            _n = int(_ex["purpose"].isin(["explore", "boost", "decorr", "play"]).sum()) if not _ex.empty else 0
            if _n:
                _last = pd.Timestamp(_ex["created"].max(), unit="s").strftime("%a %d %b %H:%M")
                _parts.append(mo.callout(mo.hstack([
                    mo.md(f"**Pick up where you left off:** {_n} simulation(s) in your journal, the last on {_last} "
                          "(UTC). Restoring brings back their diagnoses without simulating anything."),
                    restore_btn], justify="space-between", align="center"), kind="neutral"))
        if get_resume_msg():
            _parts.append(mo.callout(mo.md(get_resume_msg()), kind="success"))
    resume_view = mo.vstack(_parts) if _parts else mo.md("")
    return (resume_view,)


@app.cell(hide_code=True)
def _(R, SANDBOX, boost_btn, boost_k, boost_mode, config, confirm_in, current, custom_expr, decay_in, follow_btn,
      follow_dd, gate_btn, get_boost, get_gate, get_robust, get_submitted, lab_card, lab_card_dd, lab_card_error,
      lab_history, mo, neut_dd, pd, region_dd, robust_btn, rung_dd, sim_btn, submit_btn, trunc_in, submissions_today,
      delay_dd, brain_quota, resume_view, lab_remove_btn, lab_bin_btn, lab_remove_res, lab_clear_res, open_boost_dd,
      perf_btn, perf_view, get_bin_msg, corr_btn, decorr_btn, decorr_k, get_corr, get_decorr, decorr, views,
      inbox_btn, lab_inbox_note):
    if R is None:
        lab_view = mo.callout(mo.md("The Lab needs a BRAIN session (or sandbox mode). See the message at the top."),
                              kind="warn")
    else:
        _parts = [resume_view, mo.hstack([lab_card_dd, region_dd, inbox_btn, lab_remove_btn, lab_bin_btn],
                                         justify="start", gap=1.5, align="center", wrap=True)]
        if lab_inbox_note:
            _parts.append(mo.callout(mo.md(lab_inbox_note), kind="success"))
        _bm = get_bin_msg()
        if isinstance(_bm, tuple) and _bm[0] == "lab":
            _parts.append(mo.callout(mo.md(_bm[1]), kind="neutral"))
        if not SANDBOX:
            _q = brain_quota()
            _parts.append(mo.md(
                f"_BRAIN quota today: **{_q['remaining']:,}** of {_q['limit']:,} simulations left (resets at midnight "
                f"New York = 07:00/08:00 Nairobi). Simulations HYPOLAB counted today: {R.journal.sims_today()}._"
                if _q else f"_Simulations HYPOLAB counted today (BRAIN's day, New York time): "
                           f"{R.journal.sims_today()}. BRAIN's own remaining count appears after the next simulation._"))
        if lab_card_error:
            _parts.append(mo.callout(mo.md(lab_card_error), kind="danger"))
        if lab_card is not None:
            _ladder = pd.DataFrame([{"rung": f"{i + 1}. {s.name}", "expression": s.expression,
                                     "linter": "ok" if s.lint.ok else "BLOCKED", "IS test": s.is_test,
                                     "teaches": s.teaches}
                                    for i, s in enumerate(lab_card.steps)])
            _h = lab_card.hypothesis
            _parts += [mo.md(f"**{_h.title}** - {_h.story}\n\n_Why it can persist:_ {_h.why_persists}  "
                             f"**Expected sign:** {_h.sign}"),
                       mo.ui.table(_ladder, selection=None),
                       mo.hstack([rung_dd, delay_dd, decay_in, neut_dd, trunc_in], justify="start", gap=1.5,
                                 wrap=True),
                       custom_expr, sim_btn]
        else:
            _parts += [mo.md("**No card in the Lab.** Pick one above (or send one from the **Ideas** app), or test your own "
                             "expression - it is linted, budgeted and journaled as `manual@" + str(region_dd.value)
                             + "`."),
                       mo.hstack([delay_dd, decay_in, neut_dd, trunc_in], justify="start", gap=1.5, wrap=True),
                       custom_expr, sim_btn]
        _parts += [lab_history, mo.hstack([lab_remove_res, lab_clear_res], justify="start", gap=0.75)]
        if current is not None:
            _parts.append(mo.md(current.markdown()))
            if current.alpha_id:
                _parts.append(mo.md("### Performance"))
                _parts.append(perf_view if perf_view is not None else perf_btn)
            _parts.append(mo.accordion({
                "Follow ONE suggested action": mo.vstack([follow_dd, follow_btn]),
                "Boost a weak-but-real alpha with an independent second signal": mo.vstack([
                    mo.md("Predicted combined Sharpe = (S1 + S2) / sqrt(2 x (1 + correlation)). Every combination "
                          "counts as a try on this idea."), mo.hstack([boost_k, boost_mode]), boost_btn]),
            }))
            _b = get_boost()
            if isinstance(_b, str):
                _parts.append(mo.callout(mo.md(_b), kind="warn"))
            elif _b is not None and current.alpha_id in _b.alpha_ids():
                # the boost report stays visible while you look at the base, a booster or any combination
                _parts += [mo.md(_b.markdown()), mo.ui.table(_b.table, selection=None, show_download=False)]
                if open_boost_dd.options:
                    _parts.append(open_boost_dd)
            if current.alpha_id:
                # 1.6.0: correlation, read early and handled with BRAIN's check as the authority
                _parts.append(mo.md("### Correlation"))
                _cs = get_corr().get(current.alpha_id)
                if _cs is None:                      # already read (e.g. by Lower correlation): from the journal
                    _known = R.journal.correlation(current.alpha_id, "prod")
                    if _known is not None:
                        _cs = decorr.corr_status(current.summary.get("checks"), _known)
                if _cs is None:
                    _parts.append(mo.md("_Production correlation not read yet. Reading it is free; do it on anything "
                                        "at NEAR or PASS before you spend more simulations on it._"))
                elif "error" in _cs:
                    _parts.append(mo.callout(mo.md(f"Could not read it: {_cs['error']}"), kind="warn"))
                else:
                    _bad = any(v.get("result") in ("FAIL", "FAIL?") for v in _cs.values())
                    _parts.append(mo.callout(mo.md(f"**{decorr.status_line(_cs)}**" + (
                        "  \nAbove the limit: try **Lower correlation** below - it keeps the idea and changes one "
                        "thing at a time." if _bad else "")), kind="warn" if _bad else "success"))
                _parts.append(mo.hstack([corr_btn], justify="start"))
                _parts.append(mo.accordion({"Lower correlation, keep the signal": mo.vstack([
                    mo.md("Tries up to k principled changes, in BRAIN's order: the risk set a BRAIN theme names, "
                          "removing the crowded style the alpha resembles, an equivalent field with fewer alphas, a "
                          "CROWDING/SLOW risk set, a shorter horizon, removing overlap with your own alpha, another "
                          "peer group. Each is simulated (it counts as a try on this idea), its production "
                          "correlation is read, and the one that keeps the most Sharpe under the limit is "
                          "recommended."), mo.hstack([decorr_k, decorr_btn], justify="start", gap=1)])}))
                _dc = get_decorr()
                if isinstance(_dc, str):
                    _parts.append(mo.callout(mo.md(_dc), kind="warn"))
                elif _dc is not None and current.alpha_id in _dc.alpha_ids():
                    _parts += [mo.md(_dc.markdown()), mo.md(views.html_table(_dc.table, code_cols=["alpha"]))]
                _parts.append(mo.md("### Validate before you submit"))
                _parts.append(mo.hstack([robust_btn, gate_btn], justify="start"))
                _rb = get_robust().get(current.alpha_id)
                if _rb is not None:
                    _sc = _rb.attrs.get("score", {})
                    _parts += [mo.md(f"**Robustness:** {_sc.get('score', 0):.0%} - {_sc.get('verdict', '')}"),
                               mo.ui.table(_rb.drop(columns=["expression"], errors="ignore"), selection=None)]
                _g = get_gate()
                if _g is not None and _g.alpha_id == current.alpha_id:
                    _parts.append(mo.md(_g.markdown()))
                    if _g.ready:
                        _parts.append(mo.callout(mo.vstack([
                            mo.md(f"**Submitted today: {submissions_today}/{config.settings().get('max_submissions_per_day', 4)}.** "
                                  + ("Daily limit reached - keep this one for tomorrow. " if submissions_today >=
                                     int(config.settings().get("max_submissions_per_day", 4)) else "")),
                            mo.md("**Your decision.** " + ("Sandbox: practice submission only." if SANDBOX else
                                  "This is a real, permanent submission. One alpha per idea family per region is "
                                  "usually right.")), confirm_in, submit_btn]), kind="warn"))
            for _aid, _msg in get_submitted():
                if _aid == current.alpha_id:
                    _parts.append(mo.callout(mo.md(f"`{_aid}`: {_msg}"),
                                             kind="danger" if _msg.startswith("NOT") else "success"))
        lab_view = mo.vstack(_parts)
    return (lab_view,)


# ================================================================================================ JOURNAL
@app.cell(hide_code=True)
def _(J, mo):
    lesson_form = mo.md("{text}\n\n{idea}").batch(
        text=mo.ui.text_area(placeholder="What did this idea teach you? One or two sentences.", rows=2,
                             full_width=True),
        idea=mo.ui.text(placeholder="idea id (optional), e.g. ANL_EPS_REVISION@USA"),
    ).form(submit_button_label="Add lesson", clear_on_submit=True)
    journal_writable = not getattr(J, "readonly", False)
    return journal_writable, lesson_form


@app.cell(hide_code=True)
def _(J, get_version, journal_writable, lesson_form, mo, set_version):
    mo.stop(lesson_form.value is None or not journal_writable or not lesson_form.value["text"].strip())
    J.add_lesson(lesson_form.value["text"].strip(), idea_id=lesson_form.value["idea"].strip())
    set_version(get_version() + 1)
    return


@app.cell(hide_code=True)
def _(J, mo):
    _ex = J.experiments()
    _regions = sorted(r for r in _ex["region"].dropna().unique()) if not _ex.empty else []
    jr_region = mo.ui.dropdown(options=["all"] + _regions, value="all", label="Region")
    jr_verdicts = mo.ui.multiselect(options=["PASS", "NEAR", "WEAK", "INVERTED", "NOISE", "ERROR"], label="Verdicts")
    return jr_region, jr_verdicts


@app.cell(hide_code=True)
def _(J, config, get_boost, get_results, get_robust, get_submitted, get_version, journal_writable, jr_region,
      jr_verdicts, lesson_form, mo, views):
    get_results(), get_version(), get_submitted(), get_robust(), get_boost()
    _ex = J.experiments()
    _budget = int(config.settings()["max_sims_per_idea"])
    _real = _ex[_ex["backend"] != "sandbox"] if not _ex.empty and not getattr(J, "path", "") == ":memory:" else _ex
    journal_view = mo.vstack([
        mo.md(f"**{len(_ex)} simulation{'' if len(_ex) == 1 else 's'} recorded.** If most verdicts are NOISE, choose ideas more carefully; "
              "if one idea has used its whole budget, stop and write a lesson."),
        mo.hstack([
            mo.vstack([mo.md("### Verdict mix"), mo.ui.table(views.verdict_mix(_real), selection=None)]),
            mo.vstack([mo.md(f"### Tries per idea (budget {_budget})"),
                       mo.ui.table(views.tries_per_idea(_ex, _budget), selection=None, page_size=8)]),
        ], widths=[1, 2], gap=2),
        mo.md("### Scoreboard by family"),
        mo.ui.table(J.scoreboard(), selection=None, page_size=8),
        mo.md("### Experiments"),
        mo.hstack([jr_region, jr_verdicts], justify="start", gap=1.5),
        mo.ui.table(views.experiments_view(_ex, None if jr_region.value == "all" else jr_region.value,
                                           list(jr_verdicts.value) or None), selection=None, page_size=10),
        mo.md("### Submissions"),
        mo.ui.table(J.submissions(), selection=None),
        mo.md("### Lessons"),
        lesson_form if journal_writable else mo.md("_Read-only until you log in._"),
        mo.ui.table(J.lessons(), selection=None, page_size=8),
    ])
    return (journal_view,)


# ================================================================================================== SETUP
@app.cell(hide_code=True)
def _(config, get_conn, mo):
    get_conn()
    _st = config.settings()
    _regions = config.account_regions()
    mode_form = mo.md("{mode}\n\n{region}").batch(
        mode=mo.ui.radio(options={"Sandbox - offline practice market": "sandbox",
                                  "Live - my BRAIN account": "live"},
                         value="Sandbox - offline practice market" if config.sandbox_mode()
                         else "Live - my BRAIN account"),
        region=mo.ui.dropdown(options=_regions, value=config.live_region() if config.live_region() in _regions
                              else _regions[0], label="Live region"),
    ).form(submit_button_label="Apply")
    return (mode_form,)


@app.cell(hide_code=True)
def _(connect, get_conn, mo, mode_form, set_conn):
    mo.stop(mode_form.value is None)
    if mode_form.value["mode"] == "live":
        connect.go_live(mode_form.value["region"])
    else:
        connect.go_sandbox()
    set_conn(get_conn() + 1)
    return


@app.cell(hide_code=True)
def _(mo):
    login_form = mo.md("{email}\n\n{password}\n\n{save}").batch(
        email=mo.ui.text(kind="email", label="BRAIN email", full_width=True),
        password=mo.ui.text(kind="password", label="BRAIN password", full_width=True),
        save=mo.ui.checkbox(value=True, label="Remember on this laptop (~/.hypolab/credentials.json, readable only by you)"),
    ).form(submit_button_label="Log in", clear_on_submit=True)
    scan_done_btn = mo.ui.run_button(label="I finished the face scan", kind="success")
    logout_btn = mo.ui.run_button(label="Log out and forget my credentials", kind="danger")
    return login_form, logout_btn, scan_done_btn


@app.cell(hide_code=True)
def _(AuthError, connect, get_conn, login_form, mo, set_conn, set_login):
    mo.stop(login_form.value is None or not login_form.value["email"] or not login_form.value["password"])
    try:
        with mo.status.spinner(title="Checking your credentials with BRAIN ..."):
            _res = connect.begin_login(login_form.value["email"], login_form.value["password"],
                                       save=bool(login_form.value["save"]))
    except (AuthError, Exception) as _e:  # noqa: BLE001
        _res = {"status": "error", "detail": str(_e)}
    set_login(_res)
    if _res["status"] == "ok":
        set_conn(get_conn() + 1)
    return


@app.cell(hide_code=True)
def _(connect, get_conn, mo, scan_done_btn, set_conn, set_login):
    mo.stop(not scan_done_btn.value)
    try:
        _res = connect.finish_login()
    except Exception as _e:  # noqa: BLE001
        _res = {"status": "error", "detail": str(_e)}
    set_login(_res)
    if _res["status"] == "ok":
        set_conn(get_conn() + 1)
    return


@app.cell(hide_code=True)
def _(connect, get_conn, logout_btn, mo, set_conn, set_login):
    mo.stop(not logout_btn.value)
    connect.logout()
    set_login({"status": "logged_out"})
    set_conn(get_conn() + 1)
    return


@app.cell(hide_code=True)
def _(BrainClient, GOLD, R, SANDBOX, config, connect, get_conn, get_login, hypolab, login_form, logout_btn, mo,
      mode_form, pd, scan_done_btn):
    get_conn()
    import sys as _sys
    _left = BrainClient(verbose=False).seconds_left()
    if R is not None and not SANDBOX:
        _left = max(_left, R.brain.seconds_left())
    _status = pd.DataFrame([
        {"item": "mode", "value": "sandbox (practice)" if SANDBOX else "live"},
        {"item": "live region", "value": config.live_region()},
        {"item": "credentials", "value": connect._creds_source()},
        {"item": "BRAIN session", "value": f"about {_left / 3600:.1f} h left" if _left > 0 else "none or expired"},
        {"item": "data folder", "value": str(config.HOME)},
        {"item": "versions", "value": f"hypolab {hypolab.__version__}, marimo {mo.__version__}, "
                                      f"python {_sys.version.split()[0]}"},
    ])
    _l = get_login() or connect.pending() or {}
    _msg = mo.md("")
    if _l.get("status") == "biometric" or _l.get("status") == "waiting":
        _msg = mo.callout(mo.vstack([
            mo.md(("**BRAIN has not registered the scan yet.** Wait until the page says it is done. "
                   if _l["status"] == "waiting" else "**Face scan required.** ")
                  + f"Open [this link]({_l['url']}) in your browser, complete the scan, then press the button."),
            scan_done_btn]), kind="warn")
    elif _l.get("status") == "ok":
        _msg = mo.callout(mo.md(f"**Logged in.** Session valid for about {_l.get('hours_left', '?')} h"
                                + ("; credentials saved." if _l.get("saved") else "; credentials not saved.")
                                + (" Switch to **Live** above to use your account." if SANDBOX else "")),
                          kind="success")
    elif _l.get("status") == "error":
        _msg = mo.callout(mo.md(f"**Login failed:** {_l['detail']}\n\nNothing was saved."), kind="danger")
    elif _l.get("status") == "logged_out":
        _msg = mo.callout(mo.md("Logged out; saved credentials and session deleted."), kind="neutral")
    setup_view = mo.vstack([
        mo.md("## Where you stand"),
        mo.ui.table(_status, selection=None, show_column_summaries=False, show_download=False),
        mo.md("## Sandbox or live\nEvery tab, the scan app and the learning app follow this switch."),
        mode_form,
        mo.md("## Log in to BRAIN\nYour password goes only to BRAIN and, if you tick the box, to a file only you "
              "can read. If BRAIN asks for a face scan, a link appears here; nothing waits on a terminal."),
        login_form, _msg,
        mo.accordion({
            "Log out": logout_btn,
            "Operators you may use (Gold list)": mo.ui.table(GOLD.table(), selection=None, page_size=15),
            "A sensible daily routine (about 2 hours)": mo.md(
                "1. **20 min - read.** The daily alpha brief (17:55 Nairobi), one paper abstract from a card's "
                "references, or one BRAIN Learn page.\n"
                "2. **10 min - plan.** Ideas app, **Week** page (today's submissions, the plan) and this cockpit's "
                "**Pyramids** tab (which cells this week).\n"
                "3. **15 min - ideas.** Ideas app, **Leads**: act on one lead or one outside source; import the "
                "Writer's card on **Drafts**, check it, copy it for the Critic, approve it.\n"
                "4. **50 min - research.** Ideas app, **Cards** -> **Send to the Lab** 2-3 cards for this week's cells "
                "-> here, **Lab**: rung 1, read the diagnosis, climb at most a few rungs. Respect the stop signs.\n"
                "5. **20 min - validate.** Lab: production correlation (free), robustness and the gate on anything "
                "that passed. Submit only what clears the gate (at most 4 a day). After 100 lifetime alphas: one "
                "**SuperAlpha** a day at most, from a pool of 10+.\n"
                "6. **5 min - write.** One lesson per idea in the **Journal** tab. Fridays: the DIGEST / PLAN "
                "review on the Week page."),
        }),
    ])
    return (setup_view,)


# =================================================================================================== DATA
@app.cell(hide_code=True)
def _(catalog, get_version, mo):
    get_version()
    _ctx = catalog.contexts()
    _opts = {f"{r.region} {r.universe} D{r.delay} ({r.fields} fields)": (r.region, r.universe, int(r.delay))
             for r in _ctx.itertuples(index=False)}
    data_ctx = mo.ui.dropdown(options=_opts, value=next(iter(_opts), None), label="Region in your catalog")
    return (data_ctx,)


@app.cell(hide_code=True)
def _(config, mo):
    _st = config.settings()
    _regions = config.account_regions()
    sync_region = mo.ui.dropdown(options=_regions, value=config.live_region() if config.live_region() in _regions
                                 else _regions[0], label="Region to download")
    sync_region_btn = mo.ui.run_button(label="Download its field list (metadata only; a few minutes)")
    return sync_region, sync_region_btn


@app.cell(hide_code=True)
def _(R, SANDBOX, catalog, config, get_version, mo, set_version, sync_region, sync_region_btn):
    mo.stop(not sync_region_btn.value or R is None or SANDBOX)
    _u = config.universe_for(sync_region.value)
    mo.stop(_u is None, mo.callout(mo.md(f"HYPOLAB doesn't know {sync_region.value}'s universes yet: press "
                                         "**Download operators + simulation options** on the Account tab first."),
                                   kind="warn"))
    with mo.status.spinner(title=f"Downloading {sync_region.value} {_u} ..."):
        # 1.8.1: every category (insiders, institutions, short interest, social media ... were left out, so cards on
        # that data never bound in live regions)
        catalog.sync_from_brain(R.brain, sync_region.value, _u, 1, progress=None)
    set_version(get_version() + 1)
    return


@app.cell(hide_code=True)
def _(catalog, data_ctx, mo):
    data_summary = None
    if data_ctx.value:
        _r, _u, _d = data_ctx.value
        data_summary = catalog.dataset_summary(_r, _u, _d).round(3).reset_index(drop=True)
    _cols = ["category_name", "dataset", "name", "fields", "usable", "matrix", "vector", "median_coverage",
             "median_alpha_count", "value_score", "pyramid_multiplier", "dataset_alpha_count"]
    ds_table = mo.ui.table(data_summary[[c for c in _cols if c in data_summary.columns]]
                           if data_summary is not None and not data_summary.empty else [],
                           selection="single", page_size=10,
                           label="Most under-used first (BRAIN's value score). Tick a dataset to see what each field "
                                 "measures")
    return data_summary, ds_table


@app.cell(hide_code=True)
def _(CONCEPTS, CATEGORY_NAMES, mo):
    concept_dd = mo.ui.dropdown(options=sorted(CONCEPTS), value="cfo", searchable=True, label="Economic concept")
    concept_cats = mo.ui.multiselect(options={CATEGORY_NAMES.get(c, c): c for c in CATEGORY_NAMES},
                                     label="Only these categories")
    search_box = mo.ui.text(placeholder="e.g. short interest", label="Free-text search", debounce=True)
    return concept_cats, concept_dd, search_box


@app.cell(hide_code=True)
def _(GUIDE_DATASETS, R, SANDBOX, catalog, concept_cats, concept_dd, data_ctx, data_summary, ds_table, mo, pd,
      search_box, sync_region, sync_region_btn):
    _parts = [mo.md("Every field is classified by **nature** (balance-sheet stock, income flow, estimate, count, "
                    "vendor score, date, code ...) and matched to **economic concepts**, with **coverage** and "
                    "**crowding** (how many alphas already use it). High coverage and moderate crowding is the "
                    "sweet spot; thousands of alphas on a dataset means yours will correlate with the pool.")]
    if not SANDBOX:
        _parts.append(mo.accordion({"Download another region from BRAIN": mo.vstack(
            [sync_region, sync_region_btn] if R is not None else [mo.md("_Log in first (Setup tab)._")])}))
    if not data_ctx.value:
        _parts.append(mo.callout(mo.md("No catalog yet. Download a region above."), kind="warn"))
        data_view = mo.vstack(_parts)
    else:
        _r, _u, _d = data_ctx.value
        _have = set(data_summary["dataset"]) if data_summary is not None and not data_summary.empty else set()
        _guide = pd.DataFrame([{"category": c, "guide dataset": d, "available here": d.split(" ")[0] in _have}
                               for c, lst in GUIDE_DATASETS.items() for d in lst])
        _detail = mo.md("")
        _sel = ds_table.value
        if _sel is not None and len(_sel):
            _ds = _sel.iloc[0]["dataset"]
            _cm = catalog.concept_map(_ds, _r, _u, _d).sort_values("coverage", ascending=False) \
                .reset_index(drop=True).round(3)
            _detail = mo.vstack([mo.md(f"### What each field of `{_ds}` measures"),
                                 mo.ui.table(_cm, selection=None, page_size=10)])
        _found = catalog.find_concept(concept_dd.value, _r, _u, _d, categories=list(concept_cats.value) or None)
        _search = catalog.search(search_box.value, _r, _u, _d) if search_box.value.strip() else None
        _parts += [data_ctx, mo.md("### Datasets in this region"), ds_table, _detail,
                   mo.md("### Find fields by economic concept"), mo.hstack([concept_dd, concept_cats], justify="start"),
                   mo.ui.table(_found, selection=None, page_size=8),
                   search_box]
        if _search is not None:
            _parts.append(mo.ui.table(_search, selection=None, page_size=8))
        _parts.append(mo.accordion({"Datasets your Pyramids guide recommends - are they here?":
                                    mo.ui.table(_guide, selection=None, page_size=15)}))
        data_view = mo.vstack(_parts)
    return (data_view,)


# ================================================================================================ ACCOUNT
@app.cell(hide_code=True)
def _(mo):
    acct_btn = mo.ui.run_button(label="Download my submitted alphas, operators + simulation options from BRAIN",
                                kind="success")
    get_acct_msg, set_acct_msg = mo.state(None)
    return acct_btn, get_acct_msg, set_acct_msg


@app.cell(hide_code=True)
def _(J, R, SANDBOX, acct, acct_btn, get_version, mo, set_acct_msg, set_version, store):
    mo.stop(not acct_btn.value or R is None or SANDBOX)
    try:
        with mo.status.spinner(title="Downloading your submitted alphas (a few pages of 100) ..."):
            _res = acct.sync_account(R.brain, J)
        _c = acct.counts(J)
        # BRAIN's own count replaces the number typed by hand; HYPOLAB adds its own submissions from here on
        store.set_goal("lifetime_alphas", _c["lifetime_regular"], store.lifetime()["unlock"])
        _opt = (f" Simulation options for {_res['regions_synced']} regions saved (universes, delays, risk "
                f"neutralizations)." if _res.get("regions_synced") else
                f" Simulation options not saved: {_res['regions_error']}" if _res.get("regions_error") else "")
        set_acct_msg(("ok", f"Downloaded {_res['alphas']} submitted alphas and {_res.get('regular', 0)} REGULAR "
                               f"operators ({len(_res.get('added_to_linter', []))} new to the linter). The SuperAlpha countdown now "
                                f"uses BRAIN's count.{_opt}"))
    except Exception as _e:  # noqa: BLE001
        set_acct_msg(("error", f"Download failed: {_e}"))
    set_version(get_version() + 1)
    return


@app.cell(hide_code=True)
def _(J, R, SANDBOX, acct, get_version, mo, pd):
    # Re-run a submitted alpha with BRAIN's risk-neutralization sets or at delay 0 (BRAIN_RULES N5, S-8).
    get_version()
    _df = acct.account_alphas(J)
    _reg = _df[_df["type"] == "REGULAR"] if not _df.empty else _df
    _cols = ["alpha_id", "date_submitted", "region", "delay", "neutralization", "sharpe", "fitness", "turnover",
             "code"]
    rerun_table = mo.ui.table(_reg[[c for c in _cols if c in _reg.columns]].reset_index(drop=True)
                              if len(_reg) else pd.DataFrame(columns=_cols),
                              selection="single", page_size=8, label="Pick ONE submitted alpha")
    return (rerun_table,)


@app.cell(hide_code=True)
def _(R, mo, rerun_table):
    _sel = rerun_table.value
    _row = _sel.iloc[0].to_dict() if _sel is not None and len(_sel) else None
    _vars = R.rerun_variants(_row) if (R is not None and _row) else []
    rerun_choices = mo.ui.multiselect(options={v["label"]: i for i, v in enumerate(_vars)},
                                      label="Variants to simulate (each costs one simulation and one try)")
    rerun_btn = mo.ui.run_button(label="Simulate the chosen variants", kind="success")
    rerun_row, rerun_vars = _row, _vars
    return rerun_btn, rerun_choices, rerun_row, rerun_vars


@app.cell(hide_code=True)
def _(J, R, SANDBOX, acct, get_results, mo, rerun_btn, rerun_choices, rerun_row, rerun_vars, set_results, theme):
    mo.stop(not rerun_btn.value or R is None or rerun_row is None or not rerun_choices.value)
    _full = acct.account_alphas(J)
    _full = _full[_full["alpha_id"] == rerun_row["alpha_id"]]
    _alpha = _full.iloc[0].to_dict() if len(_full) else rerun_row
    with mo.status.spinner(title=theme.loading_line(f"{len(rerun_choices.value)} variant(s)")):
        _res = R.rerun(_alpha, [rerun_vars[i] for i in rerun_choices.value])
    set_results(get_results() + _res)
    return


@app.cell(hide_code=True)
def _(J, acct, get_version, mo):
    get_version()
    _df = acct.account_alphas(J)
    _y, _q = acct.current_quarter()
    _qs = {f"{_y} Q{_q}": (_y, _q)}
    if not _df.empty:
        for _t in _df["submitted"].dropna():
            _qs.setdefault(f"{_t.year} Q{(_t.month - 1) // 3 + 1}", (_t.year, (_t.month - 1) // 3 + 1))
    acct_quarter = mo.ui.dropdown(options=dict(sorted(_qs.items(), reverse=True)), value=f"{_y} Q{_q}",
                                  label="Quarter (BRAIN's calendar, New York time)")
    return (acct_quarter,)


@app.cell(hide_code=True)
def _(J, SANDBOX, acct, acct_btn, acct_quarter, config, get_acct_msg, get_version, mo, pd, rerun_btn,
      rerun_choices, rerun_table, rules):
    get_version()
    _y, _q = acct_quarter.value
    _last = acct.last_sync(J)
    _parts = [mo.md("Your **submitted** alphas as BRAIN records them: the real lifetime count (it feeds the SuperAlpha "
                    "countdown), operators used and unused per quarter by BRAIN's categories, and the fields you "
                    "lean on most. Download again whenever you have submitted on the BRAIN website.")]
    if SANDBOX:
        _parts.append(mo.callout(mo.md("Your account data comes from BRAIN: switch to **Live** on the Setup tab."),
                                 kind="neutral"))
    else:
        _parts.append(mo.hstack([acct_btn, mo.md(
            f"_Last download: {pd.Timestamp(_last, unit='s').strftime('%Y-%m-%d %H:%M')} UTC_" if _last
            else "_Not downloaded yet._")], justify="start", gap=1.5))
    _m = get_acct_msg()
    if _m:
        _parts.append(mo.callout(mo.md(_m[1]), kind="success" if _m[0] == "ok" else "danger"))
    _c = acct.counts(J, _y, _q)
    _summary, _bycat, _used, _unused = acct.operator_audit(J, _y, _q)
    _cat_views = {}
    for _row in _bycat.itertuples(index=False):
        _u = _used[_used["category"] == _row.category][["operator", "submissions"]]
        _n = _unused[_unused["category"] == _row.category]["operator"].tolist()
        _cat_views[f"{_row.category}: {_row.used}/{_row.available} used"] = mo.vstack([
            mo.ui.table(_u, selection=None, show_download=False) if len(_u) else mo.md("_None used this quarter._"),
            mo.md("**Not used yet:** " + (", ".join(f"`{x}`" for x in _n) if _n else "all used"))])
    _subs = acct.account_alphas(J)
    _cols = ["date_submitted", "type", "region", "delay", "sharpe", "fitness", "turnover", "status", "code"]
    _tb = acct.tiebreakers(J, _y, _q)
    _osm, _osm_notes = acct.osmosis_check(J, config.account_regions())
    _qs, _qe = rules.quarter_bounds()
    _lock = rules.osmosis_lock_deadline(_qe)
    _parts += [
        mo.md(f"### Genius tie-breakers, {_y} Q{_q} (from your submissions)\n"
              f"Per alpha: **{_tb['operators per alpha']}** operators, **{_tb['fields per alpha']}** fields (lower is "
              f"better). Distinct this quarter: **{_tb['distinct operators']}** operators, **{_tb['distinct fields']}** "
              f"fields (higher is better). Simple alphas built from many different fields win both. The simulation "
              f"streak counts too: simulate something every day (one free missed day per quarter)."),
        mo.md(f"### Osmosis check\nA valid allocation needs at least 3 region x delay scopes, each with exactly "
              f"100,000 points over at least 10 alphas. Combined Osmosis Performance needs 6 valid weeks in the "
              f"quarter: the last Sunday to lock one is **{_lock:%a %d %b}** (earlier is safer - BRAIN refreshes the "
              f"number only every 4-6 weeks). Points lock Sunday 23:59 New York time = Monday 06:59/07:59 Nairobi."),
        mo.callout(mo.md("\n\n".join(_osm_notes)), kind="info") if _osm_notes else mo.md(""),
        mo.ui.table(_osm, selection=None, page_size=12, show_column_summaries=False) if len(_osm) else mo.md(""),
        mo.md("Prefer alphas with turnover below 20% for Osmosis, and drop ones whose Sharpe falls ~60% or more with "
              "MaxTrade ON unless they are unique (BRAIN's Osmosis tips)."),
        mo.md("### Re-run a submitted alpha with a risk set or at delay 0\nBRAIN suggests re-simulating good alphas "
              "with risk neutralization (SLOW for low turnover, FAST / SLOW_AND_FAST for high turnover, "
              "REVERSION_AND_MOMENTUM for ratios over price) and re-running D1 alphas at D0. Some come out better and "
              "less correlated - candidate new signals. Results appear on the **Lab** tab, where the gate checks "
              "self-correlation with the original before you can submit."),
        rerun_table, rerun_choices, rerun_btn,
    ]
    _parts += [
        mo.md(f"### Counts\nLifetime: **{_c['lifetime_regular']}** regular and **{_c['lifetime_super']}** super "
              f"alphas submitted. {_y} Q{_q}: **{_c['quarter_regular']}** regular, **{_c['quarter_super']}** super."),
        mo.md("### Operators by category"), acct_quarter,
        mo.ui.table(_bycat, selection=None, show_download=False),
        mo.accordion(_cat_views) if _cat_views else mo.md(""),
        mo.md("Use an unused operator only when it fits the idea's mechanism; operators added just to raise "
              "coverage make weaker alphas."),
        mo.md("### Fields your submitted alphas use most\nNew ideas built on these will correlate with your own alphas."),
        mo.ui.table(acct.field_usage(J), selection=None, page_size=10),
        mo.md("### Submitted alphas"),
        mo.ui.table(_subs[[c for c in _cols if c in _subs.columns]] if not _subs.empty else [], selection=None,
                    page_size=10),
        mo.accordion({"How operators are counted": mo.ui.table(
            pd.DataFrame([{"item": k, "value": str(v)} for k, v in _summary.items()]), selection=None,
            show_download=False)}),
    ]
    account_view = mo.vstack(_parts)
    return (account_view,)


# ==================================================================================================== PLAY
@app.cell(hide_code=True)
def _(R, SANDBOX, config, mo, play):
    # The playground: random alphas from random cards or random fields. Ignores the Pyramid plan on purpose.
    _regions = ["SBX"] if SANDBOX else config.account_regions()
    _default = "SBX" if SANDBOX else (R.region if R is not None and R.region in _regions else _regions[0])
    play_mode = mo.ui.radio(options={"Mix": "mix", "Random idea cards": "cards",
                                     "Wild: random field x random template": "wild"},
                            value="Mix", inline=True, label="Dice")
    play_n = mo.ui.slider(start=1, stop=10, step=1, value=4, label="How many", show_value=True)
    play_region = mo.ui.dropdown(options=_regions, value=_default, label="Region")
    play_shuffle = mo.ui.checkbox(value=True, label="Shuffle settings too (decay, neutralization, truncation)")
    play_seed = mo.ui.number(start=0, stop=999999, step=1, value=0, label="Seed (0 = surprise me)")
    roll_btn = mo.ui.run_button(label="Roll the dice (free)", kind="neutral")
    get_roll, set_roll = mo.state(play.load_roll(SANDBOX))      # the last roll survives a restart
    get_play, set_play = mo.state([])
    return (get_play, get_roll, play_mode, play_n, play_region, play_seed, play_shuffle, roll_btn, set_play,
            set_roll)


@app.cell(hide_code=True)
def _(R, SANDBOX, mo, play, play_mode, play_n, play_region, play_seed, play_shuffle, roll_btn, set_roll):
    mo.stop(not roll_btn.value or R is None)
    _seed = int(play_seed.value) or None
    _items = R.roll(n=int(play_n.value), mode=play_mode.value, region=play_region.value, seed=_seed,
                    shuffle_settings=bool(play_shuffle.value))
    play.save_roll(_items, SANDBOX)
    set_roll(_items)
    return


@app.cell(hide_code=True)
def _(get_roll, mo, play):
    _items = get_roll()
    _t = play.items_table(_items)
    _t.insert(0, "#", range(len(_t)))
    roll_table = mo.ui.table(_t, selection="multi", page_size=10,
                             label="Rolled alphas - tick some to simulate only those, or none to simulate them all")
    play_sim_btn = mo.ui.run_button(label="Simulate (all rolled, or only the ticked ones)", kind="success")
    return play_sim_btn, roll_table


@app.cell(hide_code=True)
def _(R, get_play, get_roll, mo, play_sim_btn, roll_table, set_play, theme):
    mo.stop(not play_sim_btn.value or R is None)
    _items = get_roll()
    _sel = roll_table.value
    _keep = {int(x) for x in _sel["#"]} if _sel is not None and len(_sel) else set(range(len(_items)))
    _chosen = [it for i, it in enumerate(_items) if i in _keep]
    mo.stop(not _chosen)
    with mo.status.spinner(title=theme.loading_line(f"{len(_chosen)} random alpha(s)")):
        _res = R.play(_chosen)
    set_play(get_play() + _res)
    return


@app.cell(hide_code=True)
def _(get_play, mo, pd, views):
    _res = get_play()
    play_results = mo.ui.table(pd.DataFrame([{"#": i, **views.result_row(t)} for i, t in enumerate(_res)]),
                               selection="single", initial_selection=[len(_res) - 1] if _res else None,
                               page_size=8, label="What the dice brought back (select one to read it)")
    play_to_lab = mo.ui.run_button(label="Send this one to the Lab (robustness, gate, submit)", kind="neutral")
    return play_results, play_to_lab


@app.cell(hide_code=True)
def _(get_play, get_results, mo, play_results, play_to_lab, set_results):
    mo.stop(not play_to_lab.value)
    _sel = play_results.value
    mo.stop(_sel is None or not len(_sel))
    _t = get_play()[int(_sel.iloc[0]["#"])]
    if not any(_x is _t for _x in get_results()):
        set_results(get_results() + [_t])
    return


@app.cell(hide_code=True)
def _(J, R, SANDBOX, get_play, get_roll, mo, play, play_mode, play_n, play_region, play_results, play_seed,
      play_shuffle, play_sim_btn, play_to_lab, roll_btn, roll_table):
    if R is None:
        play_view = mo.callout(mo.md("The playground needs a BRAIN session (or sandbox mode)."), kind="warn")
    else:
        _st = play.play_stats(R.journal)       # the sandbox keeps its own in-memory journal
        _best = f"{_st['best_sharpe']:.2f}" if _st["best_sharpe"] is not None else "-"
        _parts = [
            mo.md('<span class="hl-ticker">&gt; wake up, Zacc ... the market has patterns nobody has tried. '
                  'Roll some dice.</span>'),
            mo.md("No Pyramids, no plan, no ranking: **random idea cards** (built-in or yours, any family) and "
                  "**wild rolls** (a random field from a random dataset dropped into a random template - two "
                  "fields always come from the same dataset, so the alpha stays *single dataset*). Rolling is free; "
                  "only **Simulate** spends simulations" + ("." if SANDBOX else
                  " from your BRAIN quota.")),
            mo.md(f'<span class="hl-score">dice thrown <b>{_st["plays"]}</b></span>'
                  f'<span class="hl-score">today <b>{_st["today"]}</b></span>'
                  f'<span class="hl-score">PASS <b>{_st["pass"]}</b></span>'
                  f'<span class="hl-score">NEAR <b>{_st["near"]}</b></span>'
                  f'<span class="hl-score">best Sharpe <b>{_best}</b></span>'),
            mo.hstack([play_mode, play_region], justify="start", gap=2, wrap=True),
            mo.hstack([play_n, play_seed, play_shuffle], justify="start", gap=2, wrap=True),
            roll_btn,
        ]
        if get_roll():
            _parts += [roll_table, play_sim_btn]
        elif roll_btn.value:
            _parts.append(mo.callout(mo.md("Nothing rolled: this region has no field list yet - download it on "
                                           "the **Data** tab."), kind="warn"))
        if get_play():
            _parts += [mo.md("### Results"), play_results]
            _sel = play_results.value
            if _sel is not None and len(_sel):
                _t = get_play()[int(_sel.iloc[0]["#"])]
                _parts += [mo.md(_t.markdown()), play_to_lab]
        _parts.append(mo.accordion({"Why the dice still count": mo.md(
            "Random search finds luck as easily as signal: try 40 noise fields and one will look good. So every "
            "roll is journaled as a try for its idea (`play:<card>` or `play:wild:<dataset>`). If a roll goes to "
            "the Lab and the gate, the deflated Sharpe counts all the dice you threw on that idea. A good roll is a "
            "**lead**: before you submit, ask what the economic story is - then it can become a proper card.")}))
        play_view = mo.vstack(_parts)
    return (play_view,)


# ============================================================================================ SUPERALPHA (1.10.0)
@app.cell(hide_code=True)
def _(mo):
    # phase 8: SuperAlpha results (newest last), the last gate, a message line, and a counter that re-reads the pool
    get_super, set_super = mo.state([])
    get_super_gate, set_super_gate = mo.state(None)
    get_super_msg, set_super_msg = mo.state(None)
    get_super_v, set_super_v = mo.state(0)
    return get_super, get_super_gate, get_super_msg, get_super_v, set_super, set_super_gate, set_super_msg, set_super_v


@app.cell(hide_code=True)
def _(J, R, SANDBOX, get_super_v, store):
    from hypolab import superalpha as SA
    get_super_v()
    super_pool = R.super_pool() if R is not None else SA.pool_alphas(J)
    super_pools = SA.pools(super_pool)
    super_lock = SA.unlock_status(store, J, sandbox=SANDBOX)
    return SA, super_lock, super_pool, super_pools


@app.cell(hide_code=True)
def _(SANDBOX, config, mo, store, this_week):
    # The form never depends on the pool: rebuilding it after "Build a practice pool" showed old values in the
    # browser while new ones were used (the marimo gotcha in HANDOFF, phase 3). The pools table suggests a limit.
    _regions = ["SBX"] if SANDBOX else config.account_regions()
    _plan = (store.plan(this_week) or {}).get("region")
    sa_region = mo.ui.dropdown(options=_regions, value=_plan if _plan in _regions else _regions[0], label="Region")
    return (sa_region,)


@app.cell(hide_code=True)
def _(SA, SANDBOX, config, mo, sa_region):
    _reg = sa_region.value
    _delays = [1] if SANDBOX else list(dict.fromkeys(config.REGION_DEFAULTS.get(_reg, {}).get("delays", [1]) + [1]))
    sa_delay = mo.ui.dropdown(options={f"D{d}": d for d in _delays}, value="D1", label="Delay")
    # 1.10.1: universe_for() is None until the Account tab has saved the simulation options
    sa_universe = mo.ui.text(value="SANDBOX" if SANDBOX else (config.universe_for(_reg) or
                                                              config.REGION_DEFAULTS.get(_reg, {}).get("universe") or ""),
                             label="Universe")
    _neuts = config.region_neutralizations(_reg) or ["SUBINDUSTRY"]
    sa_neut = mo.ui.dropdown(options=_neuts, value="SUBINDUSTRY" if "SUBINDUSTRY" in _neuts else _neuts[0],
                             label="Neutralization")
    sa_decay = mo.ui.number(start=0, stop=60, step=1, value=SA.DEFAULT_DECAY, label="Decay")
    sa_trunc = mo.ui.number(start=0.01, stop=1.0, step=0.01, value=SA.DEFAULT_TRUNCATION, label="Truncation")
    sa_limit = mo.ui.number(start=SA.MIN_SELECTION, stop=SA.MAX_SELECTION, step=1, value=20,
                            label="Keep the top (selectionLimit)")
    sa_handling = mo.ui.dropdown(options=list(SA.SELECTION_HANDLING), value="POSITIVE",
                                 label="Scores that count (selectionHandling)")
    sa_activation = mo.ui.dropdown(options={"IS: each alpha's whole history": "IS",
                                            "OS: only from each alpha's submission": "OS"},
                                   value="IS: each alpha's whole history", label="Component activation")
    sa_sel_dd = mo.ui.dropdown(options={r.name: r.key for r in SA.selections(30)}, value="Least correlated",
                               label="Selection recipe")
    sa_combo_dd = mo.ui.dropdown(options={r.name: r.key for r in SA.COMBOS}, value="Equal weight",
                                 label="Weighting recipe (combo)")
    sa_sel_own = mo.ui.text_area(value="", rows=2, full_width=True,
                                 label="Or your own selection (leave empty to use the recipe)")
    sa_combo_own = mo.ui.text_area(value="", rows=3, full_width=True,
                                   label="Or your own combo (leave empty to use the recipe)")
    sa_sim_btn = mo.ui.run_button(label="Simulate this SuperAlpha (1 simulation)", kind="success")
    sa_pool_btn = mo.ui.run_button(label="Build a practice pool (sandbox)", kind="neutral", disabled=not SANDBOX)
    sa_restore_btn = mo.ui.run_button(label="Restore SuperAlpha results", kind="neutral")
    return (sa_activation, sa_combo_dd, sa_combo_own, sa_decay, sa_delay, sa_handling, sa_limit, sa_neut, sa_pool_btn,
            sa_restore_btn, sa_sel_dd, sa_sel_own, sa_sim_btn, sa_trunc, sa_universe)


@app.cell(hide_code=True)
def _(SA, mo, sa_activation, sa_combo_dd, sa_combo_own, sa_decay, sa_delay, sa_handling, sa_limit, sa_region,
      sa_sel_dd, sa_sel_own, sa_trunc, super_pool, views):
    # what would be simulated, checked as you type (nothing simulates here)
    _lim = int(sa_limit.value)
    _sr, _cr = SA.recipe("selection", sa_sel_dd.value, _lim), SA.recipe("combo", sa_combo_dd.value)
    sa_selection = sa_sel_own.value.strip() or _sr.code
    sa_combo = sa_combo_own.value.strip() or _cr.code
    _rep = SA.check(sa_selection, sa_combo, _lim, sa_handling.value, sa_activation.value, int(sa_decay.value),
                    float(sa_trunc.value))
    _why = []
    if not sa_sel_own.value.strip():
        _why.append(f"**Selection - {_sr.name}:** {_sr.why}")
    if not sa_combo_own.value.strip():
        _why.append(f"**Weighting - {_cr.name}:** {_cr.why}")
    _pv = SA.preview(sa_selection, super_pool, sa_region.value, int(sa_delay.value), _lim, sa_handling.value)
    _parts = [mo.md("\n\n".join(_why)) if _why else mo.md(""),
              mo.md(f"```\nselection: {sa_selection}\ncombo:     {sa_combo}\n```"),
              mo.callout(mo.md(_rep.markdown()), kind="success" if _rep.ok and not _rep.warnings else
                         ("warn" if _rep.ok else "danger")),
              mo.md(f"**Preview on your submitted alphas:** {_pv['note']}")]
    _tab = _pv.get("table")
    if _pv.get("ok") and _tab is not None and not _tab.empty:
        _t = _tab.head(25).copy()
        _t["score"] = _t["score"].round(3)
        _parts.append(mo.accordion({"Which alphas it keeps": mo.Html(views.html_table(
            _t[["alpha_id", "score", "kept"]], code_cols=("alpha_id",)))}))
    sa_check_ok = _rep.ok
    sa_check_view = mo.vstack(_parts)
    return sa_check_ok, sa_check_view, sa_combo, sa_selection


@app.cell(hide_code=True)
def _(R, SANDBOX, get_super_v, mo, sa_pool_btn, set_super_msg, set_super_v, theme):
    mo.stop(not sa_pool_btn.value or not SANDBOX or R is None)
    with mo.status.spinner(title=theme.loading_line("practice pool")):
        _n = R.practice_super_pool(24)
    set_super_msg(f"Practice pool: {_n} sandbox alpha(s) submitted (they stand in for your 100 real ones).")
    set_super_v(get_super_v() + 1)
    return


@app.cell(hide_code=True)
def _(R, get_super, mo, sa_activation, sa_check_ok, sa_combo, sa_decay, sa_delay, sa_handling, sa_limit, sa_neut,
      sa_region, sa_selection, sa_sim_btn, sa_trunc, sa_universe, set_super, set_super_gate, store, theme):
    # Spends ONE SuperAlpha simulation, and only when you click (changing a control never simulates).
    mo.stop(not sa_sim_btn.value or R is None or not sa_check_ok)
    with mo.status.spinner(title=theme.loading_line("1 SuperAlpha simulation")):
        _t = R.super_test(sa_selection, sa_combo, sa_region.value, sa_universe.value.strip() or None,
                          int(sa_delay.value), int(sa_decay.value), sa_neut.value, float(sa_trunc.value),
                          int(sa_limit.value), sa_handling.value, sa_activation.value, store=store)
    set_super(get_super() + [_t])
    set_super_gate(None)
    return


@app.cell(hide_code=True)
def _(R, get_super, mo, sa_restore_btn, set_super):
    mo.stop(not sa_restore_btn.value or R is None)
    _have = {t.alpha_id for t in get_super()}
    set_super([t for t in R.super_results(20) if t.alpha_id not in _have] + list(get_super()))
    return


@app.cell(hide_code=True)
def _(get_super, mo):
    _res = get_super()
    _opts = {f"{i + 1}. {t.rung} | D{t.settings.get('delay')} decay {t.settings.get('decay')} | "
             f"{t.diagnosis.verdict}" + (f" {t.summary.get('is_sharpe'):.2f}" if t.summary.get("is_sharpe") is not None
                                         else ""): i for i, t in enumerate(_res)}
    sa_res_dd = mo.ui.dropdown(options=_opts, value=list(_opts)[-1] if _opts else None, label="SuperAlpha result")
    sa_gate_btn = mo.ui.run_button(label="Run the SuperAlpha gate", kind="neutral")
    return sa_gate_btn, sa_res_dd


@app.cell(hide_code=True)
def _(get_super, sa_res_dd):
    _res = get_super()
    sa_current = _res[int(sa_res_dd.value)] if _res and sa_res_dd.value is not None else None
    return (sa_current,)


@app.cell(hide_code=True)
def _(R, mo, sa_current, sa_gate_btn, set_super_gate, store):
    mo.stop(not sa_gate_btn.value or R is None or sa_current is None or not sa_current.alpha_id)
    with mo.status.spinner(title="Platform checks, correlations, deflated Sharpe ..."):
        set_super_gate(R.super_gate(sa_current, store))
    return


@app.cell(hide_code=True)
def _(J, SA, SANDBOX, get_super_gate, get_super_v, mo, sa_current, store):
    get_super_v()
    _g = get_super_gate()
    _lock = SA.unlock_status(store, J, sandbox=SANDBOX)
    _ready = (_g is not None and sa_current is not None and _g.alpha_id == sa_current.alpha_id and _g.ready
              and _lock["unlocked"] and _lock["left_today"] > 0)
    sa_confirm = mo.ui.text(value="", placeholder=f"SUBMIT {_g.alpha_id}" if _ready else "",
                            label="Type SUBMIT and the alpha id to confirm", full_width=True)
    sa_submit_btn = mo.ui.run_button(label="Submit SuperAlpha to BRAIN (permanent)" if not SANDBOX else
                                     "Submit SuperAlpha (sandbox practice)", kind="danger", disabled=not _ready)
    return sa_confirm, sa_submit_btn


@app.cell(hide_code=True)
def _(R, get_super_gate, get_super_v, mo, sa_confirm, sa_submit_btn, set_super_msg, set_super_v, store):
    mo.stop(not sa_submit_btn.value or R is None)
    _g = get_super_gate()
    try:
        _res = R.super_submit(_g, confirm=sa_confirm.value.strip(), store=store)
        set_super_msg(f"Submitted SuperAlpha `{_g.alpha_id}` (BRAIN answered {_res.get('status_code')}). That was "
                      "today's one SuperAlpha.")
    except Exception as _e:  # noqa: BLE001
        set_super_msg(f"NOT submitted: {_e}")
    set_super_v(get_super_v() + 1)
    return


@app.cell(hide_code=True)
def _(R, SA, SANDBOX, get_super_gate, get_super_msg, mo, sa_activation, sa_check_view, sa_combo_dd, sa_combo_own,
      sa_confirm, sa_current, sa_decay, sa_delay, sa_gate_btn, sa_handling, sa_limit, sa_neut, sa_pool_btn,
      sa_region, sa_res_dd, sa_restore_btn, sa_sel_dd, sa_sel_own, sa_sim_btn, sa_submit_btn, sa_trunc,
      sa_universe, super_lock, super_pools, views):
    _parts = [mo.md("## SuperAlpha builder\nA SuperAlpha combines alphas you have already **submitted** in one region "
                    "and delay: a **selection** ranks them and keeps the top ones, a **combo** weights them day by "
                    "day. BRAIN accepts **one a day**, on top of your 4 alphas."),
              mo.callout(mo.md(SA.unlock_line(super_lock)), kind="success" if super_lock["unlocked"] else "warn")]
    if get_super_msg():
        _parts.append(mo.callout(mo.md(get_super_msg()), kind="info"))
    _pt = super_pools.copy()
    if not _pt.empty:
        _pt["ready"] = _pt["ready"].map({True: "yes", False: "not yet (10+)"})
        _pt = _pt.rename(columns={"limit": "suggested limit"})
    _parts += [mo.md("### Your pools"),
               mo.Html(views.html_table(_pt)) if not _pt.empty else mo.md(
                   "_No submitted alphas known yet._ " + ("Press **Build a practice pool** below." if SANDBOX else
                                                          "Download your account on the **Account** tab.")),
               sa_pool_btn if SANDBOX else mo.md("")]
    if R is None:
        _parts.append(mo.callout(mo.md("Log in on the **Setup** tab to simulate; planning and preview work "
                                       "without."), kind="warn"))
    _parts += [mo.md("### Build one\n" + SA.ladder_note()),
               mo.hstack([sa_region, sa_delay, sa_universe, sa_neut], justify="start", gap=2, wrap=True),
               mo.hstack([sa_decay, sa_trunc, sa_limit, sa_handling, sa_activation], justify="start", gap=2,
                         wrap=True),
               mo.hstack([sa_sel_dd, sa_combo_dd], justify="start", gap=2, wrap=True),
               sa_sel_own, sa_combo_own, sa_check_view, mo.hstack([sa_sim_btn, sa_restore_btn], justify="start")]
    if sa_current is not None:
        _parts += [mo.md("### Results"), sa_res_dd, mo.md(sa_current.markdown())]
        _note = None
        try:
            _note = (R.brain._alphas.get(sa_current.alpha_id) or {}).get("sandbox_note") if SANDBOX and R else None
        except Exception:  # noqa: BLE001
            _note = None
        if _note:
            _parts.append(mo.md(f"_Sandbox: {_note}. Synthetic numbers: practise the steps, don't judge the "
                                "recipes by them._"))
        if sa_current.alpha_id:
            _parts.append(sa_gate_btn)
        _g = get_super_gate()
        if _g is not None and _g.alpha_id == sa_current.alpha_id:
            _parts += [mo.md(_g.markdown()), sa_confirm, sa_submit_btn]
    _parts.append(mo.accordion({"Where these rules come from": mo.md(SA.sources_note())}))
    super_view = mo.vstack(_parts)
    return (super_view,)


# =================================================================================================== TABS
@app.cell(hide_code=True)
def _(account_view, data_view, header, journal_view, lab_view, mo, play_view, pyramids_view, setup_view, super_view):
    mo.vstack([header, mo.ui.tabs({"Lab": lab_view, "Pyramids": pyramids_view, "Play": play_view,
                                   "SuperAlpha": super_view,
                                   "Journal": journal_view,
                                   "Account": account_view,
                                   "Data": data_view,
                                   "Setup": setup_view})])
    return


if __name__ == "__main__":
    app.run()

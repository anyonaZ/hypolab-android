"""The cockpit's Data, Account and Setup tabs, and the dataset-scan app, as web pages (1.15.0, Android phase C3).

With these the web app covers everything the marimo apps did; marimo stays on the laptop until Zacc decides.
Same engine calls and rules as apps/cockpit.py and apps/dataset_scan.py:
- Data: your catalog per region (datasets ranked by BRAIN's value score, what each field measures, fields by
  economic concept, free-text search, the Pyramids guide's datasets); downloading a region's field list from BRAIN
  is a job (live only). "Learn a dataset": Explore (free, no simulation) and Scan (one simulation per field, a job;
  a live scan can take 10-30 minutes).
- Account: download your submitted alphas, operators and simulation options (a job, live only); counts,
  tie-breakers, Osmosis check, operators by category per quarter, fields you lean on; re-run a submitted alpha with
  a risk set or at delay 0 (each variant one simulation, a job; results land in the Lab).
- Setup: where you stand, sandbox/live switch, BRAIN login (face scan through BRAIN's link, opened in the browser),
  log out, the Gold operator list and the daily routine. On the tablet, "remember my password" waits for phase D
  (Android Keystore); until then only BRAIN's session is kept.
"""
from __future__ import annotations

import pandas as pd
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route

from hypolab import config
from ideaweb.lab import LAB, _form_float, _form_int, _start, job_ctx, table

DS_COLS = ["category_name", "dataset", "name", "fields", "usable", "matrix", "vector", "median_coverage",
           "median_alpha_count", "value_score", "pyramid_multiplier", "dataset_alpha_count"]


def _catalog():
    R = LAB.researcher()
    if R is not None:
        return R.catalog
    from hypolab.catalog import Catalog
    return Catalog()


def _bump():
    """After a download the Lab's cached cards and the Pyramid counts are stale."""
    LAB._cards = {}
    LAB.pyr = None


# ============================================================================================== DATA
def data_routes(page, go):
    async def data_page(request: Request):
        from hypolab.catalog import CATEGORY_NAMES
        from hypolab.concepts import CONCEPTS
        from hypolab.pyramids import GUIDE_DATASETS
        q = request.query_params
        R = await run_in_threadpool(LAB.researcher)
        cat = _catalog()
        ctxs = cat.contexts()
        opts = [(f"{r.region}|{r.universe}|{int(r.delay)}", f"{r.region} {r.universe} D{int(r.delay)} ({r.fields} fields)")
                for r in ctxs.itertuples(index=False)]
        ctx = dict(job_ctx("/data"), R=R, sandbox=LAB.sandbox, problem=LAB.problem, opts=opts,
                   regions=config.account_regions(), live_region=config.live_region())
        if opts:
            key = q.get("ctx") if q.get("ctx") in dict(opts) else opts[0][0]
            r_, u_, d_ = key.split("|")
            d_ = int(d_)
            ctx["key"] = key
            summ = await run_in_threadpool(cat.dataset_summary, r_, u_, d_)
            summ = summ.round(3).reset_index(drop=True)
            ctx["datasets"] = summ[[c for c in DS_COLS if c in summ.columns]].to_dict("records") if not summ.empty else []
            ctx["ds_cols"] = [c for c in DS_COLS if c in summ.columns]
            ds = q.get("ds")
            if ds:
                cm = await run_in_threadpool(cat.concept_map, ds, r_, u_, d_)
                ctx["ds"] = ds
                ctx["concept_map"] = table(cm.sort_values("coverage", ascending=False).reset_index(drop=True).round(3),
                                           code_cols=["id", "field"])
            concept = q.get("concept") if q.get("concept") in CONCEPTS else "cfo"
            cats = [c for c in q.getlist("cat") if c in CATEGORY_NAMES]
            found = await run_in_threadpool(cat.find_concept, concept, r_, u_, d_, categories=cats or None)
            ctx.update(concepts=sorted(CONCEPTS), concept=concept, cat_names=CATEGORY_NAMES, cats=cats,
                       found=table(found, code_cols=["id", "field"]))
            sq = (q.get("q") or "").strip()
            ctx["q"] = sq
            if sq:
                ctx["search"] = table(await run_in_threadpool(cat.search, sq, r_, u_, d_), code_cols=["id", "field"])
            have = set(summ["dataset"]) if not summ.empty else set()
            ctx["guide"] = table(pd.DataFrame([{"category": c, "guide dataset": d,
                                                "available here": d.split(" ")[0] in have}
                                               for c, lst in GUIDE_DATASETS.items() for d in lst]))
        # Learn a dataset (the dataset-scan app)
        if R is not None:
            region = "SBX" if LAB.sandbox else config.live_region()
            u = config.REGION_DEFAULTS.get(region, {}).get("universe", "TOP3000") if not LAB.sandbox else "SANDBOX"
            dss = await run_in_threadpool(R.catalog.datasets, region, u, 1)
            ids = sorted(dss["id"].tolist()) if not dss.empty else []
            default = "sbx_analyst" if LAB.sandbox else "analyst15"
            s = LAB.scan_form or {}
            ctx["learn"] = {"region": region, "universe": u, "ids": ids,
                            "ds": s.get("ds") or (default if default in ids else (ids[0] if ids else "")),
                            "explore_n": s.get("explore_n", 6), "scan_n": s.get("scan_n",
                                                                                int(config.settings()["scan_max_fields"])),
                            "scan_max": int(config.settings()["scan_max_fields"]) * 3, "min_cov": s.get("min_cov", 0.5),
                            "left": config.settings()["max_sims_per_day"] - R.journal.sims_today()}
            ex = LAB.explore
            if ex:
                from ideaengine import views
                ctx["explore"] = views.cards_table(ex["cards"]).to_dict("records")
                pick = q.get("lens")
                card = next((c for c in ex["cards"] if c.hypothesis.id == pick), None)
                ctx["lens"] = card.markdown() if card is not None else ""
                ctx["lens_id"] = pick or ""
                ctx["explore_ds"] = ex["ds"]
            sr = LAB.scan
            if sr is not None:
                if sr["table"].empty:
                    ctx["scan_empty"] = True
                else:
                    t = sr["table"]
                    cols = ["field", "description", "nature", "lens", "sharpe", "fitness", "turnover",
                            "above_noise_bar", "cached"]
                    ctx["scan"] = {"bar": t.attrs.get("noise_bar"), "above": int(t["above_noise_bar"].sum()),
                                   "n": len(t), "ds": sr["ds"], "table": table(t[[c for c in cols if c in t.columns]],
                                                                               code_cols=["field"])}
        return page(request, "data.html", **ctx)

    async def data_download(request: Request):
        f = await request.form()
        R = LAB.researcher()
        if R is None or LAB.sandbox:
            return go("/data", "Downloading a field list needs live mode and a BRAIN login (Setup page).", "warn")
        region = f.get("region") if f.get("region") in config.account_regions() else config.live_region()
        u = config.universe_for(region)
        if u is None:
            return go("/data", f"HYPOLAB doesn't know {region}'s universes yet: press Download on the Account page "
                               "first (it saves the simulation options).", "warn")

        def run():
            R.catalog.sync_from_brain(R.brain, region, u, 1, progress=None)
            _bump()
            return f"Downloaded the {region} {u} field list."
        return _start(request, f"downloading the {region} {u} field list (a few minutes)", run, "/data")

    async def data_explore(request: Request):
        f = await request.form()
        R = LAB.researcher()
        if R is None:
            return go("/data", LAB.problem, "err")
        LAB.scan_form = {"ds": f.get("ds") or "", "explore_n": _form_int(f, "explore_n", 6, 1, 30),
                         "scan_n": _form_int(f, "scan_n", int(config.settings()["scan_max_fields"]), 2,
                                             int(config.settings()["scan_max_fields"]) * 3),
                         "min_cov": _form_float(f, "min_cov", 0.5, 0.1, 0.9)}
        s = LAB.scan_form
        region = "SBX" if LAB.sandbox else config.live_region()
        if not s["ds"]:
            return go("/data#learn", "Pick a dataset first.", "warn")
        if f.get("go") == "scan":
            def run():
                t = R.scan(s["ds"], region, max_fields=s["scan_n"], min_coverage=s["min_cov"])
                LAB.scan = {"ds": s["ds"], "table": t}
                return f"Scan of {s['ds']} finished."
            return _start(request, f"scanning {s['ds']} (up to {s['scan_n']} simulations)", run, "/data")
        if JOBS_busy():
            return go("/data#learn", "Wait for the running job to finish.", "warn")
        cards = await run_in_threadpool(R.explore, s["ds"], region, max_fields=s["explore_n"],
                                        min_coverage=s["min_cov"])
        LAB.explore = {"ds": s["ds"], "cards": cards}
        return RedirectResponse("/data#explore", status_code=303)

    return [Route("/data", data_page), Route("/data/download", data_download, methods=["POST"]),
            Route("/data/learn", data_explore, methods=["POST"])]


def JOBS_busy():
    from ideaweb.jobs import JOBS
    return JOBS.busy()


# ============================================================================================== ACCOUNT
def account_routes(page, go):
    async def account_page(request: Request):
        from hypolab import account as acct
        from hypolab import rules
        q = request.query_params
        R = await run_in_threadpool(LAB.researcher)
        J = LAB.journal()
        df = acct.account_alphas(J)
        y, qq = acct.current_quarter()
        quarters = {f"{y} Q{qq}": (y, qq)}
        if not df.empty and "submitted" in df.columns:
            for t in df["submitted"].dropna():
                quarters.setdefault(f"{t.year} Q{(t.month - 1) // 3 + 1}", (t.year, (t.month - 1) // 3 + 1))
        quarters = dict(sorted(quarters.items(), reverse=True))
        qkey = q.get("q") if q.get("q") in quarters else f"{y} Q{qq}"
        y, qq = quarters[qkey]
        last = acct.last_sync(J)
        c = acct.counts(J, y, qq)
        summary, bycat, used, unused = acct.operator_audit(J, y, qq)
        cats = []
        for row in bycat.itertuples(index=False):
            u = used[used["category"] == row.category][["operator", "submissions"]]
            n = unused[unused["category"] == row.category]["operator"].tolist()
            cats.append({"title": f"{row.category}: {row.used}/{row.available} used",
                         "used": table(u) if len(u) else "", "unused": n})
        tb = acct.tiebreakers(J, y, qq)
        osm, osm_notes = acct.osmosis_check(J, config.account_regions())
        _, qe = rules.quarter_bounds()
        lock = rules.osmosis_lock_deadline(qe)
        reg = df[df["type"] == "REGULAR"] if not df.empty else df
        rcols = ["alpha_id", "date_submitted", "region", "delay", "neutralization", "sharpe", "fitness", "turnover",
                 "code"]
        rerun_rows = reg[[x for x in rcols if x in reg.columns]].reset_index(drop=True).to_dict("records") \
            if len(reg) else []
        pick = q.get("alpha")
        variants = []
        if pick and R is not None:
            row = next((r for r in rerun_rows if r["alpha_id"] == pick), None)
            if row is not None:
                variants = [(i, v["label"]) for i, v in enumerate(R.rerun_variants(row))]
        scols = ["date_submitted", "type", "region", "delay", "sharpe", "fitness", "turnover", "status", "code"]
        return page(request, "account.html", **job_ctx("/account"), R=R, sandbox=LAB.sandbox, problem=LAB.problem,
                    last=pd.Timestamp(last, unit="s").strftime("%Y-%m-%d %H:%M") if last else "",
                    msg_acct=LAB.acct_msg, quarters=list(quarters), qkey=qkey, y=y, qq=qq, c=c, tb=tb,
                    osm=table(osm) if len(osm) else "", osm_notes=osm_notes, lock=f"{lock:%a %d %b}",
                    bycat=table(bycat), cats=cats, fields=table(acct.field_usage(J), code_cols=["field"]),
                    subs=table(df[[x for x in scols if x in df.columns]] if not df.empty else None, code_cols=["code"]),
                    howcount=table(pd.DataFrame([{"item": k, "value": str(v)} for k, v in summary.items()])),
                    rerun_rows=rerun_rows, pick=pick or "", variants=variants)

    async def account_sync(request: Request):
        from hypolab import account as acct
        R = LAB.researcher()
        if R is None or LAB.sandbox:
            return go("/account", "Your account data comes from BRAIN: switch to Live and log in (Setup page).", "warn")

        def run():
            from ideaweb.state import state
            store = state().store
            J = R.journal
            try:
                res = acct.sync_account(R.brain, J)
            except Exception as e:  # noqa: BLE001
                LAB.acct_msg = ("err", f"Download failed: {e}")
                return (LAB.acct_msg[1], "err")
            cc = acct.counts(J)
            store.set_goal("lifetime_alphas", cc["lifetime_regular"], store.lifetime()["unlock"])
            opt = (f" Simulation options for {res['regions_synced']} regions saved (universes, delays, risk "
                   f"neutralizations)." if res.get("regions_synced") else
                   f" Simulation options not saved: {res['regions_error']}" if res.get("regions_error") else "")
            _bump()
            LAB.acct_msg = ("ok", f"Downloaded {res['alphas']} submitted alphas and {res.get('regular', 0)} REGULAR "
                                  f"operators ({len(res.get('added_to_linter', []))} new to the linter). The SuperAlpha "
                                  f"countdown now uses BRAIN's count.{opt}")
            return LAB.acct_msg[1]
        return _start(request, "downloading your submitted alphas, operators and simulation options", run, "/account")

    async def account_rerun(request: Request):
        from hypolab import account as acct
        f = await request.form()
        R = LAB.researcher()
        if R is None:
            return go("/account", LAB.problem, "err")
        aid = f.get("alpha") or ""
        J = R.journal
        full = acct.account_alphas(J)
        full = full[full["alpha_id"] == aid] if not full.empty else full
        if not len(full):
            return go("/account#rerun", "Pick a submitted alpha first.", "warn")
        alpha = full.iloc[0].to_dict()
        vars_ = R.rerun_variants(alpha)
        chosen = [vars_[int(i)] for i in f.getlist("v") if str(i).isdigit() and int(i) < len(vars_)]
        if not chosen:
            return go(f"/account?alpha={aid}#rerun", "Tick at least one variant.", "warn")

        def run():
            res = R.rerun(alpha, chosen)
            LAB.add(res)
            return f"{len(res)} variant(s) simulated: they are in the Lab, where the gate checks them."
        return _start(request, f"{len(chosen)} variant(s) of {aid}", run, "/account")

    return [Route("/account", account_page), Route("/account/sync", account_sync, methods=["POST"]),
            Route("/account/rerun", account_rerun, methods=["POST"])]


# ============================================================================================== SETUP
def _creds_line() -> str:
    """connect._creds_source() in page words (it says "run connect.login()", a laptop terminal step)."""
    from hypolab import connect
    src = connect._creds_source()
    if src.startswith("none"):
        return "none saved" + (" (the tablet keeps only BRAIN's session until phase D)"
                               if config.platform() == "android" else " - log in below")
    return src


def setup_routes(page, go):
    from hypolab import connect

    def _reopen():
        LAB.mode_key = None
        LAB.problem = ""

    async def setup_page(request: Request):
        import sys
        import hypolab
        from hypolab.brain import BrainClient
        from hypolab.operators import GOLD
        R = await run_in_threadpool(LAB.researcher)
        left = await run_in_threadpool(lambda: BrainClient(verbose=False).seconds_left())
        if R is not None and not LAB.sandbox:
            left = max(left, R.brain.seconds_left())
        status = [("mode", "sandbox (practice)" if LAB.sandbox else "live"), ("live region", config.live_region()),
                  ("credentials", _creds_line()),
                  ("BRAIN session", f"about {left / 3600:.1f} h left" if left > 0 else "none or expired"),
                  ("data folder", str(config.HOME)),
                  ("versions", f"hypolab {hypolab.__version__}, python {sys.version.split()[0]}")]
        login = LAB.login_msg or connect.pending() or {}
        return page(request, "setup.html", **job_ctx("/setup"), sandbox=LAB.sandbox, status=status,
                    regions=config.account_regions(), live_region=config.live_region(), login=login,
                    can_save=config.platform() != "android", gold=table(GOLD.table(), code_cols=["name", "operator"]))

    async def setup_mode(request: Request):
        f = await request.form()
        if f.get("mode") == "live":
            reg = f.get("region") if f.get("region") in config.account_regions() else None
            connect.go_live(reg)
        else:
            connect.go_sandbox()
        _reopen()
        return go("/setup", "Live mode: the pages use your BRAIN account." if f.get("mode") == "live"
                  else "Sandbox mode: the pages use the offline practice market. Your credentials are kept.")

    async def setup_login(request: Request):
        f = await request.form()
        email, pw = (f.get("email") or "").strip(), f.get("password") or ""
        if not email or not pw:
            return go("/setup#login", "Type your BRAIN email and password.", "warn")
        save = bool(f.get("save")) and config.platform() != "android"
        try:
            res = await run_in_threadpool(connect.begin_login, email, pw, save=save)
        except Exception as e:  # noqa: BLE001 - AuthError or network
            res = {"status": "error", "detail": str(e)}
        LAB.login_msg = res
        if res.get("status") == "ok":
            _reopen()
        return RedirectResponse("/setup#login", status_code=303)

    async def setup_scan_done(request: Request):
        try:
            res = await run_in_threadpool(connect.finish_login)
        except Exception as e:  # noqa: BLE001
            res = {"status": "error", "detail": str(e)}
        LAB.login_msg = res
        if res.get("status") == "ok":
            _reopen()
        return RedirectResponse("/setup#login", status_code=303)

    async def setup_logout(request: Request):
        connect.logout()
        LAB.login_msg = {"status": "logged_out"}
        _reopen()
        return RedirectResponse("/setup#login", status_code=303)

    return [Route("/setup", setup_page), Route("/setup/mode", setup_mode, methods=["POST"]),
            Route("/setup/login", setup_login, methods=["POST"]),
            Route("/setup/scan-done", setup_scan_done, methods=["POST"]),
            Route("/setup/logout", setup_logout, methods=["POST"])]


def routes(page, go) -> list:
    return data_routes(page, go) + account_routes(page, go) + setup_routes(page, go)

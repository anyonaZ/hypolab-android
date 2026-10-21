"""MockBrain: a stand-in for BrainClient backed by the offline sandbox.

Same methods the research workflow uses (simulate, alpha, yearly_stats, pnl,
correlations, checks, submit, diversity ...), so every notebook can be
practised end-to-end with NO account, NO network and NO risk - region "SBX".
Results are synthetic: use them to learn the workflow, not to judge ideas.
"""
from __future__ import annotations

import itertools
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .sandbox.backtest import backtest
from .sandbox.evaluator import Data, EvalError, Evaluator
from .sandbox.market import make_market
from .rules import dataset_profile

PREFIX_CATEGORY = {"fnd": "fundamental", "anl": "analyst", "ern": "earnings", "mdl": "model", "snt": "sentiment",
                   "nz": "model"}
PV = {"open", "high", "low", "close", "vwap", "volume", "adv20", "returns", "cap", "sharesout"}


def sandbox_catalog_payload(data: Data) -> dict:
    rows = data.catalog_rows()
    datasets = {}
    for r in rows:
        pre = r["id"].split("_")[0]
        cat = PREFIX_CATEGORY.get(pre, "pv")
        ds = f"sbx_{cat}"
        r["dataset"], r["category"] = ds, cat
        datasets[ds] = {"id": ds, "name": f"Sandbox {cat} data", "category": cat, "description": "synthetic"}
    return {"region": "SBX", "universe": "SANDBOX", "delay": 1, "datasets": list(datasets.values()), "fields": rows}


class MockBrain:
    is_mock = True

    def __init__(self, data: Optional[Data] = None, seed: int = 7):
        if data is None:
            from . import config
            data = make_market(seed=seed, n_stocks=config.sandbox_stocks())
        self.data = data
        self.ev = Evaluator(self.data)
        self._alphas: Dict[str, dict] = {}
        self._results: Dict[str, object] = {}
        self._submitted: List[str] = []
        self._ids = (f"SBX{n:05d}" for n in itertools.count(1))
        self.user_id = "sandbox"
        self._ds_map = {r["id"]: r["dataset"] for r in sandbox_catalog_payload(self.data)["fields"]}

    def _dataset_of(self, field_id: str):
        return self._ds_map.get(field_id)

    # ------------------------------------------------------------ session
    def login(self, force: bool = False):
        print("Sandbox mode: no login needed (synthetic data, region SBX).")
        return {"user": {"id": "sandbox"}}

    def whoami(self):
        return {"user": {"id": "sandbox"}}

    def ensure(self):
        pass

    def seconds_left(self):
        return 1e9

    # ----------------------------------------------------------- simulate
    def simulate(self, payloads: List[dict], batch_size=None, concurrency=None, progress=print,
                 on_submitted=None) -> List[dict]:
        out = []
        for p in payloads:
            if on_submitted:
                on_submitted([p], f"sandbox://simulation/{len(self._alphas) + 1}")
            if p.get("type") == "SUPER":
                out.append(self._simulate_super(p))
                continue
            st = p["settings"]
            try:
                a = self.ev(p["regular"])
            except (EvalError, Exception) as e:  # noqa: BLE001 - surface any evaluation error like BRAIN does
                out.append({"ok": False, "alpha_id": None, "status": "ERROR", "error": str(e), "payload": p})
                continue
            tp = str(st.get("testPeriod", "P2Y"))
            years = float(tp[1:tp.index("Y")]) if "Y" in tp else 0.0
            prof = dataset_profile(p["regular"], self._dataset_of, int(st.get("delay", 1)))
            th = {"sharpe_2y": prof["cutoff"]} if prof.get("single") else None
            res = backtest(a, self.data, decay=int(st.get("decay", 0)), neutralization=st.get("neutralization", "MARKET"),
                           truncation=float(st.get("truncation", 0.08)), test_years=years, thresholds=th)
            aid = next(self._ids)
            self._results[aid] = res
            self._alphas[aid] = {
                "id": aid, "type": "REGULAR", "settings": dict(st), "regular": {"code": p["regular"]},
                "is": {**res.stats, "checks": res.checks}, "train": res.train or None, "test": res.test or None,
                "status": "UNSUBMITTED", "dateCreated": time.time(),
            }
            out.append({"ok": True, "alpha_id": aid, "status": "COMPLETE", "error": "", "payload": p})
        if progress:
            progress(f"sandbox: {sum(r['ok'] for r in out)}/{len(out)} simulated")
        return out

    # ------------------------------------------------------------- results
    def alpha(self, alpha_id: str) -> dict:
        return self._alphas[alpha_id]

    def yearly_stats(self, alpha_id: str) -> pd.DataFrame:
        return self._results[alpha_id].yearly

    def pnl(self, alpha_id: str) -> pd.Series:
        return self._results[alpha_id].pnl.cumsum()

    def daily_pnl(self, alpha_id: str) -> pd.Series:
        return self._results[alpha_id].pnl

    # Stand-in for BRAIN's production pool: textbook alphas "other consultants already submitted".
    # Copying a well-known idea shows up as high PRODUCTION correlation, exactly as on the platform.
    PROD_POOL = {
        "POOL_reversal": "-rank(ts_sum(returns, 5))",
        "POOL_cash_yield": "group_rank(ts_backfill(fnd_cfo, 252) / cap, subindustry)",
        "POOL_pead": "group_rank(ts_backfill(ern_eps_surprise, 63), subindustry)",
    }

    def _prod_pool(self) -> Dict[str, pd.Series]:
        if not hasattr(self, "_pool"):
            self._pool = {}
            for name, expr in self.PROD_POOL.items():
                try:
                    self._pool[name] = backtest(self.ev(expr), self.data, decay=2).pnl
                except Exception:  # noqa: BLE001
                    pass
        return self._pool

    def correlations(self, alpha_id: str, kind: str = "self") -> dict:
        me = self._results[alpha_id].pnl
        my_type = self._alphas[alpha_id].get("type", "REGULAR")
        rows = []
        if kind == "prod":
            for name, other in self._prod_pool().items():
                c = float(np.corrcoef(me.to_numpy(), other.to_numpy())[0, 1])
                rows.append({"id": name, "correlation": round(c, 4), "sharpe": None})
            df = pd.DataFrame(rows, columns=["id", "correlation", "sharpe"])
            return {"max": float(df["correlation"].max()) if not df.empty else 0.0, "min": None, "table": df}
        for other in self._submitted:
            # 1.10.0: a SuperAlpha is compared with your other SuperAlphas, an alpha with your alphas
            if other == alpha_id or self._alphas[other].get("type", "REGULAR") != my_type:
                continue
            c = float(np.corrcoef(me.to_numpy(), self._results[other].pnl.to_numpy())[0, 1])
            rows.append({"id": other, "correlation": round(c, 4), "sharpe": self._results[other].stats["sharpe"]})
        df = pd.DataFrame(rows, columns=["id", "correlation", "sharpe"])
        return {"max": float(df["correlation"].max()) if not df.empty else 0.0, "min": None, "table": df}

    def checks(self, alpha_id: str) -> pd.DataFrame:
        base = list(self._alphas[alpha_id]["is"]["checks"])
        sc = self.correlations(alpha_id)["max"] or 0.0
        base.append({"name": "SELF_CORRELATION", "limit": 0.7, "value": round(sc, 4),
                     "result": "PASS" if sc < 0.7 else "FAIL"})
        pc = self.correlations(alpha_id, "prod")["max"] or 0.0
        base.append({"name": "PROD_CORRELATION", "limit": 0.7, "value": round(pc, 4),
                     "result": "PASS" if pc < 0.7 else "FAIL"})
        return pd.DataFrame(base)

    def set_properties(self, alpha_id: str, **kw) -> int:
        self._alphas[alpha_id].update({k: v for k, v in kw.items() if v is not None})
        return 200

    def submit(self, alpha_id: str, confirm: str = "") -> dict:
        if confirm != f"SUBMIT {alpha_id}":
            raise RuntimeError(f'Refusing to submit. Re-run with confirm="SUBMIT {alpha_id}"')
        self._submitted.append(alpha_id)
        self._alphas[alpha_id]["status"] = "ACTIVE"
        return {"status_code": 200, "body": "sandbox submission recorded"}

    # ------------------------------------------------------------- account
    def my_alphas(self, status=None, region=None, max_items=2000):
        return [a for a in self._alphas.values() if status is None or a["status"] == status]

    def _categories(self, code: str) -> List[str]:
        import re
        names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", code))
        cats = {PREFIX_CATEGORY[n.split("_")[0]] for n in names if n.split("_")[0] in PREFIX_CATEGORY}
        if names & PV:
            cats.add("pv")
        return sorted(cats)

    def diversity(self) -> pd.DataFrame:
        rows = []
        for aid in self._submitted:
            a = self._alphas[aid]
            if a.get("type", "REGULAR") != "REGULAR" or not isinstance(a.get("regular"), dict):
                continue          # 1.10.1: a SuperAlpha is not in a Pyramid (and has no "regular" code)
            for c in self._categories(a["regular"]["code"]):
                rows.append({"region": "SBX", "delay": 1, "category": c, "alphas": 1})
        df = pd.DataFrame(rows, columns=["region", "delay", "category", "alphas"])
        return df.groupby(["region", "delay", "category"], as_index=False)["alphas"].sum() if not df.empty else df

    def pyramid_multipliers(self) -> pd.DataFrame:
        return pd.DataFrame()

    def simulation_options(self) -> pd.DataFrame:
        return pd.DataFrame([{"region": "SBX", "delays": [1], "universes": ["SANDBOX"],
                              "neutralizations": ["NONE", "MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY"]}])

    def platform_link(self, alpha_id: str) -> str:
        return f"(sandbox alpha {alpha_id})"

    # --------------------------------------------------------------- SuperAlphas (phase 8, 1.10.0)
    def seed_practice_pool(self, payloads: List[dict], n: int = 24, seed: int = 11, min_sharpe: float = 0.3) -> int:
        """Submit up to `n` practice alphas (regular payloads, e.g. rung 1 of the built-in cards) that show some
        signal, so the SuperAlpha builder has a pool. Returns how many were added."""
        rng = np.random.default_rng(seed)
        order = list(rng.permutation(len(payloads)))
        have = {self._alphas[a]["regular"]["code"] for a in self._submitted if self._alphas[a].get("type") == "REGULAR"}
        added = 0
        for i in order:
            if added >= n:
                break
            p = payloads[int(i)]
            if p.get("regular") in have:
                continue
            r = self.simulate([p], progress=None)[0]
            if not r["ok"] or self._results[r["alpha_id"]].stats["sharpe"] < min_sharpe:
                continue
            self._submitted.append(r["alpha_id"])
            self._alphas[r["alpha_id"]].update(status="ACTIVE", dateSubmitted=time.time())
            have.add(p.get("regular"))
            added += 1
        self._pool_cache = None
        return added

    def super_pool_props(self) -> List[dict]:
        """What a selection expression reads about each submitted (regular) sandbox alpha."""
        import re
        subs = [a for a in self._submitted if self._alphas[a].get("type", "REGULAR") == "REGULAR"]
        key = tuple(subs)
        if getattr(self, "_pool_cache", None) and self._pool_cache[0] == key:
            return [dict(r) for r in self._pool_cache[1]]
        prod = self._prod_pool()
        out = []
        for aid in subs:
            res, a = self._results[aid], self._alphas[aid]
            me = res.pnl.to_numpy()
            selfc = max([float(np.corrcoef(me, self._results[o].pnl.to_numpy())[0, 1]) for o in subs if o != aid],
                        default=0.0)
            prodc = max([float(np.corrcoef(me, v.to_numpy())[0, 1]) for v in prod.values()], default=0.0)
            code = a["regular"]["code"]
            cats = self._categories(code)
            out.append({"alpha_id": aid, "region": "SBX", "delay": int(a["settings"].get("delay", 1)),
                        "universe": a["settings"].get("universe", "SANDBOX"), "turnover": res.stats["turnover"],
                        "sharpe": res.stats["sharpe"], "fitness": res.stats["fitness"],
                        "decay": int(a["settings"].get("decay", 0)),
                        "operator_count": len(re.findall(r"[A-Za-z_][A-Za-z0-9_]*\s*\(", code)),
                        "datacategories": cats, "datacategory_count": len(cats),
                        "neutralization": a["settings"].get("neutralization"),
                        "self_correlation": round(selfc, 4), "prod_correlation": round(prodc, 4),
                        "long_count": res.stats.get("longCount", 0), "short_count": res.stats.get("shortCount", 0),
                        "_universe_size": float(self.data.fields["close"].shape[1])})
        self._pool_cache = (key, out)
        return [dict(r) for r in out]

    def _simulate_super(self, p: dict) -> dict:
        """A SuperAlpha the way BRAIN builds one, approximately: the selection ranks the submitted alphas, the
        combo weights them day by day (HYPOLAB's recipes are recognised; anything else is weighted equally)."""
        from .sandbox.backtest import BOOK, Result
        from .superalpha import MIN_SELECTION, SelectionError, TURNOVER_BAND, apply_selection, match_recipe

        def fail(msg):
            return {"ok": False, "alpha_id": None, "status": "ERROR", "error": msg, "payload": p}
        st = p["settings"]
        pool = [dict(r, own=True, color="NONE") for r in self.super_pool_props()]
        if len(pool) < MIN_SELECTION:
            return fail(f"a SuperAlpha selects from your submitted alphas: the sandbox has {len(pool)} (at least "
                        f"{MIN_SELECTION} needed). Press 'Build a practice pool'.")
        try:
            sel = apply_selection(p.get("selection", ""), pool, int(st.get("selectionLimit", 30)),
                                  st.get("selectionHandling", "POSITIVE"))
        except SelectionError as e:
            return fail(str(e))
        errs = [e for e in sel["error"] if e]
        kept = list(sel.loc[sel["kept"], "alpha_id"])
        if errs and not kept:
            return fail(f"selection: {errs[0]}")
        if not kept:
            return fail("the selection keeps no alpha (every score is outside the selection handling)")
        pnls = pd.DataFrame({a: self._results[a].pnl for a in kept}).fillna(0.0)
        rec = match_recipe("combo", p.get("combo", ""), int(st.get("selectionLimit", 30)))
        k = rec.key if rec else "equal"
        if k == "inv_vol":
            w = 1.0 / (pnls.rolling(120, min_periods=20).std() / BOOK + 1e-4)
        elif k in ("rolling_ir", "combo_a"):
            w = (pnls.rolling(250, min_periods=60).mean() / pnls.rolling(250, min_periods=60).std()).clip(lower=0)
        elif k == "least_crowded":
            c = pnls.corr().to_numpy().copy()
            np.fill_diagonal(c, np.nan)
            w = pd.DataFrame(np.tile(np.maximum(1 - np.nan_to_num(np.nanmax(c, axis=1), nan=0.0), 0.05),
                                     (len(pnls), 1)), index=pnls.index, columns=pnls.columns)
        else:
            w = pd.DataFrame(1.0, index=pnls.index, columns=pnls.columns)
        w = w.shift(1).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        dec = int(st.get("decay", 0) or 0)
        if dec > 1:
            w = w.rolling(dec, min_periods=1).mean()
        gross = w.abs().sum(axis=1)
        pnl = ((w * pnls).sum(axis=1) / gross.where(gross > 0)).fillna(0.0)
        tv = np.array([self._results[a].stats["turnover"] for a in kept])
        share = w.abs().mean().to_numpy()
        turnover = float(np.average(tv, weights=share)) if share.sum() > 0 else float(tv.mean())
        turnover = round(turnover * (1.0 / np.sqrt(max(dec, 1)) if dec > 1 else 1.0), 4)

        def stats_of(x: pd.Series) -> dict:
            x = x.to_numpy()
            if x.size < 5 or np.std(x) == 0:
                return {"sharpe": 0.0, "fitness": 0.0, "turnover": turnover, "returns": 0.0, "drawdown": 0.0}
            sh = float(np.mean(x) / np.std(x) * np.sqrt(252))
            ret = float(np.mean(x) * 252 / (BOOK / 2))
            cum = np.cumsum(x)
            return {"sharpe": round(sh, 2), "fitness": round(sh * np.sqrt(abs(ret) / max(turnover, 0.125)), 2),
                    "turnover": turnover, "returns": round(ret, 4),
                    "drawdown": round(float(np.max(np.maximum.accumulate(cum) - cum) / (BOOK / 2)), 4)}
        stats = stats_of(pnl)
        stats.update(longCount=int(np.mean([self._results[a].stats.get("longCount", 0) for a in kept])),
                     shortCount=int(np.mean([self._results[a].stats.get("shortCount", 0) for a in kept])))
        tp = str(st.get("testPeriod", "P2Y"))
        n_test = int(252 * (float(tp[1:tp.index("Y")]) if "Y" in tp else 0.0))
        train = stats_of(pnl.iloc[:-n_test]) if n_test and len(pnl) > n_test + 100 else {}
        test = stats_of(pnl.iloc[-n_test:]) if n_test and len(pnl) > n_test + 100 else {}
        yearly = pd.DataFrame([{"year": y, **stats_of(g)} for y, g in pnl.groupby(pnl.index.year)])
        lo, hi = TURNOVER_BAND
        checks = [
            {"name": "LOW_SHARPE", "limit": 1.58, "value": stats["sharpe"],
             "result": "PASS" if stats["sharpe"] >= 1.58 else "FAIL"},
            {"name": "LOW_FITNESS", "limit": 1.0, "value": stats["fitness"],
             "result": "PASS" if stats["fitness"] >= 1.0 else "FAIL"},
            {"name": "LOW_TURNOVER", "limit": lo, "value": turnover, "result": "PASS" if turnover >= lo else "FAIL"},
            {"name": "HIGH_TURNOVER", "limit": hi, "value": turnover, "result": "PASS" if turnover <= hi else "FAIL"},
        ]
        aid = next(self._ids)
        self._results[aid] = Result(stats, train, test, yearly, pnl, None, checks)
        self._alphas[aid] = {
            "id": aid, "type": "SUPER", "settings": dict(st), "combo": {"code": p.get("combo", "")},
            "selection": {"code": p.get("selection", "")}, "is": {**stats, "checks": checks},
            "train": train or None, "test": test or None, "status": "UNSUBMITTED", "dateCreated": time.time(),
            "sandbox_note": f"{len(kept)} alphas kept; weighting {'recognised: ' + rec.name if rec else 'approximated as equal weight'}"}
        return {"ok": True, "alpha_id": aid, "status": "COMPLETE", "error": "", "payload": p}

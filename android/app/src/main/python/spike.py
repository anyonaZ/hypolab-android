"""Phase A feasibility spike: import the engine, build the practice market, run one sandbox
simulation, robustness and a gate, and report time + memory for each step."""
import os
import sys
import tempfile
import time
import traceback


def _rss_mb():
    try:
        vals = {}
        with open("/proc/self/status") as fh:
            for line in fh:
                k, _, v = line.partition(":")
                if k in ("VmRSS", "VmHWM"):
                    vals[k] = int(v.split()[0]) / 1024
        return vals.get("VmRSS", 0.0), vals.get("VmHWM", 0.0)
    except Exception:
        return 0.0, 0.0


def run(home=None, expression="rank(-ts_delta(close, 5))", log=print):
    if hasattr(log, "accept"):          # a java.util.function.Consumer from the Android side
        log = log.accept
    if home:
        os.environ["HYPOLAB_HOME"] = home
    else:
        os.environ.setdefault("HYPOLAB_HOME", tempfile.mkdtemp(prefix="hypolab_spike_"))
    lines = []

    def step(name, fn):
        t0 = time.perf_counter()
        try:
            out = fn()
            ok = "ok"
        except Exception as e:  # report, keep going
            out, ok = None, "FAILED: " + repr(e) + "\n" + traceback.format_exc(limit=4)
        dt = time.perf_counter() - t0
        rss, hwm = _rss_mb()
        line = f"{name:<28} {dt:7.2f} s   RSS {rss:6.0f} MB   peak {hwm:6.0f} MB   {ok}"
        lines.append(line)
        log(line)
        return out

    log(f"Python {sys.version.split()[0]} on {sys.platform}; HYPOLAB_HOME={os.environ['HYPOLAB_HOME']}")
    np = step("import numpy", lambda: __import__("numpy"))
    step("import pandas", lambda: __import__("pandas"))
    step("import yaml, requests", lambda: (__import__("yaml"), __import__("requests")))
    step("import matplotlib (Agg)", lambda: (__import__("matplotlib").use("Agg"), __import__("matplotlib.pyplot")))
    step("import starlette/uvicorn", lambda: (__import__("starlette.applications"), __import__("uvicorn"),
                                              __import__("jinja2"), __import__("markdown")))
    hl = step("import hypolab engine", lambda: __import__("hypolab.research", fromlist=["Researcher"]))
    step("import ideaengine", lambda: __import__("ideaengine"))
    def _data():
        from hypolab import config
        return (config.BUNDLED_DATA / "themes.json").read_text()[:20]
    step("read bundled data file", _data)

    def _small():
        import gc
        from hypolab.sandbox.market import make_market
        d = make_market(n_stocks=250)
        del d
        gc.collect()
    step("half-size market (250)", _small)
    R = step("build sandbox market", lambda: hl.Researcher.sandbox())
    t = step("one sandbox simulation", lambda: R.test(expression=expression)) if R else None
    rb = step("robustness checks", lambda: R.robustness(t)) if t else None
    g = step("gate", lambda: R.gate(t, rb)) if t else None
    if t is not None:
        s = {k: v for k, v in t.summary.items() if not isinstance(v, (dict, list))}
        log("result: " + ", ".join(f"{k}={v}" for k, v in list(s.items())[:8]))
    if g is not None:
        log("gate: " + ("READY" if getattr(g, "ready", False) else "NOT READY") + " "
            + "; ".join(getattr(g, "reasons", [])[:3]))
    return "\n".join(lines)


if __name__ == "__main__":
    run()

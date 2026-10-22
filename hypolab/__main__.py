"""Terminal commands:  python -m hypolab <command>

  status            mode, region, credentials, session
  login             enter + verify + save your BRAIN credentials
  live [REGION]     switch every app to your BRAIN account (e.g. `live USA`)
  sandbox           switch every app back to the offline practice market
  logout            delete saved credentials and session
  options           regions / universes / delays / neutralizations your account can use
  web               start HYPOLAB (1.16.0: the main app - every page: Week, Leads, Cards, Drafts, Lab, Play,
                    Basics, Journal, Pyramids, SuperAlpha, Data, Account, Setup) at http://127.0.0.1:2719
  ideas             the same as `web` (the old name)
  cockpit           the OLD screens, kept for comparison: the web app plus the marimo apps (cockpit, dataset
                    scan, quant basics: http://127.0.0.1:2718). Do live work in one of them at a time.
  collect KIND      read outside sources into the Leads inbox: osap | arxiv | news | datasets | all | list
                    (see `python -m ideaengine.collect --help`; --file SAVED_PAGE reads a page you saved)
"""
import sys

from . import connect


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        connect.status()
    elif cmd == "login":
        connect.login()
    elif cmd == "live":
        connect.go_live(argv[1] if len(argv) > 1 else None)
    elif cmd == "sandbox":
        connect.go_sandbox()
    elif cmd == "logout":
        connect.logout()
    elif cmd in ("web", "ideas"):
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from ideaweb.app import main as ideas_main
        ideas_main(open_browser=True)
    elif cmd == "cockpit":
        import subprocess
        from pathlib import Path
        from . import config
        root = Path(__file__).resolve().parent.parent
        folder = root / "apps"
        extra = argv[1:]
        # 1.7.0: the Ideas web app runs next to marimo (it is light: ~100 MB, no BRAIN, no simulations)
        ideas = None
        if "--no-ideas" in extra:
            extra.remove("--no-ideas")
        else:
            ideas = subprocess.Popen([sys.executable, "-m", "ideaweb"], cwd=str(root))
            from ideaengine.handoff import ideas_url
            print(f"HYPOLAB web app (every page): {ideas_url()}")
            print("Old marimo screens (for comparison; live work in one of the two at a time): opening below ...")
        if not any(a.startswith("--session-ttl") for a in extra):
            # marimo closes an app 120 s after the browser loses its connection (laptop asleep, Wi-Fi blip) and the
            # tab then says "kernel not found". Keep it alive longer (settings.json: session_ttl_seconds).
            ttl = int(config.settings().get("session_ttl_seconds", 900))
            if ttl == 3600:        # the 1.4.2 default written whole into older settings files -> 1.7.0's 15 minutes
                ttl = 900
                config.save_settings(session_ttl_seconds=ttl)
            # each kept session holds ~0.8 GB; the page reloads itself and the Lab restores work after a longer gap
            extra += ["--session-ttl", str(ttl)]
        try:
            return subprocess.call([sys.executable, "-m", "marimo", "run", str(folder)] + extra)
        finally:
            if ideas is not None:
                ideas.terminate()
    elif cmd == "collect":
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from ideaengine.collect import main as collect_main
        return collect_main(argv[1:])
    elif cmd == "options":
        import pandas as pd
        pd.set_option("display.max_colwidth", 120, "display.width", 200)
        print(connect.client().simulation_options().to_string(index=False))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

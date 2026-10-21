"""HYPOLAB on Android: start the Ideas web app inside the app (1.12.0, phase B).

The Kotlin side calls ``start(files_dir)`` once per process and loads the URL it returns in a WebView.

- HYPOLAB_HOME = <app files>/hypolab (private to the app; the backup/import of phase E moves it between devices).
- The server listens on 127.0.0.1 only, on a port the system picks, with a secret made fresh for each launch:
  the first URL carries it once (``/?k=...``), the page keeps it as an HttpOnly cookie, and any other request is
  refused (ideaweb.app.LaunchKey). Other apps on the tablet can reach 127.0.0.1, so the secret is what keeps them out.
- The practice market has 250 stocks here (HYPOLAB_SANDBOX_STOCKS): the 500-stock one peaked at 878 MB on the
  4 GB tablet in the phase A spike.

This file must not import hypolab at module level: hypolab.config reads HYPOLAB_HOME when it is first imported.
"""
from __future__ import annotations

import os
import secrets
import socket
import threading
import time

_STATE: dict = {}
_LOCK = threading.Lock()


def _configure(files_dir: str, stocks: int) -> str:
    home = os.path.join(files_dir, "hypolab")
    os.makedirs(home, exist_ok=True)
    os.environ["HYPOLAB_HOME"] = home
    os.environ["HYPOLAB_PLATFORM"] = "android"
    os.environ.setdefault("HYPOLAB_SANDBOX_STOCKS", str(stocks))
    os.environ.setdefault("MPLBACKEND", "Agg")
    return home


def start(files_dir: str, stocks: int = 250, timeout: float = 60.0) -> str:
    """Start the server (once per process) and return the first URL to open. Raises if it does not come up."""
    with _LOCK:
        if _STATE.get("url") and _STATE["thread"].is_alive():
            return _STATE["url"]
        _configure(files_dir, stocks)
        secret = secrets.token_urlsafe(24)
        os.environ["HYPOLAB_LAUNCH_SECRET"] = secret

        import uvicorn
        from ideaweb.app import app

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        cfg = uvicorn.Config(app, log_level="warning", loop="asyncio", http="h11", ws="none", lifespan="off",
                             access_log=False)
        server = uvicorn.Server(cfg)
        th = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, name="hypolab-web", daemon=True)
        th.start()
        t0 = time.time()
        while not server.started:
            if not th.is_alive():
                raise RuntimeError("The HYPOLAB web server stopped while starting.")
            if time.time() - t0 > timeout:
                raise RuntimeError(f"The HYPOLAB web server did not start within {timeout:.0f} s.")
            time.sleep(0.05)
        url = f"http://127.0.0.1:{port}/?k={secret}"
        _STATE.update(url=url, port=port, server=server, thread=th, home=os.environ["HYPOLAB_HOME"])
        return url


def origin() -> str:
    """http://127.0.0.1:<port> of the running server ("" before start)."""
    return f"http://127.0.0.1:{_STATE['port']}" if _STATE.get("port") else ""


def stop() -> None:
    srv = _STATE.get("server")
    if srv is not None:
        srv.should_exit = True
        _STATE["thread"].join(timeout=5)
    _STATE.clear()

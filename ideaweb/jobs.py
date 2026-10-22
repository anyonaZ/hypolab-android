"""One background job at a time for the Lab pages (1.13.0).

A simulation on BRAIN can wait for minutes; a tablet's page must not hang on one request that long. So every button
that spends simulations (or reads BRAIN) starts a job here and returns at once; the page shows "working on ..." and
reloads itself every few seconds until the job ends, then shows its message once.

Rules kept from the cockpit:
- a job starts only from a button (a POST); nothing is started or repeated by itself;
- one job at a time: a second button press while one runs is refused, never queued;
- a job that fails is reported, not retried (1.10.2: an answer lost on the network is never re-sent).
"""
from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Job:
    title: str
    page: str                                 # where to come back to (e.g. /lab)
    started: float = field(default_factory=time.time)
    ended: Optional[float] = None
    message: str = ""
    kind: str = "ok"                          # ok | warn | err
    seen: bool = False

    @property
    def running(self) -> bool:
        return self.ended is None

    def seconds(self) -> int:
        return int((self.ended or time.time()) - self.started)


def explain(title: str, e: Exception) -> tuple:
    """1.17.0: a failed job in plain words. (message, kind)."""
    name = type(e).__name__
    text = str(e)
    if name == "AuthError":
        return f"{title} stopped: {text}", "err"
    if name == "UncertainOutcome":
        return (f"{title}: the connection broke after BRAIN received the request. {text} If it was a simulation, "
                "Lab > Fetch them from BRAIN collects it (no new simulation).", "err")
    if name == "BrainError" and "stopped waiting" in text.lower():
        return text, "warn"
    if name in ("ConnectionError", "ConnectTimeout", "ReadTimeout", "Timeout") or "Max retries exceeded" in text:
        return (f"{title} failed: no connection to BRAIN ({name}). Nothing was sent again. Check the Wi-Fi; if a "
                "simulation was already accepted, Lab > Fetch them from BRAIN collects it.", "err")
    return f"{title} failed: {name}: {text}", "err"


class Jobs:
    def __init__(self):
        self._lock = threading.Lock()
        self.current: Optional[Job] = None

    def busy(self) -> Optional[Job]:
        c = self.current
        return c if c is not None and c.running else None

    def start(self, title: str, page: str, fn: Callable[[], Optional[str]]) -> bool:
        """Run fn() in a thread. fn returns a message for the page (or None). False if another job is running."""
        with self._lock:
            if self.busy():
                return False
            job = Job(title=title, page=page)
            self.current = job
            from hypolab import brain
            brain.CANCEL.clear()            # a new job starts with "Stop waiting" released

        def run():
            try:
                out = fn()
                if isinstance(out, tuple):
                    job.message, job.kind = out
                else:
                    job.message = out or f"Done: {title}."
            except Exception as e:  # noqa: BLE001  - reported on the page, never retried
                job.message, job.kind = explain(title, e)
                job.trace = traceback.format_exc(limit=6)
            finally:
                job.ended = time.time()

        threading.Thread(target=run, name=f"hypolab-job", daemon=True).start()
        return True

    def stop_waiting(self) -> bool:
        """1.17.0: stop waiting for BRAIN (polling only). Nothing is cancelled on BRAIN and nothing is re-sent; what
        BRAIN accepted stays pending in the journal and Lab > Fetch them from BRAIN collects it later."""
        if not self.busy():
            return False
        from hypolab import brain
        brain.CANCEL.set()
        return True

    def take_message(self, page: str) -> Optional[Job]:
        """The finished job's message, shown once on the page it belongs to."""
        c = self.current
        if c is not None and not c.running and not c.seen and c.page == page:
            c.seen = True
            return c
        return None

    def wait(self, timeout: float = 120.0) -> None:
        """For tests: block until the current job ends."""
        t0 = time.time()
        while self.busy() and time.time() - t0 < timeout:
            time.sleep(0.05)


JOBS = Jobs()

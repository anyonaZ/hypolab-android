"""The hand-off between the Ideas web app and the marimo Lab (1.7.0).

The Ideas app (ideaweb/) never simulates and never talks to BRAIN. "Send to the Lab" writes the card id here; the
cockpit's Lab picks it up at start and on its "Pick up the card sent from Ideas" button. One small JSON file:
~/.hypolab/lab_inbox.json = {"card": id, "region": region, "at": unix time}.
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

from hypolab import config

DEFAULT_PORT = 2719


def inbox_path():
    return config.HOME / "lab_inbox.json"


def send_to_lab(card_id: str, region: Optional[str] = None) -> dict:
    config.ensure_home()
    msg = {"card": str(card_id), "region": region, "at": time.time()}
    tmp = inbox_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(msg))
    os.replace(tmp, inbox_path())
    return msg


def peek() -> Optional[dict]:
    try:
        return json.loads(inbox_path().read_text())
    except (OSError, ValueError):
        return None


def take_new() -> Optional[dict]:
    """The inbox message if the Lab has not picked it up yet (remembered in settings.json: lab_inbox_seen)."""
    m = peek()
    if not m or float(m.get("at", 0)) <= float(config.settings().get("lab_inbox_seen", 0) or 0):
        return None
    config.save_settings(lab_inbox_seen=float(m["at"]))
    return m


def ideas_port() -> int:
    return int(config.settings().get("ideas_port", DEFAULT_PORT))


def ideas_url() -> str:
    return f"http://127.0.0.1:{ideas_port()}"

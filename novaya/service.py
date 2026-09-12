"""What the server tells the client about staying current.

Every response carries a `service` envelope:

    catalog_version   changes when the tool surface changes
    client_latest     the client the server recommends
    client_min        the oldest client it still serves

The client compares, refreshes when it differs, and says one line when an
upgrade exists. No polling, no PyPI, no extra request in the steady state --
the signal rides on a call the user was already making.

Absent on an older server, and everything here degrades to a no-op.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import __version__, credentials

DAY = 86400


def _path() -> Path:
    return credentials._home_dir() / "notice.json"


def _read() -> dict:
    try:
        doc = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _write(doc: dict) -> None:
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    except OSError:
        pass


def _parts(version: str):
    out = []
    for chunk in str(version).split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out or (0,))


def newer(candidate: str, current: str = "") -> bool:
    """Is `candidate` a later release than the running client?"""
    if not candidate:
        return False
    return _parts(candidate) > _parts(current or __version__)


def upgrade_line(envelope: dict | None) -> str:
    """The notice to show, or "" -- rate-limited to once a day.

    Once a day, not every call: an upgrade notice attached to every answer
    stops being read after the second one, and this text rides inside a coding
    agent's tool output where it competes with the answer itself.
    """
    envelope = envelope or {}
    latest = str(envelope.get("client_latest") or "")
    required = str(envelope.get("client_min") or "")

    if newer(required):
        # Not rate-limited: the client is below the floor the server serves.
        return ("Novaya novgraph " + required + " is REQUIRED (running "
                + __version__ + ") — run `novgraph upgrade`")
    if not newer(latest):
        return ""

    state = _read()
    if state.get("told_about") == latest and time.time() - state.get("at", 0) < DAY:
        return ""
    _write({"told_about": latest, "at": time.time()})
    return ("Novaya novgraph " + latest + " is available — run `novgraph upgrade`")

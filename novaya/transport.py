"""The only place this package touches the network.

Every call -- shell verb, MCP, install, doctor -- goes through `request()`, so
a retry rule fixed here is fixed for all of them.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from . import __version__

DEFAULT_BASE = "https://api.trynovaya.com"
TIMEOUT = 30.0

# Retries are for the network, never for an answer. 401 never retries.
_RETRY_STATUS = (429, 500, 502, 503, 504)
_MAX_RETRIES = 2

# The `service` block from the most recent response. Set here because EVERY
# call passes through request(), so nothing has to remember to collect it.
last_service: dict = {}


def base_url() -> str:
    """The API root. Overridable so a test or a staging deploy needs no edit."""
    return (os.environ.get("NOVGRAPH_API_BASE") or DEFAULT_BASE).rstrip("/")


class ApiError(Exception):
    """An HTTP failure carrying the server's own message -- a 401 from this
    API explains its own fix, and "HTTP 401" throws that away."""

    def __init__(self, status: int, message: str, body: str = ""):
        super().__init__(f"HTTP {status}: {message}" if status else message)
        self.status = status
        self.message = message
        self.body = body

    @property
    def is_auth(self) -> bool:
        return self.status in (401, 403)


# The agent session these calls belong to. `novgraph mcp` sets it once per
# process -- one agent session -- with the name the agent gave at initialize.
# It is what gives an agent per-session dedup and per-session savings; a call
# without it still works, it just belongs to no session.
SESSION = {"id": "", "agent": ""}


def _headers(key: str) -> dict:
    h = {
        "Authorization": "Bearer " + key,
        "Accept": "application/json",
        "User-Agent": "novgraph/" + __version__,
    }
    if SESSION["id"]:
        h["X-Novayagraph-Session"] = SESSION["id"]
        if SESSION["agent"]:
            h["X-Novayagraph-Agent"] = SESSION["agent"]
    return h


def _explain(status: int, raw: bytes) -> ApiError:
    text = raw.decode("utf-8", "replace")
    message = ""
    try:
        doc = json.loads(text)
        if isinstance(doc, dict):
            message = str(doc.get("message") or doc.get("error") or "")
    except Exception:
        message = ""      # a 5xx body may be a proxy's HTML; do not paste it
    if not message:
        message = text.strip()[:200] or "no response body"
    return ApiError(status, message, text)


def request(key: str, method: str, path: str, payload: dict | None = None,
            timeout: float = TIMEOUT) -> dict:
    """One HTTP call, with the retry rule this client uses everywhere."""
    if not key:
        raise ApiError(0, "no API key available -- run `novgraph install <KEY>`")
    url = base_url() + path
    data = None
    headers = _headers(key)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            text = raw.decode("utf-8", "replace")
            if not text.strip():
                return {}
            try:
                doc = json.loads(text)
            except json.JSONDecodeError:
                raise ApiError(0, "the API returned a non-JSON body", text)
            if not isinstance(doc, dict):
                return {"result": doc}
            if isinstance(doc.get("service"), dict):
                last_service.clear()
                last_service.update(doc["service"])
            return doc
        except urllib.error.HTTPError as exc:
            err = _explain(exc.code, exc.read() or b"")
            if exc.code not in _RETRY_STATUS:
                raise err
            last = err
        except urllib.error.URLError as exc:
            last = ApiError(0, f"cannot reach {base_url()}: {exc.reason}")
        except TimeoutError:
            last = ApiError(0, f"timed out after {timeout:.0f}s reaching {base_url()}")
        if attempt < _MAX_RETRIES:
            time.sleep(0.4 * (2 ** attempt))
    raise last if last else ApiError(0, "request failed")


def catalog(key: str) -> dict:
    """GET /v1/tools. The server's own description of its surface -- every
    generated document is written from this, never from a copy."""
    return request(key, "GET", "/v1/tools")


def call(key: str, tool: str, args: dict | None = None) -> dict:
    """POST /v1/tools/<tool>. Bare and prefixed names both work server-side."""
    return request(key, "POST", "/v1/tools/" + tool, args or {})


def tool_names(cat: dict) -> list[str]:
    """The names in a catalog, tolerant of both shapes the API may send."""
    out = []
    for entry in cat.get("tools") or []:
        if isinstance(entry, dict):
            fn = entry.get("function") if isinstance(entry.get("function"), dict) else entry
            name = fn.get("name")
            if name:
                out.append(str(name))
    return out

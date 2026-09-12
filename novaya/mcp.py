"""`novgraph mcp` -- MCP over the same transport as the shell verbs.

Newline-delimited JSON-RPC: initialize, tools/list, tools/call. Two front
doors, one client, so they cannot drift.

Advertises tools even with no key or no network: an agent shown zero tools
decides the integration is broken. Supplies `codebase` from the binding made
at install; an explicit argument still wins. Only JSON-RPC goes to stdout.
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

from . import (__version__, adapters, catalog, credentials, service, sync,
               transport, workspace)

PROTOCOL_VERSION = "2024-11-05"

# Captured before anything can chdir: the launch directory is the only signal.
LAUNCH_CWD = Path.cwd()

# THE OFFLINE FALLBACK, not the source. Method is served -- the same
# `guidance` field that becomes .novgraph/rules.md is what goes into an MCP
# client's system prompt, so improving it reaches a months-old install with no
# upgrade. A hardcoded copy here was a third declaration of method, frozen at
# install, and exactly what LAW 22 exists to prevent.
FALLBACK_INSTRUCTIONS = (
    "Novayagraph holds this repository's architecture, the recorded reasoning "
    "behind its commits, historical change-coupling between files, and computed "
    "blast radius. Query it before substantive edits rather than reconstructing "
    "the same facts by reading files: novgraph_summary to orient, novgraph_why "
    "and novgraph_connections before changing a file, novgraph_impact for blast "
    "radius, novgraph_recent when chasing a regression. It describes the indexed "
    "commit -- read the working tree for current file contents. After a "
    "meaningful commit, novgraph_record_why so the memory compounds."
)

def _schemas(doc: dict):
    """Catalog -> MCP tool descriptors."""
    return [{"name": t.name,
             "description": t.description,
             "inputSchema": {"type": "object",
                             "properties": t.properties,
                             "required": list(t.required)}}
            for t in catalog.normalise(doc)]


class Server:
    def __init__(self):
        self._schemas = None
        self._codebase = workspace.codebase_for(LAUNCH_CWD)
        # One process, one agent session.
        transport.SESSION["id"] = uuid.uuid4().hex

    # -- wire ----------------------------------------------------------------

    def _send(self, mid, result):
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid,
                                     "result": result}) + "\n")
        sys.stdout.flush()

    def _fail(self, mid, code, message):
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid,
                                     "error": {"code": code,
                                               "message": message}}) + "\n")
        sys.stdout.flush()

    @staticmethod
    def _note(text):
        sys.stderr.write("novgraph-mcp: " + text + "\n")
        sys.stderr.flush()

    # -- surface -------------------------------------------------------------

    def instructions(self) -> str:
        """Method, preferred from the server -- see LAW 22."""
        served = str((catalog.cached().get("guidance") or "")).strip()
        return served or FALLBACK_INSTRUCTIONS

    def schemas(self):
        """Live if reachable, cached otherwise. LAW 18: never an empty list."""
        if self._schemas is not None:
            return self._schemas
        key = credentials.load()
        if key:
            try:
                self._schemas = _schemas(catalog.refresh(key))
                return self._schemas
            except transport.ApiError as exc:
                self._note("catalog unavailable (" + exc.message + "); using cache")
        cached = _schemas(catalog.cached())
        if not cached:
            self._note("no tool catalog. Run: novgraph install <KEY>")
        # Not cached in memory: a client started a second before `install`
        # would otherwise serve the empty list for its whole life.
        return cached

    def call(self, name: str, args: dict):
        key = credentials.load()
        if not key:
            return ("No Novayagraph API key on this machine. Run `novgraph install "
                    "<KEY>` with a key from https://app.trynovaya.com."), True
        args = dict(args or {})
        if not args.get("codebase") and self._codebase:
            args["codebase"] = self._codebase
        try:
            result = transport.call(key, name, args)
        except transport.ApiError as exc:
            if exc.is_auth:
                return ("Novayagraph rejected this machine's key: " + exc.message
                        + " Re-run `novgraph install <KEY>`; retrying will not "
                          "help."), True
            return "Novayagraph call failed: " + exc.message, True
        if catalog.sync_if_stale(key):
            sync.resync()
        text = result.get("text")
        if not (isinstance(text, str) and text.strip()):
            text = json.dumps(result, indent=2)
        # Inside the agent's own interface, appended to an answer it already
        # asked for. Once a day -- a notice on every tool result stops being
        # read after the second one and competes with the answer.
        notice = service.upgrade_line(transport.last_service)
        return (text + "\n\n" + notice) if notice else text, False

    # -- dispatch ------------------------------------------------------------

    def handle(self, message: dict):
        mid = message.get("id")
        method = message.get("method") or ""
        params = message.get("params") or {}

        if method == "initialize":
            client = str(((params.get("clientInfo") or {}).get("name")) or "")
            transport.SESSION["agent"] = re.sub(r"[^A-Za-z0-9._ -]", "", client)[:40]
            self._send(mid, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": adapters.SERVER_NAME, "version": __version__},
                "instructions": self.instructions(),
            })
            return
        if method.startswith("notifications/"):
            return                                  # notifications take no reply
        if method == "tools/list":
            self._send(mid, {"tools": self.schemas()})
            return
        if method == "tools/call":
            name = params.get("name") or ""
            args = params.get("arguments") or {}
            if not name:
                self._fail(mid, -32602, "no tool name")
                return
            text, failed = self.call(name, args)
            # isError, not a JSON-RPC error: clients swallow those, and the
            # agent needs to see the message.
            self._send(mid, {"content": [{"type": "text", "text": text}],
                             "isError": failed})
            return
        if method in ("ping", "shutdown"):
            self._send(mid, {})
            return
        if mid is not None:
            self._fail(mid, -32601, "unknown method: " + method)


def serve() -> int:
    # The protocol is UTF-8; the Windows console default (cp1252) raises on
    # the first em-dash in an answer.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    server = Server()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            Server._note("ignored a non-JSON line")
            continue
        if not isinstance(message, dict):
            continue
        try:
            server.handle(message)
        except Exception as exc:                    # never take the server down
            Server._note(type(exc).__name__ + ": " + str(exc))
            if message.get("id") is not None:
                server._fail(message.get("id"), -32603, str(exc))
    return 0

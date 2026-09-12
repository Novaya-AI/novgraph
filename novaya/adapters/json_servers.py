"""Clients that keep MCP servers as a JSON object of named entries.

Cursor, Windsurf, Gemini CLI and Cline call it `mcpServers`; VS Code calls it
`servers`. Same rules as every adapter: read-modify-write, never touch an
entry that is not ours, and leave a file we cannot parse exactly as it was.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import base


def editor_user_dir(product: str) -> Path:
    """Where a VS Code-family editor keeps its per-user settings."""
    if sys.platform.startswith("win"):
        root = Path(os.environ.get("APPDATA") or (base.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        root = base.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME") or (base.home() / ".config"))
    return root / product / "User"


class JsonServers(base.Adapter):
    container = "mcpServers"

    def config_paths(self) -> list:
        """Every file this client reads servers from, that exists or should."""
        raise NotImplementedError

    def entry(self) -> dict:
        argv = base.mcp_command()
        return {"command": argv[0], "args": argv[1:]}

    def label(self, path: Path) -> str:
        try:
            return "~/" + path.relative_to(base.home()).as_posix()
        except ValueError:
            return str(path)

    def register_mcp(self, result: base.Result):
        paths = self.config_paths()
        if not paths:
            result.warn("found no " + self.name + " configuration to register in")
        for path in paths:
            self._register(path, result)

    def _register(self, path: Path, result: base.Result):
        doc, err = base.read_json(path)
        if doc is None:
            result.warn(err + " -- left untouched; shell verbs still work")
            return
        servers = doc.get(self.container)
        if not isinstance(servers, dict):
            if servers is not None:
                result.warn("`" + self.container + "` in " + self.label(path)
                            + " is not an object -- left untouched")
                return
            servers = {}
        entry = self.entry()
        base.drop_legacy(servers)
        if servers.get(base.SERVER_NAME) == entry:
            result.act("MCP server already registered in " + self.label(path))
            return
        servers[base.SERVER_NAME] = entry
        doc[self.container] = servers
        base.write_json(path, doc)
        result.act("registered MCP server '" + base.SERVER_NAME + "' in "
                   + self.label(path))

    def unregister_mcp(self, result: base.Result):
        for path in self.config_paths():
            doc, _err = base.read_json(path)
            if doc is None or not isinstance(doc.get(self.container), dict):
                continue
            if doc[self.container].pop(base.SERVER_NAME, None) is not None:
                base.write_json(path, doc)
                result.act("removed MCP server from " + self.label(path))

    def recorded_command(self):
        for path in self.config_paths():
            doc, _err = base.read_json(path)
            servers = (doc or {}).get(self.container)
            entry = servers.get(base.SERVER_NAME) if isinstance(servers, dict) else None
            if isinstance(entry, dict) and entry.get("command"):
                return [entry["command"]] + list(entry.get("args") or [])
        return None

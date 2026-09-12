"""OpenCode: JSON at ~/.config/opencode/opencode.json, under `mcp`.

Its own shape -- one argv array and an enabled flag -- which is why adapters
are written per client rather than generated from a table. XDG path on every
platform including Windows; %APPDATA% would write a file it never reads.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import base


class OpenCode(base.Adapter):
    slug = "opencode"
    name = "OpenCode"
    instruction_file = "AGENTS.md"
    docs_url = "https://opencode.ai/docs/mcp-servers/"
    command_file = ".opencode/commands/{name}.md"
    command_fields = ("description",)

    def config_dir(self) -> Path:
        root = os.environ.get("XDG_CONFIG_HOME") or str(base.home() / ".config")
        return Path(root) / "opencode"

    def config_path(self) -> Path:
        return self.config_dir() / "opencode.json"

    def detect(self) -> bool:
        return self.config_dir().is_dir() or base.on_path("opencode")

    def register_mcp(self, result: base.Result):
        path = self.config_path()
        doc, err = base.read_json(path)
        if doc is None:
            result.warn(err + " -- left untouched; shell verbs still work")
            return
        servers = doc.get("mcp")
        if not isinstance(servers, dict):
            if servers is not None:
                result.warn("`mcp` in opencode.json is not an object -- "
                            "left untouched")
                return
            servers = {}
        entry = {"type": "local", "command": base.mcp_command(), "enabled": True}
        base.drop_legacy(servers)
        if servers.get(base.SERVER_NAME) == entry:
            result.act("MCP server already registered in opencode.json")
            return
        servers[base.SERVER_NAME] = entry
        doc["mcp"] = servers
        # Only on a file we are creating: adding a schema line to a config the
        # user already has is an opinion about their file, not part of ours.
        doc.setdefault("$schema", "https://opencode.ai/config.json")
        base.write_json(path, doc)
        result.act("registered MCP server '" + base.SERVER_NAME
                   + "' in opencode.json")

    def unregister_mcp(self, result: base.Result):
        path = self.config_path()
        doc, err = base.read_json(path)
        if doc is None or not isinstance(doc.get("mcp"), dict):
            return
        if doc["mcp"].pop(base.SERVER_NAME, None) is not None:
            base.write_json(path, doc)
            result.act("removed MCP server from opencode.json")

    def recorded_command(self):
        doc, _err = base.read_json(self.config_path())
        if doc is None:
            return None
        entry = (doc.get("mcp") or {}).get(base.SERVER_NAME)
        if not isinstance(entry, dict) or not entry.get("command"):
            return None
        return list(entry["command"])

    def verify_mcp(self) -> str:
        doc, _err = base.read_json(self.config_path())
        entry = (doc or {}).get("mcp", {}).get(base.SERVER_NAME)
        if isinstance(entry, dict) and entry.get("enabled") is False:
            return "registered in opencode.json but disabled"
        return super().verify_mcp()

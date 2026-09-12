"""Claude Code.

MCP servers go in `~/.claude.json`, not settings.json -- that file ignores an
mcpServers key silently. The same file holds every project and server the user
has, so it is read-modify-write or it is data loss.
"""
from __future__ import annotations

from pathlib import Path

from . import base


class ClaudeCode(base.Adapter):
    slug = "claude-code"
    name = "Claude Code"
    instruction_file = "CLAUDE.md"
    docs_url = "https://code.claude.com/docs/en/mcp"
    command_file = ".claude/skills/{name}/SKILL.md"
    command_fields = ("name", "description", "argument-hint",
                      "disable-model-invocation")

    def config_path(self) -> Path:
        return base.home() / ".claude.json"

    def detect(self) -> bool:
        return (self.config_path().exists()
                or (base.home() / ".claude").is_dir()
                or base.on_path("claude"))

    def register_mcp(self, result: base.Result):
        path = self.config_path()
        doc, err = base.read_json(path)
        if doc is None:
            result.warn(err + " -- left untouched; shell verbs still work")
            return
        servers = doc.get("mcpServers")
        if not isinstance(servers, dict):
            if servers is not None:
                result.warn("mcpServers in ~/.claude.json is not an object -- "
                            "left untouched")
                return
            servers = {}
        argv = base.mcp_command()
        entry = {"command": argv[0], "args": argv[1:]}
        base.drop_legacy(servers)
        if servers.get(base.SERVER_NAME) == entry:
            result.act("MCP server already registered in ~/.claude.json")
            return
        servers[base.SERVER_NAME] = entry
        doc["mcpServers"] = servers
        base.write_json(path, doc)
        result.act("registered MCP server '" + base.SERVER_NAME
                   + "' in ~/.claude.json")

    def unregister_mcp(self, result: base.Result):
        path = self.config_path()
        doc, err = base.read_json(path)
        if doc is None or not isinstance(doc.get("mcpServers"), dict):
            return
        if doc["mcpServers"].pop(base.SERVER_NAME, None) is not None:
            base.write_json(path, doc)
            result.act("removed MCP server from ~/.claude.json")

    def recorded_command(self):
        doc, _err = base.read_json(self.config_path())
        if doc is None:
            return None
        entry = (doc.get("mcpServers") or {}).get(base.SERVER_NAME)
        if not isinstance(entry, dict) or not entry.get("command"):
            return None
        return [entry["command"], *(entry.get("args") or [])]

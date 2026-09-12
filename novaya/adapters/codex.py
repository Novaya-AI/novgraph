"""Codex: TOML at $CODEX_HOME/config.toml, [mcp_servers.<name>].

Written as a comment-delimited block, not a TOML round-trip: there is no TOML
writer in the stdlib and a round-trip eats the user's comments. Parsed with
tomllib afterwards and reverted on failure -- an unparseable config.toml costs
them every other MCP server.
"""
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

from . import base


class Codex(base.Adapter):
    slug = "codex"
    name = "Codex"
    instruction_file = "AGENTS.md"
    docs_url = "https://developers.openai.com/codex/mcp"
    # Codex has skills, not custom slash commands: typed as `$novgraph review`.
    # The file is shared with Cursor, so it renders the shared way.
    command_file = base.SHARED_SKILL_FILE
    command_invoke = "${name}"
    command_body_invoke = base.SHARED_SKILL_INVOKE
    command_request = base.SHARED_SKILL_REQUEST
    command_fields = ("name", "description")

    def codex_home(self) -> Path:
        return Path(os.environ.get("CODEX_HOME") or (base.home() / ".codex"))

    def config_path(self) -> Path:
        return self.codex_home() / "config.toml"

    def detect(self) -> bool:
        return self.codex_home().is_dir() or base.on_path("codex")

    def _block(self) -> str:
        argv = base.mcp_command()
        # json.dumps gives TOML basic-string escaping; a raw Windows path
        # parses to a different path, or not at all.
        return ("[mcp_servers." + base.SERVER_NAME + "]\n"
                "command = " + json.dumps(argv[0]) + "\n"
                "args = [" + ", ".join(json.dumps(a) for a in argv[1:]) + "]\n")

    def _parses(self, path: Path) -> str:
        try:
            with open(path, "rb") as handle:
                doc = tomllib.load(handle)
        except Exception as exc:
            return "config.toml no longer parses: " + str(exc)
        servers = doc.get("mcp_servers")
        if not isinstance(servers, dict) or base.SERVER_NAME not in servers:
            return "wrote the block but config.toml does not declare the server"
        return ""

    def register_mcp(self, result: base.Result):
        path = self.config_path()
        before = path.read_text(encoding="utf-8") if path.exists() else None
        state = base.set_block(path, self._block())
        problem = self._parses(path)
        if problem:
            # Put it back exactly as it was. A broken config.toml costs the
            # user every other MCP server they have.
            if before is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(before, encoding="utf-8")
            result.warn(problem + " -- reverted")
            return
        if state == "unchanged":
            result.act("MCP server already registered in codex config.toml")
        else:
            result.act(state + " [mcp_servers." + base.SERVER_NAME
                       + "] in codex config.toml")

    def unregister_mcp(self, result: base.Result):
        if base.drop_block(self.config_path()):
            result.act("removed MCP server from codex config.toml")

    def recorded_command(self):
        path = self.config_path()
        if not path.exists():
            return None
        try:
            with open(path, "rb") as handle:
                doc = tomllib.load(handle)
        except Exception:
            return None
        entry = (doc.get("mcp_servers") or {}).get(base.SERVER_NAME)
        if not isinstance(entry, dict) or not entry.get("command"):
            return None
        return [entry["command"], *(entry.get("args") or [])]

    def verify_mcp(self) -> str:
        path = self.config_path()
        if not path.exists():
            return "no codex config.toml"
        return self._parses(path) or super().verify_mcp()

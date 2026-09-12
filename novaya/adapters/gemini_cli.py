"""Gemini CLI: ~/.gemini/settings.json under `mcpServers`; reads GEMINI.md.

`/novgraph` is a TOML command, `.gemini/commands/novgraph.toml`, and the text
typed after it lands where `{{args}}` stands. ~/.gemini alone is not proof:
Google's Antigravity creates it too. Checked against geminicli.com/docs
(cli/custom-commands, tools/mcp-server), 2026-09-11.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import base
from .. import commands
from .json_servers import JsonServers


class GeminiCli(JsonServers):
    slug = "gemini-cli"
    name = "Gemini CLI"
    instruction_file = "GEMINI.md"
    docs_url = "https://geminicli.com/docs/tools/mcp-server/"
    command_file = ".gemini/commands/{name}.toml"
    command_request = "{{args}}"

    def settings_path(self) -> Path:
        return base.home() / ".gemini" / "settings.json"

    def config_paths(self) -> list:
        return [self.settings_path()]

    def detect(self) -> bool:
        return base.on_path("gemini") or self.settings_path().exists()

    def render_command(self, spec: dict, body: str) -> str:
        # A literal multi-line string: no escapes to get wrong. It cannot hold
        # three single quotes, so a body that does is refused, not mangled.
        if "'''" in body:
            raise ValueError("command body cannot be a TOML literal string")
        description = " ".join(str(spec.get("description") or "").split())
        return ("# " + commands.MARK + "\n"
                "description = " + json.dumps(description) + "\n"
                "prompt = '''\n" + body + "\n'''\n")

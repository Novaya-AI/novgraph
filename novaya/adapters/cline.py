"""Cline: cline_mcp_settings.json under `mcpServers`; reads AGENTS.md.

Two homes, and each is its own Cline: the editor extension keeps the file in
that editor's globalStorage, the CLI in ~/.cline/data/settings/ (from the
CLI's own source; CLINE_MCP_SETTINGS_PATH overrides it). Registered wherever
Cline is actually present. `/novgraph` is a workflow,
`.clinerules/workflows/novgraph.md`, plain markdown. Checked 2026-09-11.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import base
from .json_servers import JsonServers, editor_user_dir

EXTENSION_ID = "saoudrizwan.claude-dev"
EDITORS = ("Code", "Cursor", "Windsurf", "Code - Insiders")


class Cline(JsonServers):
    slug = "cline"
    name = "Cline"
    instruction_file = "AGENTS.md"
    docs_url = "https://docs.cline.bot/mcp/configuring-mcp-servers"
    command_file = ".clinerules/workflows/{name}.md"
    command_request = "the text written after `{invoke}` in the user's message"
    command_fields = ()

    def extension_files(self) -> list:
        out = []
        for editor in EDITORS:
            storage = editor_user_dir(editor) / "globalStorage" / EXTENSION_ID
            if storage.is_dir():
                out.append(storage / "settings" / "cline_mcp_settings.json")
        return out

    def cli_file(self) -> Path | None:
        override = (os.environ.get("CLINE_MCP_SETTINGS_PATH") or "").strip()
        if override:
            return Path(override)
        cli_home = base.home() / ".cline"
        if cli_home.is_dir() or base.on_path("cline"):
            return cli_home / "data" / "settings" / "cline_mcp_settings.json"
        return None

    def config_paths(self) -> list:
        cli = self.cli_file()
        return self.extension_files() + ([cli] if cli else [])

    def entry(self) -> dict:
        return {**super().entry(), "disabled": False}

    def detect(self) -> bool:
        return bool(self.config_paths())

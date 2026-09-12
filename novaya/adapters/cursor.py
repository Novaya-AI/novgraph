"""Cursor: ~/.cursor/mcp.json under `mcpServers`; reads AGENTS.md.

`/novgraph` needs no file of its own: Cursor runs skills from `.agents/skills/`,
the folder Codex uses, so both write the one shared SKILL.md.
Checked against cursor.com/docs (context/mcp, context/skills, context/rules),
2026-09-11.
"""
from __future__ import annotations

from pathlib import Path

from . import base
from .json_servers import JsonServers


class Cursor(JsonServers):
    slug = "cursor"
    name = "Cursor"
    instruction_file = "AGENTS.md"
    docs_url = "https://cursor.com/docs/context/mcp"
    command_file = base.SHARED_SKILL_FILE
    command_body_invoke = base.SHARED_SKILL_INVOKE
    command_request = base.SHARED_SKILL_REQUEST
    command_fields = ("name", "description")

    def home_dir(self) -> Path:
        return base.home() / ".cursor"

    def config_paths(self) -> list:
        return [self.home_dir() / "mcp.json"]

    def detect(self) -> bool:
        return self.home_dir().is_dir() or base.on_path("cursor")

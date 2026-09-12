"""Windsurf: ~/.codeium/windsurf/mcp_config.json under `mcpServers`.

Reads AGENTS.md. `/novgraph` is a workflow: `.windsurf/workflows/novgraph.md`,
under the 12,000-character workflow limit. Checked against docs.devin.ai
(desktop/cascade: mcp, workflows, memories), 2026-09-11.
"""
from __future__ import annotations

from pathlib import Path

from . import base
from .json_servers import JsonServers


class Windsurf(JsonServers):
    slug = "windsurf"
    name = "Windsurf"
    instruction_file = "AGENTS.md"
    docs_url = "https://docs.devin.ai/desktop/cascade/mcp"
    command_file = ".windsurf/workflows/{name}.md"
    command_request = "the text written after `{invoke}` in the user's message"
    command_fields = ("description",)

    def home_dir(self) -> Path:
        return base.home() / ".codeium" / "windsurf"

    def config_paths(self) -> list:
        return [self.home_dir() / "mcp_config.json"]

    def detect(self) -> bool:
        return self.home_dir().is_dir() or base.on_path("windsurf")

"""GitHub Copilot in VS Code: the user-profile mcp.json, under `servers`.

User-level, not `.vscode/mcp.json`: the command is this machine's absolute
path, and a workspace file is committed for the whole team. Instructions in
`.github/copilot-instructions.md`; `/novgraph` is a prompt file,
`.github/prompts/novgraph.prompt.md`. A config with comments (VS Code tolerates
them) is left untouched with a warning. Checked against
code.visualstudio.com/docs/copilot/customization (mcp-servers, prompt-files),
2026-09-11.
"""
from __future__ import annotations

from . import base
from .json_servers import JsonServers, editor_user_dir


class Copilot(JsonServers):
    slug = "copilot"
    name = "GitHub Copilot"
    instruction_file = ".github/copilot-instructions.md"
    docs_url = "https://code.visualstudio.com/docs/copilot/customization/mcp-servers"
    container = "servers"
    command_file = ".github/prompts/{name}.prompt.md"
    command_request = "the text written after `{invoke}` in the user's message"
    command_fields = ("name", "description", "argument-hint", "agent")

    def entry(self) -> dict:
        return {"type": "stdio", **super().entry()}

    def config_paths(self) -> list:
        return [editor_user_dir("Code") / "mcp.json"]

    def detect(self) -> bool:
        extensions = base.home() / ".vscode" / "extensions"
        try:
            return any(p.name.startswith("github.copilot")
                       for p in extensions.iterdir())
        except OSError:
            return False

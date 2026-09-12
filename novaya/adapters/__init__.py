"""The adapter registry. One declaration.

install, doctor, `novgraph adapters` and the docs all read ADAPTERS. Eight ship:
each one is a claim that somebody checked where that client keeps its config.
"""
from __future__ import annotations

from .base import Adapter, Result, mcp_command, probe_server, SERVER_NAME
from .claude_code import ClaudeCode
from .cline import Cline
from .codex import Codex
from .copilot import Copilot
from .cursor import Cursor
from .gemini_cli import GeminiCli
from .opencode import OpenCode
from .windsurf import Windsurf

ADAPTERS = (ClaudeCode(), Codex(), OpenCode(), Cursor(), Windsurf(),
            GeminiCli(), Copilot(), Cline())

SLUGS = tuple(a.slug for a in ADAPTERS)

# What people type versus what the module is called. Nobody types
# "claude-code" when "claude" is the thing on their PATH.
ALIASES = {
    "claude": "claude-code", "claudecode": "claude-code", "cc": "claude-code",
    "open-code": "opencode", "oc": "opencode",
    "openai-codex": "codex",
    "gemini": "gemini-cli", "geminicli": "gemini-cli",
    "github-copilot": "copilot", "vscode": "copilot", "vs-code": "copilot",
    "cline-cli": "cline",
}


def canonical(name: str) -> str:
    name = (name or "").strip().lower()
    return ALIASES.get(name, name)


def looks_like_an_agent(token: str) -> bool:
    """Does this argument look like a client name rather than an API key?

    Used ONLY to catch `novgraph install claude` and redirect it. The positional
    on `install` is a key and nothing else -- see LAW 30.
    """
    token = (token or "").strip()
    if not token or len(token) > 24:
        return False
    return all(c.islower() or c.isdigit() or c == "-" for c in token)


def get(slug: str):
    for adapter in ADAPTERS:
        if adapter.slug == slug:
            return adapter
    return None


def detected():
    """The clients actually present on this machine."""
    return [a for a in ADAPTERS if a.detect()]


def resolve(names):
    """Names from the command line to adapters.

    ("all",) or nothing means "whatever is installed here" -- an install should
    not wire a client the user does not have, and should not need to be told
    which ones they do.
    """
    wanted = [canonical(n) for n in (names or []) if n and n.strip()]
    if not wanted or "auto" in wanted:
        return detected(), []
    if "all" in wanted:
        return list(ADAPTERS), []
    chosen, unknown = [], []
    for name in wanted:
        adapter = get(name)
        if adapter is None:
            unknown.append(name)
        elif adapter not in chosen:
            chosen.append(adapter)
    return chosen, unknown


__all__ = ["ADAPTERS", "SLUGS", "ALIASES", "Adapter", "Result", "get",
           "detected", "resolve", "canonical", "looks_like_an_agent",
           "mcp_command", "probe_server", "SERVER_NAME"]

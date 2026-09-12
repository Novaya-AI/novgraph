"""The `/novgraph` command, written in each agent's own format.

The server declares it (`commands` in /v1/tools) and this only renders it, so a
better workflow reaches every install without a release. Nothing ships here:
a server that serves no commands gets no command files.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

MARK = "Managed by `novgraph install`. Hand edits are overwritten."
HEADER = "<!-- " + MARK + " -->"

_NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
DEFAULT_NAMES = ("novgraph",)


def served(cat: dict | None) -> list:
    """The commands the server declares, minus anything unsafe to write."""
    out = []
    for spec in (cat or {}).get("commands") or []:
        if (isinstance(spec, dict) and _NAME.match(str(spec.get("name") or ""))
                and str(spec.get("body") or "").strip()):
            out.append(spec)
    return out


def path_for(root: Path, adapter, name: str) -> Path | None:
    if not adapter.command_file:
        return None
    return Path(root) / adapter.command_file.format(name=name)


def invocation(adapter, name: str) -> str:
    return adapter.command_invoke.format(name=name)


def body_for(adapter, spec: dict) -> str:
    """The served body with this client's two substitutions made."""
    invoke = (adapter.command_body_invoke or adapter.command_invoke).format(
        name=spec["name"])
    # replace(), not format(): Gemini's `{{args}}` would lose its braces.
    request = adapter.command_request.replace("{invoke}", invoke)
    return (str(spec["body"]).replace("{invoke}", invoke)
            .replace("{request}", request).strip())


def render(adapter, spec: dict) -> str:
    body = body_for(adapter, spec)
    custom = getattr(adapter, "render_command", None)
    if custom:
        return custom(spec, body)
    fields = {"name": spec["name"],
              "description": " ".join(str(spec.get("description") or "").split()),
              "argument-hint": " ".join(str(spec.get("argument_hint") or "").split()),
              "disable-model-invocation": True,
              "agent": "agent"}
    front = []
    for key in adapter.command_fields:
        value = fields.get(key)
        if value in ("", None):
            continue
        # JSON strings are valid YAML scalars, quotes and colons included.
        front.append(key + ": " + (json.dumps(value) if isinstance(value, str)
                                   else str(value).lower()))
    head = ("---\n" + "\n".join(front) + "\n---\n\n") if front else ""
    return head + HEADER + "\n\n" + body + "\n"


def write(root: Path, adapter, specs) -> list:
    """[(path, state, invocation)] -- state by content: created, updated or
    unchanged."""
    written = []
    for spec in specs:
        path = path_for(root, adapter, spec["name"])
        if path is None:
            continue
        body = render(adapter, spec)
        before = path.read_text(encoding="utf-8") if path.exists() else None
        invoke = invocation(adapter, spec["name"])
        if before == body:
            written.append((path, "unchanged", invoke))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        written.append((path, "created" if before is None else "updated", invoke))
    return written


def ours(path: Path) -> bool:
    try:
        return MARK in path.read_text(encoding="utf-8")
    except OSError:
        return False


def remove(root: Path, adapter, names=DEFAULT_NAMES) -> list:
    """Delete our command files, and any directory that leaves empty. A file
    without our header is the user's, and stays."""
    gone = []
    root = Path(root).resolve()
    for name in names:
        path = path_for(root, adapter, name)
        if path is None or not path.exists() or not ours(path):
            continue
        path.unlink()
        gone.append(path)
        parent = path.parent
        while parent != root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    return gone


def status(root: Path, adapter, spec: dict) -> str:
    """'current', 'missing' or 'outdated'."""
    path = path_for(root, adapter, spec["name"])
    if path is None:
        return "current"
    if not path.exists():
        return "missing"
    return ("current" if path.read_text(encoding="utf-8") == render(adapter, spec)
            else "outdated")

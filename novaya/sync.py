"""Carry a changed catalog into every repository this machine has bound.

LAW 22 for files: guidance and the `/novgraph` command are served, so when the
server's catalog moves, the copies written into each repository move with it
-- without waiting for `novgraph upgrade`. Only files Novayagraph already owns are
touched, and only when their content differs. Never raises: this runs on the
back of an ordinary tool call.
"""
from __future__ import annotations

from pathlib import Path

from . import adapters, catalog, commands, docs, workspace


def refresh(key: str) -> dict:
    """Fetch the catalog, and carry it into every repository when it moved.

    The one way to refresh. An MCP session start and `doctor` used to update
    the cache alone; the next call then found the versions equal and never
    resynced, so repository files kept the old surface indefinitely. Raises
    transport.ApiError like catalog.refresh."""
    before = catalog.cached_version()
    doc = catalog.refresh(key)
    if catalog.cached_version() != before:
        resync(doc)
    return doc


def resync(cat: dict | None = None) -> int:
    """Rewrite what changed. Returns how many files were written."""
    try:
        cat = cat or catalog.cached()
        specs = commands.served(cat)
        changed = 0
        for root, _ in workspace.bound_roots():
            changed += _repository(Path(root), cat, specs)
        return changed
    except Exception:
        return 0


def _repository(root: Path, cat: dict, specs) -> int:
    changed = 0
    target = docs.dir_for(root)
    if target.is_dir():
        for name, body in (("rules.md", docs.rules_md(cat)),
                           ("skills.md", docs.skills_md(cat))):
            path = target / name
            if path.exists() and path.read_text(encoding="utf-8") != body:
                path.write_text(body, encoding="utf-8")
                changed += 1
    for adapter in adapters.ADAPTERS:
        # Only where this client was wired: a command file already present, or
        # its pointer block AND the client on this machine (Codex and OpenCode
        # share AGENTS.md, so the block alone does not say which).
        present = any((commands.path_for(root, adapter, s["name"]) or Path()).exists()
                      for s in specs)
        if present or (_has_pointer(root / adapter.instruction_file)
                       and adapter.detect()):
            changed += sum(1 for _, state, _ in commands.write(root, adapter, specs)
                           if state != "unchanged")
    return changed


def _has_pointer(path: Path) -> bool:
    try:
        return docs.START in path.read_text(encoding="utf-8")
    except OSError:
        return False

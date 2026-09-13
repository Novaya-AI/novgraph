"""The tool surface, declared by the server and cached here.

LAW 16: the client never restates what /v1/tools publishes. The CLI verbs, the
MCP tool list and .novgraph/skills.md are all generated from this cache, which
`novgraph install` refreshes. A new server tool arrives without a client release.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import credentials, transport

PREFIX = "novgraph_"
# A catalog cached before the rename still names tools codewiki_*; strip
# either, or every verb comes out as `novgraph-why`.
LEGACY_PREFIX = "codewiki_"

# Never a positional: every tool takes it, and it has its own shared flag.
AMBIENT = "codebase"

_TYPES = {"integer": int, "number": float, "string": str}


def path() -> Path:
    return credentials._home_dir() / "catalog.json"


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    properties: dict
    required: tuple

    @property
    def verb(self) -> str:
        """novgraph_record_why -> record-why."""
        stem = self.name
        for prefix in (PREFIX, LEGACY_PREFIX):
            if stem.startswith(prefix):
                stem = stem[len(prefix):]
                break
        return stem.replace("_", "-")

    @property
    def positional(self) -> str:
        """The argument a person types without naming it.

        The first required one, or the first non-ambient one when nothing is
        required -- `why` takes an optional target and reads badly as --target.
        """
        for name in self.required:
            if name != AMBIENT:
                return name
        for name in self.properties:
            if name != AMBIENT:
                return name
        return ""

    def options(self):
        """Everything that is not the positional or the shared --codebase."""
        skip = {self.positional, AMBIENT}
        return [(n, s) for n, s in self.properties.items() if n not in skip]

    def describe(self, name: str) -> str:
        spec = self.properties.get(name) or {}
        return str(spec.get("description") or "") if isinstance(spec, dict) else ""

    def type_of(self, name: str):
        spec = self.properties.get(name) or {}
        kind = spec.get("type") if isinstance(spec, dict) else None
        return _TYPES.get(str(kind), str)

    @property
    def summary(self) -> str:
        """One line for --help: the first sentence, cut on a word."""
        first = self.description.strip().split(". ")[0].strip().rstrip(".")
        if len(first) <= 88:
            return first
        return first[:88].rsplit(" ", 1)[0] + "..."


def normalise(doc: dict):
    """Chat-Completions function schemas -> Tool. Tolerant of either shape."""
    out = []
    for entry in doc.get("tools") or []:
        if not isinstance(entry, dict):
            continue
        fn = entry.get("function") if isinstance(entry.get("function"), dict) else entry
        name = str(fn.get("name") or "")
        if not name:
            continue
        params = fn.get("parameters") or {}
        out.append(Tool(
            name=name,
            description=str(fn.get("description") or ""),
            properties=dict(params.get("properties") or {}),
            required=tuple(params.get("required") or ()),
        ))
    return out


def save(doc: dict) -> None:
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def cached_version() -> str:
    """The catalog_version of what we have on disk."""
    return str((cached().get("service") or {}).get("catalog_version") or "")


def sync_if_stale(key: str = "") -> bool:
    """Refresh when the server says its surface moved. Never raises.

    The whole update path in one function: the version rode in on a call the
    user was already making, so this costs a request only when something
    actually changed.
    """
    served = str((transport.last_service or {}).get("catalog_version") or "")
    if not served or served == cached_version():
        return False
    key = key or credentials.load()
    if not key:
        return False
    before = cached_version()
    try:
        refresh(key)
    except transport.ApiError:
        return False
    # True only when the refetch moved the cache: a call envelope reporting a
    # version the listing does not must not resync every repository per call.
    return cached_version() != before


def cached() -> dict:
    try:
        doc = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def refresh(key: str) -> dict:
    """Fetch and cache. Raises transport.ApiError -- install reports it."""
    doc = transport.catalog(key)
    save(doc)
    return doc


def live_or_cached() -> dict:
    """The catalog, preferring the network. Never raises.

    Used where an empty tool list is worse than a stale one: an agent shown no
    tools decides the integration is broken.
    """
    key = credentials.load()
    if key:
        try:
            return refresh(key)
        except transport.ApiError:
            pass
    return cached()


def tools(doc: dict | None = None):
    return normalise(cached() if doc is None else doc)


def by_verb(verb: str):
    for tool in tools():
        if tool.verb == verb:
            return tool
    return None

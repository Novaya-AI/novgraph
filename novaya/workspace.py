"""Which repository this is, and what the server calls it.

Resolved once at install against the server's list, then written down. A
wrongly resolved codebase gives confident answers about someone else's repo
with no error to notice -- so an uncertain match returns "" and install says
so. Matched on origin first: the runner clones a URL, so the URL is identity.
"""
from __future__ import annotations

import json
import os

from pathlib import Path

from . import credentials


def git_root(start: Path | None = None) -> Path | None:
    """The repository containing `start`. A walk, not `git rev-parse`: this is
    on the agent's critical path and works without git installed."""
    here = Path(start or Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def root_for(start: Path | None = None) -> Path:
    """The workspace root: the git repository, or the directory itself."""
    return git_root(start) or Path(start or Path.cwd()).resolve()


def origin_url(root: Path) -> str:
    """The remote, credentials stripped. "" for a repo with no remote -- a
    fact worth reporting: the runner would have nothing to clone."""
    config = Path(root) / ".git" / "config"
    try:
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    in_origin = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_origin = stripped.replace(" ", "").lower().startswith('[remote"origin"]')
            continue
        if in_origin and stripped.lower().startswith("url"):
            _, _, value = stripped.partition("=")
            return _strip_credentials(value.strip())
    return ""


def _strip_credentials(url: str) -> str:
    """https://user:token@host/x -> https://host/x. Never record a secret."""
    if "@" not in url or "://" not in url:
        return url
    scheme, _, rest = url.partition("://")
    _, _, host_part = rest.rpartition("@")
    return scheme + "://" + host_part


# -- the remembered codebase --------------------------------------------------

def _state_path() -> Path:
    return credentials._home_dir() / "workspaces.json"


def _load_state() -> dict:
    try:
        doc = json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _key(root: Path) -> str:
    # Case-folded on Windows, where the same checkout is reachable as C:\ and
    # c:\ and both are the same directory.
    text = str(Path(root).resolve())
    return text.lower() if os.name == "nt" else text


def remember(root: Path, codebase: str) -> None:
    # Normalised like the read side, or a subdirectory write reads back absent.
    root = root_for(root)
    state = _load_state()
    state[_key(root)] = {"codebase": codebase, "origin": origin_url(root)}
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def forget(root: Path) -> bool:
    root = root_for(root)
    state = _load_state()
    if state.pop(_key(root), None) is None:
        return False
    _state_path().write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return True


def bound_roots():
    """Every checkout this machine has bound, newest state first.

    This is what makes `novgraph upgrade` able to propagate a new client to all
    of a user's repositories -- they will not remember where they ran install.
    """
    out = []
    for key, entry in _load_state().items():
        if isinstance(entry, dict) and Path(key).exists():
            out.append((Path(key), str(entry.get("codebase") or "")))
    return sorted(out)


def codebase_for(start: Path | None = None) -> str:
    """The codebase name recorded for this checkout, or "" if it has none."""
    root = root_for(start)
    entry = _load_state().get(_key(root))
    if isinstance(entry, dict):
        return str(entry.get("codebase") or "")
    return ""


# -- matching a checkout to the server's list ---------------------------------

def match_codebase(names, root: Path) -> str:
    """This checkout's codebase, or "". Origin first, directory name only when
    unambiguous: unresolved is visible, wrongly resolved is not."""
    if not names:
        return ""
    origin = origin_url(root)
    if origin:
        stem = origin.rstrip("/")
        if stem.endswith(".git"):
            stem = stem[:-4]
        slug = stem.rpartition("/")[2].lower()
        owner_slug = "/".join(stem.split("/")[-2:]).lower()
        for name in names:
            low = str(name).lower()
            if low == slug or low.endswith("/" + slug) or low == owner_slug:
                return str(name)
    folder = Path(root).name.lower()
    hits = [str(n) for n in names if str(n).lower() == folder]
    if len(hits) == 1:
        return hits[0]
    return ""

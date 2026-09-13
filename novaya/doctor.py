"""Every check is a bug that actually happened.

Persistence reads the key from another process; identity checks the codebase
against the server's own list; content looks at the body, because an empty
projection answers 200. Exit 0 when nothing FAILED -- a warning is a machine
without Codex, not a broken install.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import (adapters, catalog, commands, credentials, docs, sync, transport,
               workspace)

OK = "ok"
WARN = "warn"
FAIL = "fail"

_MARK = {OK: "PASS", WARN: "WARN", FAIL: "FAIL"}


class Check:
    def __init__(self, name, status, detail=""):
        self.name = name
        self.status = status
        self.detail = detail

    def as_dict(self):
        return {"check": self.name, "status": self.status, "detail": self.detail}

    def __str__(self):
        line = _MARK[self.status] + "  " + self.name
        return line + ("  --  " + self.detail if self.detail else "")


def run(root: Path | None = None, deep: bool = True):
    """Every check, in the order a failure would cascade."""
    root = workspace.root_for(root)
    checks = []

    # -- credential ----------------------------------------------------------
    key = credentials.load()
    origin = credentials.source()
    if not key:
        checks.append(Check("credential", FAIL,
                            "no API key. Run: novgraph install <KEY> "
                            "(https://app.trynovaya.com -> Manage keys)"))
        return checks, root
    checks.append(Check("credential", OK, "loaded from " + origin))

    if credentials.load_stored():
        persists = credentials.verify_separate_process()
        checks.append(Check(
            "credential persists", OK if persists else FAIL,
            credentials.loader_hint(credentials.preferred_backend()) if persists
            else "a separate process could not read the key back -- future "
                 "sessions will not authenticate"))
    else:
        checks.append(Check(
            "credential persists", WARN,
            "this key comes from the environment, not this machine's "
            "credential store. It will not survive a new session. "
            "Run: novgraph install <KEY>"))

    # -- the API -------------------------------------------------------------
    try:
        # refresh, not fetch-and-discard: this is the request that keeps a
        # shell user's verbs current between installs.
        served = sync.refresh(key)
    except transport.ApiError as exc:
        checks.append(Check(
            "api " + transport.base_url(), FAIL,
            exc.message + (" -- the key is expired, revoked or unknown; "
                           "retrying will not help" if exc.is_auth else "")))
        return checks, root
    checks.append(Check("api " + transport.base_url(), OK,
                        str(len(catalog.tools(served))) + " tools served"))

    # -- which repository ----------------------------------------------------
    recorded = workspace.codebase_for(root)
    try:
        listing = transport.call(key, "novgraph_codebases", {})
    except transport.ApiError as exc:
        checks.append(Check("codebase", WARN,
                            "could not list codebases: " + exc.message))
        listing = {}
    available = _names_in(listing)
    graph_origin = _origins_in(listing).get(recorded) or ""
    checkout_origin = workspace.origin_url(root)
    if not available:
        checks.append(Check(
            "codebase", FAIL,
            "this key can read no codebases. Connect a repository at "
            "https://app.trynovaya.com and wait for its job to finish."))
    elif (recorded in available and graph_origin and checkout_origin
          and workspace.repo_identity(graph_origin)
          != workspace.repo_identity(checkout_origin)):
        # Bound by name before bindings compared remotes: every answer here
        # describes another repository, and nothing else would say so.
        checks.append(Check(
            "codebase", FAIL,
            "this checkout is " + checkout_origin + ", but '" + recorded
            + "' is the graph of " + graph_origin + ". Run `novgraph install` "
            "here to rebind it."))
    elif recorded and recorded in available:
        checks.append(Check("codebase", OK, recorded))
    elif recorded:
        checks.append(Check(
            "codebase", FAIL,
            "this checkout is recorded as '" + recorded + "', which this key "
            "cannot see. Available: " + ", ".join(sorted(available))))
    else:
        guess = workspace.match_codebase(available, root, _origins_in(listing))
        checks.append(Check(
            "codebase", WARN,
            ("unresolved -- run `novgraph install` here to bind it"
             + (" (looks like '" + guess + "')" if guess else
                "; none of " + ", ".join(sorted(available)) + " matches "
                + (workspace.origin_url(root) or Path(root).name)))))

    # -- is there anything in it --------------------------------------------
    target = recorded if recorded in available else ""
    if deep and target:
        try:
            answer = transport.call(key, "novgraph_summary", {"codebase": target})
            body = str(answer.get("text") or "").strip()
        except transport.ApiError as exc:
            body = ""
            checks.append(Check("graph content", FAIL,
                                "summary call failed: " + exc.message))
        else:
            if "No summary has been pushed" in body:
                # Longer than 80 characters, so it passed as "content" -- the
                # check was reading its own error message as a summary.
                body = ""
            checks.append(Check(
                "graph content", OK if len(body) > 80 else FAIL,
                (str(len(body)) + " characters of summary") if len(body) > 80
                else "the graph answered but has nothing in it -- the index "
                     "may still be running, or it failed"))
        checks.append(_freshness(key, target))

    # -- discovery -----------------------------------------------------------
    present = adapters.detected()
    if not present:
        checks.append(Check("agent clients", WARN,
                            "none of " + ", ".join(adapters.SLUGS)
                            + " found on this machine"))
    for adapter in present:
        problem = adapter.verify_mcp()
        # Not registered is a WARN: the user may not want MCP in that client,
        # and the shell verbs still work. REGISTERED AND BROKEN is a FAIL --
        # the client will launch nothing and report nothing, which is the
        # failure an upgrade that moves the shim actually produces.
        registered = adapter.recorded_command() is not None
        status = OK if not problem else (FAIL if registered else WARN)
        checks.append(Check("client " + adapter.slug + " (mcp)", status, problem))
        instruction = Path(root) / adapter.instruction_file
        has_block = (instruction.exists()
                     and docs.START in instruction.read_text(encoding="utf-8"))
        checks.append(Check(
            "client " + adapter.slug + " (pointer)",
            OK if has_block else FAIL,
            adapter.instruction_file + (" carries the block" if has_block
                                        else " has no novgraph block -- a fresh "
                                             "session will not know Novayagraph "
                                             "exists")))
        for spec in commands.served(served):
            state = commands.status(root, adapter, spec)
            invoke = commands.invocation(adapter, spec["name"])
            checks.append(Check(
                "client " + adapter.slug + " (" + invoke + ")",
                OK if state == "current" else WARN,
                "" if state == "current" else
                invoke + " is " + state + " -- run `novgraph install`"))

    # Content, not presence: a file that exists but describes an older surface
    # passed here while agents read the old tool descriptions from it.
    expected = {"rules.md": docs.rules_md(served), "skills.md": docs.skills_md(served)}
    for name in ("rules.md", "skills.md", "blueprint.md"):
        path = docs.dir_for(root) / name
        if not path.exists():
            checks.append(Check(".novgraph/" + name, FAIL,
                                "missing -- run novgraph install"))
        elif name in expected and path.read_text(encoding="utf-8") != expected[name]:
            checks.append(Check(".novgraph/" + name, WARN,
                                "describes an older tool surface than the server "
                                "serves -- run novgraph install"))
        else:
            checks.append(Check(".novgraph/" + name, OK))

    # -- our own MCP server --------------------------------------------------
    if deep:
        problem = adapters.probe_server()
        checks.append(Check("mcp server", OK if not problem else FAIL,
                            problem or " ".join(adapters.mcp_command())))

    return checks, root


def _freshness(key: str, codebase: str) -> Check:
    """Is the graph at the host's head? A full graph that stopped updating
    passes every other check and still answers from an old commit."""
    name = "graph freshness"
    try:
        sync = transport.request(key, "GET", "/v1/health?days=1").get("graph_sync") or {}
    except transport.ApiError as exc:
        return Check(name, WARN, "could not read sync state: " + exc.message)
    for repo in sync.get("repositories") or []:
        heads = repo.get("indexed_heads") or {}
        if codebase not in heads:
            continue
        state = str(repo.get("state") or "")
        head = str(repo.get("remote_head") or "")[:7]
        hook = str((repo.get("hook") or {}).get("state") or "")
        if state == "current" and hook in ("", "active"):
            return Check(name, OK, "at " + head)
        if state == "current":
            return Check(name, WARN, "at " + head + ", but the webhook is "
                         + hook + " -- commits arrive by polling, not events")
        if state == "error":
            # WARN: the fix is on the dashboard, not a re-run of install.
            return Check(name, WARN, "NOT UPDATING: "
                         + str(repo.get("error") or "sync failed")
                         + " -- https://app.trynovaya.com")
        return Check(name, WARN, state + ": indexed "
                     + (str(heads.get(codebase) or "")[:7] or "nothing")
                     + ", host at " + (head or "unknown"))
    return Check(name, WARN, "no git-host sync for this codebase; it updates "
                             "only when pushed")


def _origins_in(listing: dict) -> dict:
    """{name: remote} from the structured listing; {} when the server sent none."""
    found = {}
    for item in listing.get("codebases") or []:
        if isinstance(item, dict) and (item.get("codebase") or item.get("name")):
            found[str(item.get("codebase") or item.get("name"))] = str(
                item.get("origin_url") or "")
    return found


def _names_in(listing: dict):
    """Codebase names out of whatever shape the listing came back in."""
    found = []
    for key in ("codebases", "items", "results"):
        value = listing.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    found.append(item)
                elif isinstance(item, dict):
                    name = item.get("codebase") or item.get("name")
                    if name:
                        found.append(str(name))
    if found:
        return found
    # The tools answer in prose. Strict, because a loose parser returned a row
    # of box characters as a codebase name.
    text = str(listing.get("text") or "")
    for line in text.splitlines():
        stripped = line.strip()
        # Stop at the footer rule, or its signature line reads as a codebase.
        if stripped and all(ch in _RULE_CHARS for ch in stripped):
            break
        if not stripped:
            continue
        token = stripped.lstrip("-*").strip().split()[0].strip("`'\":,")
        if _looks_like_a_name(token):
            found.append(token)
    return found


_RULE_CHARS = "─━┄┅┈┉╌╍-=_~"


# A repository identifier: word characters and path separators, nothing else.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{1,118}$")


def _looks_like_a_name(token: str) -> bool:
    return bool(_NAME_RE.match(token or "")) and not token.endswith(".")


def failed(checks) -> bool:
    return any(c.status == FAIL for c in checks)

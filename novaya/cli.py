"""The `novgraph` command.

    uv tool install novaya
    novgraph install <KEY>

Setup is a program that runs and reports, not a document an agent obeys.
Distribution is `novaya` and the command is `novgraph` because both better names
are taken on PyPI by unrelated live projects -- build.md, LAW 1.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import (__version__, adapters, catalog, commands, credentials, docs,
               doctor, service, sync, transport, workspace)

APP_URL = "https://app.trynovaya.com"


# -- output -------------------------------------------------------------------

def out(text: str = ""):
    sys.stdout.write(text + "\n")


def rule(title: str):
    out("")
    out(title)
    out("-" * len(title))


def render(result: dict, as_json: bool) -> int:
    """Print an answer. Prose when the server sent prose."""
    if as_json:
        out(json.dumps(result, indent=2))
        return 0
    text = result.get("text")
    if isinstance(text, str) and text.strip():
        out(text.rstrip())
        return 0
    out(json.dumps(result, indent=2))
    return 0


def announce() -> None:
    """One line, to stderr, when the server says a newer client exists.

    stderr so it never pollutes `--json` output or a piped answer.
    """
    line = service.upgrade_line(transport.last_service)
    if line:
        sys.stderr.write(line + "\n")


def api_failure(exc: transport.ApiError) -> int:
    """One explanation of a failed call, shared by every verb."""
    sys.stderr.write("novgraph: " + exc.message + "\n")
    if exc.is_auth:
        sys.stderr.write(
            "  This machine's key was rejected. Get one at " + APP_URL
            + " (Manage keys) and run: novgraph install <KEY>\n"
            "  Retrying with the same key will not help.\n")
    elif exc.status == 0:
        sys.stderr.write("  The API could not be reached. Check the network, "
                         "then try again.\n")
    return 2


# -- install ------------------------------------------------------------------

def read_key(argument: str) -> str:
    """The key, or stdin with `-` -- so it never enters shell history."""
    if argument == "-":
        return sys.stdin.read().strip()
    return (argument or "").strip()


def cmd_install(args) -> int:
    # THE POSITIONAL IS A KEY. `novgraph install claude` is refused rather than
    # guessed, because it does not describe what it would do -- it installs
    # nothing named claude, it registers a client that is already installed.
    # An agent handed that line can reasonably decide the user wants Claude
    # Code installed. `novgraph wire claude` is the command, and it is not part
    # of setup: `install` already wires everything it detects.
    supplied_key = read_key(args.key or "")
    if supplied_key and adapters.looks_like_an_agent(supplied_key):
        sys.stderr.write(
            "novgraph: `install` takes an API key, not a client name.\n"
            "  `novgraph install <KEY>` already wires every client it finds.\n"
            "  To wire just one:        novgraph wire " + supplied_key + "\n"
            "  To set or rotate a key:  novgraph key <KEY>\n")
        return 2

    root = workspace.root_for(Path(args.root) if args.root else None)
    out("novgraph " + __version__ + "  --  setting up " + str(root))

    # 1. the credential -------------------------------------------------------
    rule("Credential")
    supplied = supplied_key
    if supplied:
        info = credentials.store(supplied)
        out("stored: " + info["loader"])
    key = credentials.load()
    if not key:
        out("no key on this machine.")
        out("Get one at " + APP_URL + " -> Manage keys, then run:")
        out("    novgraph install <KEY>")
        return 2
    if credentials.load_stored():
        if credentials.verify_separate_process():
            out("verified: a separate process can read it back")
        else:
            out("PROBLEM: a separate process could NOT read the key back.")
            out("Future sessions will not authenticate. Setup stops here.")
            return 2
    else:
        out("WARNING: using a key from the environment. It is not stored on "
            "this machine and will not survive this shell.")
        out("Run `novgraph install <KEY>` to persist it.")

    # 2. the server -----------------------------------------------------------
    rule("Novayagraph")
    try:
        served = catalog.refresh(key)
    except transport.ApiError as exc:
        return api_failure(exc)
    out(transport.base_url() + " -- " + str(len(catalog.tools(served)))
        + " tools cached")

    # 3. which repository -----------------------------------------------------
    codebase = (args.codebase or "").strip()
    available = []
    try:
        available = doctor._names_in(transport.call(key, "novgraph_codebases", {}))
    except transport.ApiError as exc:
        out("could not list codebases: " + exc.message)
    if codebase and available and codebase not in available:
        out("'" + codebase + "' is not one this key can read: "
            + ", ".join(sorted(available)))
        return 2
    if not codebase:
        codebase = workspace.match_codebase(available, root)
    origin = workspace.origin_url(root)
    if codebase:
        workspace.remember(root, codebase)
        out("this checkout is " + codebase)
    else:
        # Reported, never guessed: a wrong codebase fails invisibly.
        out("this checkout does not match any indexed codebase.")
        if origin:
            out("  origin: " + origin)
        out("  connect it at " + APP_URL + ", wait for the job to finish,")
        out("  then run `novgraph install` again. Or pass --codebase <name>.")
        if available:
            out("  this key can read: " + ", ".join(sorted(available)))

    # 4. the clients ----------------------------------------------------------
    # Resolved BEFORE the files are written, so the setup record can name what
    # was actually wired rather than what was hoped for.
    rule("Agents")
    # Probe before registering: a server that cannot start hangs the client.
    server_problem = adapters.probe_server()
    if server_problem:
        out("the MCP server did not answer a handshake: " + server_problem)
        out("wiring shell access only; re-run after fixing it for native tools.")
    chosen, unknown = adapters.resolve(args.agent)
    for name in unknown:
        out("no adapter for '" + name + "' yet.")
        out("  Wired automatically: " + ", ".join(adapters.SLUGS) + ".")
        out("  For anything else, `novgraph adapters` prints the command to "
            "register by hand.")
    if not chosen and not unknown:
        # Only when nothing was NAMED. Saying "force one with --agent" straight
        # after explaining that the agent they named has no adapter is a second
        # message that contradicts the first.
        out("no supported client found on this machine.")
        out("Supported: " + ", ".join(adapters.SLUGS)
            + ".  Force one with --agent <name>.")
    for adapter in chosen:
        out(adapter.name + ":")
        result = adapter.wire(root, codebase, with_mcp=not server_problem,
                              specs=commands.served(served))
        for action in result.actions:
            out("  " + action)
        for warning in result.warnings:
            out("  WARNING: " + warning)

    # 5. the files we own -----------------------------------------------------
    # Repository facts only. Which credential store this machine uses and which
    # agents it has are DOCTOR output -- committing them puts one developer's
    # username and setup into everybody else's checkout.
    rule("Files")
    for path, state in docs.write_all(root, served, codebase, origin):
        out(state + ": " + str(Path(path).relative_to(root)))

    # 6. prove it -------------------------------------------------------------
    rule("Verification")
    checks, _ = doctor.run(root, deep=True)
    for check in checks:
        out(str(check))
    if doctor.failed(checks):
        out("")
        out("Setup is INCOMPLETE. Fix the FAIL lines above and re-run "
            "`novgraph install`.")
        return 1
    if not shutil.which("novgraph"):
        out("")
        out("NOTE: `novgraph` is not on PATH, so the shell verbs will not run "
            "from a new terminal.")
        out("Fix it with `uv tool update-shell`, then open a new shell. MCP is "
            "unaffected -- it launches by absolute path.")

    out("")
    out("Done. Agents in this repository can now reach Novayagraph; nothing else "
        "to configure.")
    out("Check it any time with `novgraph doctor`.")
    announce()
    return 0


def cmd_wire(args) -> int:
    """Register Novayagraph with one already-installed client, or all of them.

    Not part of setup: `novgraph install <KEY>` wires everything it detects, and
    re-running it picks up a client installed later. This is for the selective
    case and for repair -- named `wire` because nothing here installs a coding
    agent, and a verb that says otherwise is one an agent will act on wrongly.
    """
    root = workspace.root_for(Path(args.root) if args.root else None)
    if not credentials.load():
        sys.stderr.write("novgraph: no API key on this machine.\n"
                         "  Run: novgraph key <KEY>\n")
        return 2
    codebase = workspace.codebase_for(root)

    problem = adapters.probe_server()
    if problem:
        out("the MCP server did not answer a handshake: " + problem)
        out("wiring shell access only.")
    chosen, unknown = adapters.resolve(args.agent)
    for name in unknown:
        out("no adapter for '" + name + "' yet.")
        out("  Wired automatically: " + ", ".join(adapters.SLUGS) + ".")
        out("  For anything else, `novgraph adapters` prints the command to "
            "register by hand.")
    if not chosen:
        if not unknown:
            out("no supported client found on this machine.")
            out("Supported: " + ", ".join(adapters.SLUGS) + ".")
        return 1 if unknown else 0
    for adapter in chosen:
        out(adapter.name + ":")
        result = adapter.wire(root, codebase, with_mcp=not problem,
                              specs=commands.served(catalog.cached()))
        for action in result.actions:
            out("  " + action)
        for warning in result.warnings:
            out("  WARNING: " + warning)
    out("")
    out("Check it with `novgraph doctor`.")
    return 0


def cmd_key(args) -> int:
    """Set or inspect this machine's key, and nothing else.

    Rotation is its own act. `novgraph install <NEW KEY>` also replaces the key,
    but it then resolves a codebase and rewires clients -- work that has
    nothing to do with a key having been leaked or expired, and that fails
    noisily when you happen to be standing in the wrong directory.
    """
    supplied = read_key(args.key or "")
    if not supplied:
        source = credentials.source()
        if not source:
            out("No key on this machine.")
            out("Get one at " + APP_URL + " -> Manage keys, then run:")
            out("    novgraph key <KEY>")
            return 1
        out("key source: " + source)
        if credentials.load_stored():
            out("stored in:  " + credentials.loader_hint(
                credentials.preferred_backend()))
        out("")
        out("Replace it with `novgraph key <NEW KEY>`, or `novgraph key -` to read "
            "it from stdin.")
        return 0

    info = credentials.store(supplied)
    out("stored: " + info["loader"])
    if not credentials.verify_separate_process():
        out("PROBLEM: a separate process could NOT read the key back.")
        return 2
    out("verified: a separate process can read it back")

    # Prove the NEW key works before the user walks away believing it does.
    try:
        served = catalog.refresh(supplied)
    except transport.ApiError as exc:
        out("")
        out("the key was stored, but the API rejected it:")
        return api_failure(exc)
    out("accepted by " + transport.base_url() + " -- "
        + str(len(catalog.tools(served))) + " tools")
    announce()
    return 0


def cmd_uninstall(args) -> int:
    root = workspace.root_for(Path(args.root) if args.root else None)
    for adapter in adapters.ADAPTERS:
        result = adapter.unwire(root)
        for action in result.actions:
            out(adapter.name + ": " + action)
    removed = 0
    target = docs.dir_for(root)
    for name in ("rules.md", "skills.md", "blueprint.md"):
        path = target / name
        if path.exists():
            path.unlink()
            removed += 1
    if removed and not any(target.iterdir()):
        target.rmdir()
    out("removed " + str(removed) + " file(s) from .novgraph/")
    workspace.forget(root)
    if args.keep_key:
        out("kept this machine's API key (--keep-key)")
    else:
        gone = credentials.clear()
        out("cleared the stored key" + (" (" + ", ".join(gone) + ")" if gone
                                        else " -- none was stored"))
    return 0


# -- diagnostics --------------------------------------------------------------

def cmd_doctor(args) -> int:
    root = workspace.root_for(Path(args.root) if args.root else None)
    checks, root = doctor.run(root, deep=not args.quick)
    if args.json:
        out(json.dumps({"root": str(root),
                        "checks": [c.as_dict() for c in checks]}, indent=2))
    else:
        out("novgraph " + __version__ + "  --  " + str(root))
        out("")
        for check in checks:
            out(str(check))
        announce()
    return 1 if doctor.failed(checks) else 0


def cmd_adapters(args) -> int:
    for adapter in adapters.ADAPTERS:
        mark = "installed" if adapter.detect() else "not found"
        out(adapter.slug.ljust(14) + adapter.name.ljust(14) + mark)
        out("".ljust(14) + "instructions: " + adapter.instruction_file)
        if adapter.docs_url:
            out("".ljust(14) + adapter.docs_url)
    out("")
    out("MCP command: " + " ".join(adapters.mcp_command()))
    return 0


def _move_running_shim_aside():
    """Windows will not overwrite a running .exe, and `novgraph upgrade` IS the
    running `novgraph.exe` -- so uv failed to replace it on every Windows upgrade.
    It will rename one, though: move ours aside and let uv write a fresh one.
    Returns the moved path, or None where there is nothing to do."""
    if not sys.platform.startswith("win"):
        return None
    shim = shutil.which("novgraph")
    if not shim or not shim.lower().endswith(".exe"):
        return None
    for stale in Path(shim).parent.glob(Path(shim).name + ".old-*"):
        try:
            stale.unlink()      # left by an earlier upgrade; free once it exited
        except OSError:
            pass
    aside = shim + ".old-" + str(os.getpid())
    try:
        os.replace(shim, aside)
    except OSError:
        return None
    return aside


def cmd_upgrade(args) -> int:
    """Upgrade the client, then bring every repository it knows up to date.

    The re-sync is the point. A user who installed months ago has repositories
    carrying that client's files and pointer blocks; upgrading the package
    alone would leave every one of them stale, and they will not remember
    where they ran install. `workspaces.json` does.
    """
    if not args.resync_only:
        rule("Upgrading")
        uv = shutil.which("uv")
        if not uv:
            out("`uv` is not on PATH, so this cannot upgrade the package.")
            out("Upgrade it however you installed it, then run:")
            out("    novgraph upgrade --resync-only")
            return 2
        aside = _move_running_shim_aside()
        code = subprocess.run([uv, "tool", "upgrade", "novaya"]).returncode
        if aside and not Path(str(aside).rsplit(".old-", 1)[0]).exists():
            os.replace(aside, str(aside).rsplit(".old-", 1)[0])   # put it back
        if code != 0:
            out("`uv tool upgrade novaya` failed; nothing was re-synced.")
            return code
        # Re-exec so the RE-SYNC runs the new code, not the process that
        # started before the upgrade. Otherwise `upgrade` would forever write
        # the files of the version being replaced.
        shim = shutil.which("novgraph")
        argv = ([shim] if shim else [sys.executable, "-m", "novaya"]) + \
            ["upgrade", "--resync-only"]
        return subprocess.run(argv).returncode

    rule("Repositories")
    roots = workspace.bound_roots()
    if not roots:
        out("no repositories bound on this machine yet.")
        out("Run `novgraph install <KEY>` inside one.")
        return 0
    failures = 0
    shim = shutil.which("novgraph")
    for root, codebase in roots:
        out("")
        out(str(root) + ("  (" + codebase + ")" if codebase else ""))
        argv = ([shim] if shim else [sys.executable, "-m", "novaya"]) + \
            ["install", "--root", str(root)]
        done = subprocess.run(argv, capture_output=True, text=True)
        for line in (done.stdout or "").splitlines():
            stripped = line.strip()
            if stripped.startswith(("created:", "updated:")) or "pointer block" in line \
                    or "registered MCP" in line or " command in " in line \
                    or stripped.startswith(("FAIL", "WARN")):
                out("  " + stripped)
        if done.returncode != 0:
            failures += 1
            out("  INCOMPLETE -- run `novgraph doctor` there")
    out("")
    out(str(len(roots)) + " repositor" + ("y" if len(roots) == 1 else "ies")
        + " synced" + (", " + str(failures) + " incomplete" if failures else "")
        + ".")
    return 1 if failures else 0


def cmd_mcp(args) -> int:
    from . import mcp
    return mcp.serve()


# -- the graph ----------------------------------------------------------------

def resolve_codebase(args) -> str:
    explicit = getattr(args, "codebase", "") or ""
    return explicit.strip() or workspace.codebase_for()


def run_tool(name: str, payload: dict, args) -> int:
    key = credentials.load()
    if not key:
        sys.stderr.write(
            "novgraph: no API key on this machine.\n"
            "  Get one at " + APP_URL + " -> Manage keys, then run:\n"
            "      novgraph install <KEY>\n")
        return 2
    codebase = resolve_codebase(args)
    if codebase:
        payload.setdefault("codebase", codebase)
    try:
        result = transport.call(key, name, payload)
    except transport.ApiError as exc:
        return api_failure(exc)
    code = render(result, getattr(args, "as_json", False))
    # The envelope rode in on that call. Refresh only if the surface moved,
    # and mention an upgrade at most once a day.
    if catalog.sync_if_stale(key):
        sync.resync()
    announce()
    return code


def add_graph_verbs(sub) -> int:
    """Every graph verb, generated from the cached catalog. LAW 16.

    A tool added on the server becomes a command at the next `novgraph install`,
    with no client release and no list here to fall out of step.
    """
    tools = catalog.tools()
    for tool in tools:
        node = sub.add_parser(tool.verb, help=tool.summary,
                              description=tool.description)
        node.add_argument("--codebase", default="",
                          help="target another repository")
        node.add_argument("--json", dest="as_json", action="store_true",
                          help="raw response")
        if tool.positional:
            node.add_argument(
                tool.positional,
                nargs="+" if tool.positional in tool.required else "*",
                help=tool.describe(tool.positional))
        for name, _spec in tool.options():
            node.add_argument("--" + name.replace("_", "-"), dest=name,
                              default=None, type=tool.type_of(name),
                              help=tool.describe(name))
        node.set_defaults(func=_graph_call, tool=tool)
    return len(tools)


def _graph_call(args) -> int:
    tool = args.tool
    payload = {}
    if tool.positional:
        value = getattr(args, tool.positional, None)
        if value:
            payload[tool.positional] = (" ".join(value)
                                        if isinstance(value, list) else value)
    for name, _spec in tool.options():
        value = getattr(args, name, None)
        if value not in (None, "", []):
            payload[name] = value
    return run_tool(tool.name, payload, args)


def cmd_call(args) -> int:
    """Any tool, including one newer than this client -- or a thin client
    becomes the thing holding the platform back."""
    try:
        payload = json.loads(args.json_args) if args.json_args else {}
    except json.JSONDecodeError as exc:
        sys.stderr.write("novgraph: --json is not valid JSON: " + str(exc) + "\n")
        return 2
    if not isinstance(payload, dict):
        sys.stderr.write("novgraph: --json must be a JSON object\n")
        return 2
    return run_tool(args.tool, payload, args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novgraph",
        description="Novayagraph from the command line: architecture, recorded "
                    "intent, blast radius. Setup: novgraph install <KEY>.")
    parser.add_argument("--version", action="version",
                        version="novgraph " + __version__ + " (novaya)")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("install", help="set this machine up: credential, files, agents")
    p.add_argument("key", nargs="?", default="", metavar="KEY",
                   help="API key from " + APP_URL + " (Manage keys). Use - to "
                        "read it from stdin. Omit to re-run setup with the key "
                        "already stored.")
    p.add_argument("--agent", action="append", default=[],
                   metavar="NAME",
                   help="wire a specific client (" + ", ".join(adapters.SLUGS)
                        + ", or all). Default: whatever is installed here.")
    p.add_argument("--codebase", default="",
                   help="bind this checkout to a codebase name explicitly")
    p.add_argument("--root", default="", help="set up a different directory")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("wire", help="register Novayagraph with one coding client")
    p.add_argument("agent", nargs="*", default=[], metavar="AGENT",
                   help="which client (" + ", ".join(adapters.SLUGS)
                        + ", or all). Omit for every one found here.")
    p.add_argument("--root", default="")
    p.set_defaults(func=cmd_wire)

    p = sub.add_parser("key", help="set or rotate this machine's API key")
    p.add_argument("key", nargs="?", default="",
                   help="the new key from " + APP_URL + " (Manage keys). "
                        "Use - to read it from stdin. Omit to show where the "
                        "current one is stored, never its value.")
    p.set_defaults(func=cmd_key)

    p = sub.add_parser("doctor", help="prove the setup still works")
    p.add_argument("--json", action="store_true", help="machine-readable, for CI")
    p.add_argument("--quick", action="store_true",
                   help="skip the MCP handshake and the graph-content read")
    p.add_argument("--root", default="")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("adapters", help="which clients this knows how to wire")
    p.set_defaults(func=cmd_adapters)

    p = sub.add_parser("uninstall", help="remove everything this wrote")
    p.add_argument("--keep-key", action="store_true",
                   help="leave the stored credential in place")
    p.add_argument("--root", default="")
    p.set_defaults(func=cmd_uninstall)

    p = sub.add_parser("upgrade",
                       help="upgrade the client and re-sync every repository")
    p.add_argument("--resync-only", action="store_true",
                   help="skip the package upgrade; just refresh what is bound")
    p.set_defaults(func=cmd_upgrade)

    p = sub.add_parser("mcp", help="run the MCP server (clients launch this)")
    p.set_defaults(func=cmd_mcp)

    add_graph_verbs(sub)

    p = sub.add_parser("call", help="call any tool by name, including a new one")
    p.add_argument("tool")
    p.add_argument("--json", dest="json_args", default="",
                   metavar="OBJECT", help="arguments as a JSON object")
    p.add_argument("--codebase", default="")
    p.set_defaults(func=cmd_call, as_json=False)

    return parser


def _utf8_console():
    """Survive the server's prose on Windows: cp1252 raises on the em-dashes a
    graph answer is full of. Replace rather than lose the whole answer."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


SETUP_COMMANDS = ("install", "wire", "key", "doctor", "adapters", "uninstall",
                  "mcp", "call", "upgrade")


def main(argv=None) -> int:
    _utf8_console()
    argv = list(sys.argv[1:] if argv is None else argv)
    if (argv and not argv[0].startswith("-")
            and argv[0] not in SETUP_COMMANDS and not catalog.tools()):
        sys.stderr.write(
            "novgraph: no tool catalog on this machine yet -- the verbs come "
            "from the server.\n  Run: novgraph install <KEY>\n")
        return 2
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        # Bare `novgraph`: is this set up, and if not what do I do about it.
        out("novgraph " + __version__ + "  --  the Novayagraph client")
        out("")
        if not credentials.load():
            out("Not set up. Get a key at " + APP_URL + " (Manage keys), then:")
            out("    novgraph install <KEY>")
            return 1
        checks, root = doctor.run(deep=False)
        out(str(root))
        for check in checks:
            out(str(check))
        out("")
        out("Full check: novgraph doctor    All commands: novgraph --help")
        return 1 if doctor.failed(checks) else 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

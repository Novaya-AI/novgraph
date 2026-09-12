"""What an adapter is: native MCP config, plus a pointer block.

Neither alone reaches every client. Rules all of them follow -- read-modify-
write a user's config, replace between markers rather than append, warn rather
than crash on a config we cannot parse, and place a command, never a key.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .. import commands, docs

# One name everywhere. Changing it orphans every config already written.
SERVER_NAME = "novgraph"
# What 0.1.5 and earlier registered. Removed when we register, so a
# machine is not left launching two servers, one of them the old name.
LEGACY_SERVER_NAMES = ("codewiki",)

# `.agents/skills/` is read by Codex and Cursor alike, so every adapter that
# writes it must render the same bytes -- or two installs rewrite it forever.
SHARED_SKILL_FILE = ".agents/skills/{name}/SKILL.md"
SHARED_SKILL_INVOKE = "/{name}"
SHARED_SKILL_REQUEST = ("the text written after the command (`{invoke}`; "
                        "in Codex, `$` instead of `/`) in the user's message")

BLOCK_START = "# novgraph:start"
BLOCK_END = "# novgraph:end"


@dataclass
class Result:
    """What one adapter did, in terms an install report can print."""
    slug: str
    name: str
    detected: bool = False
    actions: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.detected and not self.warnings

    def act(self, text: str):
        self.actions.append(text)

    def warn(self, text: str):
        self.warnings.append(text)


def drop_legacy(servers: dict) -> list:
    """Remove entries an older release registered. Returns the names dropped."""
    return [n for n in LEGACY_SERVER_NAMES if servers.pop(n, None) is not None]


def mcp_command() -> list:
    """How a client launches our server. The shim, ABSOLUTE: a client spawns
    MCP servers from its own environment, which often has no ~/.local/bin."""
    shim = shutil.which("novgraph")
    if shim:
        return [str(Path(shim).resolve()), "mcp"]
    # A checkout, or a PATH we cannot see. The module needs no shim.
    return [sys.executable, "-m", "novaya", "mcp"]


def home() -> Path:
    return Path.home()


def config_home() -> Path:
    """XDG config root, with the Windows equivalent."""
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or (home() / "AppData" / "Roaming"))
    return Path(os.environ.get("XDG_CONFIG_HOME") or (home() / ".config"))


def read_json(path: Path):
    """(document, error). A missing file is an empty document, not an error."""
    if not path.exists():
        return {}, ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, "could not read " + str(path) + ": " + exc.strerror
    if not text.strip():
        return {}, ""
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, "not valid JSON (" + str(exc) + "): " + str(path)
    if not isinstance(doc, dict):
        return None, "expected a JSON object at the top level: " + str(path)
    return doc, ""


def write_json(path: Path, doc: dict) -> str:
    """Write a config back; a crash cannot truncate it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".novgraph-tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return str(path)


def set_block(path: Path, body: str) -> str:
    """Replace our block in a line-based config. No TOML writer in the stdlib,
    and a round-trip parser would eat the user's comments."""
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    block = BLOCK_START + "\n" + body.strip() + "\n" + BLOCK_END
    if BLOCK_START in original and BLOCK_END in original:
        head = original.split(BLOCK_START)[0]
        tail = original.split(BLOCK_END, 1)[1]
        updated = head + block + tail
    elif original.strip():
        updated = original.rstrip("\n") + "\n\n" + block + "\n"
    else:
        updated = block + "\n"
    if updated == original:
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")
    return "updated" if original else "created"


def drop_block(path: Path) -> bool:
    if not path.exists():
        return False
    original = path.read_text(encoding="utf-8")
    if BLOCK_START not in original or BLOCK_END not in original:
        return False
    head = original.split(BLOCK_START)[0]
    tail = original.split(BLOCK_END, 1)[1]
    path.write_text((head.rstrip("\n") + "\n" + tail.lstrip("\n")).strip() + "\n",
                    encoding="utf-8")
    return True


def on_path(binary: str) -> bool:
    return shutil.which(binary) is not None


def command_problem(argv) -> str:
    """'' when argv[0] is a launchable program, else why not."""
    program = str(argv[0])
    if Path(program).is_absolute():
        return "" if Path(program).exists() else (
            "registered command no longer exists: " + program
            + " -- re-run `novgraph install`")
    if shutil.which(program):
        return ""
    return "registered command is not on PATH: " + program


class Adapter:
    """One coding client. Subclasses supply paths and a config shape."""

    slug = ""
    name = ""
    instruction_file = "AGENTS.md"
    docs_url = ""

    # The served `/novgraph` command, in this client's format. `command_file` is
    # relative to the repository; "" means the client has no such mechanism.
    command_file = ""
    command_invoke = "/{name}"
    # How the body names the command, when that differs from what this client
    # types: a file shared between clients must read the same for all of them.
    command_body_invoke = ""
    command_request = "`$ARGUMENTS`"
    command_fields = ("name", "description", "argument-hint")

    def detect(self) -> bool:
        raise NotImplementedError

    def register_mcp(self, result: Result):
        """Put our server in the client's own config. Optional per client."""
        result.act("no MCP registration for this client -- shell verbs only")

    def unregister_mcp(self, result: Result):
        pass

    # -- the half every adapter shares ----------------------------------------

    def wire(self, root: Path, codebase: str = "", with_mcp: bool = True,
             specs=()) -> Result:
        result = Result(self.slug, self.name, detected=True)
        path = Path(root) / self.instruction_file
        state = docs.apply_pointer(path, codebase)
        result.act(state + " pointer block in " + self.instruction_file)
        for written, state, invoke in commands.write(root, self, specs):
            result.act(state + " " + invoke + " command in "
                       + written.relative_to(Path(root)).as_posix())
        if not with_mcp:
            # Claude Code blocks startup on an MCP server that never
            # answers: registering a broken one hangs it, not degrades it.
            result.warn("MCP not registered -- the server did not answer a "
                        "handshake (see the mcp server check)")
            return result
        try:
            self.register_mcp(result)
        except OSError as exc:
            result.warn("MCP registration failed: " + str(exc))
        return result

    def unwire(self, root: Path) -> Result:
        result = Result(self.slug, self.name, detected=True)
        if docs.remove_pointer(Path(root) / self.instruction_file):
            result.act("removed pointer block from " + self.instruction_file)
        for gone in commands.remove(root, self):
            result.act("removed " + gone.relative_to(Path(root).resolve()).as_posix())
        try:
            self.unregister_mcp(result)
        except OSError as exc:
            result.warn("MCP removal failed: " + str(exc))
        return result

    def recorded_command(self):
        """The argv this client's config will actually launch, or None."""
        return None

    def verify_mcp(self) -> str:
        """'' when this client can really start our server, else why not.

        Presence of the key is not enough. An upgrade that moves the shim
        leaves a config naming a path that no longer exists -- the client gets
        nothing and every other check still passes, which is the silent
        success this whole design exists to remove.
        """
        argv = self.recorded_command()
        if argv is None:
            return "not registered"
        if not argv:
            return "registered with an empty command"
        return command_problem(argv)


def probe_server(timeout: float = 25.0) -> str:
    """Handshake with our own server the way a client would. Registering
    proves a config has a line; this proves the line points at something."""
    argv = mcp_command()
    request = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "novgraph-doctor", "version": "1"}},
    }) + "\n"
    try:
        proc = subprocess.run(argv, input=request, capture_output=True,
                              text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return "could not start " + " ".join(argv) + ": " + str(exc)
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(doc, dict) and doc.get("id") == 1 and "result" in doc:
            return ""
    detail = (proc.stderr or "").strip().splitlines()
    return "no initialize response" + (": " + detail[-1] if detail else "")

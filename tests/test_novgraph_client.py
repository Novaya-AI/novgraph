"""The Novayagraph client: boundaries, idempotency, and the failures it exists to stop.

These tests are written against SPECIFIC past failures rather than against the
code's shape, because the code's shape is not what broke. Each one names the
bug it prevents.

Everything that could touch a real machine is redirected. `_isolated_home` is
autouse for this module: an adapter test that reached the developer's actual
~/.claude.json would rewrite their editor's MCP configuration, which has
happened in this repository before (see tests/conftest.py).
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from novaya import catalog, credentials, docs, doctor, transport, workspace  # noqa: E402
from novaya import adapters                                       # noqa: E402
from novaya.adapters import base                                  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """No test here may see, or write, a real user's configuration."""
    home = tmp_path / "home"
    home.mkdir()
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(home))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setattr(base, "home", lambda: home)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.delenv("NOVGRAPH_API_KEY", raising=False)
    monkeypatch.delenv("CODEWIKI_API_KEY", raising=False)   # the ambient one
    monkeypatch.delenv("CODEX_HOME", raising=False)
    return home


# ── the boundary ─────────────────────────────────────────────────────────────

def test_the_client_never_imports_the_engine_or_the_gateway():
    """Novayagraph is a thin client and must stay one.

    A boundary described only in a docstring erodes -- this repository says so
    in its own principles and has the scar to prove it. The moment `novaya/`
    can import `core.novgraph`, someone adds a local index "just as a
    fallback", and the local read path this architecture deliberately retired
    grows back inside the thing that replaced it.
    """
    forbidden = ("core", "gateway", "nexus", "agents", "cli", "api_server")
    offenders = []
    for path in (REPO_ROOT / "novaya").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] if node.level == 0 else []
            else:
                continue
            for name in names:
                if name.split(".")[0] in forbidden:
                    offenders.append(str(path.relative_to(REPO_ROOT)) + " -> " + name)
    assert not offenders, "novaya/ must not import the product: " + "; ".join(offenders)


def test_the_client_has_no_third_party_dependencies():
    """`uv tool install novaya` must not drag in a dependency tree."""
    import tomllib
    with open(REPO_ROOT / "pyproject.toml", "rb") as handle:
        project = tomllib.load(handle)["project"]
    assert project["dependencies"] == []
    # 3.11 is the floor because tomllib is stdlib there; codex.py imports it
    # unguarded, so lowering this without restoring a fallback breaks install.
    assert project["requires-python"] == ">=3.11"
    assert project["scripts"]["novgraph"] == "novaya.cli:main"
    # The distribution name is NOT `novgraph`: that name is taken on PyPI by an
    # unrelated, actively maintained library, and shipping under it is not
    # possible. Locked here so a future rename has to confront the reason.
    assert project["name"] == "novaya"


# ── the pointer block ────────────────────────────────────────────────────────

def test_pointer_block_is_idempotent_and_keeps_the_users_words(tmp_path):
    """The old setup APPENDED, and repos grew three contradictory sections."""
    path = tmp_path / "CLAUDE.md"
    path.write_text("# Mine\n\nMy own instructions.\n", encoding="utf-8")

    assert docs.apply_pointer(path, "repo-a") == "updated"
    first = path.read_text(encoding="utf-8")
    assert docs.apply_pointer(path, "repo-a") == "unchanged"
    assert path.read_text(encoding="utf-8") == first
    assert first.count(docs.START) == 1
    assert "My own instructions." in first

    # A changed codebase rewrites in place rather than adding a second block.
    docs.apply_pointer(path, "repo-b")
    body = path.read_text(encoding="utf-8")
    assert body.count(docs.START) == 1
    assert "repo-b" in body and "repo-a" not in body

    assert docs.remove_pointer(path) is True
    assert path.read_text(encoding="utf-8").strip() == "# Mine\n\nMy own instructions.".strip()


def test_pointer_block_collapses_a_duplicate_that_somehow_exists(tmp_path):
    path = tmp_path / "AGENTS.md"
    block = docs.pointer_block("x")
    path.write_text(block + "\n\ntext\n\n" + block + "\n", encoding="utf-8")
    docs.apply_pointer(path, "x")
    assert path.read_text(encoding="utf-8").count(docs.START) == 1


def test_the_pointer_block_carries_no_credential():
    """Discovery is written into a repository; a key never is."""
    body = docs.pointer_block("repo") + docs.rules_md()
    for forbidden in ("Bearer ", "NOVGRAPH_API_KEY=", "CODEWIKI_API_KEY="):
        assert forbidden not in body


# ── adapters ─────────────────────────────────────────────────────────────────

def test_claude_code_keeps_every_other_mcp_server(_isolated_home, tmp_path):
    """A client config is the user's, not ours. Read, modify, write back."""
    config = _isolated_home / ".claude.json"
    config.write_text(json.dumps({
        "numStartups": 12,
        "mcpServers": {"theirs": {"command": "keep-me", "args": ["--x"]}},
    }), encoding="utf-8")

    adapter = adapters.get("claude-code")
    result = adapter.wire(tmp_path, "repo")
    assert not result.warnings

    doc = json.loads(config.read_text(encoding="utf-8"))
    assert doc["numStartups"] == 12
    assert doc["mcpServers"]["theirs"] == {"command": "keep-me", "args": ["--x"]}
    assert base.SERVER_NAME in doc["mcpServers"]
    assert adapter.verify_mcp() == ""

    adapter.unwire(tmp_path)
    doc = json.loads(config.read_text(encoding="utf-8"))
    assert "theirs" in doc["mcpServers"] and base.SERVER_NAME not in doc["mcpServers"]


def test_an_unreadable_client_config_is_a_warning_not_a_crash(_isolated_home, tmp_path):
    """Never fail closed: the shell path must survive a broken JSON config."""
    (_isolated_home / ".claude.json").write_text("{not json", encoding="utf-8")
    result = adapters.get("claude-code").wire(tmp_path, "repo")
    assert result.warnings and "JSON" in result.warnings[0]
    # The pointer still landed, so the repo is still discoverable.
    assert docs.START in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


def test_codex_block_is_valid_toml_and_keeps_the_rest(_isolated_home, tmp_path):
    """A config.toml we make unparseable costs the user every other server."""
    import tomllib
    config = _isolated_home / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('model = "gpt-5"\n\n# a comment they wrote\n'
                      '[mcp_servers.theirs]\ncommand = "keep-me"\nargs = []\n',
                      encoding="utf-8")

    result = adapters.get("codex").wire(tmp_path, "repo")
    assert not result.warnings

    text = config.read_text(encoding="utf-8")
    assert "# a comment they wrote" in text          # a TOML round-trip eats these
    doc = tomllib.loads(text)
    assert doc["model"] == "gpt-5"
    assert doc["mcp_servers"]["theirs"]["command"] == "keep-me"
    server = doc["mcp_servers"][base.SERVER_NAME]
    # Windows paths are full of backslashes; a raw write produces TOML that
    # either fails to parse or parses to a different path.
    assert Path(server["command"]).name
    assert server["args"][-1] == "mcp"

    adapters.get("codex").unwire(tmp_path)
    doc = tomllib.loads(config.read_text(encoding="utf-8"))
    assert base.SERVER_NAME not in doc.get("mcp_servers", {})
    assert doc["mcp_servers"]["theirs"]["command"] == "keep-me"


def test_opencode_entry_has_opencodes_shape(_isolated_home, tmp_path):
    """Three clients, three genuinely different config shapes."""
    adapters.get("opencode").wire(tmp_path, "repo")
    config = _isolated_home / ".config" / "opencode" / "opencode.json"
    entry = json.loads(config.read_text(encoding="utf-8"))["mcp"][base.SERVER_NAME]
    assert entry["type"] == "local"
    assert entry["enabled"] is True
    assert isinstance(entry["command"], list) and entry["command"][-1] == "mcp"


def test_mcp_is_not_registered_when_the_server_cannot_start(_isolated_home, tmp_path):
    """Claude Code BLOCKS on an MCP server that never answers.

    Registering one that cannot start does not degrade the client, it hangs it
    -- so a failed handshake must leave the config alone and still deliver the
    pointer block.
    """
    adapter = adapters.get("claude-code")
    result = adapter.wire(tmp_path, "repo", with_mcp=False)
    assert result.warnings
    assert not (_isolated_home / ".claude.json").exists()
    assert docs.START in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


def test_a_registered_command_that_no_longer_exists_is_a_failure(
        _isolated_home, tmp_path):
    """The upgrade bug, as a test.

    An upgrade that moves the shim leaves a config naming a path that is gone.
    Checking only that the SERVER NAME is a key in the config reported PASS
    while the client launched nothing -- verified by hand before this existed.
    """
    adapter = adapters.get("claude-code")
    adapter.wire(tmp_path, "repo")
    assert adapter.verify_mcp() == ""

    config = _isolated_home / ".claude.json"
    doc = json.loads(config.read_text(encoding="utf-8"))
    doc["mcpServers"][base.SERVER_NAME]["command"] = str(tmp_path / "gone.exe")
    config.write_text(json.dumps(doc), encoding="utf-8")

    problem = adapter.verify_mcp()
    assert "no longer exists" in problem
    # and it is registered, so doctor must grade it FAIL rather than WARN
    assert adapter.recorded_command() is not None


def test_generated_files_carry_no_version(tmp_path):
    """A version in the header churns a committed directory whenever two
    teammates run different clients. Content is the only identity needed."""
    assert "0.1.0" not in docs.GENERATED_HEADER
    docs.write_all(tmp_path, CATALOG, "repo", "https://git/o/r.git")
    body = (tmp_path / ".novgraph" / "rules.md").read_text(encoding="utf-8")
    assert "Generated by `novgraph install`" in body


def test_blueprint_commits_no_machine_facts(tmp_path):
    """It is a COMMITTED file. One developer's credential path and wired
    agents have no business in everybody else's checkout."""
    docs.write_all(tmp_path, CATALOG, "repo", "https://git/o/r.git")
    body = (tmp_path / ".novgraph" / "blueprint.md").read_text(encoding="utf-8")
    for leaked in ("Credential store", "Agents wired", "Installed by",
                   "DPAPI", "Keychain", str(Path.home())):
        assert leaked not in body, leaked


def test_every_adapter_is_reachable_from_the_registry():
    """One declaration: install, doctor, `adapters` and the docs all read it."""
    assert set(adapters.SLUGS) == {"claude-code", "codex", "opencode", "cursor",
                                   "windsurf", "gemini-cli", "copilot", "cline"}
    for slug in adapters.SLUGS:
        adapter = adapters.get(slug)
        assert adapter.instruction_file in ("CLAUDE.md", "AGENTS.md", "GEMINI.md",
                                            ".github/copilot-instructions.md")
        assert adapter.name and adapter.docs_url
    chosen, unknown = adapters.resolve(["claude-code", "nope"])
    assert [a.slug for a in chosen] == ["claude-code"] and unknown == ["nope"]
    assert len(adapters.resolve(["all"])[0]) == len(adapters.ADAPTERS)


# ── credentials ──────────────────────────────────────────────────────────────

@pytest.fixture
def _file_backend(monkeypatch):
    """Force the portable backend: no keychain prompt, no PowerShell, in CI."""
    monkeypatch.setattr(credentials, "preferred_backend", lambda: "file")
    monkeypatch.setattr(credentials, "_WINDOWS", False)
    monkeypatch.setattr(credentials, "_MACOS", False)


def test_a_stored_key_survives_and_can_be_cleared(_file_backend):
    info = credentials.store("key-abc")
    assert info["backend"] == "file"
    assert credentials.load_stored() == "key-abc"
    assert credentials.load() == "key-abc"
    assert credentials.clear()
    assert credentials.load_stored() == ""


def test_the_store_beats_an_inherited_key_but_not_an_explicit_one(
        _file_backend, monkeypatch):
    """The precedence rule, which is the whole reason this module exists.

    An agent's shell frequently carries a stale CODEWIKI_API_KEY it never
    chose; the machine's own credential must win over that. NOVGRAPH_API_KEY is
    somebody deliberately overriding, so it wins over everything.
    """
    credentials.store("stored")
    monkeypatch.setenv(credentials.ENV_AMBIENT, "inherited-and-stale")
    assert credentials.load() == "stored"
    monkeypatch.setenv(credentials.ENV_EXPLICIT, "deliberate")
    assert credentials.load() == "deliberate"


def test_the_loader_hint_never_contains_the_key(_file_backend):
    credentials.store("super-secret-value")
    hint = credentials.loader_hint("file")
    assert "super-secret-value" not in hint
    assert "super-secret-value" not in credentials.source()


def test_windows_dpapi_helper_excludes_powershell_7_modules(
        monkeypatch, tmp_path):
    """PowerShell 7's modules break Security-module loading in powershell.exe.

    Python preserves the parent's mixed PSModulePath while a PowerShell parent
    normally repairs it when launching Windows PowerShell. The credential
    helper is launched by Python, so it has to make that edition boundary
    explicit itself.
    """
    for name in tuple(credentials.os.environ):
        if name.casefold() == "psmodulepath":
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "PSMODULEPATH",
        r"C:\Program Files\PowerShell\Modules;"
        r"C:\Windows\System32\WindowsPowerShell\v1.0\Modules",
    )
    captured = {}

    def fake_run(argv, stdin_text="", timeout=20.0, env=None):
        captured.update(env or {})
        return None

    monkeypatch.setattr(credentials, "_run", fake_run)
    credentials._powershell("irrelevant", tmp_path / "key.dpapi")

    module_key = next(
        name for name in captured if name.casefold() == "psmodulepath")
    paths = captured[module_key].split(";")
    assert paths
    assert all("windowspowershell" in path.casefold() for path in paths)
    assert not any(r"\PowerShell\Modules" in path and
                   r"\WindowsPowerShell\Modules" not in path for path in paths)


# ── which repository ─────────────────────────────────────────────────────────

def test_the_codebase_is_matched_on_the_origin(tmp_path):
    """The runner clones a URL, so the URL is the repository's identity."""
    root = tmp_path / "some-local-folder-name"
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "config").write_text(
        '[remote "origin"]\n'
        '\turl = https://github.com/Owner/sample-project.git\n',
        encoding="utf-8")
    assert workspace.match_codebase(
        ["something-else", "sample-project"], root
    ) == "sample-project"


def test_credentials_are_stripped_out_of_a_recorded_origin(tmp_path):
    root = tmp_path / "r"
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "config").write_text(
        '[remote "origin"]\n\turl = https://user:ghp_secret@github.com/o/r.git\n',
        encoding="utf-8")
    origin = workspace.origin_url(root)
    assert origin == "https://github.com/o/r.git" and "ghp_secret" not in origin


def test_an_ambiguous_or_absent_match_returns_nothing(tmp_path):
    """A wrong codebase gives confident answers about someone else's repo.

    There is no error to notice, which is why this must return "" and let
    `install` say so rather than pick the plausible one.
    """
    root = tmp_path / "widgets"
    root.mkdir()
    assert workspace.match_codebase(["alpha", "beta"], root) == ""
    assert workspace.match_codebase([], root) == ""


def test_a_remembered_codebase_round_trips(_file_backend, tmp_path):
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    workspace.remember(root, "proj-graph")
    assert workspace.codebase_for(root) == "proj-graph"
    assert workspace.forget(root) is True
    assert workspace.codebase_for(root) == ""


# ── reading the server's prose ───────────────────────────────────────────────

def test_codebase_names_are_read_without_swallowing_the_decoration():
    """The listing is prose with a rule and a signature line.

    A loose parser returned a row of box characters and the word "Novaya" as
    codebase names -- which `install` would then have offered to bind a
    checkout to.
    """
    listing = {"text": (
        "  sample-project — 967 files, 10 subsystems\n"
        "  second-repo — 3 files\n"
        "\n"
        # Parenthesised on purpose: implicit literal concatenation binds
        # tighter than `*`, so without them this multiplies the whole
        # preceding block by 40 instead of the rule character.
        + ("─" * 40) + "\n"
        + "◆ Novayagraph · listed the codebases this key can read")}
    assert doctor._names_in(listing) == ["sample-project", "second-repo"]


def test_the_structured_field_wins_over_the_prose_that_broke_it():
    """REGRESSION, from production.

    The live listing gained a closing sentence beginning "Name one explicitly
    on every repository call", and the scraper offered "Name" as a codebase.
    The fix was server-side -- a `codebases` field -- which reaches clients
    already installed precisely because they prefer it when it is there.
    """
    listing = {
        "text": ("  sample-project \u2014 967 files, 10 subsystems\n"
                 "        https://github.com/o/r @ 79d1cf63b5 (main)\n\n"
                 "Name one explicitly on every repository call \u2014 the remote "
                 "URL works too."),
        "codebases": [{"codebase": "sample-project",
                       "origin_url": "https://github.com/o/r", "files": 967}],
    }
    assert doctor._names_in(listing) == ["sample-project"]

    # Without the field, the old scraper still trips on that sentence -- which
    # is why the fix belonged on the server, where it reaches every client.
    assert "Name" in doctor._names_in({"text": listing["text"]})


def test_structured_listings_are_preferred_when_the_api_sends_them():
    assert doctor._names_in({"codebases": ["a", {"name": "b"}]}) == ["a", "b"]


# ── the generated files ──────────────────────────────────────────────────────

CATALOG = {
    "instructions": "Novayagraph serves indexed repository structure.",
    "tools": [{"type": "function", "function": {
        "name": "novgraph_why",
        "description": "The recorded reasoning behind a file.",
        "parameters": {"type": "object",
                       "properties": {"target": {"type": "string",
                                                 "description": "a path"}},
                       "required": ["target"]}}}],
}


def test_the_three_files_say_three_different_things(tmp_path):
    written = docs.write_all(tmp_path, CATALOG, "repo-x", "https://git/o/r.git")
    assert [state for _p, state in written] == ["created"] * 3
    # Regenerating with identical inputs must not churn: a generated file that
    # always shows dirty gets gitignored, and then stops being shared.
    assert [state for _p, state in
            docs.write_all(tmp_path, CATALOG, "repo-x", "https://git/o/r.git")] \
        == ["unchanged"] * 3

    rules = (tmp_path / ".novgraph" / "rules.md").read_text(encoding="utf-8")
    skills = (tmp_path / ".novgraph" / "skills.md").read_text(encoding="utf-8")
    blueprint = (tmp_path / ".novgraph" / "blueprint.md").read_text(encoding="utf-8")

    assert "cross-check" in rules                       # method
    assert "novgraph_why" in skills or "novgraph why" in skills   # the surface
    assert "repo-x" in blueprint and "https://git/o/r.git" in blueprint  # this repo
    # The catalog is the source for skills.md, so a tool the server does not
    # serve cannot appear in it.
    assert "novgraph_impact" not in skills


def test_an_unindexed_checkout_says_so_instead_of_inventing_a_name(tmp_path):
    docs.write_all(tmp_path, CATALOG, "", "")
    blueprint = (tmp_path / ".novgraph" / "blueprint.md").read_text(encoding="utf-8")
    assert "not indexed yet" in blueprint
    assert "app.trynovaya.com" in blueprint


# ── the MCP server ───────────────────────────────────────────────────────────

def test_the_mcp_server_serves_the_cache_with_no_key(_file_backend, monkeypatch):
    """An agent shown zero tools decides the integration is broken.

    With no key and no network the cache written at install is the floor -- a
    real tool list, whose calls fail with a message that names the fix.
    """
    from novaya import mcp
    catalog.save(CATALOG)
    server = mcp.Server()
    tools = server.schemas()
    assert [t["name"] for t in tools] == ["novgraph_why"]
    assert tools[0]["inputSchema"]["required"] == ["target"]

    text, failed = server.call("novgraph_why", {"target": "x"})
    assert failed and "novgraph install" in text


def test_the_mcp_server_supplies_the_codebase(_file_backend, monkeypatch):
    """The launch directory decides the repository, resolved once at install."""
    from novaya import mcp
    sent = {}

    def fake_call(key, tool, args):
        sent.update({"tool": tool, "args": args})
        return {"text": "ok"}

    monkeypatch.setattr(mcp.credentials, "load", lambda: "k")
    monkeypatch.setattr(mcp.transport, "call", fake_call)
    server = mcp.Server()
    server._codebase = "bound-repo"

    server.call("novgraph_why", {"target": "a.py"})
    assert sent["args"]["codebase"] == "bound-repo"
    # An explicit argument still wins: cross-repo questions must stay possible.
    server.call("novgraph_why", {"target": "a.py", "codebase": "other"})
    assert sent["args"]["codebase"] == "other"


def test_the_mcp_server_answers_a_handshake(_file_backend, capsys):
    from novaya import mcp
    server = mcp.Server()
    server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": mcp.PROTOCOL_VERSION}})
    reply = json.loads(capsys.readouterr().out.strip())
    assert reply["result"]["protocolVersion"] == mcp.PROTOCOL_VERSION
    assert reply["result"]["serverInfo"]["name"] == base.SERVER_NAME
    # A notification must produce no reply at all, or the client desynchronises.
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert capsys.readouterr().out == ""


# ── the key, and wiring one client ───────────────────────────────────────────

def test_the_positional_tells_a_key_from_a_client_name():
    """One positional on `install`, and the rule for reading it is written
    down rather than inferred by whoever touches it next."""
    assert adapters.looks_like_an_agent("claude")
    assert adapters.looks_like_an_agent("gemini-cli")
    assert not adapters.looks_like_an_agent("cwk_" + "a" * 43)
    assert not adapters.looks_like_an_agent("cwk_SHORTBUTUPPER")
    assert not adapters.looks_like_an_agent("")


def test_the_name_people_type_resolves_to_the_adapter():
    assert adapters.canonical("claude") == "claude-code"
    assert adapters.canonical("CC") == "claude-code"
    assert adapters.canonical("open-code") == "opencode"
    chosen, unknown = adapters.resolve(["claude"])
    assert [a.slug for a in chosen] == ["claude-code"] and not unknown


def test_install_refuses_a_client_name_instead_of_guessing(
        _file_backend, capsys, tmp_path):
    """`novgraph install claude` installs nothing named claude.

    It registers a client already on the machine. Refused rather than guessed,
    and the error names the command that does mean that -- plus the fact that
    setup already wired everything, so the step is usually unnecessary.
    """
    from novaya import cli
    assert cli.main(["install", "claude", "--root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "takes an API key, not a client name" in err
    assert "already wires every client it finds" in err
    assert "novgraph wire claude" in err


def test_wire_names_a_client_it_cannot_do(_file_backend, capsys, tmp_path,
                                          monkeypatch):
    """`novgraph wire grok` must not silently do nothing."""
    from novaya import cli
    monkeypatch.setattr(cli.credentials, "load", lambda: "k")
    monkeypatch.setattr(cli.adapters, "probe_server", lambda: "")
    assert cli.main(["wire", "grok", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "no adapter for 'grok' yet" in out


def test_wire_registers_one_client_without_touching_the_key(
        _isolated_home, _file_backend, tmp_path, monkeypatch):
    """Wiring is not setup: no key is stored, no codebase is resolved.

    The repo needs a real .git, or workspace.root_for walks UP out of tmp_path
    into whatever repository encloses it -- which on this machine is the home
    directory, and an earlier version of this test wrote a CLAUDE.md there.
    """
    from novaya import cli
    (tmp_path / ".git").mkdir()
    credentials.store("cwk_" + "d" * 43)
    monkeypatch.setattr(cli.adapters, "probe_server", lambda: "")
    monkeypatch.setattr(cli.adapters, "resolve",
                        lambda names: ([adapters.get("claude-code")], []))
    assert cli.main(["wire", "claude", "--root", str(tmp_path)]) == 0
    assert docs.START in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert credentials.load_stored() == "cwk_" + "d" * 43


def test_key_reports_where_it_is_without_printing_it(_file_backend, capsys):
    """Rotation is its own act: `install` also replaces the key, but then
    resolves a codebase and rewires clients -- work a leaked key does not
    need, and which fails noisily from the wrong directory."""
    from novaya import cli
    credentials.store("super-secret-value")
    assert cli.main(["key"]) == 0
    out = capsys.readouterr().out
    assert "credential store" in out
    assert "super-secret-value" not in out


def test_key_with_no_key_anywhere_says_what_to_run(_file_backend, capsys):
    from novaya import cli
    assert cli.main(["key"]) == 1
    assert "novgraph key <KEY>" in capsys.readouterr().out


def test_key_stores_verifies_and_proves_the_new_one_works(
        _file_backend, capsys, monkeypatch):
    """A stored key the API rejects is worse than no key: the user walks away
    believing rotation worked."""
    from novaya import cli
    monkeypatch.setattr(cli.catalog, "refresh", lambda key: CATALOG)
    # The real check spawns a subprocess, which cannot see an in-process
    # backend patch. Persistence is covered by
    # test_a_stored_key_survives_and_can_be_cleared and the end-to-end runs.
    monkeypatch.setattr(cli.credentials, "verify_separate_process", lambda: True)
    assert cli.main(["key", "cwk_" + "b" * 43]) == 0
    out = capsys.readouterr().out
    assert "verified: a separate process can read it back" in out
    assert "accepted by" in out
    assert credentials.load_stored() == "cwk_" + "b" * 43

    def reject(key):
        raise transport.ApiError(401, "This API key was not recognised.")
    monkeypatch.setattr(cli.catalog, "refresh", reject)
    assert cli.main(["key", "cwk_" + "c" * 43]) == 2
    assert "the API rejected it" in capsys.readouterr().out


def test_removing_our_block_removes_a_file_we_created(tmp_path):
    """uninstall must leave no trace of what it made.

    When the block is the whole file, writing back "" left a 0-byte CLAUDE.md
    that reads like the user's own.
    """
    ours = tmp_path / "AGENTS.md"
    docs.apply_pointer(ours, "repo")
    assert docs.remove_pointer(ours) is True
    assert not ours.exists()

    theirs = tmp_path / "CLAUDE.md"
    theirs.write_text("# Mine\n", encoding="utf-8")
    docs.apply_pointer(theirs, "repo")
    docs.remove_pointer(theirs)
    assert theirs.read_text(encoding="utf-8").strip() == "# Mine"


# ── staying current ──────────────────────────────────────────────────────────

def test_the_notice_appears_once_a_day_not_once_a_call(_file_backend):
    """An upgrade line on every answer stops being read after the second one,
    and inside a coding agent it competes with the answer itself."""
    from novaya import service
    envelope = {"client_latest": "9.9.9", "client_min": "0.0.1"}
    first = service.upgrade_line(envelope)
    assert "9.9.9" in first and "novgraph upgrade" in first
    assert service.upgrade_line(envelope) == ""          # same day, same version
    # A NEWER release breaks through rather than waiting out the day.
    assert "9.9.10" in service.upgrade_line({"client_latest": "9.9.10"})


def test_a_client_below_the_floor_is_told_every_time(_file_backend):
    """Below client_min the server no longer serves this client. That is not
    a once-a-day courtesy."""
    from novaya import service
    line = service.upgrade_line({"client_min": "9.9.9"})
    assert "REQUIRED" in line
    assert service.upgrade_line({"client_min": "9.9.9"}) == line   # not silenced


def test_no_notice_when_the_server_says_nothing(_file_backend):
    """An older server sends no envelope; everything degrades to a no-op."""
    from novaya import service
    assert service.upgrade_line(None) == ""
    assert service.upgrade_line({}) == ""


def test_the_catalog_refreshes_only_when_the_surface_moved(
        _file_backend, monkeypatch):
    """The version rides in on a call the user was already making, so a
    refresh costs a request only when something actually changed."""
    from novaya import catalog, transport
    calls = []
    monkeypatch.setattr(transport, "catalog",
                        lambda key: (calls.append(key), CATALOG)[1])
    monkeypatch.setattr(catalog.credentials, "load", lambda: "k")

    catalog.save({**CATALOG, "service": {"catalog_version": "aaa"}})
    transport.last_service.clear()

    transport.last_service.update({"catalog_version": "aaa"})
    assert catalog.sync_if_stale() is False and calls == []      # unchanged

    transport.last_service.update({"catalog_version": "bbb"})
    assert catalog.sync_if_stale() is True and len(calls) == 1   # moved

    transport.last_service.clear()
    assert catalog.sync_if_stale() is False                      # old server


def test_mcp_instructions_come_from_the_server_too(_file_backend):
    """LAW 22 applies to BOTH surfaces, or method drifts between them.

    The MCP system prompt carried a hardcoded copy -- a third declaration of
    method, frozen at install, while rules.md had already moved to the server.
    An agent would then be told one thing natively and another by the file.
    """
    from novaya import mcp
    served = "# Served method\n\nDo it this way."
    catalog.save(dict(CATALOG, guidance=served))
    assert mcp.Server().instructions() == served

    # Offline, the shipped copy stands in rather than sending nothing.
    catalog.save(CATALOG)
    assert mcp.Server().instructions() == mcp.FALLBACK_INSTRUCTIONS


def test_guidance_comes_from_the_server_when_it_sends_any(tmp_path):
    """LAW 16 applied to prose: improving method must reach a client that was
    installed months ago, without an upgrade."""
    served = dict(CATALOG, guidance="# Served rules\n\nDo it this way.")
    docs.write_all(tmp_path, served, "repo")
    body = (tmp_path / ".novgraph" / "rules.md").read_text(encoding="utf-8")
    assert "Served rules" in body
    assert "cross-check" not in body            # the shipped fallback stood down

    docs.write_all(tmp_path, CATALOG, "repo")   # server sends none
    body = (tmp_path / ".novgraph" / "rules.md").read_text(encoding="utf-8")
    assert "cross-check" in body                # fallback carries it offline


def test_upgrade_knows_every_repository_it_bound(_file_backend, tmp_path):
    """A user who installed months ago will not remember where they ran it."""
    one, two = tmp_path / "one", tmp_path / "two"
    for r in (one, two):
        (r / ".git").mkdir(parents=True)
    workspace.remember(one, "alpha")
    workspace.remember(two, "beta")
    assert [(r.name, c) for r, c in workspace.bound_roots()] == \
        [("one", "alpha"), ("two", "beta")]

    # A checkout the user deleted is not offered for re-sync.
    import shutil as _sh
    _sh.rmtree(two)
    assert [r.name for r, _ in workspace.bound_roots()] == ["one"]


# ── the command ──────────────────────────────────────────────────────────────

def test_the_verbs_are_generated_from_the_catalog(_file_backend):
    """LAW 16: a new server tool becomes a command with no client release."""
    catalog.save({"tools": [
        {"function": {"name": "novgraph_why", "description": "Recorded reasoning.",
                      "parameters": {"type": "object", "properties": {
                          "target": {"type": "string", "description": "a path"},
                          "limit": {"type": "integer", "description": "how many"},
                          "codebase": {"type": "string"}},
                          "required": ["target"]}}},
        {"function": {"name": "codewiki_brand_new", "description": "Invented today.",
                      "parameters": {"type": "object", "properties": {}}}},
    ]})
    from novaya import cli
    verbs = set(cli.build_parser()._subparsers._group_actions[0].choices)
    assert {"why", "brand-new"} <= verbs

    args = cli.build_parser().parse_args(["why", "a.py", "--limit", "3"])
    assert args.tool.name == "novgraph_why"
    assert args.target == ["a.py"] and args.limit == 3


def test_no_module_restates_the_tool_surface():
    """LAW 16, structurally.

    Naming one tool to call it is fine. A COLLECTION of tool names in a literal
    is a second declaration of the surface, and the drift starts there.
    """
    offenders = []
    for path in (REPO_ROOT / "novaya").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Dict, ast.List, ast.Tuple, ast.Set)):
                continue
            names = {n.value for n in ast.walk(node)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)
                     and n.value.startswith("novgraph_")}
            if len(names) > 2:
                offenders.append(str(path.relative_to(REPO_ROOT))
                                 + " line " + str(node.lineno))
    assert not offenders, ("the tool surface is declared by the server: "
                           + "; ".join(offenders))


def test_a_verb_is_derived_from_the_tool_name():
    tool = catalog.Tool("novgraph_record_why", "", {"why": {}}, ("why",))
    assert tool.verb == "record-why" and tool.positional == "why"
    # `codebase` is shared, never the positional.
    optional = catalog.Tool("novgraph_summary", "", {"codebase": {}}, ())
    assert optional.positional == ""


def test_the_command_says_the_verbs_come_from_the_server(_file_backend, capsys):
    """Before any install there is no catalog, so there are no verbs. Say that
    rather than argparse's "invalid choice"."""
    from novaya import cli
    assert cli.main(["summary"]) == 2
    assert "novgraph install" in capsys.readouterr().err


def test_a_known_verb_with_no_key_reports_the_missing_setup(
        _file_backend, capsys):
    catalog.save(CATALOG)
    from novaya import cli
    assert cli.main(["why", "a.py"]) == 2
    assert "novgraph install" in capsys.readouterr().err


def test_call_rejects_arguments_that_are_not_an_object(_file_backend, capsys):
    from novaya import cli
    assert cli.main(["call", "novgraph_why", "--json", "[1,2]"]) == 2
    assert "JSON object" in capsys.readouterr().err


@pytest.mark.parametrize("repo, status", [
    ({"state": "current", "remote_head": "b" * 40, "indexed_heads": {"cb": "b" * 40}}, doctor.OK),
    ({"state": "behind", "remote_head": "b" * 40, "indexed_heads": {"cb": "a" * 40}}, doctor.WARN),
    ({"state": "error", "error": "git host needs reconnecting",
      "indexed_heads": {"cb": "a" * 40}}, doctor.WARN),
    ({"state": "current", "indexed_heads": {"other": "a" * 40}}, doctor.WARN),
    ({"state": "current", "remote_head": "b" * 40, "indexed_heads": {"cb": "b" * 40},
      "hook": {"state": "needs_reconnect"}}, doctor.WARN),
])
def test_doctor_grades_graph_freshness(monkeypatch, repo, status):
    """A full graph that stopped updating passed every other check."""
    monkeypatch.setattr(transport, "request", lambda key, method, path, *a, **k:
                        {"graph_sync": {"repositories": [repo]}})
    check = doctor._freshness("key", "cb")
    assert check.status == status
    if repo["state"] == "error":
        assert "NOT UPDATING" in check.detail and "reconnecting" in check.detail


def test_an_mcp_session_tags_every_call_with_its_session_and_agent(monkeypatch):
    """REST calls carried no session, so `novgraph` agents had no per-session
    dedup and no per-session savings. One `novgraph mcp` process = one session."""
    from novaya import mcp
    monkeypatch.setattr(transport, "SESSION", {"id": "", "agent": ""})
    assert "X-Novayagraph-Session" not in transport._headers("k"), "a shell call sends none"
    sent = []
    monkeypatch.setattr(mcp.Server, "_send", lambda self, mid, result: sent.append(result))
    server = mcp.Server()
    server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"clientInfo": {"name": "claude-code"}}})
    h = transport._headers("k")
    assert len(h["X-Novayagraph-Session"]) == 32 and h["X-Novayagraph-Agent"] == "claude-code"
    first = h["X-Novayagraph-Session"]
    mcp.Server()
    assert transport._headers("k")["X-Novayagraph-Session"] != first, "a new process, a new session"


def test_doctor_does_not_read_a_missing_summary_as_content(monkeypatch, tmp_path):
    """"No summary has been pushed for X. Call overview ..." is over 80
    characters, and the content check passed on it."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    workspace.remember(root, "cb")
    monkeypatch.setattr(doctor.credentials, "load", lambda: "k")
    monkeypatch.setattr(doctor.credentials, "load_stored", lambda: "")
    monkeypatch.setattr(doctor.catalog, "refresh", lambda key: {"tools": []})
    monkeypatch.setattr(doctor.adapters, "detected", lambda: [])
    monkeypatch.setattr(doctor, "_freshness", lambda key, cb: doctor.Check("f", doctor.OK))

    def call(key, tool, args):
        if tool == "novgraph_codebases":
            return {"codebases": ["cb"]}
        return {"text": "No summary has been pushed for cb. Call overview for the "
                        "structural picture."}
    monkeypatch.setattr(doctor.transport, "call", call)
    checks, _ = doctor.run(root, deep=True)
    row = next(c for c in checks if c.name == "graph content")
    assert row.status == doctor.FAIL


# ── 0.1.7 ────────────────────────────────────────────────────────────────────

def _checkout(tmp_path, folder, url):
    root = tmp_path / folder
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "config").write_text(
        '[remote "origin"]\n\turl = ' + url + "\n", encoding="utf-8")
    return root


def test_a_checkout_binds_to_the_graph_of_its_own_remote(tmp_path):
    """`acme/api` and `other/api` are indexed as `api` and `other-api`. Matching
    on the name bound a checkout of `other/api` to acme's graph."""
    names = ["api", "other-api"]
    origins = {"api": "https://github.com/acme/api",
               "other-api": "https://github.com/other/api"}
    root = _checkout(tmp_path, "api", "git@github.com:Other/api.git")
    assert workspace.match_codebase(names, root, origins) == "other-api"

    # A remote nothing was indexed from never borrows a same-named graph.
    stranger = _checkout(tmp_path, "s/api", "https://github.com/third/api")
    assert workspace.match_codebase(names, stranger, origins) == ""

    # A graph with no recorded remote still matches by name, as before.
    assert workspace.match_codebase(["api"], stranger, {"api": ""}) == "api"

    # One remote indexed under two names is for the user to pick.
    twice = {"a": "https://github.com/other/api", "b": "https://github.com/other/api.git"}
    assert workspace.match_codebase(["a", "b"], root, twice) == ""

    # An older server with no structured listing keeps the old matching.
    assert workspace.match_codebase(names, root) == "api"


def _doctor_stubs(monkeypatch, listing, served=None):
    monkeypatch.setattr(doctor.credentials, "load", lambda: "k")
    monkeypatch.setattr(doctor.credentials, "load_stored", lambda: "")
    monkeypatch.setattr(doctor.catalog, "refresh",
                        lambda key: (catalog.save(served or CATALOG), served or CATALOG)[1])
    monkeypatch.setattr(doctor.adapters, "detected", lambda: [])
    monkeypatch.setattr(doctor, "_freshness", lambda key, cb: doctor.Check("f", doctor.OK))
    monkeypatch.setattr(doctor.transport, "call", lambda key, tool, args:
                        listing if tool == "novgraph_codebases" else {"text": "x" * 200})


def test_doctor_fails_a_binding_to_another_repositorys_graph(
        _file_backend, monkeypatch, tmp_path):
    """0.1.6 bound by name, so such bindings exist on machines already. Every
    answer describes the wrong repository and no other check notices."""
    root = _checkout(tmp_path, "api", "https://github.com/other/api.git")
    workspace.remember(root, "api")
    _doctor_stubs(monkeypatch, {"codebases": [
        {"codebase": "api", "origin_url": "https://github.com/acme/api"},
        {"codebase": "other-api", "origin_url": "https://github.com/other/api"}]})
    row = next(c for c in doctor.run(root, deep=False)[0] if c.name == "codebase")
    assert row.status == doctor.FAIL and "acme/api" in row.detail
    assert "novgraph install" in row.detail

    workspace.remember(root, "other-api")
    row = next(c for c in doctor.run(root, deep=False)[0] if c.name == "codebase")
    assert row.status == doctor.OK


def test_doctor_reads_the_generated_files_not_just_their_names(
        _file_backend, monkeypatch, tmp_path):
    """skills.md kept a retired tool description while doctor passed: it only
    checked that the file existed."""
    root = _checkout(tmp_path, "repo", "https://github.com/o/repo")
    workspace.remember(root, "repo")
    docs.write_all(root, CATALOG, "repo", "https://github.com/o/repo")
    _doctor_stubs(monkeypatch, {"codebases": [
        {"codebase": "repo", "origin_url": "https://github.com/o/repo"}]})
    rows = {c.name: c for c in doctor.run(root, deep=False)[0]}
    assert rows[".novgraph/skills.md"].status == doctor.OK

    (root / ".novgraph" / "skills.md").write_text("an older surface\n", encoding="utf-8")
    rows = {c.name: c for c in doctor.run(root, deep=False)[0]}
    assert rows[".novgraph/skills.md"].status == doctor.WARN


def test_any_refresh_that_moves_the_catalog_rewrites_bound_repositories(
        _file_backend, monkeypatch, tmp_path):
    """MCP session start and doctor refreshed the cache without resyncing; the
    next call then saw equal versions, so the files never caught up."""
    from novaya import sync
    root = _checkout(tmp_path, "repo", "https://github.com/o/repo")
    workspace.remember(root, "repo")
    old = {**CATALOG, "service": {"catalog_version": "old"}}
    catalog.save(old)
    docs.write_all(root, old, "repo")

    new = {**CATALOG, "service": {"catalog_version": "new"},
           "tools": [{"type": "function", "function": {
               "name": "novgraph_why", "description": "Reworded today.",
               "parameters": {"type": "object", "properties": {}}}}]}
    monkeypatch.setattr(transport, "catalog", lambda key: new)
    sync.refresh("k")
    assert "Reworded today." in (root / ".novgraph" / "skills.md").read_text(encoding="utf-8")

    # Unmoved, nothing is rewritten.
    (root / ".novgraph" / "skills.md").write_text("left alone\n", encoding="utf-8")
    sync.refresh("k")
    assert (root / ".novgraph" / "skills.md").read_text(encoding="utf-8") == "left alone\n"


def test_a_call_version_the_listing_never_reports_does_not_resync(
        _file_backend, monkeypatch):
    """A server whose call envelope disagrees with its listing made every call
    refetch and resync. Only a refetch that moved the cache counts."""
    catalog.save({**CATALOG, "service": {"catalog_version": "listed"}})
    monkeypatch.setattr(transport, "catalog",
                        lambda key: {**CATALOG, "service": {"catalog_version": "listed"}})
    transport.last_service.clear()
    transport.last_service.update({"catalog_version": "from-a-call"})
    assert catalog.sync_if_stale("k") is False


def test_a_numeric_positional_reaches_the_server_as_a_number(_file_backend, monkeypatch):
    """`novgraph recent 5` sent "5" and the server refused it as not an integer."""
    catalog.save({"tools": [{"function": {
        "name": "novgraph_recent", "description": "Recent commits.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "how many"},
            "codebase": {"type": "string"}}}}}]})
    from novaya import cli
    sent = {}
    monkeypatch.setattr(cli, "run_tool", lambda name, payload, args: sent.update(payload) or 0)
    assert cli.main(["recent", "5"]) == 0 and sent == {"limit": 5}
    sent.clear()
    assert cli.main(["recent"]) == 0 and sent == {}


def test_the_mcp_server_negotiates_the_protocol_and_announces_tool_changes(
        _file_backend, monkeypatch, capsys):
    from novaya import mcp
    server = mcp.Server()
    for asked, answered in (("2025-06-18", "2025-06-18"), ("2024-11-05", "2024-11-05"),
                            ("1999-01-01", mcp.PROTOCOL_VERSION), (None, mcp.PROTOCOL_VERSION)):
        server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": asked}})
        reply = json.loads(capsys.readouterr().out.strip())
        assert reply["result"]["protocolVersion"] == answered
        assert reply["result"]["capabilities"]["tools"]["listChanged"] is True

    catalog.save(CATALOG)
    monkeypatch.setattr(mcp.credentials, "load", lambda: "k")
    monkeypatch.setattr(mcp.transport, "call", lambda key, tool, args: {"text": "ok"})
    monkeypatch.setattr(mcp.sync, "resync", lambda *a: 0)
    moved = iter([True, False])
    monkeypatch.setattr(mcp.catalog, "sync_if_stale", lambda key: next(moved))
    for expect_notice in (True, False):
        server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                       "params": {"name": "novgraph_why", "arguments": {}}})
        lines = [json.loads(x) for x in capsys.readouterr().out.strip().splitlines()]
        assert lines[0]["id"] == 2, "the answer goes first"
        assert (len(lines) == 2 and lines[1]["method"]
                == "notifications/tools/list_changed") is expect_notice


def test_adapter_names_never_run_into_the_status_column(capsys, monkeypatch):
    from novaya import cli
    monkeypatch.setattr(base.Adapter, "detect", lambda self: False, raising=False)
    cli.cmd_adapters(None)
    rows = [l for l in capsys.readouterr().out.splitlines() if l.endswith("not found")]
    assert rows and all("  not found" in r for r in rows)

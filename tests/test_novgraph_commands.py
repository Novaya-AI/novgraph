"""The `/novgraph` command: served once, rendered per agent, removed cleanly."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from novaya import adapters, catalog, commands, docs, sync, workspace  # noqa: E402
from novaya.adapters import base                                     # noqa: E402

SPEC = {"name": "novgraph", "description": "Novayagraph workflows: review, brief.",
        "argument_hint": "review | brief <task>",
        "workflows": ["review", "brief"],
        "body": "# {invoke}\n\nThe request: {request}\n\nNext: {invoke} brief x\n"}
CAT = {"tools": [], "guidance": "# Rules\n\nServed.", "commands": [SPEC]}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
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
    monkeypatch.delenv("CODEX_HOME", raising=False)
    return home


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    return root


def _front(text: str) -> dict:
    head = text.split("---", 2)[1]
    return dict(line.split(": ", 1) for line in head.strip().splitlines())


def test_each_agent_gets_its_own_format(repo):
    written = {}
    for adapter in map(adapters.get, ("claude-code", "codex", "opencode")):
        [(path, state, invoke)] = commands.write(repo, adapter, [SPEC])
        assert state == "created"
        written[adapter.slug] = (path.relative_to(repo).as_posix(), invoke,
                                 path.read_text(encoding="utf-8"))

    path, invoke, text = written["claude-code"]
    assert path == ".claude/skills/novgraph/SKILL.md" and invoke == "/novgraph"
    front = _front(text)
    assert front["name"] == '"novgraph"'
    assert front["argument-hint"] == '"review | brief <task>"'
    # Typed by the user; a model-loaded copy would arrive with no request.
    assert front["disable-model-invocation"] == "true"
    assert "The request: `$ARGUMENTS`" in text and "# /novgraph" in text

    path, invoke, text = written["codex"]
    assert path == ".agents/skills/novgraph/SKILL.md" and invoke == "$novgraph"
    assert set(_front(text)) == {"name", "description"}
    assert "$ARGUMENTS" not in text, "Codex does not substitute it"
    # Shared with Cursor, which types /novgraph: the body names both.
    assert "`$` instead of `/`" in text and "Next: /novgraph brief" in text

    path, invoke, text = written["opencode"]
    assert path == ".opencode/commands/novgraph.md" and invoke == "/novgraph"
    assert set(_front(text)) == {"description"}, "the file name is the name"
    assert "`$ARGUMENTS`" in text

    for _, _, text in written.values():
        assert commands.HEADER in text
        assert "{invoke}" not in text and "{request}" not in text


def test_a_second_write_changes_nothing(repo):
    claude = adapters.get("claude-code")
    commands.write(repo, claude, [SPEC])
    assert [s for _, s, _ in commands.write(repo, claude, [SPEC])] == ["unchanged"]
    assert commands.status(repo, claude, SPEC) == "current"
    assert commands.status(repo, claude, dict(SPEC, body="new")) == "outdated"


def test_an_unsafe_name_from_the_server_is_never_written():
    bad = [dict(SPEC, name="../../evil"), dict(SPEC, name="Novayagraph"),
           dict(SPEC, body="  "), "not-a-dict"]
    assert commands.served({"commands": bad + [SPEC]}) == [SPEC]
    assert commands.served({}) == [] and commands.served(None) == []


def test_no_served_commands_writes_nothing(repo):
    for adapter in adapters.ADAPTERS:
        assert commands.write(repo, adapter, commands.served({"tools": []})) == []
    assert not (repo / ".claude").exists()


def test_removal_leaves_no_trace_and_spares_the_users_files(repo):
    claude, opencode = adapters.get("claude-code"), adapters.get("opencode")
    commands.write(repo, claude, [SPEC])
    commands.write(repo, opencode, [SPEC])
    theirs = repo / ".opencode" / "commands" / "deploy.md"
    theirs.write_text("their command\n", encoding="utf-8")

    assert commands.remove(repo, claude)
    assert not (repo / ".claude").exists(), "empty directories we made stay behind"
    assert commands.remove(repo, opencode)
    assert theirs.read_text(encoding="utf-8") == "their command\n"

    # Same name, no header: the user's own, never ours to delete.
    mine = repo / ".claude" / "skills" / "novgraph" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text("hand written\n", encoding="utf-8")
    assert commands.remove(repo, claude) == []
    assert mine.exists()


def test_wire_and_unwire_carry_the_command(repo):
    claude = adapters.get("claude-code")
    result = claude.wire(repo, "cb", with_mcp=False, specs=[SPEC])
    assert any("/novgraph command in .claude/skills/novgraph/SKILL.md" in a
               for a in result.actions)
    result = claude.unwire(repo)
    assert any("removed .claude/skills/novgraph/SKILL.md" in a for a in result.actions)
    assert not (repo / ".claude").exists()


def test_a_changed_command_reaches_bound_repositories_without_an_upgrade(
        repo, monkeypatch):
    claude, opencode = adapters.get("claude-code"), adapters.get("opencode")
    monkeypatch.setattr(type(claude), "detect", lambda self: True)
    monkeypatch.setattr(type(opencode), "detect", lambda self: False)
    workspace.remember(repo, "cb")
    claude.wire(repo, "cb", with_mcp=False, specs=[SPEC])
    docs.write_all(repo, CAT, "cb")

    moved = dict(CAT, guidance="# Rules\n\nImproved.",
                 commands=[dict(SPEC, body="# {invoke}\n\nImproved {request}\n")])
    assert sync.resync(moved) == 2          # rules.md and the command
    skill = (repo / ".claude" / "skills" / "novgraph" / "SKILL.md").read_text(
        encoding="utf-8")
    assert "Improved `$ARGUMENTS`" in skill
    assert "Improved." in (repo / ".novgraph" / "rules.md").read_text(encoding="utf-8")
    # OpenCode shares AGENTS.md with Codex but is not on this machine.
    assert not (repo / ".opencode").exists()
    assert sync.resync(moved) == 0


def test_resync_never_raises(monkeypatch):
    monkeypatch.setattr(workspace, "bound_roots",
                        lambda: (_ for _ in ()).throw(OSError("disk gone")))
    assert sync.resync(CAT) == 0


def test_skills_md_names_the_command_in_each_syntax():
    text = docs.skills_md(CAT)
    assert "`/novgraph <workflow>`" in text and "`$novgraph <workflow>`" in text
    assert "review | brief <task>" in text


def test_doctor_flags_a_missing_command(repo, monkeypatch):
    from novaya import doctor
    claude = adapters.get("claude-code")
    monkeypatch.setattr(adapters, "detected", lambda: [claude])
    monkeypatch.setattr(type(claude), "verify_mcp", lambda self: "")
    monkeypatch.setattr(type(claude), "recorded_command", lambda self: ["x"])
    monkeypatch.setattr(adapters, "probe_server", lambda: "")
    monkeypatch.setattr(doctor.credentials, "load", lambda: "k")
    monkeypatch.setattr(doctor.credentials, "load_stored", lambda: "")
    monkeypatch.setattr(doctor.catalog, "refresh", lambda key: CAT)
    monkeypatch.setattr(doctor.transport, "call", lambda *a, **k: {"codebases": []})

    checks, _ = doctor.run(repo, deep=False)
    row = next(c for c in checks if c.name == "client claude-code (/novgraph)")
    assert row.status == doctor.WARN and "missing" in row.detail
    commands.write(repo, claude, [SPEC])
    checks, _ = doctor.run(repo, deep=False)
    row = next(c for c in checks if c.name == "client claude-code (/novgraph)")
    assert row.status == doctor.OK

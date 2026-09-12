"""Cursor, Windsurf, Gemini CLI, GitHub Copilot and Cline: wired like the rest."""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from novaya import adapters, commands                              # noqa: E402
from novaya.adapters import base, cline, json_servers              # noqa: E402

SPEC = {"name": "novgraph", "description": "Novayagraph workflows.",
        "argument_hint": "review | brief <task>",
        "body": "# {invoke}\n\nThe request: {request}\n\nNext: {invoke} brief x\n"}
NEW = ("cursor", "windsurf", "gemini-cli", "copilot", "cline")


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """No test here may see, or write, a real user's configuration."""
    home = tmp_path / "home"
    home.mkdir()
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(home))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.delenv("CLINE_MCP_SETTINGS_PATH", raising=False)
    monkeypatch.setattr(base, "home", lambda: home)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(base, "mcp_command", lambda: ["/abs/novgraph", "mcp"])
    monkeypatch.setattr(base, "on_path", lambda name: False)
    return home


def _present(home: Path):
    """Make every client look installed, the way each one actually shows."""
    (home / ".cursor").mkdir()
    (home / ".codeium" / "windsurf").mkdir(parents=True)
    (home / ".gemini").mkdir()
    (home / ".gemini" / "settings.json").write_text("{}", encoding="utf-8")
    (home / ".vscode" / "extensions" / "github.copilot-chat-0.40.0").mkdir(parents=True)
    storage = json_servers.editor_user_dir("Code") / "globalStorage" / cline.EXTENSION_ID
    storage.mkdir(parents=True)
    (home / ".cline").mkdir()


def test_all_eight_ship_and_each_is_detected_by_its_own_footprint(_isolated):
    assert set(NEW) <= set(adapters.SLUGS) and len(adapters.SLUGS) == 8
    assert not any(adapters.get(s).detect() for s in NEW)
    _present(_isolated)
    assert all(adapters.get(s).detect() for s in NEW)


def test_antigravity_alone_is_not_gemini_cli(_isolated):
    (_isolated / ".gemini" / "antigravity").mkdir(parents=True)
    assert not adapters.get("gemini-cli").detect()


@pytest.mark.parametrize("slug, where, container, extra", [
    ("cursor", ".cursor/mcp.json", "mcpServers", {}),
    ("windsurf", ".codeium/windsurf/mcp_config.json", "mcpServers", {}),
    ("gemini-cli", ".gemini/settings.json", "mcpServers", {}),
    ("copilot", "AppData/Roaming/Code/User/mcp.json" if sys.platform.startswith("win")
     else None, "servers", {"type": "stdio"}),
])
def test_registration_is_read_modify_write(_isolated, slug, where, container, extra):
    adapter = adapters.get(slug)
    path = adapter.config_paths()[0]
    if where:
        assert path == _isolated / where
    path.parent.mkdir(parents=True, exist_ok=True)
    theirs = {"other": {"command": "keep-me"}}
    path.write_text(json.dumps({container: theirs, "theme": "dark"}), encoding="utf-8")

    result = base.Result(slug, adapter.name, detected=True)
    adapter.register_mcp(result)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["theme"] == "dark" and doc[container]["other"] == {"command": "keep-me"}
    assert doc[container][base.SERVER_NAME] == {**extra, "command": "/abs/novgraph",
                                               "args": ["mcp"]}
    assert adapter.recorded_command() == ["/abs/novgraph", "mcp"]

    again = base.Result(slug, adapter.name, detected=True)
    adapter.register_mcp(again)
    assert any("already registered" in a for a in again.actions)

    adapter.unregister_mcp(base.Result(slug, adapter.name, detected=True))
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert base.SERVER_NAME not in doc[container] and doc[container]["other"]


def test_a_config_we_cannot_parse_is_left_exactly_as_it_was(_isolated):
    adapter = adapters.get("copilot")
    path = adapter.config_paths()[0]
    path.parent.mkdir(parents=True)
    jsonc = '{\n  // VS Code tolerates comments\n  "servers": {}\n}\n'
    path.write_text(jsonc, encoding="utf-8")
    result = base.Result("copilot", adapter.name, detected=True)
    adapter.register_mcp(result)
    assert path.read_text(encoding="utf-8") == jsonc
    assert result.warnings and "left untouched" in result.warnings[0]


def test_cline_registers_in_every_cline_on_the_machine(_isolated):
    _present(_isolated)
    adapter = adapters.get("cline")
    paths = adapter.config_paths()
    assert [p.name for p in paths] == ["cline_mcp_settings.json"] * 2
    assert paths[1] == _isolated / ".cline" / "data" / "settings" / "cline_mcp_settings.json"
    adapter.register_mcp(base.Result("cline", "Cline", detected=True))
    for path in paths:
        entry = json.loads(path.read_text(encoding="utf-8"))["mcpServers"][base.SERVER_NAME]
        assert entry == {"command": "/abs/novgraph", "args": ["mcp"], "disabled": False}


def test_a_file_two_clients_share_renders_the_same_for_both():
    """Codex and Cursor both read .agents/skills: different bytes would have
    each install rewrite the other's file forever."""
    by_file = {}
    for adapter in adapters.ADAPTERS:
        if adapter.command_file:
            by_file.setdefault(adapter.command_file, []).append(adapter)
    shared = by_file[base.SHARED_SKILL_FILE]
    assert {a.slug for a in shared} == {"codex", "cursor"}
    renders = {commands.render(a, SPEC) for a in shared}
    assert len(renders) == 1
    [text] = renders
    assert "# /novgraph" in text and "`$` instead of `/`" in text


def test_each_new_client_gets_its_own_command_format(tmp_path):
    out = {}
    for slug in NEW:
        [(path, state, invoke)] = commands.write(tmp_path, adapters.get(slug), [SPEC])
        out[slug] = (path.relative_to(tmp_path).as_posix(), invoke,
                     path.read_text(encoding="utf-8"))

    assert out["windsurf"][0] == ".windsurf/workflows/novgraph.md"
    assert out["windsurf"][2].startswith('---\ndescription: "Novayagraph workflows."\n---')

    assert out["cline"][0] == ".clinerules/workflows/novgraph.md"
    assert out["cline"][2].startswith(commands.HEADER), "a workflow is plain markdown"

    path, invoke, text = out["copilot"]
    assert path == ".github/prompts/novgraph.prompt.md" and invoke == "/novgraph"
    assert 'name: "novgraph"' in text and 'agent: "agent"' in text
    assert 'argument-hint: "review | brief <task>"' in text

    path, invoke, text = out["gemini-cli"]
    assert path == ".gemini/commands/novgraph.toml"
    doc = tomllib.loads(text)
    assert doc["description"] == "Novayagraph workflows."
    assert "The request: {{args}}" in doc["prompt"], "Gemini's placeholder, braces intact"
    assert commands.ours(tmp_path / path)

    for _, _, text in out.values():
        assert "{invoke}" not in text and "{request}" not in text


def test_the_served_body_is_safe_as_a_gemini_prompt():
    """Gemini runs `!{...}` as shell and inlines `@{...}` files in a command
    prompt. The served body must never contain either."""
    # The server declares the command; outside this repo (the open-source
    # client) a snapshot of it, written by packaging/export_oss.py, stands in.
    fixture = Path(__file__).parent / "fixtures" / "novgraph_command.json"
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from gateway import hosted_port
        spec = dict(hosted_port.CLIENT_COMMANDS[0])
    except ImportError:
        spec = json.loads(fixture.read_text(encoding="utf-8"))
    body = spec["body"]
    assert "!{" not in body and "@{" not in body and "'''" not in body
    rendered = commands.render(adapters.get("gemini-cli"), spec)
    assert tomllib.loads(rendered)["prompt"].strip()


def test_windows_upgrade_moves_the_running_launcher_aside(tmp_path, monkeypatch):
    """`novgraph upgrade` is itself the running novgraph.exe, which Windows will
    not let uv overwrite -- but will let us rename."""
    from novaya import cli
    shim = tmp_path / "novgraph.exe"
    shim.write_bytes(b"old")
    (tmp_path / "novgraph.exe.old-1").write_bytes(b"stale")
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setattr(cli.shutil, "which", lambda name: str(shim))
    aside = cli._move_running_shim_aside()
    assert aside and Path(aside).read_bytes() == b"old" and not shim.exists()
    assert not (tmp_path / "novgraph.exe.old-1").exists(), "stale launchers are swept"

    monkeypatch.setattr(cli.sys, "platform", "linux")
    assert cli._move_running_shim_aside() is None

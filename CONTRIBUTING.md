# Contributing to novgraph

Thanks for helping. Two rules shape everything here:

1. **No runtime dependencies.** novgraph runs on other people's machines;
   standard library only.
2. **No engine.** novgraph is a client: auth, agent setup, transport. It never
   indexes, stores or analyses code itself. A test enforces both.

## Set up

```sh
git clone https://github.com/Novaya-AI/novgraph && cd novgraph
python -m pip install pytest
python -m pytest
```

Tests never touch your real home directory or agent configs; each one runs in
a temporary home.

## Add support for an agent

Each agent is one module in `novaya/adapters/` and one line in
`novaya/adapters/__init__.py`. Most agents keep MCP servers in a JSON file, so
the module is short:

```python
from pathlib import Path
from . import base
from .json_servers import JsonServers


class MyAgent(JsonServers):
    slug = "my-agent"
    name = "My Agent"
    instruction_file = "AGENTS.md"               # the file it reads at startup
    docs_url = "https://example.com/docs/mcp"    # where you checked the format
    command_file = ".my-agent/commands/{name}.md" # its custom-command format

    def config_paths(self) -> list:
        return [base.home() / ".my-agent" / "mcp.json"]

    def detect(self) -> bool:
        return (base.home() / ".my-agent").is_dir() or base.on_path("my-agent")
```

Then:

- **Check the format against the agent's current docs**, and put the link in
  `docs_url`. Config paths change between versions; guessing is how setups
  silently fail.
- **Add tests** in `tests/test_novgraph_more_adapters.py`: registration keeps the
  user's other entries, a second run changes nothing, uninstall removes only
  our entry, and an unparseable config is left exactly as it was.
- **Run it for real** if you have the agent installed: `novgraph wire my-agent`,
  then `novgraph doctor`.

## Pull requests

- One change per PR, with tests.
- Say which agent versions you tested against.
- Keep comments short: state the fact, not the reasoning that produced it.

By contributing you agree your contribution is licensed under Apache-2.0.

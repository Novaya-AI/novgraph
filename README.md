# novgraph

**A live knowledge graph of your codebase, queried by coding agents.**

[![PyPI](https://img.shields.io/pypi/v/novaya?label=pypi%20%C2%B7%20novaya)](https://pypi.org/project/novaya/)
[![Python](https://img.shields.io/pypi/pyversions/novaya)](https://pypi.org/project/novaya/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![CI](https://github.com/Novaya-AI/novgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/Novaya-AI/novgraph/actions/workflows/ci.yml)

Command-line client for **Novgraph**, Novaya's proprietary hosted code
knowledge graph. Coding agents query it over MCP or the shell for repository
context that source search alone does not preserve: recorded intent, code that
tends to evolve together, ranked change impact, and architecture context.

**Live 0.1.7 sample: 96.04% to 99.81% smaller than complete cited-file reads**
on six measurable retrieval calls. These are directional product telemetry,
not provider billing or a universal result against grep. Read the
[benchmark report](https://github.com/Novaya-AI/novgraph/blob/main/BENCHMARK.md).

This repository is the client only — auth, agent detection, MCP registration
and request transport. Python 3.11+, standard library, **no dependencies, no
engine**. Indexing, storage and retrieval run on Novaya's servers.

```sh
uv tool install novaya      # the PyPI package is `novaya`
novgraph install <KEY>      # generate a key at https://app.trynovaya.com
```

`install` detects every supported agent on the machine, registers the MCP
server, writes a pointer into each agent's instruction file, adds a
`/novgraph` command, resolves which indexed codebase this checkout is, and
verifies each step. `novgraph doctor` re-runs those checks with an exit code.

---

## What problem it solves

A coding agent starts each session with no memory of the repository. To answer
"what does this touch", it greps, opens files, and reconstructs context that it
loses at the end of the session. Source search is useful for current text, but
it does not preserve the intent behind decisions or provide a repository-wide
view of relationships and change impact.

Novgraph gives the agent that context directly. A query returns a focused
answer and reports its estimated size against the complete files it cites:

```
◆ Novgraph · saved you an estimated ~191k tokens · ~622k this session
  traced what changes with src/auth/session.py · vs reading the 12 files it cites
```

The API reports the estimated response size beside the estimated size of the
complete files that answer cites. In the published 0.1.7 sample, measurable
answers ranged from **96.04% to 99.81% smaller than those complete files**.
Minimal local grep was cheaper for a simple symbol location; Novgraph became
smaller when the task required contextual relationship inspection. The full
results, paired commands, latency, raw summaries and failed `ask` case are in the
[benchmark report](https://github.com/Novaya-AI/novgraph/blob/main/BENCHMARK.md).

## What Novgraph provides

Each repository gets a maintained knowledge graph designed for coding-agent
questions. It can locate code, recall recorded decisions, identify related
areas, rank likely change impact, and summarize architecture. Results include
evidence and freshness information so the agent knows when to verify the
current working tree.

Language coverage includes Python, JavaScript, TypeScript, Go, Rust, Java and C.
The hosted service maintains the graph as the repository evolves.

## Features

- **Recorded intent.** `
- **Co-change context.** 
- **Ranked blast radius.**
- **Architecture context.**
- **Precise code discovery.
- **Continuous history.**
- **Visible context accounting.** Answers report estimated context reduction;
  `/novgraph savings` prints the session ledger, and the
  [benchmark report](https://github.com/Novaya-AI/novgraph/blob/main/BENCHMARK.md)
  shows where compact grep costs less.

- **Freshness awareness.**

### Knowledge graph vs. the alternatives

| | grep + file reads | static code graph | novgraph |
| --- | --- | --- | --- |
| Symbols, calls, imports | manual | yes | yes |
| Commit intent | no | no | yes |
| Code that tends to evolve together | manual | no | yes |
| Ranked change impact with evidence | manual | partial | yes |
| Precise identifier discovery | yes | partial | yes |
| Context preserved as code evolves | n/a | no | yes |
| Freshness reported | current text | depends on tool | yes |
| Token cost reported | no | no | approximate response vs complete cited-file size |
| Runs on your machine | yes | yes | no |

## Commands

### Setup

```
novgraph install <KEY>     set up this machine and repository, then verify
novgraph install -         read the key from stdin
novgraph doctor            re-run every check; non-zero exit on failure
novgraph doctor --json     same, machine-readable
novgraph doctor --quick    skip the MCP handshake and graph read
novgraph wire <agent>      set up one agent (claude-code, codex, cursor, ...)
novgraph adapters          list supported agents and what each one needs
novgraph key <KEY>         replace this machine's key
novgraph upgrade           update the client, then re-sync every bound repo
novgraph uninstall         remove every entry and file it wrote
```

### Querying the graph

Each verb works in any terminal inside a bound repository, and is also exposed
as an MCP tool to agents.

```
novgraph summary                    what this project is
novgraph overview                   computed architecture
novgraph search <query>             locate code by concept or exact name
novgraph why <path>                 recorded reasoning behind a file
novgraph connections <path>         imports, callers, co-change
novgraph impact <path>              what breaks, most certain first
novgraph recent [limit]             recent commits and their intent
novgraph ask "<question>"           a briefing composed from several reads
novgraph record-why "<why>" --intent "..." --reasoning "..." --commit <sha>
novgraph codebases                  which repositories this key can read
novgraph call <tool> --json '{...}' any tool, including newer than this client
```

### Agent workflows

`install` writes a `/novgraph` command into each agent that supports one:

```
/novgraph review          checks the current diff against co-change history
/novgraph brief <task>    files, constraints, blast radius, a plan
/novgraph impact <file>   what breaks, most certain first
/novgraph debug <error>   ranked causes, each with evidence and a check
/novgraph record          write a commit's reasoning back to the graph
/novgraph onboard [area]  guided tour of an unfamiliar codebase
/novgraph summary         the codebase at its latest indexed commit
/novgraph savings         measured token savings for this session
```

Codex has skills rather than slash commands, so there it is `$novgraph`.

## What it writes

| Agent | MCP registration | Instruction file | Command file |
| --- | --- | --- | --- |
| Claude Code | `~/.claude.json` | `CLAUDE.md` | `.claude/skills/novgraph/SKILL.md` |
| Codex | `~/.codex/config.toml` | `AGENTS.md` | `.agents/skills/novgraph/SKILL.md` |
| Cursor | `~/.cursor/mcp.json` | `AGENTS.md` | `.agents/skills/novgraph/SKILL.md` |
| GitHub Copilot | VS Code `mcp.json` | `.github/copilot-instructions.md` | `.github/prompts/novgraph.prompt.md` |
| Gemini CLI | `~/.gemini/settings.json` | `GEMINI.md` | `.gemini/commands/novgraph.toml` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | `AGENTS.md` | `.windsurf/workflows/novgraph.md` |
| Cline | `cline_mcp_settings.json` | `AGENTS.md` | `.clinerules/workflows/novgraph.md` |
| OpenCode | `~/.config/opencode/opencode.json` | `AGENTS.md` | `.opencode/commands/novgraph.md` |

Plus `.novgraph/rules.md`, `.novgraph/skills.md` and `.novgraph/blueprint.md`
in the repository — generated, safe to commit.

Every edit is one named MCP entry and one marked block, added by
read-modify-write. A config file that cannot be parsed is left byte-for-byte
unchanged and reported. `novgraph uninstall` removes exactly what was written.

## Key handling and data

- The key is stored in the OS credential store: Windows DPAPI, macOS Keychain,
  libsecret via `secret-tool`, or a `0600` file. It is never written to the
  repository, an agent config, or a log.
- `NOVGRAPH_API_KEY` overrides the store when set — for CI. `NOVGRAPH_API_BASE`
  overrides the endpoint.
- Requests carry the key, the query, and a per-session id. **File contents are
  not sent.** The hosted graph holds paths, symbol names, relationships,
  counts and recorded reasoning.
- Indexing reads the repository through your GitHub or GitLab grant on the
  server side; the client never uploads source.

## Requirements

- Python 3.11 or newer. No third-party packages.
- A repository indexed by Novgraph — connect it at
  [app.trynovaya.com](https://app.trynovaya.com).
- For the MCP path, an agent that speaks MCP over stdio. The shell verbs work
  anywhere.

## Development

```sh
python -m pytest -q          # 80 tests, no network, no dependencies
```

Adding an agent is one module in `novaya/adapters/` plus an entry in
`ADAPTERS`; there are eight to copy from. See
[CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities privately per
[SECURITY.md](SECURITY.md).

## License

Apache-2.0 for this client. The hosted service it queries is proprietary.

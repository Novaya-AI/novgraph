# novgraph

**A live knowledge graph of your codebase, queried by coding agents.**

[![PyPI](https://img.shields.io/pypi/v/novaya?label=pypi%20%C2%B7%20novaya)](https://pypi.org/project/novaya/)
[![Python](https://img.shields.io/pypi/pyversions/novaya)](https://pypi.org/project/novaya/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![CI](https://github.com/Novaya-AI/novgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/Novaya-AI/novgraph/actions/workflows/ci.yml)

Command-line client for **Novgraph**, a hosted **knowledge graph** of a git
repository. The graph holds your files and symbols as nodes and their real
relationships as typed edges, and coding agents query it over MCP or the shell
for four things a file read cannot give them: the recorded intent behind each
commit, files that change together without importing each other, ranked blast
radius, and computed architecture.

**Live 0.1.7 sample: 96.04% to 99.81% smaller than complete cited-file reads**
on six measurable retrieval calls. Counts use a disclosed characters/bytes ÷ 4
approximation; this is a content-size comparison, not provider billing or a
universal result against grep. Read the
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
"what does this touch", it greps, opens files, and infers — spending tokens to
rebuild a picture it loses at the end of the session. Three classes of fact are
not recoverable that way at all:

| Fact | Where it lives | Why reading files misses it |
| --- | --- | --- |
| Why a change was made | commit history + recorded reasoning | git stores the diff, not the intent or the rejected alternative |
| Files that change together | commit co-occurrence | there is no import, call or reference to follow |
| Computed architecture | whole-graph analysis | hubs, layering and cycles are properties of the graph, not of any file |

Novgraph holds all three in a knowledge graph per repository and answers from
the graph. A query returns a few hundred tokens where the equivalent file reads
cost tens of thousands, and every answer reports the difference measured against the files
it cites:

```
◆ Novgraph · saved you an estimated ~191k tokens · ~622k this session
  traced what changes with core/novgraph_summary.py · vs reading the 12 files it cites
```

The API reports the estimated response size beside the estimated size of the
complete files that answer cites. In the published 0.1.7 sample, measurable
answers ranged from **96.04% to 99.81% smaller than those complete files**.
Minimal local grep was cheaper for a simple symbol location; Novgraph became
smaller when the task required contextual relationship inspection. The full
method, paired commands, latency, raw summaries and failed `ask` case are in the
[benchmark report](https://github.com/Novaya-AI/novgraph/blob/main/BENCHMARK.md).

## What's in the knowledge graph

One graph per repository, built from the working tree and the full git history.

| | |
| --- | --- |
| **Nodes** | files, and symbols within them: `function`, `class`, `method`, `constant` |
| **Structural edges** | `imports`, `calls`, `inherits`, `contains` — parsed from source |
| **History edges** | `co_change` (files committed together, weighted by commit count), `changed` (which update touched which file) |
| **Inferred edges** | runtime relationships no parser can see, added by an LLM pass over the graph |
| **Records** | one why-entry per commit: subject, intent, reasoning, files touched, serial number |
| **Computed views** | load-bearing hubs, de-facto subsystems, layering, dependency cycles — derived from the whole graph, not declared anywhere |

Language coverage is Python and JS/TS via tree-sitter, with a generic
tree-sitter path for Go, Rust, Java and C. Nothing about the graph is
hand-maintained: it is rebuilt from the repository on every push.

## Features

- **Recorded intent per commit.** `why <path>` returns the reasoning behind the
  changes that touched a file, written back by agents via `record-why`.
- **Co-change coupling.** `connections <path>` includes files that historically
  change with it and have no static link to it, with the commit count.
- **Blast radius, ordered by certainty.** `impact <path>` separates facts
  (callers, importers) from history (co-change), and states when the history is
  too shallow to be evidence.
- **Computed architecture.** `overview` reports load-bearing files, de-facto
  subsystems, layering and dependency cycles.
- **Exact identifier resolution**, including module-level constants. A query
  for `MAX_RETRIES` returns its definition; if nothing is named that, the answer
  says so instead of returning fuzzy matches on a fragment of the name.
- **History follows renames.** After `git mv`, recorded reasoning and co-change
  edges move to the new path instead of staying attached to a path that no
  longer exists.
- **Visible context accounting.** Every answer is compared against the
  approximate token cost of reading the complete files it cites. An answer whose
  baseline cannot be established reports no saving rather than a guess.
  `/novgraph savings` prints the per-query ledger, and the
  [benchmark report](https://github.com/Novaya-AI/novgraph/blob/main/BENCHMARK.md)
  shows where compact grep costs less.
- **Per-session deduplication.** A repeated query in one agent session returns a
  short reference instead of the same text again.
- **Explicit staleness.** While a new commit is indexing, changed files are
  flagged and ranked below fresh ones, and structural answers name the commit
  they describe. Anything newer than the index is reported as such, so the agent
  reads the working tree instead.

### Knowledge graph vs. the alternatives

| | grep + file reads | static code graph | novgraph |
| --- | --- | --- | --- |
| Symbols, calls, imports | manual | yes | yes |
| Commit intent | no | no | yes |
| Co-change without a static link | no | no | yes |
| Blast radius split facts/history | no | partial | yes |
| Constants resolved exactly | yes | partial | yes |
| History survives a rename | n/a | no | yes |
| Refresh | none needed | re-run it | webhook per push |
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

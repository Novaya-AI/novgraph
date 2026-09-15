Novgraph

Give every coding agent durable context for your codebase.

Novgraph is persistent codebase memory for AI coding agents. Before an agent edits a file, it can ask what the change affects, why the code exists, what has changed together before, and how the repository fits together.

""PyPI" (https://img.shields.io/pypi/v/novaya?label=PyPI%20%E2%80%94%20novaya)" (https://pypi.org/project/novaya/)
""Python" (https://img.shields.io/pypi/pyversions/novaya)" (https://pypi.org/project/novaya/)
""License" (https://img.shields.io/badge/client-Apache--2.0-blue)" (LICENSE)
""CI" (https://github.com/Novaya-AI/novgraph/actions/workflows/ci.yml/badge.svg)" (https://github.com/Novaya-AI/novgraph/actions/workflows/ci.yml)

"Get a key" (https://app.trynovaya.com) · "Website" (https://trynovaya.com) · "Read the benchmark" (BENCHMARK.md)

uv tool install novaya
novgraph install <KEY>

Get "<KEY>" at "app.trynovaya.com" (https://app.trynovaya.com). Setup finds supported agents on your machine, connects them to Novgraph, and verifies the connection.

Stop making agents rediscover your repository

Every new coding-agent session starts nearly cold. It searches, reads, and guesses its way back to an understanding that disappears at the end of the session.

Novgraph gives the agent a maintained view of the codebase instead:

Ask before you edit| Novgraph gives the agent
What will this change affect?| A ranked impact briefing
Why is this code here?| The recorded reasoning behind prior changes
What belongs together?| Relevant relationships across the repository
Where should I begin?| A focused codebase or area briefing
Is this context current?| A fresh, explicitly marked answer

The result is fewer blind file reads, better plans, and less repeated context work across sessions.

Built for real coding workflows

Use Novgraph to:

- Onboard into an unfamiliar repository without manually tracing the whole tree.
- Plan a change before writing code and surface the files, constraints, and likely consequences.
- Debug with repository history instead of treating every error as isolated.
- Review a diff with context about related areas and prior decisions.
- Keep decision-making with the codebase as agents work and commits evolve.

novgraph summary
novgraph impact <path>
novgraph why <path>
novgraph connections <path>
novgraph overview
novgraph recent

Agents can use the same capabilities through MCP and their native command or skill surface.

Works where you already code

Novgraph connects with:

Claude Code · Codex · Cursor · GitHub Copilot · Gemini CLI · Windsurf · Cline · OpenCode

Run "novgraph doctor" at any time to verify that your agent integrations and repository connection are healthy.

Context efficiency, measured

In Novgraph’s published 0.1.7 sample, measured retrieval answers were 96.04% to 99.81% smaller than reading the complete files cited by those answers. This is a content-size comparison for the published flows—not a provider-billing claim or a universal substitute for a quick local search.

See the "reproducible benchmark and its limits" (BENCHMARK.md).

Your code stays under your control

- The workstation client does not upload source files.
- Connect repositories through your own GitHub or GitLab authorization.
- Your access key is kept out of the repository and agent instructions.
- Novgraph explicitly marks context that is not current, so agents can check the working tree instead of relying on stale answers.

Open client. Protected product core.

This repository contains the lightweight, Apache-2.0 Novgraph client: setup, agent integration, and transport.

The continuously maintained codebase-memory service it connects to is operated by Novaya and remains proprietary. That lets the public client stay small, auditable, and easy to install while the product core evolves safely.

Quick reference

novgraph install <KEY>  # connect this machine and repository
novgraph doctor         # verify the connection
novgraph summary        # understand the repository
novgraph impact <path>  # scope a change
novgraph why <path>     # recover prior reasoning
novgraph uninstall      # remove Novgraph-managed setup

Contributing and security

Contributions to the client are welcome; see "CONTRIBUTING.md" (CONTRIBUTING.md). For security reports, follow "SECURITY.md" (SECURITY.md).

License

Apache-2.0 applies to this client. The hosted Novgraph service is proprietary.
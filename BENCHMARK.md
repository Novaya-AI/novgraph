# Novgraph 0.1.7 benchmark: compression, latency, and accuracy

**Run date:** 13 September 2026<br>
**Status:** preliminary, single-repository field test<br>
**Subject:** private production codebase, approximately 1,000 indexed files<br>
**Client:** `novaya` 0.1.7 on Windows, calling `https://api.trynovaya.com`

This report tests what Novgraph can substantiate today. It separates three
questions that are easy to blur together:

1. How small is a Novgraph answer compared with reading every source file it
   cites?
2. How small is it compared with actual compact `rg` or `git` command output?
3. Did the answer contain the information requested?

The answers are different. Novgraph compressed complete cited files by
**96.04%–99.81%** on the six calls where that baseline was measurable. Against
an actual local command, a simple symbol lookup was cheaper with minimal `rg`,
while Novgraph's relationship answers were **94.63%–94.91% smaller** than a
context-rich `rg` trace. The local commands were faster. Eight of nine
repository-reading calls returned useful task context; the session-scoped
`ask` call did not follow its supplied question.

These results support a focused claim: Novgraph can compress broad repository
context and return relationships that plain text search does not classify. They
do not support a universal “99% versus grep” claim.

## Test design

One fresh Novgraph session called every advertised repository-reading tool once:

- `summary`
- `overview`
- `search`
- `why`
- `connections`
- `impact`
- `recent`
- `codebases`
- `ask`

The target was `novaya/credentials.py`, the exact search symbol was
`load_stored`, and the task supplied to `ask` was:

> Before changing `novaya/credentials.py`, explain its constraints, identify
> its callers and tests, and rank the likely blast radius.

`savings` was called afterwards to inspect the session ledger. `record_why` was
not executed because it writes production history; a synthetic benchmark record
would pollute the product being measured. The API catalog contained **11
advertised tools** in total.

No coding model was invoked. This is a retrieval and transport test, not an
end-to-end software-engineering evaluation. Every live call used HTTPS and no
request was retried by the benchmark harness.

### Reported context reduction

Novgraph reports how much smaller each focused answer is than the complete
source context it cites. The percentages below are directional product
telemetry from this live run. They are not tokenizer output, provider billing,
a universal result, or a guarantee. Calls without comparable complete-file
context are marked unmeasured.

### Local command baselines

The paired commands ran against the same checkout. Two `rg` forms were measured:

- **Compact discovery:** a matching line or candidate filenames only.
- **Contextual inspection:** matching lines with nearby source context.

Those command outputs are not automatically equivalent to a Novgraph answer.
They do not classify calls, imports, tests, historical co-change, recorded
intent, architecture, or graph freshness. They show what a careful agent can
obtain cheaply before it begins follow-up reading and reasoning.

## Live results by tool

| Tool | Output tokens | Full cited files | Reduction | HTTPS wall time | Server tool time | Review |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `summary` | 377 | 103,005 | 99.63% | 360.18 ms | 6 ms | Useful orientation; aggregate architecture not independently recomputed |
| `overview` | 198 | 105,946 | 99.81% | 779.07 ms | 8 ms | Returned hubs, subsystems and cycle count; not independently recomputed |
| `search` | 107 | 2,702 | 96.04% | 361.85 ms | 11 ms | Exact symbol resolved to the correct file on the first result |
| `why` | 149 | unmeasured | — | 795.14 ms | 5 ms | Correct commit history, but this file had little substantive recorded rationale |
| `connections` | 199 | 31,187 | 99.36% | 816.28 ms | 7 ms | Seven direct importers matched an independent AST scan exactly |
| `impact` | 210 | 31,187 | 99.33% | 381.79 ms | 10 ms | Ranked the same seven dependents as facts and reported no co-change evidence |
| `recent` | 274 | unmeasured | — | 753.38 ms | 4 ms | Current commit sequence plus one graph-only reasoning record |
| `codebases` | 133 | unmeasured | — | 333.42 ms | 1 ms | Correct remote, branch, commit, file count and freshness |
| `ask` | 94 | 2,702 | 96.52% | 325.70 ms | 19 ms | **Failed task adherence:** returned the generated session label as `TASK` |
| `savings` | 363 | unmeasured | — | 347.14 ms | 1 ms | Telemetry response; not repository retrieval |
| `record_why` | — | — | — | — | — | Deliberately not called; write operation |

All ten read-only HTTP calls completed without a transport error. Across the
nine repository-reading calls, median HTTPS wall time was **381.79 ms** and the
maximum was **816.28 ms**. Median reported server tool time was **7 ms** and the
maximum was **19 ms**, so most observed latency was outside tool execution:
network, TLS, request routing, and client overhead.

Six repository-reading calls had comparable complete-file context. Their median
reported reduction was **99.35%**. Each result is presented independently;
overlapping cited files mean the rows should not be combined into a session-wide
savings claim.

## Novgraph compared with actual `rg` and `git` output

| Question | Novgraph output | Compact local command | Compact output | Contextual local output | Finding |
| --- | ---: | --- | ---: | ---: | --- |
| Locate `load_stored` | 107 tokens | `rg -n` matching definition | 8 tokens | 126 tokens | Minimal grep was 13.4× smaller; Novgraph was 15.1% smaller than the 18-line contextual result |
| Find attached files | 199 tokens | `rg -l` over imports and uses | 90 tokens | 3,910 tokens | Filename-only grep was 2.2× smaller; Novgraph was 94.91% smaller than contextual inspection |
| Rank likely impact | 210 tokens | Same candidate-file search | 90 tokens | 3,910 tokens | Filename-only grep was 2.3× smaller; Novgraph was 94.63% smaller than contextual inspection |
| Explain history | 149 tokens | `git log --follow --oneline` | 45 tokens | — | Git was smaller and the sampled Novgraph history added little rationale because none had been recorded for this file |
| Show recent work | 274 tokens | `git log --oneline -5` | 72 tokens | — | Git was smaller; Novgraph added timestamps, graph serials and a reasoning-only record |
| Identify repository | 133 tokens | `git remote -v` | 40 tokens | — | Git was smaller; Novgraph also supplied indexed commit, branch, size and freshness |
| Summarize project | 377 tokens | No single equivalent command | — | — | Requires file selection, reading and synthesis in a conventional workflow |
| Compute architecture | 198 tokens | No single equivalent `rg` command | — | — | Requires dependency extraction and whole-graph analysis |
| Compose task briefing | 94 tokens | No single equivalent command | — | — | The live response failed its supplied question in this run |

The contextual relationship pattern intentionally cast a broad net over imports
and calls. It produced 3,910 estimated tokens and included unrelated credential
references. A skilled agent could start from the 90-token filename list and read
only selected regions. The true alternative therefore lies between those two
measurements and depends on the agent's search strategy.

Local commands took 29.65–121.82 ms in the final recorded run. For the
comparable cases, Novgraph took roughly 5.4×–17.2× longer in wall-clock time.
Simple current-text
lookups should continue to use `rg` when relationship or historical context is
not needed.

## Accuracy checks

The benchmark performed targeted checks rather than assigning a broad accuracy
percentage:

- `search` returned `novaya/credentials.py#load_stored` as expected.
- An independent Python AST scan found exactly the seven files Novgraph listed
  as direct importers of `novaya/credentials.py`: six client modules and
  `tests/test_novgraph_client.py`.
- `why` matched the three commits returned by `git log --follow`.
- `recent` matched the current Git sequence and also exposed a graph-only
  reasoning record about the OSS export contract.
- `codebases` matched the checkout's remote, branch and indexed revision.
- `ask` did not answer the supplied task. It returned a generated
  `novgraph:public-benchmark-…` session marker as the task and only identified
  the target file. This is a product defect, not a benchmark-harness pass.

No aggregate precision, recall, or task-completion percentage is claimed.
`summary` and `overview` contain many aggregate facts that were not independently
recomputed in this run.

## What can be claimed from this run

A precise public statement is:

> In one live Novgraph 0.1.7 run over an approximately 1,000-file production
> codebase, six
> measurable retrieval answers were 96.04%–99.81% smaller than reading their
> complete cited files. For one dependency investigation, `connections` and
> `impact` were 94.63%–94.91% smaller than a context-rich ripgrep trace, while
> matching an independent AST scan's seven direct importers. Median HTTPS
> latency was 382 ms. One of nine repository-reading tools, `ask`, failed its
> supplied task in the sampled session.


## Reproduce

The credential-safe scripts and result summaries used for this sample are
committed beside this report:

- [`benchmarks/benchmark_read_tools.py`](benchmarks/benchmark_read_tools.py)
- [`benchmarks/benchmark_cli_baselines.py`](benchmarks/benchmark_cli_baselines.py)
- [`benchmarks/2026-09-13-novgraph-live.json`](benchmarks/2026-09-13-novgraph-live.json)
- [`benchmarks/2026-09-13-cli-baselines.json`](benchmarks/2026-09-13-cli-baselines.json)

From an indexed repository with Novgraph installed:

```sh
uv run python benchmarks/benchmark_read_tools.py \
  --codebase YOUR_CODEBASE \
  --target path/to/a/load-bearing-file.py \
  --query an_exact_symbol \
  --output novgraph-live.json

uv run python benchmarks/benchmark_cli_baselines.py \
  --target path/to/a/load-bearing-file.py \
  --symbol an_exact_symbol \
  --search-root path/to/source \
  --search-root path/to/tests \
  --output cli-baselines.json \
  --strip-output
```

The first script loads the key from Novgraph's credential backend and never
accepts or writes it. Responses are represented by hashes unless
`--include-text` is explicitly supplied. The second records the paired command
arguments and output sizes. The published percentages are Novgraph product
telemetry; the public artifacts intentionally do not define the service's
internal accounting implementation.

The next useful benchmark should repeat this design across several public
repositories and run matched coding tasks through the same model in two
conditions: Novgraph enabled and Novgraph unavailable. Capture provider input
tokens, completion quality, elapsed time, tool calls, files opened, and final
test results. That would measure realized agent performance rather than content
compression alone.

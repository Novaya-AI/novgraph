"""Run a bounded live benchmark of every read-only Novgraph tool.

The script loads the API key through the installed Novgraph credential backend.
It never accepts or writes a key. Repository answers are hashed by default; pass
``--include-text`` only when the output file is safe to keep private.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid

from novaya import __version__, credentials, transport


def estimated_tokens(value: str) -> int:
    """Use the same disclosed approximation as the hosted response metadata."""
    return (len(value) + 3) // 4


def run(codebase: str, target: str, query: str, question: str,
        include_text: bool = False) -> dict:
    key = credentials.load()
    if not key:
        raise RuntimeError("No Novgraph key is available; run `novgraph install <KEY>`.")

    session_id = "public-benchmark-" + str(uuid.uuid4())
    transport.SESSION.update(id=session_id, agent="Novgraph public benchmark")

    catalog = transport.catalog(key)
    catalog_json = json.dumps(catalog.get("tools") or [], separators=(",", ":"))
    advertised = transport.tool_names(catalog)
    cases = [
        ("novgraph_summary", {"codebase": codebase}),
        ("novgraph_overview", {"codebase": codebase}),
        ("novgraph_search", {"query": query, "codebase": codebase}),
        ("novgraph_why", {
            "target": target, "precision": "general", "limit": 8,
            "codebase": codebase,
        }),
        ("novgraph_connections", {"target": target, "codebase": codebase}),
        ("novgraph_impact", {"target": target, "codebase": codebase}),
        ("novgraph_recent", {"limit": 5, "codebase": codebase}),
        ("novgraph_codebases", {"codebase": codebase}),
        ("novgraph_ask", {
            "question": question, "budget_tokens": 900, "codebase": codebase,
        }),
    ]

    rows = []
    for tool, arguments in cases:
        started = time.perf_counter()
        response = transport.call(key, tool, arguments)
        wall_ms = round((time.perf_counter() - started) * 1000, 2)
        text = str(response.get("text") or "")
        estimate = response.get("token_estimate") or {}
        row = {
            "tool": tool,
            "arguments": arguments,
            "http_wall_ms": wall_ms,
            "server_tool_ms": response.get("latency_ms"),
            "response_chars": len(text),
            "response_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "baseline_tokens": response.get("baseline_tokens", 0),
            "token_estimate": estimate,
            "non_empty": bool(text.strip()),
        }
        if include_text:
            row["text"] = text
        rows.append(row)

    # This is telemetry for the session above, not another retrieval case.
    started = time.perf_counter()
    savings = transport.call(key, "novgraph_savings", {"days": 7, "codebase": codebase})
    savings_wall_ms = round((time.perf_counter() - started) * 1000, 2)
    savings_text = str(savings.get("text") or "")
    savings_row = {
        "tool": "novgraph_savings",
        "arguments": {"days": 7, "codebase": codebase},
        "http_wall_ms": savings_wall_ms,
        "server_tool_ms": savings.get("latency_ms"),
        "response_chars": len(savings_text),
        "response_sha256": hashlib.sha256(savings_text.encode("utf-8")).hexdigest(),
        "baseline_tokens": savings.get("baseline_tokens", 0),
        "token_estimate": savings.get("token_estimate") or {},
        "non_empty": bool(savings_text.strip()),
        "classification": "session telemetry; no grep retrieval baseline",
    }
    if include_text:
        savings_row["text"] = savings_text
    rows.append(savings_row)

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "client_version": __version__,
        "api_base": transport.base_url(),
        "codebase": codebase,
        "target": target,
        "query": query,
        "session_id_sha256": hashlib.sha256(session_id.encode("utf-8")).hexdigest(),
        "advertised_tools": advertised,
        "advertised_tool_count": len(advertised),
        "catalog_estimated_tokens": estimated_tokens(catalog_json),
        "token_method": "response characters and cited source bytes divided by four",
        "baseline": "complete contents of every file cited by each answer",
        "model_inference": False,
        "provider_token_telemetry": False,
        "record_why_executed": False,
        "record_why_reason": "write operation excluded to avoid synthetic production history",
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codebase", required=True)
    parser.add_argument("--target", required=True,
                        help="existing file used for why/connections/impact")
    parser.add_argument("--query", required=True,
                        help="exact symbol used for search")
    parser.add_argument("--question", default="",
                        help="task-shaped ask prompt; a default is built from target")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-text", action="store_true")
    args = parser.parse_args()
    question = args.question or (
        f"Before changing {args.target}, explain its constraints, identify its "
        "callers and tests, and rank the likely blast radius."
    )
    result = run(args.codebase, args.target, args.query, question, args.include_text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} ({len(result['rows'])} read-only calls; no key stored).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Measure compact command-line discovery outputs used beside Novgraph.

These are command-output measurements, not claims of task equivalence. Grep
cannot return recorded intent, co-change, computed architecture, or an already
composed task briefing. The JSON therefore records exactly which command was
run and leaves those non-equivalent cases unmeasured.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time


def measure(name: str, argv: list[str], cwd: Path) -> dict:
    started = time.perf_counter()
    completed = subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False,
    )
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    output = completed.stdout + completed.stderr
    return {
        "name": name,
        "argv": argv,
        "exit_code": completed.returncode,
        "wall_ms": elapsed,
        "output_chars": len(output),
        "output": output,
    }


def run(root: Path, target: str, symbol: str, search_roots: list[str]) -> dict:
    symbol_pattern = rf"def\s+{symbol}\b"
    relationship_pattern = (
        rf"from novaya import credentials|from \. import credentials|"
        rf"import novaya\.credentials|credentials\.|{symbol}\("
    )
    rows = [
        measure("search-location", ["rg", "-n", symbol_pattern, target], root),
        measure("search-with-context", ["rg", "-n", "-B", "2", "-A", "16",
                                        symbol_pattern, target], root),
        measure("relationship-file-list", [
            "rg", "-l", "--glob", "*.py", relationship_pattern, *search_roots,
        ], root),
        measure("relationship-with-context", [
            "rg", "-n", "-C", "2", "--glob", "*.py",
            relationship_pattern, *search_roots,
        ], root),
        measure("why-history", ["git", "log", "--follow", "--oneline", "--", target], root),
        measure("recent", ["git", "log", "--oneline", "-5"], root),
        measure("codebases-local-identity", ["git", "remote", "-v"], root),
    ]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": root.name,
        "target": target,
        "symbol": symbol,
        "search_roots": search_roots,
        "scope": "command output only; excludes follow-up reads, model reasoning, and schema cost",
        "rows": rows,
        "no_single_command_equivalent": [
            "novgraph_summary", "novgraph_overview", "novgraph_ask",
            "novgraph_savings", "novgraph_record_why",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--target", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--search-root", action="append", default=[],
                        help="directory searched for relationships; repeatable (default: .)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strip-output", action="store_true",
                        help="omit raw command output from the JSON artifact")
    args = parser.parse_args()
    result = run(args.root.resolve(), args.target, args.symbol,
                 args.search_root or ["."])
    if args.strip_output:
        for row in result["rows"]:
            row.pop("output", None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} ({len(result['rows'])} command baselines).")
    return int(any(row["exit_code"] for row in result["rows"]))


if __name__ == "__main__":
    raise SystemExit(main())

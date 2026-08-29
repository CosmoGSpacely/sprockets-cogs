"""Selected-model capability probe for Stage 99.

This wraps the read-only memory-tool probe so capability results are stamped
with model, mode, date, and an explicit write-authority boundary.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Sequence

from specialists.uniblab.memory_tool_probe import (
    MemoryToolProbeResult,
    probe_memory_tool_choice,
    probe_memory_tool_choice_json_contract,
)


DEFAULT_MODEL = os.environ.get("SPROCKETS_COGS_MODEL", "gemma4:12b-16k-cosmo")
DEFAULT_QUERIES = (
    "Find memory related to the tractor tire remounting project.",
    "Summarize recent Cogs from the last three days.",
    "Set a timer for 20 minutes.",
)
ProbeFunc = Callable[[str, str], MemoryToolProbeResult]


@dataclass(frozen=True)
class CapabilityProbeRun:
    model: str
    mode: str
    tested_at: str
    write_authority: str
    results: tuple[MemoryToolProbeResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.valid for result in self.results)


def run_capability_probe(
    model: str,
    *,
    mode: str = "json-contract",
    queries: Sequence[str] = DEFAULT_QUERIES,
    native_probe: ProbeFunc = probe_memory_tool_choice,
    json_probe: ProbeFunc = probe_memory_tool_choice_json_contract,
) -> CapabilityProbeRun:
    """Run selected-model read-only capability checks."""

    probe = native_probe if mode == "native" else json_probe
    results = tuple(probe(query, model) for query in queries)
    return CapabilityProbeRun(
        model=model,
        mode=mode,
        tested_at=datetime.now().isoformat(timespec="seconds"),
        write_authority="none",
        results=results,
    )


def run_to_dict(run: CapabilityProbeRun) -> dict:
    return {
        "model": run.model,
        "mode": run.mode,
        "tested_at": run.tested_at,
        "write_authority": run.write_authority,
        "passed": run.passed,
        "results": [
            {
                "query": result.query,
                "valid": result.valid,
                "tool": result.tool_choice.name if result.tool_choice else "",
                "arguments": result.tool_choice.arguments if result.tool_choice else {},
                "issue": result.issue,
            }
            for result in run.results
        ],
    }


def format_capability_probe(run: CapabilityProbeRun) -> str:
    lines = [
        "Stage 99 selected-model capability probe",
        f"- model: {run.model}",
        f"- mode: {run.mode}",
        f"- tested at: {run.tested_at}",
        f"- read-only tool selection: {'pass' if run.passed else 'fail'}",
        f"- write authority: {run.write_authority}",
        "",
        "Results",
    ]
    for result in run.results:
        tool = result.tool_choice.name if result.tool_choice else "-"
        issue = f" issue={result.issue}" if result.issue else ""
        lines.append(
            f"- {'pass' if result.valid else 'fail'} tool={tool} query={result.query!r}{issue}"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe selected model read-only capability posture.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="model to probe")
    parser.add_argument(
        "--mode",
        choices=("native", "json-contract"),
        default="json-contract",
        help="probe native tool calls or structured JSON tool-choice contract",
    )
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="custom query; repeat to run multiple queries",
    )
    parser.add_argument("--json", action="store_true", help="print JSON report")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    run = run_capability_probe(
        args.model,
        mode=args.mode,
        queries=tuple(args.queries or DEFAULT_QUERIES),
    )
    if args.json:
        print(json.dumps(run_to_dict(run), indent=2, sort_keys=True))
    else:
        print(format_capability_probe(run))


if __name__ == "__main__":
    main()

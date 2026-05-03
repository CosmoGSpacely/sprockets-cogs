"""Review-first OpenAI fallback evaluation harness.

Runs curated hard cases without touching the vault. By default this only checks
the fallback contract locally. Pass --live-openai to call the configured OpenAI
fallback model and print candidate nodes.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from models import validate_node
from openai_fallback import (
    _fallback_user_message,
    _openai_classify_schema,
    classify_nodes_with_openai_fallback,
    openai_fallback_enabled,
)


@dataclass(frozen=True)
class FallbackEvalCase:
    name: str
    reason: str
    context: str
    raw_nodes: list[dict]


CASES = [
    FallbackEvalCase(
        name="relative-date-task",
        reason="retry failed: cogs/daily: date must be YYYY-MM-DD",
        context="Already in today's note: (none)",
        raw_nodes=[{"raw": "call Jordan next Thursday", "type_hint": "task"}],
    ),
    FallbackEvalCase(
        name="specific-two-day-setting",
        reason="confidence: low",
        context="Already in today's note: (none)",
        raw_nodes=[{"raw": "WFH Monday and Tuesday", "type_hint": "setting"}],
    ),
    FallbackEvalCase(
        name="hierarchy-project-note",
        reason="confidence: low",
        context=(
            "Already in today's note: (none)\n"
            "Known hierarchy parent targets:\n"
            "Area: Learn Agentic AI\n"
            "Goal: Build Sprockets-Cogs (under Learn Agentic AI)\n"
            "Project: Phase 2 - Hardening (under Build Sprockets-Cogs)"
        ),
        raw_nodes=[
            {
                "raw": "Reflection for Phase 2 - Hardening: review-first fallback keeps the vault safer",
                "type_hint": "note",
            }
        ],
    ),
]


def _validate_candidates(candidates: list[dict]) -> tuple[int, list[str]]:
    errors: list[str] = []
    valid_count = 0
    for candidate in candidates:
        try:
            validate_node(candidate)
            valid_count += 1
        except Exception as exc:
            errors.append(f"{candidate.get('node_type', '?')}: {exc}")
    return valid_count, errors


def run_contract_check() -> None:
    schema = _openai_classify_schema()
    node_schema = schema["properties"]["nodes"]["items"]
    print("Fallback contract")
    print(f"- root additionalProperties: {schema['additionalProperties']}")
    print(f"- node additionalProperties: {node_schema['additionalProperties']}")
    print(f"- required node fields: {', '.join(node_schema['required'])}")
    print()
    for case in CASES:
        message = _fallback_user_message(case.raw_nodes, case.context, case.reason)
        print(f"{case.name}")
        print(f"- reason: {case.reason}")
        print(f"- raw items: {len(case.raw_nodes)}")
        print(f"- prompt chars: {len(message)}")


def run_live_openai() -> None:
    if not openai_fallback_enabled():
        raise SystemExit("OPENAI_API_KEY is not set; live fallback eval skipped.")

    for case in CASES:
        print(f"\n=== {case.name} ===")
        candidates = classify_nodes_with_openai_fallback(
            case.raw_nodes,
            case.context,
            case.reason,
        )
        if not candidates:
            print("No candidates returned. OpenAI fallback may be unavailable, out of quota, or declined.")
            continue
        valid_count, errors = _validate_candidates(candidates)
        print(json.dumps(candidates, indent=2))
        print(f"valid candidates: {valid_count}/{len(candidates)}")
        for error in errors:
            print(f"invalid: {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-openai",
        action="store_true",
        help="Call the configured OpenAI fallback model. Never writes to the vault.",
    )
    args = parser.parse_args()

    if args.live_openai:
        run_live_openai()
    else:
        run_contract_check()


if __name__ == "__main__":
    main()

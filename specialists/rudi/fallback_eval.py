"""Review-first OpenAI fallback evaluation harness.

Runs curated hard cases without touching the vault. By default this only checks
the fallback contract locally. Pass --live-openai to call the configured OpenAI
fallback model and print candidate nodes.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from models import CogsDailyItem, SprocketsNote, SprocketsTask, validate_node
from specialists.rudi.openai_fallback import (
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
    expected_node_types: list[str]
    required_text: list[str]


@dataclass(frozen=True)
class FallbackEvalResult:
    case_name: str
    candidate_count: int
    valid_count: int
    passed: bool
    issues: list[str]


CASES = [
    FallbackEvalCase(
        name="relative-date-task",
        reason="retry failed: cogs/daily: date must be YYYY-MM-DD",
        context="Already in today's note: (none)",
        raw_nodes=[{"raw": "call Alex next Thursday", "type_hint": "task"}],
        expected_node_types=["sprockets/task", "cogs/daily"],
        required_text=["Alex"],
    ),
    FallbackEvalCase(
        name="specific-two-day-setting",
        reason="confidence: low",
        context="Already in today's note: (none)",
        raw_nodes=[{"raw": "WFH Monday and Tuesday", "type_hint": "setting"}],
        expected_node_types=["cogs/daily", "cogs/daily"],
        required_text=["WFH"],
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
        expected_node_types=["sprockets/note"],
        required_text=["Phase 2 - Hardening"],
    ),
]

PROMOTION_CRITERIA = [
    "All live fallback eval cases return at least one valid candidate.",
    "Every case scores pass without missing required node types or required text.",
    "Task candidates include a same-date cogs/daily companion before review routing.",
    "Hierarchy candidates use exact existing parent_hint values or leave parent_hint empty.",
    "No fallback candidate creates area/goal/project hierarchy nodes directly.",
    "OpenAI outage, quota, or refusal still falls back to local review without traceback.",
    "Fallback output remains review-first; direct vault writes stay disabled.",
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


def _candidate_text(candidate: dict) -> str:
    return " ".join(
        str(candidate.get(field, ""))
        for field in ["title", "item_text", "parent_hint", "date"]
    )


def _score_case(case: FallbackEvalCase, candidates: list[dict]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    nodes = []
    for candidate in candidates:
        try:
            nodes.append(validate_node(candidate))
        except Exception as exc:
            issues.append(f"invalid {candidate.get('node_type', '?')}: {exc}")

    actual_types = [node.node_type for node in nodes]
    expected_counts = {
        node_type: case.expected_node_types.count(node_type)
        for node_type in set(case.expected_node_types)
    }
    for node_type, expected in expected_counts.items():
        actual = actual_types.count(node_type)
        if actual < expected:
            issues.append(f"expected at least {expected} {node_type}, got {actual}")

    combined = "\n".join(_candidate_text(candidate) for candidate in candidates)
    for text in case.required_text:
        if text.lower() not in combined.lower():
            issues.append(f"missing required text: {text}")

    for node in nodes:
        if isinstance(node, SprocketsTask):
            if not any(isinstance(other, CogsDailyItem) for other in nodes):
                issues.append("sprockets/task candidate missing cogs/daily companion")
        if isinstance(node, SprocketsNote) and case.name == "hierarchy-project-note":
            if node.parent_hint != "Phase 2 - Hardening":
                issues.append("hierarchy note should use exact parent_hint: Phase 2 - Hardening")

    return not issues, issues


def _select_cases(case_name: str = "") -> list[FallbackEvalCase]:
    if not case_name:
        return CASES
    selected = [case for case in CASES if case.name == case_name]
    if not selected:
        names = ", ".join(case.name for case in CASES)
        raise SystemExit(f"Unknown fallback eval case: {case_name}. Available: {names}")
    return selected


def _evaluate_case(case: FallbackEvalCase, candidates: list[dict]) -> FallbackEvalResult:
    valid_count, validation_errors = _validate_candidates(candidates)
    passed, score_issues = _score_case(case, candidates)
    issues = score_issues if score_issues else validation_errors
    return FallbackEvalResult(
        case_name=case.name,
        candidate_count=len(candidates),
        valid_count=valid_count,
        passed=passed,
        issues=issues,
    )


def _print_summary(results: list[FallbackEvalResult]) -> None:
    passed = sum(1 for result in results if result.passed)
    needs_review = len(results) - passed
    print("\nSummary")
    print(f"- passed: {passed}")
    print(f"- review: {needs_review}")
    print(f"- total:  {len(results)}")


def print_promotion_criteria() -> None:
    print("Fallback promotion criteria")
    for i, criterion in enumerate(PROMOTION_CRITERIA, start=1):
        print(f"{i}. {criterion}")


def run_contract_check(case_name: str = "") -> None:
    schema = _openai_classify_schema()
    node_schema = schema["properties"]["nodes"]["items"]
    print("Fallback contract")
    print(f"- root additionalProperties: {schema['additionalProperties']}")
    print(f"- node additionalProperties: {node_schema['additionalProperties']}")
    print(f"- required node fields: {', '.join(node_schema['required'])}")
    print()
    for case in _select_cases(case_name):
        message = _fallback_user_message(case.raw_nodes, case.context, case.reason)
        print(f"{case.name}")
        print(f"- reason: {case.reason}")
        print(f"- raw items: {len(case.raw_nodes)}")
        print(f"- expected node types: {', '.join(case.expected_node_types)}")
        print(f"- required text: {', '.join(case.required_text)}")
        print(f"- prompt chars: {len(message)}")


def run_live_openai(case_name: str = "", quiet: bool = False) -> None:
    if not openai_fallback_enabled():
        raise SystemExit("OPENAI_API_KEY is not set; live fallback eval skipped.")

    results: list[FallbackEvalResult] = []
    for case in _select_cases(case_name):
        print(f"\n=== {case.name} ===")
        candidates = classify_nodes_with_openai_fallback(
            case.raw_nodes,
            case.context,
            case.reason,
        )
        if not candidates:
            print("No candidates returned. OpenAI fallback may be unavailable, out of quota, or declined.")
            results.append(
                FallbackEvalResult(
                    case_name=case.name,
                    candidate_count=0,
                    valid_count=0,
                    passed=False,
                    issues=["no candidates returned"],
                )
            )
            continue

        result = _evaluate_case(case, candidates)
        results.append(result)
        if not quiet:
            print(json.dumps(candidates, indent=2))
        print(f"valid candidates: {result.valid_count}/{result.candidate_count}")
        print(f"eval result: {'pass' if result.passed else 'review'}")
        for issue in result.issues:
            print(f"issue: {issue}")
    _print_summary(results)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-openai",
        action="store_true",
        help="Call the configured OpenAI fallback model. Never writes to the vault.",
    )
    parser.add_argument(
        "--case",
        default="",
        help="Run one named case instead of the full corpus.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="In live mode, hide raw candidate JSON and print only scores.",
    )
    parser.add_argument(
        "--criteria",
        action="store_true",
        help="Print the fallback promotion criteria and exit.",
    )
    args = parser.parse_args()

    if args.criteria:
        print_promotion_criteria()
    elif args.live_openai:
        run_live_openai(args.case, quiet=args.quiet)
    else:
        run_contract_check(args.case)


if __name__ == "__main__":
    main()

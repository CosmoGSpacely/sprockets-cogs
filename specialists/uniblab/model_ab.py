"""Read-only real-input model A/B harness for Stage 99.

The harness compares local capture models on the same representative inputs
without writing to the vault. It scores boring things first: parseability,
validated node shape, confidence, latency, review pressure, and deterministic
structural-guard compatibility.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from extractor_classifier import ExtractClassifier, ExtractClassifierConfig
from models import validate_node


DEFAULT_MODELS = ("qwen3.5:9b-32k-cosmo", "gemma4:12b-32k-cosmo")
DEFAULT_NOW = datetime(2026, 6, 12, 9, 0)
DEFAULT_CONTEXT = (
    "Already in today's note: (none)\n"
    "Known hierarchy parents: General, Farm, Sprockets-Cogs Builder\n"
)


@dataclass(frozen=True)
class CaptureCase:
    """One representative capture input."""

    case_id: str
    content: str
    source: str
    expected_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelCaseResult:
    """Result for one model on one capture case."""

    model: str
    case_id: str
    raw_nodes: list[dict[str, Any]]
    classified_nodes: list[dict[str, Any]]
    elapsed_seconds: float
    valid_nodes: int
    invalid_nodes: int
    low_confidence_nodes: int
    expected_terms_found: int
    structural_guard_reasons: tuple[str, ...] = field(default_factory=tuple)
    error: str = ""

    @property
    def score(self) -> int:
        return (
            self.valid_nodes * 4
            + self.expected_terms_found * 2
            - self.invalid_nodes * 5
            - self.low_confidence_nodes
            - len(self.structural_guard_reasons) * 2
            - (10 if self.error else 0)
        )


def default_cases() -> tuple[CaptureCase, ...]:
    """Return real-input-inspired cases that cover Stage 99 pressure."""

    return (
        CaptureCase(
            case_id="ordinary-call",
            source="/home/cosmo/sc/archive/stage83-loop-smoke.input",
            content="Call Alex about the Stage 83 responsibility map today.",
            expected_terms=("Alex", "Stage 83"),
        ),
        CaptureCase(
            case_id="telegram-structural-note",
            source="/home/cosmo/sc/archive/telegram-telegram783798616125.input",
            content="Plan token ration map",
            expected_terms=("token", "ration"),
        ),
        CaptureCase(
            case_id="settings-errands",
            source="/home/cosmo/sc/archive/pilot-input-2026-05-23.input",
            content=(
                "To do today:\n"
                "KOHLS: pick up order, 10 off $25 coupon\n"
                "Relocate turtle\n"
                "GIANT: steaks sale\n"
                "HARBOR FREIGHT: 20 off one item coupon\n"
                "Check and charge Dale battery"
            ),
            expected_terms=("KOHLS", "GIANT", "HARBOR FREIGHT", "Dale"),
        ),
        CaptureCase(
            case_id="date-contact-entity",
            source="/home/cosmo/sc/archive/test-contact.input",
            content=(
                "Met Sarah Johnson from GlobalCo today. Her email is "
                "sarah@globalco.com. She wants a proposal by next Friday."
            ),
            expected_terms=("Sarah", "GlobalCo", "proposal"),
        ),
        CaptureCase(
            case_id="structural-guard-pressure",
            source="Stage 98 structural guard fixture",
            content="Area: Farm. Goal: Fix tractor. Task: Remount front tires.",
            expected_terms=("Farm", "tractor", "tires"),
        ),
    )


def load_case_files(paths: Sequence[Path]) -> tuple[CaptureCase, ...]:
    """Load external input files as A/B cases."""

    cases: list[CaptureCase] = []
    for path in paths:
        content = path.read_text()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) == 3:
                content = parts[2].strip()
        cases.append(
            CaptureCase(
                case_id=path.stem,
                content=content.strip(),
                source=str(path),
            )
        )
    return tuple(cases)


def _flatten_node_text(nodes: Sequence[dict[str, Any]]) -> str:
    return " ".join(
        " ".join(str(node.get(field, "")) for field in ("raw", "title", "item_text"))
        for node in nodes
    ).lower()


def _validate_nodes(nodes: Sequence[dict[str, Any]]) -> tuple[int, int]:
    valid = 0
    invalid = 0
    for node in nodes:
        try:
            validate_node(dict(node))
        except Exception:
            invalid += 1
        else:
            valid += 1
    return valid, invalid


def _structural_guard_reasons(
    content: str,
    raw_nodes: list[dict[str, Any]],
    classified_nodes: list[dict[str, Any]],
) -> tuple[str, ...]:
    from agentic_loop import _structural_guard_reasons as guard_reasons

    return guard_reasons(content, raw_nodes, classified_nodes)


def run_model_case(
    model: str,
    case: CaptureCase,
    *,
    context: str = DEFAULT_CONTEXT,
    now: datetime = DEFAULT_NOW,
    classifier_factory: Callable[[str], ExtractClassifier] | None = None,
) -> ModelCaseResult:
    """Run one model against one case."""

    start = time.monotonic()
    try:
        classifier = (
            classifier_factory(model)
            if classifier_factory is not None
            else ExtractClassifier(ExtractClassifierConfig(model=model, temperature=0.1))
        )
        raw_nodes = classifier.extract_nodes(case.content, now=now)
        classified_nodes = classifier.classify_nodes(raw_nodes, context, now=now)
        elapsed = time.monotonic() - start
        valid, invalid = _validate_nodes(classified_nodes)
        low_confidence = sum(
            1 for node in classified_nodes if node.get("confidence") == "low"
        )
        flattened = _flatten_node_text([*raw_nodes, *classified_nodes])
        expected_terms_found = sum(
            1 for term in case.expected_terms if term.lower() in flattened
        )
        return ModelCaseResult(
            model=model,
            case_id=case.case_id,
            raw_nodes=raw_nodes,
            classified_nodes=classified_nodes,
            elapsed_seconds=elapsed,
            valid_nodes=valid,
            invalid_nodes=invalid,
            low_confidence_nodes=low_confidence,
            expected_terms_found=expected_terms_found,
            structural_guard_reasons=_structural_guard_reasons(
                case.content,
                raw_nodes,
                classified_nodes,
            ),
        )
    except Exception as exc:
        return ModelCaseResult(
            model=model,
            case_id=case.case_id,
            raw_nodes=[],
            classified_nodes=[],
            elapsed_seconds=time.monotonic() - start,
            valid_nodes=0,
            invalid_nodes=0,
            low_confidence_nodes=0,
            expected_terms_found=0,
            error=str(exc),
        )


def run_ab(
    models: Sequence[str],
    cases: Sequence[CaptureCase],
    *,
    classifier_factory: Callable[[str], ExtractClassifier] | None = None,
) -> tuple[ModelCaseResult, ...]:
    """Run every model over every case."""

    results: list[ModelCaseResult] = []
    for model in models:
        for case in cases:
            results.append(
                run_model_case(
                    model,
                    case,
                    classifier_factory=classifier_factory,
                )
            )
    return tuple(results)


def summarize_results(results: Sequence[ModelCaseResult]) -> dict[str, dict[str, Any]]:
    """Summarize model totals."""

    summary: dict[str, dict[str, Any]] = {}
    for result in results:
        item = summary.setdefault(
            result.model,
            {
                "cases": 0,
                "score": 0,
                "valid_nodes": 0,
                "invalid_nodes": 0,
                "low_confidence_nodes": 0,
                "structural_guard_hits": 0,
                "errors": 0,
                "elapsed_seconds": 0.0,
            },
        )
        item["cases"] += 1
        item["score"] += result.score
        item["valid_nodes"] += result.valid_nodes
        item["invalid_nodes"] += result.invalid_nodes
        item["low_confidence_nodes"] += result.low_confidence_nodes
        item["structural_guard_hits"] += len(result.structural_guard_reasons)
        item["errors"] += 1 if result.error else 0
        item["elapsed_seconds"] += result.elapsed_seconds
    return summary


def results_to_dict(results: Sequence[ModelCaseResult]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "writes": "none",
        "summary": summarize_results(results),
        "results": [
            {
                "model": result.model,
                "case_id": result.case_id,
                "score": result.score,
                "raw_count": len(result.raw_nodes),
                "classified_count": len(result.classified_nodes),
                "valid_nodes": result.valid_nodes,
                "invalid_nodes": result.invalid_nodes,
                "low_confidence_nodes": result.low_confidence_nodes,
                "expected_terms_found": result.expected_terms_found,
                "structural_guard_reasons": list(result.structural_guard_reasons),
                "elapsed_seconds": round(result.elapsed_seconds, 3),
                "error": result.error,
            }
            for result in results
        ],
    }


def format_results(results: Sequence[ModelCaseResult]) -> str:
    """Format a compact comparison table."""

    summary = summarize_results(results)
    lines = [
        "Stage 99 real-input model A/B",
        "- writes: none",
        f"- cases: {len({result.case_id for result in results})}",
        "",
        "Model summary",
    ]
    for model, item in summary.items():
        lines.append(
            f"- {model}: score={item['score']} valid={item['valid_nodes']} "
            f"invalid={item['invalid_nodes']} low={item['low_confidence_nodes']} "
            f"guard_hits={item['structural_guard_hits']} errors={item['errors']} "
            f"seconds={item['elapsed_seconds']:.1f}"
        )
    lines.append("")
    lines.append("Case results")
    for result in results:
        guard = ",".join(result.structural_guard_reasons) or "-"
        error = f" error={result.error}" if result.error else ""
        lines.append(
            f"- {result.model} / {result.case_id}: score={result.score} "
            f"raw={len(result.raw_nodes)} classified={len(result.classified_nodes)} "
            f"valid={result.valid_nodes} invalid={result.invalid_nodes} "
            f"low={result.low_confidence_nodes} guard={guard}{error}"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run read-only capture A/B over representative real inputs.",
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="model to test; repeat to compare multiple models",
    )
    parser.add_argument(
        "--input-file",
        action="append",
        type=Path,
        dest="input_files",
        help="optional .input file to use instead of default embedded cases",
    )
    parser.add_argument("--json", action="store_true", help="print JSON report")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    models = tuple(args.models or DEFAULT_MODELS)
    cases = (
        load_case_files(tuple(args.input_files))
        if args.input_files
        else default_cases()
    )
    results = run_ab(models, cases)
    if args.json:
        print(json.dumps(results_to_dict(results), indent=2, sort_keys=True))
    else:
        print(format_results(results))


if __name__ == "__main__":
    main()

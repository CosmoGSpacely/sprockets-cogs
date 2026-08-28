"""Stage 138 graded capture harness.

Runs a fixed fixture set through the real `extract_nodes` / `classify_nodes`
call path for any model and config combination, and scores the classified nodes
against known-correct expected output.

This is the reusable successor to the Stage 99 `model_ab` probe. `model_ab`
compares models on proxy signals only (schema validity, confidence, latency);
it has no notion of a right answer and no way to vary configuration. This
module grades against ground truth and takes the config axes Stage 138 needs to
test: model tag, classifier context cap, and few-shot examples on/off.

Read-only: never writes to the vault.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from specialists.rosie.extractor_classifier import (
    DEFAULT_CONTEXT_MAX_CHARS,
    ExtractClassifier,
    ExtractClassifierConfig,
)
from specialists.uniblab.capture_fixtures import (
    FIXTURE_DIR,
    CaptureFixture,
    load_capture_fixtures,
)
from substrate.models import validate_node


@dataclass(frozen=True)
class HarnessConfig:
    """One point in the model/config space under test."""

    model: str
    context_max_chars: int = DEFAULT_CONTEXT_MAX_CHARS
    use_examples: bool = True
    temperature: float = 0.1

    @property
    def label(self) -> str:
        parts = [self.model]
        if self.context_max_chars != DEFAULT_CONTEXT_MAX_CHARS:
            parts.append(f"cap{self.context_max_chars}")
        if not self.use_examples:
            parts.append("noexamples")
        if self.temperature != 0.1:
            parts.append(f"t{self.temperature}")
        return "/".join(parts)


@dataclass(frozen=True)
class FixtureResult:
    """Graded result for one config on one fixture."""

    config_label: str
    fixture_id: str
    category: str
    raw_nodes: list[dict[str, Any]]
    classified_nodes: list[dict[str, Any]]
    elapsed_seconds: float
    matched: int
    expected_count: int
    actual_count: int
    missing: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()
    extracted_count: int = 0
    expected_item_count: int | None = None
    invalid_nodes: int = 0
    low_confidence_nodes: int = 0
    structural_guard_reasons: tuple[str, ...] = ()
    expect_structural_guard: bool = False
    error: str = ""

    @property
    def recall(self) -> float:
        if self.expected_count == 0:
            return 1.0
        return self.matched / self.expected_count

    @property
    def precision(self) -> float:
        if self.actual_count == 0:
            return 1.0 if self.expected_count == 0 else 0.0
        return self.matched / self.actual_count

    @property
    def f1(self) -> float:
        total = self.precision + self.recall
        if total == 0:
            return 0.0
        return 2 * self.precision * self.recall / total

    @property
    def guard_ok(self) -> bool:
        fired = bool(self.structural_guard_reasons)
        return fired == self.expect_structural_guard

    @property
    def passed(self) -> bool:
        """Exact behavioral pass: every expected node found, nothing spurious."""

        return (
            not self.error
            and self.matched == self.expected_count
            and self.actual_count == self.expected_count
            and self.invalid_nodes == 0
            and self.guard_ok
        )


def _describe_expected(expected) -> str:
    terms = ",".join(expected.must_include) if expected.must_include else "*"
    date = expected.date or "*"
    return f"{expected.node_type}[{terms}]@{date}"


def _describe_node(node: dict[str, Any]) -> str:
    title = str(node.get("title") or node.get("item_text") or "")[:40]
    return f"{node.get('node_type', '?')}[{title}]@{node.get('date', '?')}"


def grade_nodes(
    fixture: CaptureFixture,
    classified_nodes: Sequence[dict[str, Any]],
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    """Greedily match expected nodes against actual nodes.

    Returns (matched, missing descriptions, extra descriptions). Each actual
    node can satisfy at most one expectation, so duplicated output cannot
    inflate the score.
    """

    unmatched = list(range(len(classified_nodes)))
    matched = 0
    missing: list[str] = []
    for expected in fixture.expected_nodes:
        hit = next(
            (i for i in unmatched if expected.matches(classified_nodes[i])),
            None,
        )
        if hit is None:
            missing.append(_describe_expected(expected))
        else:
            unmatched.remove(hit)
            matched += 1
    extra = tuple(_describe_node(classified_nodes[i]) for i in unmatched)
    return matched, tuple(missing), extra


def _validate_nodes(nodes: Sequence[dict[str, Any]]) -> int:
    invalid = 0
    for node in nodes:
        try:
            validate_node(dict(node))
        except Exception:
            invalid += 1
    return invalid


def _structural_guard_reasons(
    content: str,
    raw_nodes: list[dict[str, Any]],
    classified_nodes: list[dict[str, Any]],
) -> tuple[str, ...]:
    from specialists.rosie.loop import _structural_guard_reasons as guard_reasons

    return guard_reasons(content, raw_nodes, classified_nodes)


def run_fixture(
    config: HarnessConfig,
    fixture: CaptureFixture,
    *,
    classifier_factory: Callable[[HarnessConfig], Any] | None = None,
) -> FixtureResult:
    """Run one config against one fixture and grade the result."""

    start = time.monotonic()
    try:
        if classifier_factory is not None:
            classifier = classifier_factory(config)
        else:
            classifier = ExtractClassifier(
                ExtractClassifierConfig(
                    model=config.model,
                    temperature=config.temperature,
                    context_max_chars=config.context_max_chars,
                )
            )
        raw_nodes = classifier.extract_nodes(fixture.content, now=fixture.now)
        classified_nodes = classifier.classify_nodes(
            raw_nodes,
            fixture.context,
            use_examples=config.use_examples,
            now=fixture.now,
        )
        elapsed = time.monotonic() - start
        matched, missing, extra = grade_nodes(fixture, classified_nodes)
        return FixtureResult(
            config_label=config.label,
            fixture_id=fixture.fixture_id,
            category=fixture.category,
            raw_nodes=raw_nodes,
            classified_nodes=classified_nodes,
            elapsed_seconds=elapsed,
            matched=matched,
            expected_count=len(fixture.expected_nodes),
            actual_count=len(classified_nodes),
            missing=missing,
            extra=extra,
            extracted_count=len(raw_nodes),
            expected_item_count=fixture.expected_item_count,
            invalid_nodes=_validate_nodes(classified_nodes),
            low_confidence_nodes=sum(
                1 for node in classified_nodes if node.get("confidence") == "low"
            ),
            structural_guard_reasons=_structural_guard_reasons(
                fixture.content, raw_nodes, classified_nodes
            ),
            expect_structural_guard=fixture.expect_structural_guard,
        )
    except Exception as exc:
        return FixtureResult(
            config_label=config.label,
            fixture_id=fixture.fixture_id,
            category=fixture.category,
            raw_nodes=[],
            classified_nodes=[],
            elapsed_seconds=time.monotonic() - start,
            matched=0,
            expected_count=len(fixture.expected_nodes),
            actual_count=0,
            expected_item_count=fixture.expected_item_count,
            expect_structural_guard=fixture.expect_structural_guard,
            error=str(exc),
        )


def run_harness(
    configs: Sequence[HarnessConfig],
    fixtures: Sequence[CaptureFixture],
    *,
    repeat: int = 1,
    classifier_factory: Callable[[HarnessConfig], Any] | None = None,
) -> tuple[FixtureResult, ...]:
    """Run every config over every fixture, `repeat` times each."""

    results: list[FixtureResult] = []
    for config in configs:
        for _ in range(repeat):
            for fixture in fixtures:
                results.append(
                    run_fixture(
                        config,
                        fixture,
                        classifier_factory=classifier_factory,
                    )
                )
    return tuple(results)


def summarize(results: Sequence[FixtureResult]) -> dict[str, dict[str, Any]]:
    """Aggregate per config label."""

    summary: dict[str, dict[str, Any]] = {}
    for result in results:
        item = summary.setdefault(
            result.config_label,
            {
                "runs": 0,
                "passed": 0,
                "matched": 0,
                "expected": 0,
                "actual": 0,
                "invalid_nodes": 0,
                "low_confidence_nodes": 0,
                "guard_mismatches": 0,
                "errors": 0,
                "elapsed_seconds": 0.0,
            },
        )
        item["runs"] += 1
        item["passed"] += 1 if result.passed else 0
        item["matched"] += result.matched
        item["expected"] += result.expected_count
        item["actual"] += result.actual_count
        item["invalid_nodes"] += result.invalid_nodes
        item["low_confidence_nodes"] += result.low_confidence_nodes
        item["guard_mismatches"] += 0 if result.guard_ok else 1
        item["errors"] += 1 if result.error else 0
        item["elapsed_seconds"] += result.elapsed_seconds

    for item in summary.values():
        expected = item["expected"]
        actual = item["actual"]
        matched = item["matched"]
        item["recall"] = round(matched / expected, 3) if expected else 1.0
        item["precision"] = round(matched / actual, 3) if actual else 0.0
        total = item["recall"] + item["precision"]
        item["f1"] = round(2 * item["recall"] * item["precision"] / total, 3) if total else 0.0
        item["pass_rate"] = round(item["passed"] / item["runs"], 3) if item["runs"] else 0.0
        item["elapsed_seconds"] = round(item["elapsed_seconds"], 1)
    return summary


def results_to_dict(results: Sequence[FixtureResult]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "writes": "none",
        "summary": summarize(results),
        "results": [
            {
                "config": result.config_label,
                "fixture_id": result.fixture_id,
                "category": result.category,
                "passed": result.passed,
                "matched": result.matched,
                "expected_count": result.expected_count,
                "actual_count": result.actual_count,
                "recall": round(result.recall, 3),
                "precision": round(result.precision, 3),
                "f1": round(result.f1, 3),
                "missing": list(result.missing),
                "extra": list(result.extra),
                "extracted_count": result.extracted_count,
                "expected_item_count": result.expected_item_count,
                "invalid_nodes": result.invalid_nodes,
                "low_confidence_nodes": result.low_confidence_nodes,
                "structural_guard_reasons": list(result.structural_guard_reasons),
                "guard_ok": result.guard_ok,
                "elapsed_seconds": round(result.elapsed_seconds, 3),
                "error": result.error,
                "raw_nodes": result.raw_nodes,
                "classified_nodes": result.classified_nodes,
            }
            for result in results
        ],
    }


def format_results(results: Sequence[FixtureResult]) -> str:
    """Format a compact scored report."""

    summary = summarize(results)
    fixtures = {result.fixture_id for result in results}
    lines = [
        "Stage 138 capture harness",
        "- writes: none",
        f"- fixtures: {len(fixtures)}",
        f"- configs: {len(summary)}",
        "",
        "Config summary",
    ]
    for label, item in summary.items():
        lines.append(
            f"- {label}: pass={item['passed']}/{item['runs']} "
            f"f1={item['f1']} recall={item['recall']} precision={item['precision']} "
            f"invalid={item['invalid_nodes']} low={item['low_confidence_nodes']} "
            f"guard_miss={item['guard_mismatches']} errors={item['errors']} "
            f"seconds={item['elapsed_seconds']}"
        )
    lines.append("")
    lines.append("Fixture results")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        detail = ""
        if result.missing:
            detail += f" missing={';'.join(result.missing)}"
        if result.extra:
            detail += f" extra={';'.join(result.extra)}"
        if not result.guard_ok:
            detail += " guard=mismatch"
        if result.error:
            detail += f" error={result.error}"
        lines.append(
            f"- [{status}] {result.config_label} / {result.fixture_id}: "
            f"matched={result.matched}/{result.expected_count} "
            f"actual={result.actual_count} f1={result.f1:.2f} "
            f"extracted={result.extracted_count}"
            f"{f'/{result.expected_item_count}' if result.expected_item_count is not None else ''}"
            f" {result.elapsed_seconds:.1f}s{detail}"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the graded capture fixture harness (read-only).",
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="model tag to test; repeat to compare models",
    )
    parser.add_argument(
        "--context-max-chars",
        action="append",
        type=int,
        dest="context_caps",
        help="classifier context cap to test; repeat to compare caps",
    )
    parser.add_argument(
        "--no-examples",
        action="store_true",
        help="also run each model with few-shot examples disabled",
    )
    parser.add_argument(
        "--fixture",
        action="append",
        dest="fixture_ids",
        help="limit to specific fixture ids",
    )
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        help="limit to fixture categories",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=FIXTURE_DIR,
        help="fixture directory override",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="runs per config, for variance checks",
    )
    parser.add_argument("--json", action="store_true", help="print JSON report")
    return parser


def configs_from_args(args: argparse.Namespace) -> tuple[HarnessConfig, ...]:
    models = tuple(args.models or (ExtractClassifierConfig().model,))
    caps = tuple(args.context_caps or (DEFAULT_CONTEXT_MAX_CHARS,))
    configs = [
        HarnessConfig(model=model, context_max_chars=cap)
        for model in models
        for cap in caps
    ]
    if args.no_examples:
        configs.extend(
            HarnessConfig(model=model, context_max_chars=cap, use_examples=False)
            for model in models
            for cap in caps
        )
    return tuple(configs)


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    fixtures = load_capture_fixtures(
        args.fixture_dir,
        only=tuple(args.fixture_ids or ()),
        categories=tuple(args.categories or ()),
    )
    if not fixtures:
        parser.error("no fixtures matched")
    results = run_harness(
        configs_from_args(args),
        fixtures,
        repeat=args.repeat,
    )
    if args.json:
        print(json.dumps(results_to_dict(results), indent=2, sort_keys=True))
    else:
        print(format_results(results))


if __name__ == "__main__":
    main()

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

from substrate.format import apply_cogs_item_format
from substrate.time_context import (
    apply_bounded_recurrence_context,
    apply_multi_day_setting_context,
    apply_runtime_date_context,
)
from specialists.rosie.architectures import ARCHITECTURES, DEFAULT_ARCHITECTURE
from specialists.uniblab.cloud_client import AnthropicChatClient, is_cloud_model
from specialists.rosie.extractor_classifier import (
    DEFAULT_CONTEXT_MAX_CHARS,
    CallStats,
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
    repeat_penalty: float | None = None
    presence_penalty: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    architecture: str = DEFAULT_ARCHITECTURE
    """Which call architecture assembles the model calls (Stage 142 slice 1).

    `two-call` is the shipped chain and the baseline. Every other value changes
    the number of calls or the seam between them while leaving the fixtures,
    the grader, and the post-classify chain identical, so the architecture is
    the only variable.
    """

    full_pipeline: bool = True
    """Score the live post-classify chain, not raw classify output.

    `loop.py` runs `apply_runtime_date_context`, `apply_bounded_recurrence_
    context`, and `apply_cogs_item_format` after classify. Stages 138 and 139
    scored raw classify output and so measured a path the product never runs
    (Stage 139 finding 34). Set False to reproduce the old numbers or to
    measure the size of the gap.
    """

    @property
    def label(self) -> str:
        parts = [self.model]
        if self.architecture != DEFAULT_ARCHITECTURE:
            parts.append(self.architecture)
        if not self.full_pipeline:
            parts.append("rawclassify")
        if self.context_max_chars != DEFAULT_CONTEXT_MAX_CHARS:
            parts.append(f"cap{self.context_max_chars}")
        if not self.use_examples:
            parts.append("noexamples")
        if self.temperature != 0.1:
            parts.append(f"t{self.temperature}")
        for name, prefix in (
            ("repeat_penalty", "rp"),
            ("presence_penalty", "pp"),
            ("top_k", "k"),
            ("top_p", "p"),
        ):
            value = getattr(self, name)
            if value is not None:
                parts.append(f"{prefix}{value}")
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
    """Graded node count: matched plus spurious, excluding absorbed extras."""

    emitted_count: int = 0
    """Every node the model produced, including ones allowed_extra absorbed."""

    missing: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()
    extracted_count: int = 0
    expected_item_count: int | None = None
    invalid_nodes: int = 0
    low_confidence_nodes: int = 0
    structural_guard_reasons: tuple[str, ...] = ()
    pipeline_steps: tuple[str, ...] = ()
    """Live post-classify steps that changed something on this fixture."""
    expect_structural_guard: bool = False
    error: str = ""
    call_stats: tuple[CallStats, ...] = ()
    architecture: str = DEFAULT_ARCHITECTURE
    architecture_notes: tuple[str, ...] = ()
    """What the architecture did that the score alone will not show - a
    segmenter decline, an escalation, a lost inspection point."""

    @property
    def call_count(self) -> int:
        """Model calls actually made. The point of the whole experiment, and
        not inferable from the architecture name: `segmented` pays one or two
        depending on whether the splitter declined, and `conditional` pays one
        or two depending on what the first call returned."""

        return len(self.call_stats)

    @property
    def prompt_tokens(self) -> int:
        """Total prompt tokens across both model calls."""

        return sum(stat.prompt_tokens or 0 for stat in self.call_stats)

    @property
    def completion_tokens(self) -> int:
        return sum(stat.completion_tokens or 0 for stat in self.call_stats)

    @property
    def peak_prompt_tokens(self) -> int:
        """Largest single-call prompt, i.e. the real context-window pressure."""

        return max((stat.prompt_tokens or 0 for stat in self.call_stats), default=0)

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


_NUM_CTX_CACHE: dict[str, int | None] = {}


def model_num_ctx(model: str) -> int | None:
    """Resolved context window for a model tag, or None if unavailable.

    Reads the parameters Ollama actually resolved, not the Modelfile text on
    disk, so an inherited num_ctx is reported correctly.
    """

    if model in _NUM_CTX_CACHE:
        return _NUM_CTX_CACHE[model]
    value: int | None = None
    try:
        import ollama

        parameters = ollama.show(model).get("parameters") or ""
        for line in parameters.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == "num_ctx":
                value = int(parts[1])
                break
    except Exception:
        value = None
    _NUM_CTX_CACHE[model] = value
    return value


def _round(value: float | None) -> float | None:
    """Round a duration for the report, preserving a real zero.

    `if value else None` would turn a genuine 0.0 - a warm model reporting no
    load time - into a missing measurement, which is a different claim.
    """

    return None if value is None else round(value, 3)


def _describe_expected(expected) -> str:
    terms = ",".join(expected.must_include) if expected.must_include else "*"
    date = expected.date or "*"
    return f"{expected.node_type}[{terms}]@{date}"


def _describe_node(node: dict[str, Any]) -> str:
    title = str(node.get("title") or node.get("item_text") or "")[:40]
    return f"{node.get('node_type', '?')}[{title}]@{node.get('date', '?')}"


#: The post-classify chain in `specialists/rosie/loop.py`, in order.
#:
#: The harness reaches into specialist internals rather than driving capture
#: through `loop.py` (deferred as D099), which is what let it silently score a
#: path the product does not run for two whole stages. This tuple plus the
#: drift test in `tests/test_stage_139_full_pipeline.py` is the guard that
#: buys that shortcut: if `loop.py` gains, drops, or reorders a step, the test
#: fails and names this list.
#: Every post-classify call `loop.py` makes, in source order.
LIVE_POST_CLASSIFY_STEPS = (
    "apply_runtime_date_context",
    "apply_bounded_recurrence_context",
    "apply_multi_day_setting_context",
    "apply_cogs_item_format",
    "route_structural_guard_to_review",
    "route_ordinary_entity_authority_to_review",
    "route_recurrence_to_review",
    "apply_explicit_hierarchy_hints",
    "ensure_hierarchy_tasks",
    "log_memory_parent_trace",
    "write_memory_parent_trace",
    "ensure_memory_hierarchy_tasks",
    "apply_memory_parent_title",
    "ensure_cogs_companions",
)

#: The steps the harness runs, in live order. Pure functions of
#: (raw_nodes, classified): no vault, no memory, no writes.
MODELED_STEPS = (
    "apply_runtime_date_context",
    "apply_bounded_recurrence_context",
    "apply_multi_day_setting_context",
    "apply_cogs_item_format",
    "apply_explicit_hierarchy_hints",
    "ensure_hierarchy_tasks",
    "ensure_cogs_companions",
)

#: Steps the harness cannot run, and why. The harness is read-only by
#: contract; these either write review packets and trace files or need live
#: vault and memory state. Fixture scores therefore still describe a partial
#: path - a smaller gap than Stages 138-139 had, but not zero. Anything
#: claimed about hierarchy parents or review routing must account for this.
UNMODELED_STEPS = {
    "route_structural_guard_to_review": "writes a review proposal packet",
    "route_ordinary_entity_authority_to_review": "writes a review packet",
    "route_recurrence_to_review": "writes a review packet",
    "log_memory_parent_trace": "logging only, no node transformation",
    "write_memory_parent_trace": "writes a trace file",
    "ensure_memory_hierarchy_tasks": "needs live RUDI memory retrieval",
    "apply_memory_parent_title": "needs live RUDI memory retrieval",
}


def apply_live_post_classify(
    raw_nodes: Sequence[dict[str, Any]],
    classified_nodes: Sequence[dict[str, Any]],
    source_date: str,
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """Run the live post-classify chain, in `loop.py`'s order.

    Returns the transformed nodes and the names of the steps that actually
    changed something, so a score movement can be attributed to a step rather
    than guessed at.
    """

    nodes = list(classified_nodes)
    applied: list[str] = []

    nodes, date_decisions = apply_runtime_date_context(raw_nodes, nodes, source_date)
    if date_decisions:
        applied.append("apply_runtime_date_context")

    nodes, recurrence_decisions = apply_bounded_recurrence_context(
        raw_nodes, nodes, source_date
    )
    if recurrence_decisions:
        applied.append("apply_bounded_recurrence_context")

    nodes, multi_day_decisions = apply_multi_day_setting_context(
        raw_nodes, nodes, source_date
    )
    if multi_day_decisions:
        applied.append("apply_multi_day_setting_context")

    nodes, format_decisions = apply_cogs_item_format(raw_nodes, nodes)
    if format_decisions:
        applied.append("apply_cogs_item_format")

    # The three review-routing steps sit here in loop.py and are skipped:
    # they write packets, and the harness is read-only. See UNMODELED_STEPS.
    from specialists.rosie.loop import (
        apply_explicit_hierarchy_hints,
        ensure_cogs_companions,
        ensure_hierarchy_tasks,
    )

    before = [dict(node) for node in nodes]
    nodes = apply_explicit_hierarchy_hints(list(raw_nodes), nodes)
    if nodes != before:
        applied.append("apply_explicit_hierarchy_hints")

    before = [dict(node) for node in nodes]
    nodes = ensure_hierarchy_tasks(list(raw_nodes), nodes)
    if nodes != before:
        applied.append("ensure_hierarchy_tasks")

    # The two memory-parent steps sit here in loop.py and are skipped: they
    # need live RUDI retrieval. See UNMODELED_STEPS.
    before = [dict(node) for node in nodes]
    nodes = ensure_cogs_companions(list(raw_nodes), nodes, source_date)
    if nodes != before:
        applied.append("ensure_cogs_companions")

    return nodes, tuple(applied)


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

    # Defensible-but-not-required nodes are absorbed: they do not satisfy an
    # expectation, and they do not count as spurious either.
    for permitted in fixture.allowed_extra:
        hit = next(
            (i for i in unmatched if permitted.matches(classified_nodes[i])),
            None,
        )
        if hit is not None:
            unmatched.remove(hit)

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
            # Stage 145: a `claude-*` model is served by Anthropic instead of
            # Ollama. Everything downstream - fixtures, grader, post-classify
            # chain - is identical, so the provider is the only variable.
            chat_client = None
            if is_cloud_model(config.model):
                chat_client = AnthropicChatClient()
            classifier = ExtractClassifier(
                ExtractClassifierConfig(
                    model=config.model,
                    temperature=config.temperature,
                    context_max_chars=config.context_max_chars,
                    repeat_penalty=config.repeat_penalty,
                    presence_penalty=config.presence_penalty,
                    top_k=config.top_k,
                    top_p=config.top_p,
                ),
                chat_client=chat_client,
            )
        architecture = ARCHITECTURES[config.architecture]
        run = architecture(
            classifier, fixture.content, fixture.now, fixture.context, config
        )
        raw_nodes = run.raw_nodes
        classified_nodes = run.classified_nodes
        architecture_notes = run.notes
        pipeline_steps: tuple[str, ...] = ()
        if config.full_pipeline:
            classified_nodes, pipeline_steps = apply_live_post_classify(
                raw_nodes, classified_nodes, fixture.now.strftime("%Y-%m-%d")
            )
        elapsed = time.monotonic() - start
        matched, missing, extra = grade_nodes(fixture, classified_nodes)
        # Graded count excludes nodes absorbed by allowed_extra, so a
        # defensible reading does not depress precision.
        graded_count = matched + len(extra)
        return FixtureResult(
            config_label=config.label,
            fixture_id=fixture.fixture_id,
            category=fixture.category,
            raw_nodes=raw_nodes,
            classified_nodes=classified_nodes,
            elapsed_seconds=elapsed,
            matched=matched,
            expected_count=len(fixture.expected_nodes),
            actual_count=graded_count,
            emitted_count=len(classified_nodes),
            missing=missing,
            extra=extra,
            extracted_count=len(raw_nodes),
            expected_item_count=fixture.expected_item_count,
            invalid_nodes=_validate_nodes(classified_nodes),
            low_confidence_nodes=sum(
                1 for node in classified_nodes if node.get("confidence") == "low"
            ),
            pipeline_steps=pipeline_steps,
            structural_guard_reasons=_structural_guard_reasons(
                fixture.content, raw_nodes, classified_nodes
            ),
            expect_structural_guard=fixture.expect_structural_guard,
            call_stats=tuple(getattr(classifier, "call_stats", ())),
            architecture=config.architecture,
            architecture_notes=architecture_notes,
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
            architecture=config.architecture,
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
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "peak_prompt_tokens": 0,
                "model": result.config_label.split("/")[0],
            },
        )
        item["prompt_tokens"] += result.prompt_tokens
        item["completion_tokens"] += result.completion_tokens
        item["peak_prompt_tokens"] = max(
            item["peak_prompt_tokens"], result.peak_prompt_tokens
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
        num_ctx = model_num_ctx(item["model"])
        item["num_ctx"] = num_ctx
        item["peak_context_utilization"] = (
            round(item["peak_prompt_tokens"] / num_ctx, 4) if num_ctx else None
        )
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
                "emitted_count": result.emitted_count,
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
                "pipeline_steps": list(result.pipeline_steps),
                "guard_ok": result.guard_ok,
                "architecture": result.architecture,
                "architecture_notes": list(result.architecture_notes),
                # Not inferable from the architecture name: `segmented` and
                # `conditional` both pay one or two calls depending on the
                # input, and their whole claim is that the second is rare.
                "call_count": result.call_count,
                "elapsed_seconds": round(result.elapsed_seconds, 3),
                "error": result.error,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "peak_prompt_tokens": result.peak_prompt_tokens,
                "calls": [
                    {
                        "call": stat.call,
                        "prompt_chars": stat.prompt_chars,
                        "prompt_tokens": stat.prompt_tokens,
                        "completion_tokens": stat.completion_tokens,
                        "chars_per_token": (
                            round(stat.chars_per_token, 2)
                            if stat.chars_per_token
                            else None
                        ),
                        # Decode. Dominates cost: measured at ~20 tok/s against
                        # prefill near 1000 tok/s, so a call costs what it
                        # emits, not what it reads.
                        "eval_seconds": _round(stat.eval_seconds),
                        # Prefill, load, and the total the server reports.
                        # Serialized as of Stage 142 slice 0a: the call
                        # architecture experiment compares designs that trade
                        # prefill against decode, and without these the
                        # comparison is wall-clock subtraction. load_seconds
                        # also answers whether a cold start dominates a short
                        # conversational reply, which nothing has measured.
                        "prompt_eval_seconds": _round(stat.prompt_eval_seconds),
                        "load_seconds": _round(stat.load_seconds),
                        "total_seconds": _round(stat.total_seconds),
                    }
                    for stat in result.call_stats
                ],
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
        utilization = item.get("peak_context_utilization")
        lines.append(
            f"    tokens: prompt={item['prompt_tokens']} "
            f"completion={item['completion_tokens']} "
            f"peak_prompt={item['peak_prompt_tokens']} "
            f"num_ctx={item.get('num_ctx')} "
            f"peak_use={f'{utilization:.2%}' if utilization else 'n/a'}"
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
            f"tok={result.prompt_tokens}+{result.completion_tokens} "
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
        "--architecture",
        action="append",
        dest="architectures",
        choices=sorted(ARCHITECTURES),
        help="call architecture to test; repeat to compare (Stage 142 slice 1)",
    )
    parser.add_argument(
        "--raw-classify",
        action="store_true",
        help=(
            "also score raw classify output, without the live post-classify "
            "chain, to measure the gap against the full pipeline"
        ),
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
    parser.add_argument(
        "--temperature",
        action="append",
        type=float,
        dest="temperatures",
        help="temperature to test; repeat to compare",
    )
    for name in ("repeat-penalty", "presence-penalty", "top-p"):
        parser.add_argument(
            f"--{name}",
            action="append",
            type=float,
            dest=name.replace("-", "_") + "s",
            help=f"{name} to test; repeat to compare. Unset leaves it to the model.",
        )
    parser.add_argument(
        "--top-k",
        action="append",
        type=int,
        dest="top_ks",
        help="top_k to test; repeat to compare. Unset leaves it to the model.",
    )
    parser.add_argument("--json", action="store_true", help="print JSON report")
    return parser


def configs_from_args(args: argparse.Namespace) -> tuple[HarnessConfig, ...]:
    """Build the config grid. Unset axes stay at one value, so the grid stays small."""

    models = tuple(args.models or (ExtractClassifierConfig().model,))
    caps = tuple(args.context_caps or (DEFAULT_CONTEXT_MAX_CHARS,))
    temperatures = tuple(getattr(args, "temperatures", None) or (0.1,))
    repeat_penalties = tuple(getattr(args, "repeat_penaltys", None) or (None,))
    presence_penalties = tuple(getattr(args, "presence_penaltys", None) or (None,))
    top_ks = tuple(getattr(args, "top_ks", None) or (None,))
    top_ps = tuple(getattr(args, "top_ps", None) or (None,))
    example_modes = (True, False) if args.no_examples else (True,)
    pipeline_modes = (True, False) if getattr(args, "raw_classify", False) else (True,)
    architectures = tuple(
        getattr(args, "architectures", None) or (DEFAULT_ARCHITECTURE,)
    )

    return tuple(
        HarnessConfig(
            architecture=architecture,
            model=model,
            context_max_chars=cap,
            use_examples=use_examples,
            temperature=temperature,
            repeat_penalty=repeat_penalty,
            presence_penalty=presence_penalty,
            top_k=top_k,
            top_p=top_p,
            full_pipeline=full_pipeline,
        )
        # Architecture is the outermost axis so every fixture for one
        # architecture runs consecutively. Finding 63: alternating scaffolds
        # halve the prefix-cache hit rate, so interleaving architectures would
        # charge each one for the others' cache evictions.
        for architecture in architectures
        for model in models
        for full_pipeline in pipeline_modes
        for cap in caps
        for use_examples in example_modes
        for temperature in temperatures
        for repeat_penalty in repeat_penalties
        for presence_penalty in presence_penalties
        for top_k in top_ks
        for top_p in top_ps
    )


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

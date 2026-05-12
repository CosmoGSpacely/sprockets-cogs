"""Read-only orchestration contract for Phase 4 specialist routing.

Stage 37 starts with a deterministic contract harness. It does not call models,
write vault files, or replace the live watcher.
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from typing import Literal


WorkflowMode = Literal[
    "capture",
    "memory-guard",
    "review",
    "maintenance",
    "planning",
    "retrieval",
    "operations",
    "adapter",
    "orchestration-preview",
]

Specialist = Literal[
    "orchestrator",
    "extractor-classifier",
    "cogs",
    "sprockets",
    "memory",
    "review",
    "operations",
    "adapter",
]

WritePosture = Literal[
    "read-only",
    "proven-writes-only",
    "guarded-maintenance-writes",
    "proposal-or-review-only",
    "human-approved-only",
]

ReviewRequirement = Literal["not-required", "required", "recommended"]
Confidence = Literal["high", "medium", "low"]

_MODES: frozenset[str] = frozenset(
    {
        "capture",
        "memory-guard",
        "review",
        "maintenance",
        "planning",
        "retrieval",
        "operations",
        "adapter",
        "orchestration-preview",
    }
)


@dataclass(frozen=True)
class WorkRequest:
    """Normalized request shape for read-only routing previews."""

    source: str
    mode: WorkflowMode = "orchestration-preview"
    request_id: str = "preview"
    content: str = ""
    content_ref: str | None = None
    constraints: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RouteDecision:
    """Deterministic routing decision for a normalized work request."""

    specialist: Specialist
    mode: WorkflowMode
    confidence: Confidence
    write_posture: WritePosture
    review: ReviewRequirement
    reasons: tuple[str, ...]


def normalize_mode(value: str | None) -> WorkflowMode:
    """Return a known workflow mode or raise a clear error."""

    mode = (value or "orchestration-preview").strip().lower()
    if mode not in _MODES:
        raise ValueError(f"unknown workflow mode: {value}")
    return mode  # type: ignore[return-value]


def route_work_request(request: WorkRequest) -> RouteDecision:
    """Route a work request without side effects."""

    if request.mode != "orchestration-preview":
        return _route_explicit_mode(request)
    return _route_preview(request)


def _route_explicit_mode(request: WorkRequest) -> RouteDecision:
    mode = request.mode
    if mode == "capture":
        return RouteDecision(
            specialist="extractor-classifier",
            mode="capture",
            confidence="high",
            write_posture="proven-writes-only",
            review="not-required",
            reasons=("explicit mode: capture",),
        )
    if mode == "memory-guard":
        return RouteDecision(
            specialist="memory",
            mode="memory-guard",
            confidence="high",
            write_posture="proven-writes-only",
            review="not-required",
            reasons=("explicit mode: memory-guard",),
        )
    if mode == "review":
        return RouteDecision(
            specialist="review",
            mode="review",
            confidence="high",
            write_posture="human-approved-only",
            review="required",
            reasons=("explicit mode: review",),
        )
    if mode == "maintenance":
        return RouteDecision(
            specialist="operations",
            mode="maintenance",
            confidence="medium",
            write_posture="guarded-maintenance-writes",
            review="recommended",
            reasons=("explicit mode: maintenance",),
        )
    if mode == "planning":
        return RouteDecision(
            specialist="cogs",
            mode="planning",
            confidence="medium",
            write_posture="proposal-or-review-only",
            review="required",
            reasons=("explicit mode: planning",),
        )
    if mode == "retrieval":
        return RouteDecision(
            specialist="memory",
            mode="retrieval",
            confidence="high",
            write_posture="read-only",
            review="not-required",
            reasons=("explicit mode: retrieval",),
        )
    if mode == "operations":
        return RouteDecision(
            specialist="operations",
            mode="operations",
            confidence="high",
            write_posture="read-only",
            review="not-required",
            reasons=("explicit mode: operations",),
        )
    if mode == "adapter":
        return RouteDecision(
            specialist="adapter",
            mode="adapter",
            confidence="medium",
            write_posture="read-only",
            review="recommended",
            reasons=("explicit mode: adapter",),
        )
    return _route_preview(request)


def _route_preview(request: WorkRequest) -> RouteDecision:
    haystack = " ".join([request.source, request.content, request.content_ref or ""]).lower()

    if _contains_any(haystack, ("review", "approve", "discard", "packet")):
        return RouteDecision(
            specialist="review",
            mode="review",
            confidence="high",
            write_posture="human-approved-only",
            review="required",
            reasons=("matched review workflow terms",),
        )
    if _contains_any(haystack, ("status", "health", "service", "timer", "backup", "syncthing")):
        return RouteDecision(
            specialist="operations",
            mode="operations",
            confidence="high",
            write_posture="read-only",
            review="not-required",
            reasons=("matched operations/status terms",),
        )
    if _contains_any(haystack, ("retrieval", "retrieve", "memory", "embedding", "benchmark")):
        return RouteDecision(
            specialist="memory",
            mode="retrieval",
            confidence="high",
            write_posture="read-only",
            review="not-required",
            reasons=("matched retrieval/memory terms",),
        )
    if _contains_any(haystack, ("nightly", "carry", "weekly", "monthly", "annual", "5wow")):
        return RouteDecision(
            specialist="cogs",
            mode="maintenance",
            confidence="medium",
            write_posture="guarded-maintenance-writes",
            review="recommended",
            reasons=("matched cogs maintenance terms",),
        )
    if _contains_any(haystack, ("hierarchy", "area", "goal", "project", "parent")):
        return RouteDecision(
            specialist="sprockets",
            mode="planning",
            confidence="medium",
            write_posture="proposal-or-review-only",
            review="required",
            reasons=("matched sprockets planning terms",),
        )
    if request.source.endswith(".input") or _contains_any(request.source.lower(), ("input", ".input")):
        return RouteDecision(
            specialist="extractor-classifier",
            mode="capture",
            confidence="high",
            write_posture="proven-writes-only",
            review="not-required",
            reasons=("source looks like canonical input",),
        )
    return RouteDecision(
        specialist="review",
        mode="review",
        confidence="low",
        write_posture="proposal-or-review-only",
        review="required",
        reasons=("no deterministic route matched",),
    )


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    for needle in needles:
        pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
        if re.search(pattern, text):
            return True
    return False


def format_route_decision(request: WorkRequest, decision: RouteDecision) -> str:
    """Format a route preview for humans and tests."""

    lines = [
        "Orchestrator route preview",
        f"- request_id: {request.request_id}",
        f"- source: {request.source}",
        f"- requested mode: {request.mode}",
        f"- selected mode: {decision.mode}",
        f"- specialist: {decision.specialist}",
        f"- confidence: {decision.confidence}",
        f"- write posture: {decision.write_posture}",
        f"- review: {decision.review}",
        "- reasons:",
    ]
    lines.extend(f"  - {reason}" for reason in decision.reasons)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview Phase 4 orchestrator routing.")
    parser.add_argument("content", nargs="*", help="Request text to route.")
    parser.add_argument("--source", default="preview", help="Request source or source file.")
    parser.add_argument("--mode", default="orchestration-preview", help="Workflow mode.")
    parser.add_argument("--request-id", default="preview", help="Traceable request id.")
    parser.add_argument("--content-ref", default=None, help="Optional source payload reference.")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    request = WorkRequest(
        source=args.source,
        mode=normalize_mode(args.mode),
        request_id=args.request_id,
        content=" ".join(args.content),
        content_ref=args.content_ref,
    )
    print(format_route_decision(request, route_work_request(request)))


if __name__ == "__main__":
    main()

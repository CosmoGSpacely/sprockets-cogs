"""Read-only end-to-end orchestration rehearsal for Phase 4.

Stage 44 starts by connecting the existing route contract and message-bus
handoff shape into a single inspectable trace. It does not append to the bus,
execute specialists, call models, or write the vault.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Sequence

import specialists.rudi.orchestrator_contract as orchestrator
from specialists.rudi.agent_message_bus import AgentMessage, message_to_dict


@dataclass(frozen=True)
class RehearsalTrace:
    """End-to-end dry-run trace for one orchestrated request."""

    request: orchestrator.WorkRequest
    decision: orchestrator.RouteDecision
    handoff: AgentMessage
    specialist_command: tuple[str, ...]
    writes: bool = False
    appends_message: bool = False
    executes_specialist: bool = False


def build_rehearsal_trace(request: orchestrator.WorkRequest) -> RehearsalTrace:
    """Build a read-only trace from request to specialist handoff."""

    decision = orchestrator.route_work_request(request)
    handoff = orchestrator.route_handoff_message(request, decision)
    return RehearsalTrace(
        request=request,
        decision=decision,
        handoff=handoff,
        specialist_command=specialist_preview_command(request, decision),
    )


def specialist_preview_command(
    request: orchestrator.WorkRequest,
    decision: orchestrator.RouteDecision,
) -> tuple[str, ...]:
    """Return the read-only command that would inspect the recipient boundary."""

    content = request.content.strip()
    if decision.specialist == "extractor-classifier":
        if request.content_ref:
            return ("scripts/capture-preview", "--file", request.content_ref)
        return ("scripts/capture-preview", content or "(input text)")
    if decision.specialist == "cogs":
        return ("scripts/cogs-specialist", "--inventory")
    if decision.specialist == "sprockets":
        return ("scripts/sprockets-specialist", "--inventory")
    if decision.specialist == "memory":
        return ("scripts/memory-specialist", "--retrieval-preview", content or "status")
    if decision.specialist == "review":
        return ("scripts/review-specialist", "--inventory")
    if decision.specialist == "operations":
        return ("scripts/status",)
    return ("scripts/orchestrator-route", "--source", request.source, content)


def rehearsal_trace_payload(trace: RehearsalTrace) -> dict[str, object]:
    """Return deterministic machine-readable rehearsal trace payload."""

    return {
        "request": asdict(trace.request),
        "decision": asdict(trace.decision),
        "handoff": message_to_dict(trace.handoff),
        "specialist_command": list(trace.specialist_command),
        "writes": trace.writes,
        "appends_message": trace.appends_message,
        "executes_specialist": trace.executes_specialist,
    }


def format_rehearsal_trace(trace: RehearsalTrace) -> str:
    """Format the rehearsal trace for operator inspection."""

    lines = [
        "Orchestrated rehearsal preview",
        f"- request_id: {trace.request.request_id}",
        f"- source: {trace.request.source}",
        f"- requested mode: {trace.request.mode}",
        f"- selected specialist: {trace.decision.specialist}",
        f"- selected mode: {trace.decision.mode}",
        f"- write posture: {trace.decision.write_posture}",
        f"- review: {trace.decision.review}",
        f"- handoff trace_id: {trace.handoff.trace_id}",
        f"- handoff idempotency_key: {trace.handoff.idempotency_key}",
        f"- handoff kind: {trace.handoff.kind}",
        f"- specialist preview command: {' '.join(trace.specialist_command)}",
        f"- appends message: {'yes' if trace.appends_message else 'no'}",
        f"- executes specialist: {'yes' if trace.executes_specialist else 'no'}",
        f"- writes: {'yes' if trace.writes else 'no'}",
        "- reasons:",
    ]
    lines.extend(f"  - {reason}" for reason in trace.decision.reasons)
    return "\n".join(lines)


def format_rehearsal_trace_json(trace: RehearsalTrace) -> str:
    """Format the rehearsal trace as deterministic JSON."""

    return json.dumps(rehearsal_trace_payload(trace), indent=2, sort_keys=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview an end-to-end Phase 4 orchestration rehearsal.")
    parser.add_argument("content", nargs="*", help="Request text to rehearse.")
    parser.add_argument("--source", default="preview", help="Request source or source file.")
    parser.add_argument("--mode", default="orchestration-preview", help="Workflow mode.")
    parser.add_argument("--request-id", default="rehearsal-preview", help="Traceable request id.")
    parser.add_argument("--content-ref", default=None, help="Optional source payload reference.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    request = orchestrator.WorkRequest(
        source=args.source,
        mode=orchestrator.normalize_mode(args.mode),
        request_id=args.request_id,
        content=" ".join(args.content),
        content_ref=args.content_ref,
    )
    trace = build_rehearsal_trace(request)
    if args.json:
        print(format_rehearsal_trace_json(trace))
    else:
        print(format_rehearsal_trace(trace))


if __name__ == "__main__":
    main()

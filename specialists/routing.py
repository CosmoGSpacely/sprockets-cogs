"""Stage 101 all-specialist route audit."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import specialists.cogs.specialist as cogs_specialist
from graph.mutations import MutationCommand
from graph.proposals import ReviewProposal
from intents.models import (
    AuthorityAssessment,
    Confidence,
    ContextScope,
    IntentClass,
    IntentClassification,
    NormalizedInput,
    RequiredGuard,
    RuntimeTimeContext,
    SourceAuthority,
    SourceMetadata,
    SourceType,
    SuggestedRoute,
)
import specialists.rudi.memory_specialist as memory_specialist
import specialists.uniblab.phase86_status as phase86_status
import specialists.jane.specialist as review_specialist
import specialists.sprockets.specialist as sprockets_specialist


DEFAULT_INPUT = (
    "Project: Remount front tractor tires; "
    "Cog: Saturday buy tire valves, sealant, and tire mounting kit."
)


@dataclass(frozen=True)
class SpecialistAuditEvent:
    """One visible specialist boundary event for a routed input."""

    input_id: str
    specialist: str
    action: str
    artifact: str
    decision: str
    timestamp: str
    result: str
    writes: str = "no"


@dataclass(frozen=True)
class AllSpecialistRouteResult:
    """Complete Stage 101 route evidence."""

    input_id: str
    input_text: str
    events: tuple[SpecialistAuditEvent, ...]

    def specialist_ids(self) -> tuple[str, ...]:
        return tuple(event.specialist for event in self.events)


@dataclass(frozen=True)
class RouteFacts:
    """Small deterministic facts extracted from the structural input."""

    sprocket_title: str
    cog_text: str
    parent_hint: str = "General"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _event(
    *,
    input_id: str,
    specialist: str,
    action: str,
    artifact: str,
    decision: str,
    result: str,
    timestamp: str,
) -> SpecialistAuditEvent:
    return SpecialistAuditEvent(
        input_id=input_id,
        specialist=specialist,
        action=action,
        artifact=artifact,
        decision=decision,
        timestamp=timestamp,
        result=result,
    )


def parse_route_facts(input_text: str) -> RouteFacts:
    """Extract stable demo facts from the Stage 101 structural input class."""

    project = _field_value(input_text, "Project") or "Unresolved structural project"
    cog = _field_value(input_text, "Cog") or input_text.strip()
    parent = _field_value(input_text, "Parent") or "General"
    return RouteFacts(sprocket_title=project, cog_text=cog, parent_hint=parent)


def _field_value(input_text: str, label: str) -> str:
    pattern = rf"\b{re.escape(label)}\s*:\s*(.*?)(?=\s+\b[A-Z][A-Za-z ]{{1,24}}\s*:|$)"
    match = re.search(pattern, input_text, flags=re.IGNORECASE)
    return match.group(1).strip(" ;.") if match else ""


def _normalized_input(input_id: str, input_text: str, timestamp: str) -> NormalizedInput:
    return NormalizedInput(
        input_id=input_id,
        raw_text=input_text,
        normalized_text=" ".join(input_text.split()),
        source=SourceMetadata(
            source_type=SourceType.CLI,
            source_authority=SourceAuthority.USER,
            locator="scripts/specialist-route",
            adapter="specialist_route",
            confidence=Confidence.HIGH,
            provenance=("stage-101-route",),
        ),
        runtime_time=RuntimeTimeContext(
            local_date=timestamp[:10],
            local_time=timestamp[11:19],
            timezone=datetime.now().astimezone().tzname() or "local",
            generated_at=timestamp,
            scope=ContextScope.VOLATILE_RUNTIME,
        ),
    )


def _intent_classification() -> IntentClassification:
    return IntentClassification(
        intent_class=IntentClass.STRUCTURAL_PROPOSAL,
        confidence=Confidence.HIGH,
        authority=AuthorityAssessment(
            detected_authority_risks=("structural proposal crosses Sprockets and Cogs",),
            required_guard=RequiredGuard.DETERMINISTIC_PACKET_REQUIRED,
            packet_required_suggestion=True,
        ),
        evidence=("explicit Project: and Cog: labels",),
        uncertainty=("requires review before graph mutation",),
        suggested_route=(
            SuggestedRoute.ROSIE,
            SuggestedRoute.RUDI,
            SuggestedRoute.SPROCKETS,
            SuggestedRoute.COGS,
            SuggestedRoute.JANE,
            SuggestedRoute.UNIBLAB,
        ),
    )


def _review_proposal(input_id: str, input_text: str, facts: RouteFacts) -> ReviewProposal:
    command = MutationCommand(
        id=f"{input_id}-mutation",
        operation="create_sprocket_and_bridge",
        target_layer="product_graph",
        review_class="review_first",
        payload={
            "sprocket_title": facts.sprocket_title,
            "cog_text": facts.cog_text,
            "parent_hint": facts.parent_hint,
            "source_text": input_text,
        },
        expected_current_state={
            "direct_write_allowed": False,
            "jane_review_required": True,
        },
    )
    return ReviewProposal(
        id=f"{input_id}-proposal",
        reason="structural proposal requires review before graph mutation",
        display_text=input_text,
        mutation_command=command,
        source={"route": "stage-101-all-specialist"},
    )


def run_all_specialist_route(
    input_text: str = DEFAULT_INPUT,
    *,
    input_id: str = "stage101-route",
    vault_dir: Path = Path.home() / "vault",
    cogs_dir: Path | None = None,
    review_dir: Path = Path.home() / "vault" / "review",
    builder_dir: Path | None = None,
) -> AllSpecialistRouteResult:
    """Route one structural input class through all six specialist boundaries."""

    timestamp = _now()
    facts = parse_route_facts(input_text)
    normalized = _normalized_input(input_id, input_text, timestamp)
    intent = _intent_classification()
    proposal = _review_proposal(input_id, input_text, facts)
    cogs_root = cogs_dir or vault_dir / "Cogs"

    rudi = memory_specialist.MemorySpecialist(
        memory_specialist.MemorySpecialistConfig(vault_dir=vault_dir)
    )
    rudi_preview = rudi.memory_guard_preview(facts.cog_text, retriever_name="memory-vault")

    sprockets = sprockets_specialist.SprocketsSpecialist(
        sprockets_specialist.SprocketsSpecialistConfig(vault_dir=vault_dir)
    )
    sprockets_preview = sprockets.hierarchy_proposal_preview(
        "project",
        facts.sprocket_title,
        parent_hint=facts.parent_hint,
    )

    cogs = cogs_specialist.CogsSpecialist(
        cogs_specialist.CogsSpecialistConfig(
            cogs_dir=cogs_root,
            daily_dir=cogs_root,
        )
    )
    cogs_preview = cogs.planning_preview(normalized.runtime_time.local_date)

    jane = review_specialist.ReviewSpecialist(
        review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
    )
    jane_inventory = jane.inventory()

    ops = phase86_status.build_phase86_status(builder_dir)

    events = (
        _event(
            input_id=input_id,
            specialist="rosie",
            action="normalize_and_classify_intent",
            artifact="NormalizedInput + IntentClassification",
            decision="structural proposal requires packet",
            timestamp=timestamp,
            result=(
                f"intent={intent.intent_class.value}; "
                f"route={','.join(route.value for route in intent.suggested_route)}; "
                f"source={normalized.source.source_type.value}"
            ),
        ),
        _event(
            input_id=input_id,
            specialist="rudi",
            action="memory_guard_preview",
            artifact="MemoryGuardPreview",
            decision="evidence only",
            timestamp=timestamp,
            result=(
                f"top_parent={rudi_preview.parent_title or '(none)'}; "
                f"would_apply_parent_hint={'yes' if rudi_preview.would_apply_parent_hint else 'no'}"
            ),
        ),
        _event(
            input_id=input_id,
            specialist="sprockets",
            action="hierarchy_proposal_preview",
            artifact="SprocketsHierarchyProposalPreview",
            decision="review_first",
            timestamp=timestamp,
            result=(
                f"project={sprockets_preview.title}; slug={sprockets_preview.slug}; "
                f"issues={len(sprockets_preview.issues)}"
            ),
        ),
        _event(
            input_id=input_id,
            specialist="cogs",
            action="planning_surface_preview",
            artifact="CogsPlanningPreview",
            decision="time consequence preview only",
            timestamp=timestamp,
            result=f"value={cogs_preview.value}; planned_items={len(cogs_preview.create_plan)}",
        ),
        _event(
            input_id=input_id,
            specialist="jane",
            action="review_packet_boundary",
            artifact="ReviewProposal",
            decision="present to user; no silent mutation",
            timestamp=timestamp,
            result=(
                f"proposal={proposal.id}; operation={proposal.mutation_command.operation}; "
                f"queue_total={jane_inventory.total}"
            ),
        ),
        _event(
            input_id=input_id,
            specialist="uniblab",
            action="operator_audit_summary",
            artifact="Phase86Status",
            decision="report route and promotion posture",
            timestamp=timestamp,
            result=(
                f"phase86_promoted={ops.promoted_count}; "
                f"active_stage_ledgers={len(ops.stages)}; "
                f"unscheduled_deferred={len(ops.unscheduled_rows)}"
            ),
        ),
    )
    return AllSpecialistRouteResult(
        input_id=input_id,
        input_text=input_text,
        events=events,
    )


def route_result_payload(result: AllSpecialistRouteResult) -> dict[str, Any]:
    return {
        "input_id": result.input_id,
        "input_text": result.input_text,
        "specialists": list(result.specialist_ids()),
        "events": [asdict(event) for event in result.events],
        "writes": "no",
    }


def format_route_result(result: AllSpecialistRouteResult) -> str:
    lines = [
        "Sprockets-Cogs all-specialist route",
        f"- input_id: {result.input_id}",
        f"- specialists: {', '.join(result.specialist_ids())}",
        "- writes: no",
        "",
        "Audit Events",
    ]
    for event in result.events:
        lines.extend(
            [
                f"- {event.specialist}: {event.action}",
                f"  artifact: {event.artifact}",
                f"  decision: {event.decision}",
                f"  result: {event.result}",
                f"  writes: {event.writes}",
            ]
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one read-only route through every Sprockets-Cogs specialist.",
    )
    parser.add_argument("input", nargs="*", help="Structural input text to route.")
    parser.add_argument("--input-id", default="stage101-route", help="Stable route input id.")
    parser.add_argument("--vault-dir", type=Path, default=Path.home() / "vault")
    parser.add_argument("--cogs-dir", type=Path, default=None)
    parser.add_argument("--review-dir", type=Path, default=Path.home() / "vault" / "review")
    parser.add_argument("--builder-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print machine-readable audit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    input_text = " ".join(args.input).strip() or DEFAULT_INPUT
    result = run_all_specialist_route(
        input_text,
        input_id=args.input_id,
        vault_dir=args.vault_dir,
        cogs_dir=args.cogs_dir,
        review_dir=args.review_dir,
        builder_dir=args.builder_dir,
    )
    if args.json:
        print(json.dumps(route_result_payload(result), indent=2, sort_keys=True))
    else:
        print(format_route_result(result))


if __name__ == "__main__":
    main()

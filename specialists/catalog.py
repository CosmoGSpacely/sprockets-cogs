"""Importable specialist catalog for the Sprockets-Cogs agentic boundary map."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SpecialistDefinition:
    specialist_id: str
    display_name: str
    role: str
    runtime_form: str
    implementation_files: tuple[str, ...]
    commands: tuple[str, ...]
    always_on: bool = False
    live_dispatch: bool = False


SPECIALISTS: tuple[SpecialistDefinition, ...] = (
    SpecialistDefinition(
        specialist_id="rosie",
        display_name="Rosie",
        role="Intake and classification",
        runtime_form="Always-on file watcher service",
        implementation_files=(
            "agentic_loop.py",
            "extractor_classifier.py",
            "capture_preview.py",
        ),
        commands=("scripts/capture-preview",),
        always_on=True,
    ),
    SpecialistDefinition(
        specialist_id="rudi",
        display_name="RUDI",
        role="Reasoning, orchestration, and memory/retrieval",
        runtime_form="Commands, previews, and library provider",
        implementation_files=(
            "orchestrator_contract.py",
            "orchestrated_rehearsal.py",
            "agent_message_bus.py",
            "memory_specialist.py",
            "memory_index.py",
            "memory_guards.py",
            "production_retrieval.py",
            "memory_packets.py",
            "memory_trace_log.py",
            "specialists/rudi/memory_demo.py",
            "specialists/routing.py",
        ),
        commands=(
            "scripts/orchestrator-route",
            "scripts/orchestrated-rehearsal",
            "scripts/agent-message-bus",
            "scripts/memory-specialist",
            "scripts/memory-demo",
            "scripts/specialist-route",
            "scripts/retrieval-preview",
            "scripts/retrieval-traces",
            "scripts/memory-packets",
        ),
    ),
    SpecialistDefinition(
        specialist_id="cogs",
        display_name="Cogs",
        role="Planning, carry, migration, and reconciliation",
        runtime_form="Commands and scheduled jobs",
        implementation_files=(
            "cogs_specialist.py",
            "cogs_planning.py",
            "cogs_naming.py",
            "carry.py",
            "nightly.py",
            "vault.py",
        ),
        commands=(
            "scripts/cogs-specialist",
            "scripts/cogs-planning",
            "scripts/carry",
            "scripts/nightly",
        ),
    ),
    SpecialistDefinition(
        specialist_id="sprockets",
        display_name="Sprockets",
        role="Hierarchy, graph, and durable structure",
        runtime_form="Commands and review-first previews",
        implementation_files=(
            "sprockets_specialist.py",
            "vault_graph.py",
            "inspect_hierarchy.py",
            "models.py",
        ),
        commands=(
            "scripts/sprockets-specialist",
            "scripts/hierarchy",
        ),
    ),
    SpecialistDefinition(
        specialist_id="jane",
        display_name="Jane",
        role="Human-in-the-loop review",
        runtime_form="Commands and guarded apply previews",
        implementation_files=(
            "review_specialist.py",
            "review.py",
        ),
        commands=(
            "scripts/review-specialist",
            "scripts/review",
        ),
    ),
    SpecialistDefinition(
        specialist_id="uniblab",
        display_name="Uniblab",
        role="Operations, health, status, and readiness",
        runtime_form="Commands, possible scheduled health checks",
        implementation_files=(
            "system_status.py",
            "job_status.py",
            "job_supervisor.py",
        ),
        commands=(
            "scripts/status",
            "scripts/job-status",
            "scripts/job-supervisor",
        ),
    ),
)


def iter_specialists() -> Iterable[SpecialistDefinition]:
    return iter(SPECIALISTS)


def get_specialist(specialist_id: str) -> SpecialistDefinition:
    for specialist in SPECIALISTS:
        if specialist.specialist_id == specialist_id:
            return specialist
    raise KeyError(f"unknown specialist: {specialist_id}")

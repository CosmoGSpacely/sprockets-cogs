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
        specialist_id="orbit",
        display_name="Orbit",
        role="Source normalization and adapters",
        runtime_form="Adapter commands and foreground polling",
        implementation_files=(
            "specialists/orbit/adapters/input_adapter.py",
            "specialists/orbit/adapters/input_adapter_preview.py",
            "specialists/orbit/adapters/telegram_adapter.py",
            "specialists/orbit/adapters/telegram_adapter_preview.py",
            "specialists/orbit/adapters/telegram_response.py",
            "specialists/orbit/adapters/telegram_update_probe.py",
            "specialists/orbit/adapters/markitdown_adapter.py",
            "specialists/orbit/adapters/markitdown_batch.py",
            "specialists/orbit/adapters/source_surfaces.py",
            "specialists/orbit/adapters/rich_inputs.py",
            "specialists/orbit/adapters/telegram_polling.py",
            "specialists/orbit/pilot3.py",
        ),
        commands=(
            "scripts/input-adapter-preview",
            "scripts/telegram-adapter-preview",
            "scripts/telegram-poll",
            "scripts/telegram-response",
            "scripts/telegram-update-probe",
            "scripts/markitdown-preview",
            "scripts/markitdown-batch",
            "scripts/pilot3-telegram-once",
            "scripts/pilot3-telegram-watch",
        ),
    ),
    SpecialistDefinition(
        specialist_id="rosie",
        display_name="Rosie",
        role="Intake, extraction, and classification",
        runtime_form="Always-on file watcher service",
        implementation_files=(
            "specialists/rosie/loop.py",
            "specialists/rosie/extractor_classifier.py",
            "specialists/rosie/classifier_context.py",
            "specialists/rosie/capture_preview.py",
            "specialists/rosie/prompts.py",
        ),
        commands=("scripts/capture-preview",),
        always_on=True,
    ),
    SpecialistDefinition(
        specialist_id="rudi",
        display_name="RUDI",
        role="Reasoning, orchestration, response routing, and retrieval",
        runtime_form="Commands, previews, and library provider",
        implementation_files=(
            "specialists/rudi/orchestrator_contract.py",
            "specialists/rudi/orchestrated_rehearsal.py",
            "specialists/rudi/agent_message_bus.py",
            "specialists/rudi/memory_specialist.py",
            "specialists/rudi/memory_index.py",
            "specialists/rudi/memory_guards.py",
            "specialists/rudi/production_retrieval.py",
            "specialists/rudi/memory_packets.py",
            "specialists/rudi/memory_packets_cli.py",
            "specialists/rudi/memory_trace_log.py",
            "specialists/rudi/response_routing.py",
            "specialists/rudi/openai_fallback.py",
            "specialists/rudi/fallback_eval.py",
            "specialists/rudi/retrieval_cases.py",
            "specialists/rudi/retrieval_eval.py",
            "specialists/rudi/retrieval_memory.py",
            "specialists/rudi/retrieval_nodes.py",
            "specialists/rudi/retrieval_preview.py",
            "specialists/rudi/retrieval_strategies.py",
            "specialists/rudi/retrieval_trace_report.py",
            "specialists/rudi/retrieval_types.py",
            "specialists/rudi/embeddings.py",
            "specialists/rudi/vector_math.py",
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
            "specialists/cogs/specialist.py",
            "specialists/cogs/planning.py",
            "specialists/cogs/naming.py",
            "specialists/cogs/format.py",
            "specialists/cogs/time_context.py",
            "specialists/cogs/carry.py",
            "specialists/cogs/nightly.py",
        ),
        commands=(
            "scripts/cogs-specialist",
            "scripts/cogs-planning",
            "scripts/carry",
            "scripts/nightly",
        ),
    ),
    SpecialistDefinition(
        specialist_id="astro",
        display_name="Astro",
        role="Vault-facing render and manual work surfaces",
        runtime_form="Library provider and vault-facing commands",
        implementation_files=(
            "specialists/astro/vault.py",
            "specialists/astro/obsidian_views.py",
            "specialists/astro/inspect_hierarchy.py",
        ),
        commands=(
            "scripts/obsidian-views",
            "scripts/hierarchy",
        ),
    ),
    SpecialistDefinition(
        specialist_id="cogswell",
        display_name="Cogswell",
        role="Database and collection graph bridge",
        runtime_form="Commands and SQLite-backed graph resources",
        implementation_files=(
            "specialists/cogswell/collections.py",
            "specialists/cogswell/fixture_data/stage109_lincoln_cents.csv",
            "specialists/cogswell/fixture_data/stage109_us_stamps.csv",
        ),
        commands=(
            "scripts/collections-init",
            "scripts/collections-import",
            "scripts/collections-query",
            "scripts/collections-sync",
            "scripts/collections-bridge",
            "scripts/collections-surface",
            "scripts/collections-export",
        ),
    ),
    SpecialistDefinition(
        specialist_id="sprockets",
        display_name="Sprockets",
        role="Hierarchy, graph, and durable structure",
        runtime_form="Commands and review-first previews",
        implementation_files=(
            "specialists/sprockets/specialist.py",
            "specialists/sprockets/vault_graph.py",
            "substrate/models.py",
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
            "specialists/jane/specialist.py",
            "specialists/jane/review.py",
        ),
        commands=(
            "scripts/review-specialist",
            "scripts/review",
        ),
    ),
    SpecialistDefinition(
        specialist_id="uniblab",
        display_name="Uniblab",
        role="Operations, health, status, readiness, and model probes",
        runtime_form="Commands and possible scheduled health checks",
        implementation_files=(
            "specialists/uniblab/system_status.py",
            "specialists/uniblab/job_status.py",
            "specialists/uniblab/job_supervisor.py",
            "specialists/uniblab/model_ab.py",
            "specialists/uniblab/model_capability_probe.py",
            "specialists/uniblab/memory_tool_probe.py",
            "specialists/uniblab/phase86_status.py",
            "specialists/uniblab/backup.py",
            "specialists/uniblab/smoke_test.py",
            "specialists/uniblab/stage_closeout.py",
        ),
        commands=(
            "scripts/status",
            "scripts/job-status",
            "scripts/job-supervisor",
            "scripts/model-ab",
            "scripts/model-capability-probe",
            "scripts/phase86-status",
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

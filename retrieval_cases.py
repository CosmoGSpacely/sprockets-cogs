"""Static retrieval benchmark cases and fixture nodes."""
from __future__ import annotations

from pathlib import Path

from retrieval_types import RetrievalCase, RetrievalNode


def stage_15_fixture_nodes() -> tuple[RetrievalNode, ...]:
    """Return in-memory nodes that match the built-in readiness cases."""

    return (
        RetrievalNode(
            node_id="contacts/jordan-mack",
            title="Jordan Mack",
            node_type="sprockets/contact",
            path=Path("contacts/jordan-mack.md"),
            text="Proposal follow-up contact for current product feedback.",
        ),
        RetrievalNode(
            node_id="contacts/jordan-lee",
            title="Jordan Lee",
            node_type="sprockets/contact",
            path=Path("contacts/jordan-lee.md"),
            text="Unrelated contact for legal filings.",
        ),
        RetrievalNode(
            node_id="goals/build-sprockets-cogs",
            title="Build Sprockets-Cogs",
            node_type="sprockets/goal",
            path=Path("goals/build-sprockets-cogs.md"),
            text="Goal covering the agentic personal operating system.",
        ),
        RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("projects/phase-3-memory-enhancement.md"),
            parent_slugs=("build-sprockets-cogs",),
            text="Evaluate retrieval quality before embedding or memory index work.",
        ),
        RetrievalNode(
            node_id="projects/phase-2-hardening",
            title="Phase 2 - Hardening",
            node_type="sprockets/project",
            path=Path("projects/phase-2-hardening.md"),
            parent_slugs=("build-sprockets-cogs",),
            text="Completed service hardening and review routing phase.",
        ),
        RetrievalNode(
            node_id="daily/2026-05-02",
            title="Sat 02 May 2026",
            node_type="cogs/daily",
            path=Path("daily/Sat 02 May 2026.md"),
            text="Yesterday note about retrieval traces and memory benchmark setup.",
        ),
        RetrievalNode(
            node_id="daily/2026-04-01",
            title="Wed 01 Apr 2026",
            node_type="cogs/daily",
            path=Path("daily/Wed 01 Apr 2026.md"),
            text="Old retrieval traces scratch note from a stale experiment.",
        ),
        RetrievalNode(
            node_id="notes/openai-fallback-review-first",
            title="OpenAI fallback review-first",
            node_type="sprockets/note",
            path=Path("notes/openai-fallback-review-first.md"),
            text="Current fallback provider routes candidates to review before vault writes.",
        ),
        RetrievalNode(
            node_id="notes/anthropic-fallback-plan",
            title="Anthropic fallback plan",
            node_type="sprockets/note",
            path=Path("notes/anthropic-fallback-plan.md"),
            text="Obsolete fallback provider plan from before OpenAI review routing.",
        ),
        RetrievalNode(
            node_id="notes/dataview-dashboard",
            title="Dataview dashboard",
            node_type="sprockets/note",
            path=Path("notes/dataview-dashboard.md"),
            text="Compact Dataview dashboard idea for current task review.",
        ),
        RetrievalNode(
            node_id="notes/old-dashboard-verbatim-draft",
            title="Old dashboard verbatim draft",
            node_type="sprockets/note",
            path=Path("notes/old-dashboard-verbatim-draft.md"),
            text="Old verbose dashboard prose that should not contaminate fresh captures.",
        ),
        RetrievalNode(
            node_id="projects/learn-how-to-bring-a-project-to-production",
            title="Learn how to bring a project to production",
            node_type="sprockets/project",
            path=Path("projects/learn-how-to-bring-a-project-to-production.md"),
            parent_slugs=("acquire-necessary-skills",),
            text="Deployment, release operations, service monitoring, backups, and production readiness.",
        ),
        RetrievalNode(
            node_id="notes/laptop-setup",
            title="Laptop setup",
            node_type="sprockets/note",
            path=Path("notes/laptop-setup.md"),
            text="Local workstation setup details for development only.",
        ),
    )


def stage_15_cases() -> tuple[RetrievalCase, ...]:
    """Return the initial Phase 3 readiness cases."""

    return (
        RetrievalCase(
            name="named-contact-followup",
            category="named_entity",
            query="Remind me to ask Jordan about the proposal follow-up.",
            expected_ids=frozenset({"contacts/jordan-mack"}),
            avoid_ids=frozenset({"contacts/jordan-lee"}),
            reason="Named people must retrieve the right contact without grabbing a similarly named contact.",
        ),
        RetrievalCase(
            name="project-scoped-task",
            category="project_scope",
            query="Add a task for the Phase 3 memory work to evaluate retrieval quality.",
            expected_ids=frozenset({"projects/phase-3-memory-enhancement"}),
            avoid_ids=frozenset({"projects/phase-2-hardening"}),
            reason="Project-scoped work should retrieve the active project, not a completed phase.",
        ),
        RetrievalCase(
            name="hierarchy-parent-hint",
            category="hierarchy",
            query="This belongs under Build Sprockets-Cogs, probably the memory phase.",
            expected_ids=frozenset({
                "goals/build-sprockets-cogs",
                "projects/phase-3-memory-enhancement",
            }),
            reason="Hierarchy context should include both the goal and the relevant project.",
        ),
        RetrievalCase(
            name="recent-cogs-history",
            category="recent_cogs",
            query="Continue the note from yesterday about retrieval traces.",
            expected_ids=frozenset({"daily/2026-05-02"}),
            avoid_ids=frozenset({"daily/2026-04-01"}),
            reason="Recent daily context should be available without reviving stale daily notes.",
        ),
        RetrievalCase(
            name="stale-note-rejection",
            category="staleness",
            query="Use the current fallback provider for review routing.",
            expected_ids=frozenset({"notes/openai-fallback-review-first"}),
            avoid_ids=frozenset({"notes/anthropic-fallback-plan"}),
            reason="Retrieval must prefer the current OpenAI fallback design over obsolete Anthropic notes.",
        ),
        RetrievalCase(
            name="contamination-resistance",
            category="contamination",
            query="Capture an idea about a compact Dataview dashboard.",
            expected_ids=frozenset({"notes/dataview-dashboard"}),
            avoid_ids=frozenset({"notes/old-dashboard-verbatim-draft"}),
            reason="Relevant memory should guide classification without copying old prose into new output.",
        ),
        RetrievalCase(
            name="semantic-language-gap",
            category="semantic_gap",
            query="What should I study so this can run beyond my laptop?",
            expected_ids=frozenset({"projects/learn-how-to-bring-a-project-to-production"}),
            avoid_ids=frozenset({"notes/laptop-setup"}),
            reason="The harness should include at least one case that keyword matching alone is unlikely to solve.",
        ),
    )


def stage_15_real_vault_cases() -> tuple[RetrievalCase, ...]:
    """Return readiness cases grounded in the current real vault contents."""

    return (
        RetrievalCase(
            name="named-contact-followup",
            category="named_entity",
            query="Call Tom Reilly at GlobalTech about the invoice.",
            expected_ids=frozenset({
                "contacts/tom-reilly",
                "entities/globaltech",
            }),
            avoid_ids=frozenset({
                "contacts/sandra-cho",
                "entities/vertex-industries",
            }),
            reason="Named people and organizations should retrieve the right contact/entity context.",
        ),
        RetrievalCase(
            name="project-scoped-task",
            category="project_scope",
            query="Add a task for the Phase 3 memory work to evaluate retrieval quality.",
            expected_ids=frozenset({"projects/phase-3-memory-enhancement"}),
            avoid_ids=frozenset({"projects/phase-2-hardening"}),
            reason="Project-scoped work should retrieve the active memory project, not the completed hardening phase.",
        ),
        RetrievalCase(
            name="hierarchy-parent-hint",
            category="hierarchy",
            query="This belongs under Build Sprockets-Cogs, probably the memory phase.",
            expected_ids=frozenset({
                "goals/build-sprockets-cogs",
                "projects/phase-3-memory-enhancement",
            }),
            reason="Hierarchy context should include both the goal and the relevant project.",
        ),
        RetrievalCase(
            name="recent-cogs-history",
            category="recent_cogs",
            query="Continue the note from today about hierarchy context tests.",
            expected_ids=frozenset({"daily/2026-05-03"}),
            avoid_ids=frozenset({"daily/2026-04-23"}),
            reason="Recent daily context should be available without reviving older daily notes.",
        ),
        RetrievalCase(
            name="stale-note-rejection",
            category="staleness",
            query="Use the weekly review template idea for review planning.",
            expected_ids=frozenset({"notes/idea-build-a-weekly-review-template"}),
            avoid_ids=frozenset({"notes/reflection-on-phase-2---hierarchy"}),
            reason="Retrieval should prefer the current review-template note over unrelated hierarchy reflections.",
        ),
        RetrievalCase(
            name="contamination-resistance",
            category="contamination",
            query="Capture a reflection on Phase 2 hierarchy work.",
            expected_ids=frozenset({"notes/reflection-on-phase-2---hierarchy"}),
            avoid_ids=frozenset({"tasks/add-hierarchy-context-tests-for-phase-2---hardening"}),
            reason="Retrieval should find the reflection note without pulling task text in as prose to copy.",
        ),
        RetrievalCase(
            name="semantic-language-gap",
            category="semantic_gap",
            query="What should I study so this can run beyond my laptop?",
            expected_ids=frozenset({"projects/learn-how-to-bring-a-project-to-production"}),
            avoid_ids=frozenset({"notes/follow-up-with-ben-hartley"}),
            reason="This real-vault case should remain difficult for lexical retrieval and useful for embeddings.",
        ),
    )


def select_cases(case_set: str, retriever_name: str) -> tuple[RetrievalCase, ...]:
    """Choose fixture or real-vault cases for a benchmark run."""

    if case_set == "fixture":
        return stage_15_cases()
    if case_set == "real-vault":
        return stage_15_real_vault_cases()
    if retriever_name in {
        "lexical-vault",
        "memory-vault",
        "memory-embedding-vault",
        "memory-embedding-gated-vault",
        "memory-embedding-graph-gated-vault",
        "memory-packet-embedding-gated-vault",
        "embedding-vault",
        "hybrid-vault",
        "hybrid-graph-vault",
        "hybrid-graph-intent-vault",
    }:
        return stage_15_real_vault_cases()
    return stage_15_cases()

"""Stage 15 retrieval readiness harness.

This module defines the measuring surface for Phase 3 memory work. It does
not implement semantic search, embeddings, or a memory index; it only names
the cases future retrievers must satisfy and provides deterministic scoring.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import frontmatter

from vault_graph import build_graph, sprockets_dirs


@dataclass(frozen=True)
class RetrievalNode:
    """A compact representation of a vault node available for retrieval."""

    node_id: str
    title: str
    node_type: str
    path: Path
    parent_slugs: tuple[str, ...] = ()
    text: str = ""


@dataclass(frozen=True)
class RetrievalCase:
    """A single retrieval expectation for a future memory implementation."""

    name: str
    query: str
    expected_ids: frozenset[str]
    avoid_ids: frozenset[str] = frozenset()
    category: str = "general"
    reason: str = ""


@dataclass(frozen=True)
class RetrievalCaseResult:
    """Result for one retrieval case."""

    case: RetrievalCase
    retrieved_ids: tuple[str, ...]
    missing_ids: frozenset[str]
    forbidden_ids: frozenset[str]

    @property
    def passed(self) -> bool:
        return not self.missing_ids and not self.forbidden_ids


@dataclass(frozen=True)
class RetrievalSuiteResult:
    """Aggregate result for a retrieval benchmark run."""

    results: tuple[RetrievalCaseResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def total_count(self) -> int:
        return len(self.results)


Retriever = Callable[[str], Iterable[object]]


def _retrieved_id(item: object) -> str:
    if isinstance(item, RetrievalNode):
        return item.node_id
    if isinstance(item, Path):
        return item.as_posix()
    if isinstance(item, dict):
        for key in ("node_id", "id", "path"):
            value = item.get(key)
            if value:
                return str(value)
    return str(item)


def evaluate_retriever(
    cases: Iterable[RetrievalCase],
    retriever: Retriever,
) -> RetrievalSuiteResult:
    """Run cases against a retriever and record missing or contaminating hits."""

    results: list[RetrievalCaseResult] = []
    for case in cases:
        retrieved_ids = tuple(dict.fromkeys(_retrieved_id(item) for item in retriever(case.query)))
        retrieved_set = set(retrieved_ids)
        results.append(
            RetrievalCaseResult(
                case=case,
                retrieved_ids=retrieved_ids,
                missing_ids=frozenset(case.expected_ids - retrieved_set),
                forbidden_ids=frozenset(case.avoid_ids & retrieved_set),
            )
        )
    return RetrievalSuiteResult(tuple(results))


def load_retrieval_nodes(vault_dir: Path) -> list[RetrievalNode]:
    """Load compact retrieval candidates from Sprockets frontmatter and bodies."""

    graph = build_graph(vault_dir)
    nodes: list[RetrievalNode] = []
    for folder in sprockets_dirs(vault_dir):
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.md")):
            try:
                post = frontmatter.load(str(path))
            except Exception:
                continue
            slug = path.stem
            nodes.append(
                RetrievalNode(
                    node_id=f"{folder.name}/{slug}",
                    title=str(post.get("title", slug)),
                    node_type=str(post.get("node_type", "")),
                    path=path,
                    parent_slugs=tuple(graph.successors(slug)) if graph.has_node(slug) else (),
                    text=post.content.strip(),
                )
            )
    return nodes


def stage_15_cases() -> tuple[RetrievalCase, ...]:
    """Return the initial Phase 3 readiness cases.

    The IDs are intentionally fixture-friendly rather than tied to the user's
    live vault. Future stages can add a real-vault smoke case once the index
    abstraction exists.
    """

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
    )


def main() -> None:
    """Print the current retrieval baseline without failing the build."""

    import argparse

    import agentic_loop

    parser = argparse.ArgumentParser(description="Run the Stage 15 retrieval readiness benchmark.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero unless every retrieval case passes.",
    )
    args = parser.parse_args()

    result = evaluate_retriever(stage_15_cases(), agentic_loop.retrieve_relevant_nodes)

    print("Stage 15 retrieval readiness")
    print(f"- passed: {result.passed_count}/{result.total_count}")
    print(f"- status: {'pass' if result.passed else 'baseline'}")
    for case_result in result.results:
        marker = "pass" if case_result.passed else "miss"
        print(f"\n{case_result.case.name}: {marker}")
        print(f"- category: {case_result.case.category}")
        if case_result.missing_ids:
            print("- missing: " + ", ".join(sorted(case_result.missing_ids)))
        if case_result.forbidden_ids:
            print("- forbidden: " + ", ".join(sorted(case_result.forbidden_ids)))

    if args.strict and not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

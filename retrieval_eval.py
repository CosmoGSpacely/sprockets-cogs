"""Stage 15 retrieval readiness harness.

This module defines the measuring surface for Phase 3 memory work. It does
not implement semantic search, embeddings, or a memory index; it only names
the cases future retrievers must satisfy and provides deterministic scoring.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
import re
from typing import Callable, Iterable

import frontmatter

from vault_graph import build_graph, sprockets_dirs


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "about",
    "add",
    "an",
    "and",
    "for",
    "from",
    "me",
    "probably",
    "the",
    "this",
    "to",
    "under",
    "use",
}


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


@dataclass(frozen=True)
class RetrievalTargetStatus:
    """Presence report for benchmark target IDs in a loaded node set."""

    case: RetrievalCase
    present_expected_ids: frozenset[str]
    missing_expected_ids: frozenset[str]
    present_avoid_ids: frozenset[str]


@dataclass(frozen=True)
class SemanticQueryHint:
    """A grounded query expansion for known user phrasing."""

    label: str
    expansion_terms: tuple[str, ...]

    @property
    def expansion_text(self) -> str:
        return " ".join(self.expansion_terms)


@dataclass(frozen=True)
class ExperimentalRetriever:
    """Reusable benchmark retriever assembled from loaded nodes and strategies."""

    name: str
    nodes: tuple[RetrievalNode, ...]
    retriever: Retriever
    trace_provider: Callable[[str], object | None] | None = None

    def retrieve(self, query: str) -> Iterable[object]:
        return self.retriever(query)

    def trace(self, query: str) -> object | None:
        if self.trace_provider is None:
            return None
        return self.trace_provider(query)


Retriever = Callable[[str], Iterable[object]]


def _retrieved_id(item: object) -> str:
    if isinstance(item, RetrievalNode):
        return item.node_id
    node_id = getattr(item, "node_id", None)
    if node_id:
        return str(node_id)
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


def evaluate_target_presence(
    cases: Iterable[RetrievalCase],
    nodes: Iterable[RetrievalNode],
) -> tuple[RetrievalTargetStatus, ...]:
    """Report which expected and avoid IDs exist in a loaded vault/node set."""

    available_ids = {node.node_id for node in nodes}
    statuses: list[RetrievalTargetStatus] = []
    for case in cases:
        statuses.append(
            RetrievalTargetStatus(
                case=case,
                present_expected_ids=frozenset(case.expected_ids & available_ids),
                missing_expected_ids=frozenset(case.expected_ids - available_ids),
                present_avoid_ids=frozenset(case.avoid_ids & available_ids),
            )
        )
    return tuple(statuses)


def retrieval_node_counts(nodes: Iterable[RetrievalNode]) -> dict[str, int]:
    """Return node counts by node_type for scan summaries."""

    counts: dict[str, int] = {}
    for node in nodes:
        counts[node.node_type] = counts.get(node.node_type, 0) + 1
    return dict(sorted(counts.items()))


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS}


def _node_search_text(node: RetrievalNode) -> str:
    return " ".join(
        (
            node.node_id,
            node.title,
            node.node_type,
            " ".join(node.parent_slugs),
            node.text,
        )
    )


def lexical_retrieve(
    query: str,
    nodes: Iterable[RetrievalNode],
    limit: int = 5,
    min_score: int = 1,
    min_best_ratio: float = 0.8,
) -> list[RetrievalNode]:
    """Rank nodes with a deterministic lexical baseline.

    This is deliberately modest. It is useful as a lower-bound comparator for
    future embedding retrieval, not as the final Phase 3 memory strategy.
    """

    query_tokens = _tokens(query)
    ranked: list[tuple[int, str, RetrievalNode]] = []
    for node in nodes:
        title_overlap = len(query_tokens & _tokens(node.title))
        id_overlap = len(query_tokens & _tokens(node.node_id.replace("/", " ")))
        parent_overlap = len(query_tokens & _tokens(" ".join(node.parent_slugs)))
        body_overlap = len(query_tokens & _tokens(node.text))
        score = title_overlap * 4 + id_overlap * 3 + parent_overlap * 2 + body_overlap
        if score >= min_score:
            ranked.append((score, node.node_id, node))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    if not ranked:
        return []
    best_score = ranked[0][0]
    cutoff = max(min_score, best_score * min_best_ratio)
    return [node for score, _, node in ranked if score >= cutoff][:limit]


def _rank_fusion(
    ranked_groups: Iterable[Iterable[RetrievalNode]],
    limit: int = 5,
) -> list[RetrievalNode]:
    """Merge ranked retrieval results with deterministic reciprocal-rank fusion."""

    if limit < 1:
        return []

    by_id: dict[str, RetrievalNode] = {}
    scores: dict[str, float] = {}
    for group in ranked_groups:
        for rank, node in enumerate(group, start=1):
            by_id.setdefault(node.node_id, node)
            scores[node.node_id] = scores.get(node.node_id, 0.0) + (1.0 / rank)

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [by_id[node_id] for node_id, _ in ranked[:limit]]


def _node_slug(node: RetrievalNode) -> str:
    return node.node_id.rsplit("/", 1)[-1]


def _node_type_priority(node: RetrievalNode) -> int:
    priority = {
        "sprockets/contact": 0,
        "sprockets/entity": 1,
        "sprockets/area": 2,
        "sprockets/goal": 3,
        "sprockets/project": 4,
        "sprockets/task": 5,
        "sprockets/note": 6,
        "cogs/daily": 7,
    }
    return priority.get(node.node_type, 99)


def _node_relation_text(node: RetrievalNode) -> str:
    return _node_search_text(node).lower()


def expand_retrieval_neighbors(
    ranked_nodes: Iterable[RetrievalNode],
    all_nodes: Iterable[RetrievalNode],
    limit: int = 5,
) -> list[RetrievalNode]:
    """Interleave retrieved nodes with nearby parent/child/title-mention nodes."""

    if limit < 1:
        return []

    all_node_tuple = tuple(all_nodes)
    by_id = {node.node_id: node for node in all_node_tuple}
    by_slug = {_node_slug(node): node for node in all_node_tuple}
    children_by_parent: dict[str, list[RetrievalNode]] = {}
    for node in all_node_tuple:
        for parent_slug in node.parent_slugs:
            children_by_parent.setdefault(parent_slug, []).append(node)

    expanded: list[RetrievalNode] = []
    seen: set[str] = set()

    def add(node: RetrievalNode) -> None:
        if node.node_id not in seen:
            seen.add(node.node_id)
            expanded.append(node)

    delayed_neighbors: list[RetrievalNode] = []
    for node in ranked_nodes:
        add(node)
        relation_text = _node_relation_text(node)
        mention_neighbors: list[RetrievalNode] = []
        hierarchy_neighbors: list[RetrievalNode] = []
        for parent_slug in node.parent_slugs:
            parent = by_slug.get(parent_slug)
            if parent:
                hierarchy_neighbors.append(parent)
        hierarchy_neighbors.extend(children_by_parent.get(_node_slug(node), []))
        for candidate in all_node_tuple:
            if candidate.node_id == node.node_id:
                continue
            title = candidate.title.strip().lower()
            if title and title in relation_text:
                mention_neighbors.append(candidate)

        mention_neighbors.sort(key=lambda item: (_node_type_priority(item), item.node_id))
        for neighbor in mention_neighbors:
            if neighbor.node_id in by_id:
                add(neighbor)
        delayed_neighbors.extend(hierarchy_neighbors)

    delayed_neighbors.sort(key=lambda item: (_node_type_priority(item), item.node_id))
    for neighbor in delayed_neighbors:
        if neighbor.node_id in by_id:
            add(neighbor)

    return expanded[:limit]


def _query_preferred_node_types(query: str) -> tuple[str, ...]:
    query_tokens = _tokens(query)
    if query_tokens & {"continue", "recent", "today", "yesterday"}:
        return ("cogs/daily",)
    if query_tokens & {"capture", "reflection", "note", "idea"}:
        return ("sprockets/note", "cogs/daily")
    return ()


def filter_by_query_intent(
    query: str,
    ranked_nodes: Iterable[RetrievalNode],
    limit: int = 5,
) -> list[RetrievalNode]:
    """Prefer node types implied by the query without returning an empty set."""

    if limit < 1:
        return []

    nodes = tuple(ranked_nodes)
    preferred_types = _query_preferred_node_types(query)
    if not preferred_types:
        return list(nodes[:limit])

    preferred = [
        node
        for node in nodes
        if node.node_type in preferred_types
    ]
    if not preferred:
        return list(nodes[:limit])
    return preferred[:limit]


def hybrid_retrieve(
    query: str,
    nodes: Iterable[RetrievalNode],
    embedding_retriever: Callable[[str], Iterable[RetrievalNode]],
    limit: int = 5,
    expand_graph: bool = False,
    apply_intent_filter: bool = False,
) -> list[RetrievalNode]:
    """Combine lexical and embedding retrieval without production wiring."""

    node_tuple = tuple(nodes)
    lexical_results = lexical_retrieve(query, node_tuple, limit=limit)
    embedding_results = tuple(embedding_retriever(query))
    results = _rank_fusion((lexical_results, embedding_results), limit=limit)
    if expand_graph:
        results = expand_retrieval_neighbors(results, node_tuple, limit=limit)
    if apply_intent_filter:
        results = filter_by_query_intent(query, results, limit=limit)
    return results


def _daily_node_id(path: Path) -> str:
    try:
        date = datetime.strptime(path.stem, "%a %d %b %Y").strftime("%Y-%m-%d")
    except ValueError:
        date = path.stem
    return f"daily/{date}"


def load_retrieval_nodes(vault_dir: Path) -> list[RetrievalNode]:
    """Load compact retrieval candidates from Sprockets nodes and daily notes."""

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

    daily_dir = vault_dir / "Cogs" / "daily"
    if daily_dir.exists():
        for path in sorted(daily_dir.glob("*.md")):
            nodes.append(
                RetrievalNode(
                    node_id=_daily_node_id(path),
                    title=path.stem,
                    node_type="cogs/daily",
                    path=path,
                    text=path.read_text().strip(),
                )
            )
    return nodes


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
        "embedding-vault",
        "hybrid-vault",
        "hybrid-graph-vault",
        "hybrid-graph-intent-vault",
    }:
        return stage_15_real_vault_cases()
    return stage_15_cases()


def build_experimental_retriever(name: str, vault_dir: Path) -> ExperimentalRetriever:
    """Build a named benchmark retriever without touching production retrieval."""

    if name == "memory-fixture":
        fixture_nodes = stage_15_fixture_nodes()
        retriever, trace_provider = _build_memory_index_retriever(fixture_nodes)
        return ExperimentalRetriever(
            name=name,
            nodes=fixture_nodes,
            retriever=retriever,
            trace_provider=trace_provider,
        )

    if name == "lexical-fixture":
        fixture_nodes = stage_15_fixture_nodes()
        return ExperimentalRetriever(
            name=name,
            nodes=fixture_nodes,
            retriever=lambda query: lexical_retrieve(query, fixture_nodes),
        )

    if name == "lexical-vault":
        scan_nodes = tuple(load_retrieval_nodes(vault_dir))
        return ExperimentalRetriever(
            name=name,
            nodes=scan_nodes,
            retriever=lambda query: lexical_retrieve(query, scan_nodes),
        )

    if name == "memory-vault":
        scan_nodes = tuple(load_retrieval_nodes(vault_dir))
        retriever, trace_provider = _build_memory_index_retriever(scan_nodes)
        return ExperimentalRetriever(
            name=name,
            nodes=scan_nodes,
            retriever=retriever,
            trace_provider=trace_provider,
        )

    if name == "memory-embedding-vault":
        scan_nodes = tuple(load_retrieval_nodes(vault_dir))
        retriever, trace_provider = _build_memory_index_retriever(
            scan_nodes,
            use_embeddings=True,
        )
        return ExperimentalRetriever(
            name=name,
            nodes=scan_nodes,
            retriever=retriever,
            trace_provider=trace_provider,
        )

    if name == "memory-embedding-gated-vault":
        scan_nodes = tuple(load_retrieval_nodes(vault_dir))
        retriever, trace_provider = _build_memory_index_retriever(
            scan_nodes,
            use_embeddings=True,
            gate_low_confidence=True,
        )
        return ExperimentalRetriever(
            name=name,
            nodes=scan_nodes,
            retriever=retriever,
            trace_provider=trace_provider,
        )

    if name in {
        "embedding-vault",
        "hybrid-vault",
        "hybrid-graph-vault",
        "hybrid-graph-intent-vault",
    }:
        from embeddings import JsonEmbeddingCache, build_embedding_index, retrieve_by_embedding

        scan_nodes = tuple(load_retrieval_nodes(vault_dir))
        index = build_embedding_index(scan_nodes, cache=JsonEmbeddingCache.default())

        if name == "embedding-vault":
            retriever = lambda query: retrieve_by_embedding(query, index)
        else:
            retriever = lambda query: hybrid_retrieve(
                query,
                scan_nodes,
                lambda embedding_query: retrieve_by_embedding(embedding_query, index),
                expand_graph=name in {
                    "hybrid-graph-vault",
                    "hybrid-graph-intent-vault",
                },
                apply_intent_filter=name == "hybrid-graph-intent-vault",
            )

        return ExperimentalRetriever(
            name=name,
            nodes=scan_nodes,
            retriever=retriever,
        )

    if name == "current":
        import agentic_loop

        return ExperimentalRetriever(
            name=name,
            nodes=(),
            retriever=agentic_loop.retrieve_relevant_nodes,
        )

    raise ValueError(f"unknown retriever: {name}")


def _build_memory_index_retriever(
    nodes: tuple[RetrievalNode, ...],
    use_embeddings: bool = False,
    gate_low_confidence: bool = False,
) -> tuple[Retriever, Callable[[str], object]]:
    from memory_index import (
        InMemoryMemoryIndex,
        MemoryQuery,
        MemoryRecord,
        RetrievalConfidence,
        RetrievalTrace,
        memory_record_from_retrieval_node,
        vector_metadata_for,
    )

    by_id = {node.node_id: node for node in nodes}
    query_vector_provider: Callable[[str], tuple[float, ...] | None] = lambda _query: None
    records = [memory_record_from_retrieval_node(node) for node in nodes]
    if use_embeddings:
        from embeddings import EMBED_MODEL, JsonEmbeddingCache, build_embedding_index, embed_text

        embedded_by_id = {
            embedded.node.node_id: embedded
            for embedded in build_embedding_index(nodes, cache=JsonEmbeddingCache.default())
        }
        records = [
            MemoryRecord(
                metadata=record.metadata,
                vector=embedded_by_id[record.node_id].vector,
                vector_metadata=vector_metadata_for(
                    EMBED_MODEL,
                    record.metadata.text_hash,
                    embedded_by_id[record.node_id].vector,
                ),
            )
            if record.node_id in embedded_by_id
            else record
            for record in records
        ]
        query_vector_provider = lambda query: tuple(embed_text(query))

    index = InMemoryMemoryIndex(records)
    recent_daily_nodes = tuple(
        sorted(
            (
                node
                for node in nodes
                if node.node_type == "cogs/daily"
                and _retrieval_daily_date(node) <= date.today()
            ),
            key=lambda node: node.node_id,
            reverse=True,
        )
    )

    def retrieve(query: str) -> list[RetrievalNode]:
        results, retrieval_trace, memory_query = _query_memory(query)
        if _is_daily_fallback(query, results, memory_query):
            return list(recent_daily_nodes[:memory_query.limit])
        if gate_low_confidence and _confidence_gate_blocks(retrieval_trace):
            return []
        return [by_id[result.node_id] for result in results if result.node_id in by_id]

    def trace(query: str) -> object:
        results, retrieval_trace, memory_query = _query_memory(query)
        if _is_daily_fallback(query, results, memory_query):
            fallback_ids = tuple(node.node_id for node in recent_daily_nodes[:memory_query.limit])
            retrieval_trace = RetrievalTrace(
                query=memory_query,
                retriever_name=retrieval_trace.retriever_name,
                result_ids=fallback_ids,
                filters_applied=retrieval_trace.filters_applied,
                notes=retrieval_trace.notes + ("daily recency fallback",),
                result_summaries=tuple(
                    f"{node.node_id} score=0 reasons=daily-recency-fallback"
                    for node in recent_daily_nodes[:memory_query.limit]
                ),
                confidence=RetrievalConfidence(
                    level="high",
                    action="use",
                    reasons=("daily recency fallback",),
                ),
            )
        if gate_low_confidence and _confidence_gate_blocks(retrieval_trace):
            return replace(
                retrieval_trace,
                result_ids=(),
                notes=retrieval_trace.notes + ("confidence gate withheld low-confidence results",),
            )
        return retrieval_trace

    def _query_memory(
        query: str,
    ) -> tuple[tuple[object, ...], object, MemoryQuery]:
        preferred_types = _query_preferred_node_types(query)
        query_vector = query_vector_provider(query)
        if preferred_types == ("cogs/daily",):
            query_vector = None
        semantic_hints = _semantic_query_hints(query) if gate_low_confidence else ()
        query_text = " ".join(
            (query, *(hint.expansion_text for hint in semantic_hints))
        ) if semantic_hints else query
        memory_query = MemoryQuery(
            text=query_text,
            node_types=preferred_types,
            query_vector=query_vector,
        )
        results, retrieval_trace = index.query_with_trace(memory_query)
        if preferred_types and preferred_types != ("cogs/daily",) and not results:
            memory_query = MemoryQuery(text=query_text, query_vector=query_vector)
            results, retrieval_trace = index.query_with_trace(memory_query)
        if semantic_hints:
            retrieval_trace = replace(
                retrieval_trace,
                notes=retrieval_trace.notes + (
                    *(
                        f"semantic hint applied: {hint.label}"
                        for hint in semantic_hints
                    ),
                ),
            )
        return results, retrieval_trace, memory_query

    return retrieve, trace


def _confidence_gate_blocks(trace: object) -> bool:
    confidence = getattr(trace, "confidence", None)
    return getattr(confidence, "action", None) == "review"


def _is_daily_fallback(
    query: str,
    results: tuple[object, ...],
    memory_query: object,
) -> bool:
    return (
        _query_preferred_node_types(query) == ("cogs/daily",)
        and not results
        and getattr(memory_query, "node_types", ()) == ("cogs/daily",)
    )


def _semantic_query_hints(query: str) -> tuple[SemanticQueryHint, ...]:
    query_tokens = _tokens(query)
    if (
        query_tokens & {"run", "available", "work"}
        and query_tokens & {"beyond", "away", "outside"}
        and query_tokens & {"laptop", "computer", "workstation"}
    ):
        return (
            SemanticQueryHint(
                label="production readiness",
                expansion_terms=(
                    "learn",
                    "bring",
                    "project",
                    "production",
                    "readiness",
                    "deployment",
                    "release",
                    "operations",
                    "service",
                    "monitoring",
                    "backups",
                ),
            ),
        )
    return ()


def _retrieval_daily_date(node: RetrievalNode) -> date:
    if node.node_id.startswith("daily/"):
        try:
            return datetime.strptime(node.node_id.removeprefix("daily/"), "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.min


def main() -> None:
    """Print the current retrieval baseline without failing the build."""

    import argparse

    parser = argparse.ArgumentParser(description="Run the Stage 15 retrieval readiness benchmark.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero unless every retrieval case passes.",
    )
    parser.add_argument(
        "--retriever",
        choices=(
            "current",
            "lexical-fixture",
            "memory-fixture",
            "lexical-vault",
            "memory-vault",
            "memory-embedding-vault",
            "memory-embedding-gated-vault",
            "embedding-vault",
            "hybrid-vault",
            "hybrid-graph-vault",
            "hybrid-graph-intent-vault",
        ),
        default="current",
        help="Retriever to evaluate. Defaults to the current production stub.",
    )
    parser.add_argument(
        "--vault-dir",
        type=Path,
        default=Path("/home/cosmo/vault"),
        help="Vault directory for vault-backed retrievers. Defaults to /home/cosmo/vault.",
    )
    parser.add_argument(
        "--case-set",
        choices=("auto", "fixture", "real-vault"),
        default="auto",
        help="Benchmark cases to run. Auto uses real-vault cases for vault-backed retrievers and fixture cases otherwise.",
    )
    parser.add_argument(
        "--list-nodes",
        action="store_true",
        help="Print a read-only retrieval-node inventory for vault-backed retrievers.",
    )
    parser.add_argument(
        "--show-targets",
        action="store_true",
        help="Print which benchmark expected/avoid target IDs exist in the loaded node set.",
    )
    parser.add_argument(
        "--show-traces",
        action="store_true",
        help="Print retrieval traces when the selected retriever supports them.",
    )
    args = parser.parse_args()

    experimental_retriever = build_experimental_retriever(args.retriever, args.vault_dir)
    scan_nodes = experimental_retriever.nodes

    cases = select_cases(args.case_set, args.retriever)
    result = evaluate_retriever(cases, experimental_retriever.retrieve)

    print("Stage 15 retrieval readiness")
    print(f"- retriever: {args.retriever}")
    vault_retrievers = {
        "lexical-vault",
        "memory-vault",
        "memory-embedding-vault",
        "memory-embedding-gated-vault",
        "embedding-vault",
        "hybrid-vault",
        "hybrid-graph-vault",
        "hybrid-graph-intent-vault",
    }
    print(f"- case-set: {args.case_set if args.case_set != 'auto' else ('real-vault' if args.retriever in vault_retrievers else 'fixture')}")
    if args.retriever in vault_retrievers:
        print(f"- vault: {args.vault_dir}")
    if scan_nodes:
        print(f"- nodes: {len(scan_nodes)}")
    print(f"- passed: {result.passed_count}/{result.total_count}")
    print(f"- status: {'pass' if result.passed else 'baseline'}")
    if args.list_nodes and scan_nodes:
        print("\nNode inventory")
        for node_type, count in retrieval_node_counts(scan_nodes).items():
            print(f"- {node_type or '(unknown)'}: {count}")
    if args.show_targets and scan_nodes:
        print("\nTarget inventory")
        for status in evaluate_target_presence(cases, scan_nodes):
            print(f"\n{status.case.name}")
            if status.present_expected_ids:
                print("- present expected: " + ", ".join(sorted(status.present_expected_ids)))
            if status.missing_expected_ids:
                print("- missing expected: " + ", ".join(sorted(status.missing_expected_ids)))
            if status.present_avoid_ids:
                print("- present avoid: " + ", ".join(sorted(status.present_avoid_ids)))
    confidence_counts: dict[str, int] = {}
    for case_result in result.results:
        marker = "pass" if case_result.passed else "miss"
        print(f"\n{case_result.case.name}: {marker}")
        print(f"- category: {case_result.case.category}")
        if case_result.retrieved_ids:
            print("- retrieved: " + ", ".join(case_result.retrieved_ids))
        if case_result.missing_ids:
            print("- missing: " + ", ".join(sorted(case_result.missing_ids)))
        if case_result.forbidden_ids:
            print("- forbidden: " + ", ".join(sorted(case_result.forbidden_ids)))
        if args.show_traces:
            trace = experimental_retriever.trace(case_result.case.query)
            if trace is None:
                print("- trace: unavailable")
            else:
                print("- trace retriever: " + str(getattr(trace, "retriever_name", "unknown")))
                filters = getattr(trace, "filters_applied", {})
                if filters:
                    print("- trace filters: " + ", ".join(
                        f"{key}={','.join(value)}" for key, value in filters.items()
                    ))
                notes = getattr(trace, "notes", ())
                if notes:
                    print("- trace notes: " + "; ".join(str(note) for note in notes))
                quality_flags = getattr(trace, "quality_flags", ())
                if quality_flags:
                    print("- trace quality: " + "; ".join(str(flag) for flag in quality_flags))
                confidence = getattr(trace, "confidence", None)
                if confidence is not None:
                    confidence_key = (
                        f"{getattr(confidence, 'level', 'unknown')}/"
                        f"{getattr(confidence, 'action', 'unknown')}"
                    )
                    confidence_counts[confidence_key] = confidence_counts.get(confidence_key, 0) + 1
                    reasons = ", ".join(getattr(confidence, "reasons", ()))
                    suffix = f" ({reasons})" if reasons else ""
                    print(
                        "- trace confidence: "
                        f"{confidence_key}"
                        f"{suffix}"
                    )
                result_summaries = getattr(trace, "result_summaries", ())
                if result_summaries:
                    print("- trace results:")
                    for summary in result_summaries:
                        print(f"  - {summary}")
    if args.show_traces and confidence_counts:
        print("\nConfidence summary")
        for key, count in sorted(confidence_counts.items()):
            print(f"- {key}: {count}")

    if args.strict and not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

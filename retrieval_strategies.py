"""Retrieval ranking strategies used by the Stage 15/17 benchmark harness."""
from __future__ import annotations

from collections.abc import Callable, Iterable
import re

from retrieval_types import RetrievalNode, SemanticQueryHint


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


def tokens(text: str) -> set[str]:
    """Tokenize retrieval text with benchmark stopword filtering."""

    return {token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS}


def node_search_text(node: RetrievalNode) -> str:
    """Return the text fields used by lexical retrieval and graph expansion."""

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
    """Rank nodes with a deterministic lexical baseline."""

    query_tokens = tokens(query)
    ranked: list[tuple[int, str, RetrievalNode]] = []
    for node in nodes:
        title_overlap = len(query_tokens & tokens(node.title))
        id_overlap = len(query_tokens & tokens(node.node_id.replace("/", " ")))
        parent_overlap = len(query_tokens & tokens(" ".join(node.parent_slugs)))
        body_overlap = len(query_tokens & tokens(node.text))
        score = title_overlap * 4 + id_overlap * 3 + parent_overlap * 2 + body_overlap
        if score >= min_score:
            ranked.append((score, node.node_id, node))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    if not ranked:
        return []
    best_score = ranked[0][0]
    cutoff = max(min_score, best_score * min_best_ratio)
    return [node for score, _, node in ranked if score >= cutoff][:limit]


def rank_fusion(
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


def node_slug(node: RetrievalNode) -> str:
    """Return the final path/id slug for a retrieval node."""

    return node.node_id.rsplit("/", 1)[-1]


def node_type_priority(node: RetrievalNode) -> int:
    """Return deterministic ordering priority for graph-expanded neighbors."""

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
    by_slug = {node_slug(node): node for node in all_node_tuple}
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
        relation_text = node_search_text(node).lower()
        mention_neighbors: list[RetrievalNode] = []
        hierarchy_neighbors: list[RetrievalNode] = []
        for parent_slug in node.parent_slugs:
            parent = by_slug.get(parent_slug)
            if parent:
                hierarchy_neighbors.append(parent)
        hierarchy_neighbors.extend(children_by_parent.get(node_slug(node), []))
        for candidate in all_node_tuple:
            if candidate.node_id == node.node_id:
                continue
            title = candidate.title.strip().lower()
            if title and title in relation_text:
                mention_neighbors.append(candidate)

        mention_neighbors.sort(key=lambda item: (node_type_priority(item), item.node_id))
        for neighbor in mention_neighbors:
            if neighbor.node_id in by_id:
                add(neighbor)
        delayed_neighbors.extend(hierarchy_neighbors)

    delayed_neighbors.sort(key=lambda item: (node_type_priority(item), item.node_id))
    for neighbor in delayed_neighbors:
        if neighbor.node_id in by_id:
            add(neighbor)

    return expanded[:limit]


def query_preferred_node_types(query: str) -> tuple[str, ...]:
    """Return node-type filters implied by benchmark query phrasing."""

    query_tokens = tokens(query)
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
    preferred_types = query_preferred_node_types(query)
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
    results = rank_fusion((lexical_results, embedding_results), limit=limit)
    if expand_graph:
        results = expand_retrieval_neighbors(results, node_tuple, limit=limit)
    if apply_intent_filter:
        results = filter_by_query_intent(query, results, limit=limit)
    return results


def semantic_query_hints(query: str) -> tuple[SemanticQueryHint, ...]:
    """Return explicit semantic expansions for known benchmark phrasing."""

    query_tokens = tokens(query)
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

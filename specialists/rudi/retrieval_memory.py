"""Memory-index retriever builders for retrieval benchmark modes."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime

from retrieval_strategies import (
    expand_retrieval_neighbors_with_reasons,
    query_preferred_node_types,
    semantic_query_hints,
)
from retrieval_types import RetrievalNode


Retriever = Callable[[str], list[RetrievalNode]]


def build_memory_index_retriever(
    nodes: tuple[RetrievalNode, ...],
    use_embeddings: bool = False,
    gate_low_confidence: bool = False,
    expand_graph: bool = False,
) -> tuple[Retriever, Callable[[str], object]]:
    """Build an in-memory benchmark retriever backed by MemoryIndex."""

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
                and retrieval_daily_date(node) <= date.today()
            ),
            key=lambda node: node.node_id,
            reverse=True,
        )
    )

    def retrieve(query: str) -> list[RetrievalNode]:
        results, retrieval_trace, memory_query = query_memory(query)
        if is_daily_fallback(query, results, memory_query):
            return list(recent_daily_nodes[:memory_query.limit])
        if gate_low_confidence and confidence_gate_blocks(retrieval_trace):
            return []
        result_nodes = [by_id[result.node_id] for result in results if result.node_id in by_id]
        if expand_graph:
            expanded_nodes, _reasons = expand_top_memory_result_graph(
                result_nodes,
                nodes,
                limit=memory_query.limit,
            )
            return expanded_nodes
        return result_nodes

    def trace(query: str) -> object:
        results, retrieval_trace, memory_query = query_memory(query)
        if is_daily_fallback(query, results, memory_query):
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
            return retrieval_trace
        if gate_low_confidence and confidence_gate_blocks(retrieval_trace):
            return replace(
                retrieval_trace,
                result_ids=(),
                notes=retrieval_trace.notes + ("confidence gate withheld low-confidence results",),
            )
        if expand_graph:
            result_nodes = [by_id[result.node_id] for result in results if result.node_id in by_id]
            expanded_nodes, reasons = expand_top_memory_result_graph(
                result_nodes,
                nodes,
                limit=memory_query.limit,
            )
            return replace(
                retrieval_trace,
                result_ids=tuple(node.node_id for node in expanded_nodes),
                notes=retrieval_trace.notes + ("graph expansion applied",),
                result_summaries=tuple(
                    f"{node.node_id} graph={reasons.get(node.node_id, 'direct')}"
                    for node in expanded_nodes
                ),
            )
        return retrieval_trace

    def query_memory(
        query: str,
    ) -> tuple[tuple[object, ...], object, MemoryQuery]:
        preferred_types = query_preferred_node_types(query)
        query_vector = query_vector_provider(query)
        if preferred_types == ("cogs/daily",):
            query_vector = None
        semantic_hints = semantic_query_hints(query) if gate_low_confidence else ()
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


def expand_top_memory_result_graph(
    result_nodes: list[RetrievalNode],
    all_nodes: tuple[RetrievalNode, ...],
    limit: int,
) -> tuple[list[RetrievalNode], dict[str, str]]:
    """Expand graph context around the strongest memory result, preserving direct hits."""

    if limit < 1 or not result_nodes:
        return [], {}

    expanded_nodes, reasons = expand_retrieval_neighbors_with_reasons(
        result_nodes[:1],
        all_nodes,
        limit=limit,
    )

    ordered: list[RetrievalNode] = []
    seen: set[str] = set()

    def add(node: RetrievalNode, reason: str) -> None:
        if len(ordered) >= limit or node.node_id in seen:
            return
        ordered.append(node)
        reasons[node.node_id] = reason
        seen.add(node.node_id)

    add(result_nodes[0], "direct")
    preferred_graph_nodes = [
        node
        for node in expanded_nodes[1:]
        if reasons.get(node.node_id, "").startswith(("parent of ", "title mention in "))
    ]
    delayed_graph_nodes = [
        node
        for node in expanded_nodes[1:]
        if node not in preferred_graph_nodes
    ]
    for node in preferred_graph_nodes:
        add(node, reasons[node.node_id])
    for node in result_nodes[1:]:
        add(node, "direct")
    for node in delayed_graph_nodes:
        add(node, reasons[node.node_id])
    return ordered, {node.node_id: reasons[node.node_id] for node in ordered}


def confidence_gate_blocks(trace: object) -> bool:
    """Return whether a retrieval trace should be blocked by confidence gating."""

    confidence = getattr(trace, "confidence", None)
    return getattr(confidence, "action", None) == "review"


def is_daily_fallback(
    query: str,
    results: tuple[object, ...],
    memory_query: object,
) -> bool:
    """Return whether empty daily-filtered memory results should fall back to recency."""

    return (
        query_preferred_node_types(query) == ("cogs/daily",)
        and not results
        and getattr(memory_query, "node_types", ()) == ("cogs/daily",)
    )


def retrieval_daily_date(node: RetrievalNode) -> date:
    """Return a sortable date for a daily retrieval node."""

    if node.node_id.startswith("daily/"):
        try:
            return datetime.strptime(node.node_id.removeprefix("daily/"), "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.min

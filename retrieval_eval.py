"""Stage 15 retrieval readiness harness.

This module defines the measuring surface for Phase 3 memory work. It does
not implement semantic search, embeddings, or a memory index; it only names
the cases future retrievers must satisfy and provides deterministic scoring.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterable

from retrieval_cases import (
    select_cases,
    stage_15_cases,
    stage_15_fixture_nodes,
    stage_15_real_vault_cases,
)
from retrieval_nodes import load_retrieval_nodes, retrieval_node_counts
from retrieval_strategies import (
    expand_retrieval_neighbors,
    filter_by_query_intent,
    hybrid_retrieve,
    lexical_retrieve,
    query_preferred_node_types as _query_preferred_node_types,
    semantic_query_hints as _semantic_query_hints,
)
from retrieval_types import RetrievalCase, RetrievalNode, SemanticQueryHint


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

"""Stage 15 retrieval readiness harness.

This module defines the measuring surface for Phase 3 memory work. It does
not implement semantic search, embeddings, or a memory index; it only names
the cases future retrievers must satisfy and provides deterministic scoring.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from retrieval_cases import (
    select_cases,
    stage_15_cases,
    stage_15_fixture_nodes,
    stage_15_real_vault_cases,
    stage_22_packet_vault_cases,
)
from retrieval_memory import build_memory_index_retriever as _build_memory_index_retriever
from retrieval_nodes import load_retrieval_nodes, retrieval_node_counts
from retrieval_strategies import (
    expand_retrieval_neighbors,
    filter_by_query_intent,
    hybrid_retrieve,
    hybrid_retrieve_with_trace,
    lexical_retrieve,
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

    if name == "memory-embedding-graph-gated-vault":
        scan_nodes = tuple(load_retrieval_nodes(vault_dir))
        retriever, trace_provider = _build_memory_index_retriever(
            scan_nodes,
            use_embeddings=True,
            gate_low_confidence=True,
            expand_graph=True,
        )
        return ExperimentalRetriever(
            name=name,
            nodes=scan_nodes,
            retriever=retriever,
            trace_provider=trace_provider,
        )

    if name == "memory-packet-embedding-gated-vault":
        from memory_packets import load_memory_packet_retrieval_nodes

        source_nodes = tuple(load_retrieval_nodes(vault_dir))
        packet_nodes = load_memory_packet_retrieval_nodes(vault_dir)
        scan_nodes = source_nodes + packet_nodes
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
            trace_provider = None
        else:
            expand_graph = name in {
                "hybrid-graph-vault",
                "hybrid-graph-intent-vault",
            }
            apply_intent_filter = name == "hybrid-graph-intent-vault"

            def hybrid_result_and_trace(query: str) -> tuple[list[RetrievalNode], object]:
                return hybrid_retrieve_with_trace(
                    query,
                    scan_nodes,
                    lambda embedding_query: retrieve_by_embedding(embedding_query, index),
                    expand_graph=expand_graph,
                    apply_intent_filter=apply_intent_filter,
                    retriever_name=name,
                )

            retriever = lambda query: hybrid_result_and_trace(query)[0]
            trace_provider = lambda query: hybrid_result_and_trace(query)[1]

        return ExperimentalRetriever(
            name=name,
            nodes=scan_nodes,
            retriever=retriever,
            trace_provider=trace_provider,
        )

    if name == "current":
        import agentic_loop

        return ExperimentalRetriever(
            name=name,
            nodes=(),
            retriever=agentic_loop.retrieve_relevant_nodes,
        )

    raise ValueError(f"unknown retriever: {name}")


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
            "memory-embedding-graph-gated-vault",
            "memory-packet-embedding-gated-vault",
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
        default=Path.home() / "vault",
        help="Vault directory for vault-backed retrievers. Defaults to ~/vault.",
    )
    parser.add_argument(
        "--case-set",
        choices=("auto", "fixture", "real-vault", "packet-vault"),
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
        "memory-embedding-graph-gated-vault",
        "memory-packet-embedding-gated-vault",
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

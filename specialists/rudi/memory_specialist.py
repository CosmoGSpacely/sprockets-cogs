"""Memory specialist facade for Phase 4 orchestration.

Stage 41A keeps this boundary read-only. It reports memory configuration,
embedding cache posture, and guarded production retrieval status without
running retrieval, embedding calls, or production writes.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import embeddings
import production_retrieval
import retrieval_eval
from retrieval_nodes import load_retrieval_nodes, retrieval_node_counts
import retrieval_preview as retrieval_preview_module
import retrieval_trace_report


MEMORY_TRACE_PATH_ENV = "SPROCKETS_COGS_MEMORY_TRACE_PATH"
DEFAULT_MEMORY_TRACE_PATH = Path.home() / "sc" / "output" / "memory-parent-traces.jsonl"


@dataclass(frozen=True)
class MemorySpecialistConfig:
    """Filesystem and model settings owned by the Memory specialist."""

    vault_dir: Path = Path.home() / "vault"
    embedding_cache_path: Path = embeddings.EMBED_CACHE_PATH
    embedding_model: str = embeddings.EMBED_MODEL
    embedding_keep_alive: str = embeddings.EMBED_KEEP_ALIVE
    memory_trace_path: Path = DEFAULT_MEMORY_TRACE_PATH


@dataclass(frozen=True)
class EmbeddingCacheInventory:
    """Read-only summary of the embedding cache file."""

    path: Path
    exists: bool
    readable: bool
    schema_version: int | None = None
    entry_count: int = 0
    models: tuple[str, ...] = ()
    vector_dimensions: tuple[int, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class MemoryInventoryPreview:
    """Read-only memory specialist inventory result."""

    config: MemorySpecialistConfig
    cache: EmbeddingCacheInventory
    production_status: production_retrieval.ProductionRetrievalStatus


@dataclass(frozen=True)
class EmbeddingCacheCoverage:
    """Read-only cache coverage report for current vault retrieval nodes."""

    vault_dir: Path
    cache_path: Path
    model: str
    node_count: int
    covered_count: int
    missing_count: int
    stale_count: int
    extra_count: int
    node_counts: dict[str, int]
    missing_node_ids: tuple[str, ...] = ()
    stale_node_ids: tuple[str, ...] = ()
    extra_node_ids: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class MemoryBenchmarkPreview:
    """Read-only benchmark posture result for a selected retriever."""

    retriever_name: str
    case_set: str
    vault_dir: Path
    node_count: int
    passed_count: int
    total_count: int
    misses: tuple[str, ...] = ()


class MemorySpecialist:
    """Facade for memory retrieval, embeddings, traces, and cache maintenance."""

    def __init__(self, config: MemorySpecialistConfig | None = None) -> None:
        self.config = config or MemorySpecialistConfig()

    def cache_inventory(self) -> EmbeddingCacheInventory:
        """Inspect embedding cache metadata without mutating it."""

        path = self.config.embedding_cache_path
        if not path.exists():
            return EmbeddingCacheInventory(path=path, exists=False, readable=False)
        try:
            raw = json.loads(path.read_text())
        except Exception as exc:
            return EmbeddingCacheInventory(
                path=path,
                exists=True,
                readable=False,
                error=str(exc),
            )

        entries = raw.get("entries", {})
        if not isinstance(entries, dict):
            return EmbeddingCacheInventory(
                path=path,
                exists=True,
                readable=False,
                schema_version=_int_or_none(raw.get("schema_version")),
                error="entries must be an object",
            )

        models: set[str] = set()
        dimensions: set[int] = set()
        for entry in entries.values():
            if not isinstance(entry, dict):
                continue
            model = entry.get("model")
            if isinstance(model, str) and model:
                models.add(model)
            vector = entry.get("vector")
            if isinstance(vector, list):
                dimensions.add(len(vector))

        return EmbeddingCacheInventory(
            path=path,
            exists=True,
            readable=True,
            schema_version=_int_or_none(raw.get("schema_version")),
            entry_count=len(entries),
            models=tuple(sorted(models)),
            vector_dimensions=tuple(sorted(dimensions)),
        )

    def inventory(self) -> MemoryInventoryPreview:
        """Return read-only Memory specialist inventory."""

        return MemoryInventoryPreview(
            config=self.config,
            cache=self.cache_inventory(),
            production_status=production_retrieval.production_retrieval_status(self.config.vault_dir),
        )

    def retrieval_preview(
        self,
        query: str,
        retriever_name: str = retrieval_preview_module.DEFAULT_RETRIEVER,
    ) -> retrieval_preview_module.RetrievalPreview:
        """Run a read-only retrieval preview through the Memory boundary."""

        return retrieval_preview_module.preview_retrieval(
            query,
            vault_dir=self.config.vault_dir,
            retriever_name=retriever_name,
        )

    def context_preview(
        self,
        query: str,
        retriever_name: str = retrieval_preview_module.DEFAULT_RETRIEVER,
    ) -> str:
        """Preview compact prompt-context formatting without enabling memory context."""

        return retrieval_preview_module.format_context_preview(
            self.retrieval_preview(query, retriever_name=retriever_name)
        )

    def memory_guard_preview(
        self,
        query: str,
        retriever_name: str = retrieval_preview_module.DEFAULT_RETRIEVER,
    ) -> retrieval_preview_module.MemoryGuardPreview:
        """Preview post-classification memory guard behavior without writing."""

        return retrieval_preview_module.preview_memory_guard(
            self.retrieval_preview(query, retriever_name=retriever_name)
        )

    def production_return_preview(self, query: str) -> retrieval_preview_module.ProductionReturnPreview:
        """Preview exact compact production retrieval return nodes without writing."""

        return retrieval_preview_module.preview_production_return(query, vault_dir=self.config.vault_dir)

    def trace_report(
        self,
        limit: int | None = 20,
        decision: str = "",
        since: str = retrieval_trace_report.DEFAULT_SINCE,
        service_name: str = retrieval_trace_report.SERVICE_NAME,
        file_path: Path | None = None,
        jsonl_path: Path | None = None,
        use_journal: bool = False,
    ) -> str:
        """Return a read-only memory parent trace report."""

        if jsonl_path is not None or (not use_journal and file_path is None):
            path = jsonl_path or self.config.memory_trace_path
            lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else ()
            return retrieval_trace_report.format_memory_guard_jsonl_report(
                lines,
                limit=limit,
                decision=decision,
            )

        if file_path is not None:
            lines = file_path.read_text(encoding="utf-8").splitlines() if file_path.exists() else ()
        else:
            lines = retrieval_trace_report.fetch_service_log_lines(since=since, service_name=service_name)

        return retrieval_trace_report.format_memory_guard_report(
            retrieval_trace_report.parse_memory_guard_log(lines),
            limit=limit,
            decision=decision,
        )

    def cache_coverage(self, sample_limit: int = 10) -> EmbeddingCacheCoverage:
        """Compare current vault retrieval nodes to the embedding cache without writing."""

        nodes = tuple(load_retrieval_nodes(self.config.vault_dir))
        cache_path = self.config.embedding_cache_path
        if not cache_path.exists():
            return EmbeddingCacheCoverage(
                vault_dir=self.config.vault_dir,
                cache_path=cache_path,
                model=self.config.embedding_model,
                node_count=len(nodes),
                covered_count=0,
                missing_count=len(nodes),
                stale_count=0,
                extra_count=0,
                node_counts=retrieval_node_counts(nodes),
                missing_node_ids=tuple(node.node_id for node in nodes[:sample_limit]),
                error="cache file missing",
            )

        try:
            raw = json.loads(cache_path.read_text())
        except Exception as exc:
            return EmbeddingCacheCoverage(
                vault_dir=self.config.vault_dir,
                cache_path=cache_path,
                model=self.config.embedding_model,
                node_count=len(nodes),
                covered_count=0,
                missing_count=len(nodes),
                stale_count=0,
                extra_count=0,
                node_counts=retrieval_node_counts(nodes),
                error=str(exc),
            )

        entries = raw.get("entries", {})
        if not isinstance(entries, dict):
            return EmbeddingCacheCoverage(
                vault_dir=self.config.vault_dir,
                cache_path=cache_path,
                model=self.config.embedding_model,
                node_count=len(nodes),
                covered_count=0,
                missing_count=len(nodes),
                stale_count=0,
                extra_count=0,
                node_counts=retrieval_node_counts(nodes),
                error="entries must be an object",
            )

        covered: list[str] = []
        missing: list[str] = []
        stale: list[str] = []
        node_ids = {node.node_id for node in nodes}
        for node in nodes:
            entry = entries.get(node.node_id)
            if not isinstance(entry, dict):
                missing.append(node.node_id)
                continue
            expected_hash = embeddings.embedding_text_hash(embeddings.node_embedding_text(node))
            vector = entry.get("vector")
            if entry.get("model") != self.config.embedding_model:
                missing.append(node.node_id)
            elif entry.get("text_hash") != expected_hash:
                stale.append(node.node_id)
            elif not isinstance(vector, list) or not vector:
                stale.append(node.node_id)
            else:
                covered.append(node.node_id)

        extra = sorted(
            node_id
            for node_id, entry in entries.items()
            if node_id not in node_ids and isinstance(entry, dict) and entry.get("model") == self.config.embedding_model
        )
        return EmbeddingCacheCoverage(
            vault_dir=self.config.vault_dir,
            cache_path=cache_path,
            model=self.config.embedding_model,
            node_count=len(nodes),
            covered_count=len(covered),
            missing_count=len(missing),
            stale_count=len(stale),
            extra_count=len(extra),
            node_counts=retrieval_node_counts(nodes),
            missing_node_ids=tuple(missing[:sample_limit]),
            stale_node_ids=tuple(stale[:sample_limit]),
            extra_node_ids=tuple(extra[:sample_limit]),
        )

    def benchmark_preview(
        self,
        retriever_name: str = retrieval_preview_module.DEFAULT_RETRIEVER,
        case_set: str = "real-vault",
    ) -> MemoryBenchmarkPreview:
        """Run a read-only retrieval benchmark through the Memory boundary."""

        experimental = retrieval_eval.build_experimental_retriever(retriever_name, self.config.vault_dir)
        cases = retrieval_eval.select_cases(case_set, retriever_name)
        result = retrieval_eval.evaluate_retriever(cases, experimental.retrieve)
        misses = tuple(case_result.case.name for case_result in result.results if not case_result.passed)
        return MemoryBenchmarkPreview(
            retriever_name=retriever_name,
            case_set=case_set,
            vault_dir=self.config.vault_dir,
            node_count=len(experimental.nodes),
            passed_count=result.passed_count,
            total_count=result.total_count,
            misses=misses,
        )


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def format_cache_inventory(cache: EmbeddingCacheInventory) -> str:
    """Format embedding cache inventory for operator inspection."""

    lines = [
        "Memory specialist embedding cache inventory",
        f"- path: {cache.path}",
        f"- exists: {'yes' if cache.exists else 'no'}",
        f"- readable: {'yes' if cache.readable else 'no'}",
    ]
    if cache.schema_version is not None:
        lines.append(f"- schema version: {cache.schema_version}")
    lines.extend(
        [
            f"- entries: {cache.entry_count}",
            "- models: " + (", ".join(cache.models) if cache.models else "(none)"),
            "- vector dimensions: "
            + (", ".join(str(value) for value in cache.vector_dimensions) if cache.vector_dimensions else "(none)"),
        ]
    )
    if cache.error:
        lines.append(f"- error: {cache.error}")
    lines.append("- writes: no")
    return "\n".join(lines)


def format_memory_inventory(preview: MemoryInventoryPreview) -> str:
    """Format a read-only Memory specialist inventory."""

    status = preview.production_status
    return "\n".join(
        [
            "Memory specialist inventory preview",
            f"- vault: {preview.config.vault_dir}",
            f"- embedding model: {preview.config.embedding_model}",
            f"- embedding keep-alive: {preview.config.embedding_keep_alive}",
            f"- cache path: {preview.cache.path}",
            f"- cache entries: {preview.cache.entry_count}",
            f"- memory retrieval: {'enabled' if status.enabled else 'disabled'}",
            f"- memory context: {'enabled' if status.context_enabled else 'disabled'}",
            f"- production retriever: {status.retriever_name}",
            f"- retriever env accepted: {'yes' if status.retriever_env_accepted else 'no'}",
            f"- allowed retrievers: {', '.join(status.allowed_retrievers)}",
            "- writes: no",
        ]
    )


def format_production_status(status: production_retrieval.ProductionRetrievalStatus) -> str:
    """Format guarded production retrieval status without running retrieval."""

    return "\n".join(
        [
            "Memory specialist production retrieval status",
            f"- memory retrieval: {'enabled' if status.enabled else 'disabled'}",
            f"- enable env: {status.enable_env}",
            f"- memory context: {'enabled' if status.context_enabled else 'disabled'}",
            f"- context env: {status.context_env}",
            f"- retriever: {status.retriever_name}",
            f"- raw retriever env: {status.raw_retriever_name}",
            f"- retriever env accepted: {'yes' if status.retriever_env_accepted else 'no'}",
            f"- allowed retrievers: {', '.join(status.allowed_retrievers)}",
            f"- production node limit: {status.node_limit}",
            f"- production text limit: {status.text_limit}",
            f"- vault: {status.vault_dir}",
            "- writes: no",
        ]
    )


def format_retrieval_preview(preview: retrieval_preview_module.RetrievalPreview, show_trace: bool = False) -> str:
    """Format a Memory specialist retrieval preview."""

    return "\n".join(
        [
            "Memory specialist retrieval preview",
            "- writes: no",
            "",
            retrieval_preview_module.format_preview(preview, show_trace=show_trace),
        ]
    )


def format_context_preview(context: str) -> str:
    """Format a Memory specialist context preview."""

    return "\n".join(
        [
            "Memory specialist context preview",
            "- prompt memory context remains disabled unless explicitly enabled elsewhere",
            "- writes: no",
            "",
            context,
        ]
    )


def format_memory_guard_preview(guard: retrieval_preview_module.MemoryGuardPreview) -> str:
    """Format a Memory specialist memory-guard preview."""

    return "\n".join(
        [
            "Memory specialist guard preview",
            "- writes: no",
            "",
            retrieval_preview_module.format_memory_guard_preview(guard),
        ]
    )


def format_production_return_preview(preview: retrieval_preview_module.ProductionReturnPreview) -> str:
    """Format a Memory specialist production-return preview."""

    return "\n".join(
        [
            "Memory specialist production return preview",
            "- writes: no",
            "",
            retrieval_preview_module.format_production_return_preview(preview),
        ]
    )


def format_trace_report(report: str) -> str:
    """Format a Memory specialist trace report."""

    return "\n".join(
        [
            "Memory specialist trace report",
            "- writes: no",
            "",
            report,
        ]
    )


def format_cache_coverage(coverage: EmbeddingCacheCoverage) -> str:
    """Format embedding cache coverage for operator inspection."""

    lines = [
        "Memory specialist cache coverage preview",
        f"- vault: {coverage.vault_dir}",
        f"- cache path: {coverage.cache_path}",
        f"- model: {coverage.model}",
        f"- nodes: {coverage.node_count}",
        f"- covered: {coverage.covered_count}",
        f"- missing: {coverage.missing_count}",
        f"- stale: {coverage.stale_count}",
        f"- extra cache entries: {coverage.extra_count}",
    ]
    if coverage.node_counts:
        lines.append("- node types: " + ", ".join(
            f"{node_type or '(unknown)'}={count}"
            for node_type, count in coverage.node_counts.items()
        ))
    if coverage.missing_node_ids:
        lines.append("- missing sample: " + ", ".join(coverage.missing_node_ids))
    if coverage.stale_node_ids:
        lines.append("- stale sample: " + ", ".join(coverage.stale_node_ids))
    if coverage.extra_node_ids:
        lines.append("- extra sample: " + ", ".join(coverage.extra_node_ids))
    if coverage.error:
        lines.append(f"- error: {coverage.error}")
    lines.append("- writes: no")
    return "\n".join(lines)


def format_benchmark_preview(preview: MemoryBenchmarkPreview) -> str:
    """Format a Memory specialist benchmark preview."""

    lines = [
        "Memory specialist benchmark preview",
        f"- retriever: {preview.retriever_name}",
        f"- case-set: {preview.case_set}",
        f"- vault: {preview.vault_dir}",
        f"- nodes: {preview.node_count}",
        f"- passed: {preview.passed_count}/{preview.total_count}",
        f"- status: {'pass' if preview.passed_count == preview.total_count else 'baseline'}",
    ]
    if preview.misses:
        lines.append("- misses: " + ", ".join(preview.misses))
    lines.append("- writes: no")
    return "\n".join(lines)


def default_memory_trace_path() -> Path:
    """Return the current durable memory trace path."""

    return Path(os.environ.get(MEMORY_TRACE_PATH_ENV, str(DEFAULT_MEMORY_TRACE_PATH)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Memory specialist preview.")
    parser.add_argument(
        "--vault-dir",
        type=Path,
        default=Path.home() / "vault",
        help="Vault directory. Defaults to ~/vault.",
    )
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=embeddings.EMBED_CACHE_PATH,
        help="Embedding cache path. Defaults to SPROCKETS_COGS_EMBED_CACHE_PATH or project default.",
    )
    parser.add_argument(
        "--retriever",
        choices=(
            "memory-vault",
            "memory-embedding-gated-vault",
            "memory-embedding-graph-gated-vault",
        ),
        default=retrieval_preview_module.DEFAULT_RETRIEVER,
        help="Read-only preview retriever. Defaults to gated embedded memory.",
    )
    parser.add_argument(
        "--show-trace",
        action="store_true",
        help="Print retrieval trace details for --retrieval.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of most recent trace events to show for --traces. Defaults to 20.",
    )
    parser.add_argument(
        "--decision",
        choices=("selected", "skipped"),
        default="",
        help="Only show selected or skipped memory parent decisions for --traces.",
    )
    parser.add_argument(
        "--since",
        default=retrieval_trace_report.DEFAULT_SINCE,
        help="journalctl --since value for --traces --journal. Defaults to '24 hours ago'.",
    )
    parser.add_argument(
        "--service",
        default=retrieval_trace_report.SERVICE_NAME,
        help="systemd user service name for --traces --journal.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Parse a service log file for --traces instead of JSONL or journalctl.",
    )
    parser.add_argument(
        "--jsonl",
        type=Path,
        default=default_memory_trace_path(),
        help="Parse a durable memory trace JSONL file for --traces.",
    )
    parser.add_argument(
        "--journal",
        action="store_true",
        help="Read --traces from journalctl instead of the durable JSONL trace sink.",
    )
    parser.add_argument(
        "--case-set",
        choices=("auto", "fixture", "real-vault", "packet-vault"),
        default="real-vault",
        help="Benchmark case set for --benchmark. Defaults to real-vault.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Number of node IDs to sample in --cache-coverage. Defaults to 10.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--inventory",
        action="store_true",
        help="Preview memory inventory without running retrieval or embeddings.",
    )
    mode.add_argument(
        "--cache",
        action="store_true",
        help="Preview embedding cache inventory without writing.",
    )
    mode.add_argument(
        "--status",
        action="store_true",
        help="Preview guarded production retrieval status without running retrieval.",
    )
    mode.add_argument(
        "--retrieval",
        metavar="QUERY",
        help="Preview retrieval results without production writes.",
    )
    mode.add_argument(
        "--context",
        metavar="QUERY",
        help="Preview compact context formatting without enabling memory context.",
    )
    mode.add_argument(
        "--memory-guard",
        metavar="QUERY",
        help="Preview memory parent guard behavior without writing.",
    )
    mode.add_argument(
        "--production-return",
        metavar="QUERY",
        help="Preview exact compact production retrieval return nodes.",
    )
    mode.add_argument(
        "--traces",
        action="store_true",
        help="Report memory parent guard traces without writing.",
    )
    mode.add_argument(
        "--cache-coverage",
        action="store_true",
        help="Compare current vault retrieval nodes to cached embeddings without writing.",
    )
    mode.add_argument(
        "--benchmark",
        action="store_true",
        help="Run a read-only retrieval benchmark summary through the Memory boundary.",
    )
    return parser


def specialist_from_args(args: argparse.Namespace) -> MemorySpecialist:
    return MemorySpecialist(
        MemorySpecialistConfig(
            vault_dir=args.vault_dir,
            embedding_cache_path=args.cache_path,
            memory_trace_path=args.jsonl,
        )
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    specialist = specialist_from_args(args)

    if args.inventory:
        print(format_memory_inventory(specialist.inventory()))
    elif args.cache:
        print(format_cache_inventory(specialist.cache_inventory()))
    elif args.status:
        print(format_production_status(production_retrieval.production_retrieval_status(args.vault_dir)))
    elif args.retrieval:
        print(
            format_retrieval_preview(
                specialist.retrieval_preview(args.retrieval, retriever_name=args.retriever),
                show_trace=args.show_trace,
            )
        )
    elif args.context:
        print(format_context_preview(specialist.context_preview(args.context, retriever_name=args.retriever)))
    elif args.memory_guard:
        print(format_memory_guard_preview(specialist.memory_guard_preview(args.memory_guard, retriever_name=args.retriever)))
    elif args.production_return:
        print(format_production_return_preview(specialist.production_return_preview(args.production_return)))
    elif args.traces:
        print(format_trace_report(
            specialist.trace_report(
                limit=args.limit,
                decision=args.decision,
                since=args.since,
                service_name=args.service,
                file_path=args.file,
                jsonl_path=None if args.journal or args.file else args.jsonl,
                use_journal=args.journal,
            )
        ))
    elif args.cache_coverage:
        print(format_cache_coverage(specialist.cache_coverage(sample_limit=args.sample_limit)))
    elif args.benchmark:
        print(format_benchmark_preview(
            specialist.benchmark_preview(
                retriever_name=args.retriever,
                case_set=args.case_set,
            )
        ))


if __name__ == "__main__":
    main()

"""Memory specialist facade for Phase 4 orchestration.

Stage 41A keeps this boundary read-only. It reports memory configuration,
embedding cache posture, and guarded production retrieval status without
running retrieval, embedding calls, or production writes.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import embeddings
import production_retrieval
import retrieval_preview as retrieval_preview_module


@dataclass(frozen=True)
class MemorySpecialistConfig:
    """Filesystem and model settings owned by the Memory specialist."""

    vault_dir: Path = Path.home() / "vault"
    embedding_cache_path: Path = embeddings.EMBED_CACHE_PATH
    embedding_model: str = embeddings.EMBED_MODEL
    embedding_keep_alive: str = embeddings.EMBED_KEEP_ALIVE


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
    return parser


def specialist_from_args(args: argparse.Namespace) -> MemorySpecialist:
    return MemorySpecialist(
        MemorySpecialistConfig(
            vault_dir=args.vault_dir,
            embedding_cache_path=args.cache_path,
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


if __name__ == "__main__":
    main()

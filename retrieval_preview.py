"""Read-only preview for Stage 17 memory retrieval.

This module lets us inspect the gated memory retriever as a candidate production
path without wiring it into the running agent loop.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from vault_graph import HIERARCHY_PARENT_NODE_TYPES
from production_retrieval import (
    ProductionRetrievalStatus,
    format_retrieval_context,
    memory_retrieval_enabled,
    production_retrieval_status,
    retrieve_with_gated_memory,
)
from retrieval_eval import RetrievalNode, build_experimental_retriever


DEFAULT_VAULT_DIR = Path("/home/cosmo/vault")
DEFAULT_RETRIEVER = "memory-embedding-gated-vault"


@dataclass(frozen=True)
class RetrievalPreview:
    """Read-only retrieval preview for one query."""

    query: str
    retriever_name: str
    vault_dir: Path
    results: tuple[RetrievalNode, ...]
    trace: object | None = None


@dataclass(frozen=True)
class MemoryGuardPreview:
    """Read-only preview of the post-classification memory parent guard."""

    query: str
    parent_title: str
    parent_node_id: str
    parent_node_type: str
    task_like: bool
    derived_task_title: str

    @property
    def would_apply_parent_hint(self) -> bool:
        return bool(self.parent_title)

    @property
    def would_add_hierarchy_task(self) -> bool:
        return self.task_like and bool(self.parent_title)


@dataclass(frozen=True)
class ProductionReturnPreview:
    """Read-only preview of what production retrieval would return now."""

    query: str
    vault_dir: Path
    enabled: bool
    results: tuple[RetrievalNode, ...]
    error: str = ""


def preview_retrieval(
    query: str,
    vault_dir: Path = DEFAULT_VAULT_DIR,
    retriever_name: str = DEFAULT_RETRIEVER,
) -> RetrievalPreview:
    """Run a benchmark retriever as a production preview without agent wiring."""

    experimental = build_experimental_retriever(retriever_name, vault_dir)
    results = tuple(_retrieval_nodes(experimental.retrieve(query)))
    return RetrievalPreview(
        query=query,
        retriever_name=retriever_name,
        vault_dir=vault_dir,
        results=results,
        trace=experimental.trace(query),
    )


def preview_memory_guard(preview: RetrievalPreview) -> MemoryGuardPreview:
    """Return a write-free summary of the memory parent guard outcome."""

    parent = _top_hierarchy_result(preview.results)
    task_like = _looks_task_like(preview.query)
    return MemoryGuardPreview(
        query=preview.query,
        parent_title=parent.title if parent else "",
        parent_node_id=parent.node_id if parent else "",
        parent_node_type=parent.node_type if parent else "",
        task_like=task_like,
        derived_task_title=_derive_task_title(preview.query) if task_like else "",
    )


def preview_production_return(
    query: str,
    vault_dir: Path = DEFAULT_VAULT_DIR,
) -> ProductionReturnPreview:
    """Return the compact nodes agentic_loop.retrieve_relevant_nodes would expose."""

    enabled = memory_retrieval_enabled()
    if not enabled:
        return ProductionReturnPreview(
            query=query,
            vault_dir=vault_dir,
            enabled=False,
            results=(),
        )
    try:
        results = retrieve_with_gated_memory(query, vault_dir)
    except Exception as exc:
        return ProductionReturnPreview(
            query=query,
            vault_dir=vault_dir,
            enabled=True,
            results=(),
            error=str(exc),
        )
    return ProductionReturnPreview(
        query=query,
        vault_dir=vault_dir,
        enabled=True,
        results=results,
    )


def format_preview(preview: RetrievalPreview, show_trace: bool = False) -> str:
    """Format a preview as compact terminal output."""

    lines = [
        "Sprockets-Cogs retrieval preview",
        f"- query: {preview.query}",
        f"- retriever: {preview.retriever_name}",
        f"- vault: {preview.vault_dir}",
        f"- results: {len(preview.results)}",
    ]
    for index, node in enumerate(preview.results, start=1):
        lines.append(
            f"{index}. {node.node_id} [{node.node_type}] {node.title}"
        )
        lines.append(f"   path: {node.path}")
    if show_trace:
        lines.extend(_format_trace(preview.trace))
    return "\n".join(lines)


def format_memory_guard_preview(guard: MemoryGuardPreview) -> str:
    """Format the post-classification memory guard preview."""

    lines = [
        "Sprockets-Cogs memory guard preview",
        f"- query: {guard.query}",
        f"- top hierarchy parent: {guard.parent_title or '(none)'}",
    ]
    if guard.parent_node_id:
        lines.append(f"- parent node: {guard.parent_node_id} [{guard.parent_node_type}]")
    lines.extend([
        f"- task-like input: {'yes' if guard.task_like else 'no'}",
        f"- would apply parent_hint: {'yes' if guard.would_apply_parent_hint else 'no'}",
        f"- would add Sprockets task if classifier emits daily-only: {'yes' if guard.would_add_hierarchy_task else 'no'}",
    ])
    if guard.derived_task_title:
        lines.append(f"- derived task title: {guard.derived_task_title}")
    lines.append("- writes: none")
    return "\n".join(lines)


def format_production_return_preview(preview: ProductionReturnPreview) -> str:
    """Format compact production retrieval results without writing."""

    lines = [
        "Sprockets-Cogs production retrieval return preview",
        f"- query: {preview.query}",
        f"- memory retrieval enabled: {'yes' if preview.enabled else 'no'}",
        f"- vault: {preview.vault_dir}",
        f"- results: {len(preview.results)}",
    ]
    if preview.error:
        lines.append(f"- error: {preview.error}")
    for index, node in enumerate(preview.results, start=1):
        lines.append(f"{index}. {node.node_id} [{node.node_type}] {node.title}")
        if node.parent_slugs:
            lines.append(f"   parents: {', '.join(node.parent_slugs)}")
        if node.text:
            lines.append(f"   text: {node.text}")
        lines.append(f"   path: {node.path}")
    lines.append("- writes: none")
    return "\n".join(lines)


def format_context_preview(preview: RetrievalPreview) -> str:
    """Format preview results as the prompt context they could become."""

    context = format_retrieval_context(preview.results)
    return context or "Relevant memory: (none)"


def format_status(status: ProductionRetrievalStatus) -> str:
    """Format guarded production retrieval status for terminal output."""

    enabled = "enabled" if status.enabled else "disabled"
    context_enabled = "enabled" if status.context_enabled else "disabled"
    return "\n".join([
        "Sprockets-Cogs production retrieval status",
        f"- memory retrieval: {enabled}",
        f"- enable env: {status.enable_env}",
        f"- memory context: {context_enabled}",
        f"- context env: {status.context_env}",
        f"- retriever: {status.retriever_name}",
        f"- retriever env: {status.retriever_env}",
        f"- retriever env accepted: {'yes' if status.retriever_env_accepted else 'no'}",
        f"- raw retriever env: {status.raw_retriever_name}",
        f"- allowed retrievers: {', '.join(status.allowed_retrievers)}",
        f"- production node limit: {status.node_limit}",
        f"- node limit env: {status.node_limit_env}",
        f"- production text limit: {status.text_limit}",
        f"- text limit env: {status.text_limit_env}",
        f"- vault: {status.vault_dir}",
    ])


def _retrieval_nodes(items: Iterable[object]) -> Iterable[RetrievalNode]:
    for item in items:
        if isinstance(item, RetrievalNode):
            yield item


def _top_hierarchy_result(nodes: Iterable[RetrievalNode]) -> RetrievalNode | None:
    for node in nodes:
        if node.node_type in HIERARCHY_PARENT_NODE_TYPES:
            return node
    return None


def _looks_task_like(text: str) -> bool:
    stripped = text.strip().lower()
    return bool(re.match(r"^(need to|remember to|todo:?)\b", stripped))


def _derive_task_title(text: str) -> str:
    title = re.sub(r"^(need to|remember to|todo:?)\s+", "", text.strip(), flags=re.IGNORECASE).strip()
    return title[:1].upper() + title[1:] if title else text.strip()


def _format_trace(trace: object | None) -> list[str]:
    if trace is None:
        return ["", "Trace", "- unavailable"]

    lines = ["", "Trace"]
    lines.append("- retriever: " + str(getattr(trace, "retriever_name", "unknown")))
    filters = getattr(trace, "filters_applied", {})
    if filters:
        lines.append("- filters: " + ", ".join(
            f"{key}={','.join(value)}" for key, value in filters.items()
        ))
    notes = getattr(trace, "notes", ())
    if notes:
        lines.append("- notes: " + "; ".join(str(note) for note in notes))
    quality_flags = getattr(trace, "quality_flags", ())
    if quality_flags:
        lines.append("- quality: " + "; ".join(str(flag) for flag in quality_flags))
    confidence = getattr(trace, "confidence", None)
    if confidence is not None:
        confidence_key = (
            f"{getattr(confidence, 'level', 'unknown')}/"
            f"{getattr(confidence, 'action', 'unknown')}"
        )
        reasons = ", ".join(getattr(confidence, "reasons", ()))
        suffix = f" ({reasons})" if reasons else ""
        lines.append(f"- confidence: {confidence_key}{suffix}")
    result_summaries = getattr(trace, "result_summaries", ())
    if result_summaries:
        lines.append("- results:")
        lines.extend(f"  - {summary}" for summary in result_summaries)
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview gated memory retrieval without production wiring.",
    )
    parser.add_argument("query", nargs="*", help="Query text to retrieve against.")
    parser.add_argument(
        "--vault-dir",
        type=Path,
        default=DEFAULT_VAULT_DIR,
        help="Vault directory. Defaults to /home/cosmo/vault.",
    )
    parser.add_argument(
        "--retriever",
        choices=("memory-vault", "memory-embedding-gated-vault"),
        default=DEFAULT_RETRIEVER,
        help="Read-only preview retriever. Defaults to gated embedded memory.",
    )
    parser.add_argument(
        "--show-trace",
        action="store_true",
        help="Print retrieval trace details.",
    )
    parser.add_argument(
        "--context",
        action="store_true",
        help="Print compact prompt-context formatting for preview results.",
    )
    parser.add_argument(
        "--memory-guard",
        action="store_true",
        help="Preview the post-classification memory parent guard without writing.",
    )
    parser.add_argument(
        "--production-return",
        action="store_true",
        help="Preview compact production retrieval return nodes without writing.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print guarded production retrieval status without running a query.",
    )
    args = parser.parse_args()

    if args.status:
        print(format_status(production_retrieval_status(args.vault_dir)))
        return
    if not args.query:
        parser.error("query is required unless --status is used")

    query = " ".join(args.query)
    if args.production_return:
        print(format_production_return_preview(
            preview_production_return(query, vault_dir=args.vault_dir)
        ))
        return

    preview = preview_retrieval(
        query,
        vault_dir=args.vault_dir,
        retriever_name=args.retriever,
    )
    if args.context:
        print(format_context_preview(preview))
        return
    if args.memory_guard:
        print(format_memory_guard_preview(preview_memory_guard(preview)))
        return
    print(format_preview(preview, show_trace=args.show_trace))


if __name__ == "__main__":
    main()

"""Read-only preview for Stage 17 memory retrieval.

This module lets us inspect the gated memory retriever as a candidate production
path without wiring it into the running agent loop.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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


def _retrieval_nodes(items: Iterable[object]) -> Iterable[RetrievalNode]:
    for item in items:
        if isinstance(item, RetrievalNode):
            yield item


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
    parser.add_argument("query", nargs="+", help="Query text to retrieve against.")
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
    args = parser.parse_args()

    preview = preview_retrieval(
        " ".join(args.query),
        vault_dir=args.vault_dir,
        retriever_name=args.retriever,
    )
    print(format_preview(preview, show_trace=args.show_trace))


if __name__ == "__main__":
    main()

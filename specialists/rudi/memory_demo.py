"""Stage 100 read-only memory demo surface."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import memory_specialist
import retrieval_preview


DEFAULT_RETRIEVER = "memory-vault"


def build_memory_demo(
    query: str,
    *,
    vault_dir: Path = retrieval_preview.DEFAULT_VAULT_DIR,
    retriever_name: str = DEFAULT_RETRIEVER,
) -> str:
    """Return retrieved evidence and guard traces without writing anywhere."""

    specialist = memory_specialist.MemorySpecialist(
        memory_specialist.MemorySpecialistConfig(vault_dir=vault_dir)
    )
    preview = specialist.retrieval_preview(query, retriever_name=retriever_name)
    guard = retrieval_preview.preview_memory_guard(preview)

    return "\n".join(
        [
            "Sprockets-Cogs read-only memory demo",
            f"- query: {query}",
            f"- retriever: {retriever_name}",
            f"- vault: {vault_dir}",
            "- writes: no",
            "- prompt memory context: unchanged",
            "",
            "Retrieved Evidence",
            retrieval_preview.format_preview(preview, show_trace=True),
            "",
            "Memory Guard",
            retrieval_preview.format_memory_guard_preview(guard),
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show read-only memory evidence and traces for one query.",
    )
    parser.add_argument("query", nargs="+", help="Query text to retrieve against.")
    parser.add_argument(
        "--vault-dir",
        type=Path,
        default=retrieval_preview.DEFAULT_VAULT_DIR,
        help="Vault directory. Defaults to ~/vault.",
    )
    parser.add_argument(
        "--retriever",
        choices=(
            "memory-vault",
            "memory-embedding-gated-vault",
            "memory-embedding-graph-gated-vault",
        ),
        default=DEFAULT_RETRIEVER,
        help="Read-only retriever. Defaults to lexical vault memory.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    print(
        build_memory_demo(
            " ".join(args.query),
            vault_dir=args.vault_dir,
            retriever_name=args.retriever,
        )
    )


if __name__ == "__main__":
    main()

"""Production-safe memory retrieval adapter.

Stage 17 keeps semantic retrieval behind an explicit environment flag while the
benchmark harness remains the source of truth for quality.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from retrieval_eval import RetrievalNode, build_experimental_retriever


MEMORY_RETRIEVAL_ENV = "SPROCKETS_COGS_MEMORY_RETRIEVAL"
MEMORY_CONTEXT_ENV = "SPROCKETS_COGS_MEMORY_CONTEXT"
RETRIEVER_ENV = "SPROCKETS_COGS_MEMORY_RETRIEVER"
DEFAULT_RETRIEVER = "memory-embedding-gated-vault"
ALLOWED_RETRIEVERS = frozenset({
    "memory-embedding-gated-vault",
    "memory-vault",
})
DEFAULT_CONTEXT_NODE_LIMIT = 5
DEFAULT_CONTEXT_TEXT_LIMIT = 240

_TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ProductionRetrievalStatus:
    """Operational status for the guarded production retrieval adapter."""

    enabled: bool
    context_enabled: bool
    retriever_name: str
    vault_dir: Path
    raw_retriever_name: str
    allowed_retrievers: tuple[str, ...]
    enable_env: str = MEMORY_RETRIEVAL_ENV
    context_env: str = MEMORY_CONTEXT_ENV
    retriever_env: str = RETRIEVER_ENV

    @property
    def retriever_env_accepted(self) -> bool:
        return self.raw_retriever_name == self.retriever_name


def memory_retrieval_enabled() -> bool:
    """Return whether production semantic retrieval is explicitly enabled."""

    return os.environ.get(MEMORY_RETRIEVAL_ENV, "").strip().lower() in _TRUE_VALUES


def memory_context_enabled() -> bool:
    """Return whether retrieved memory may be added to classifier context."""

    return os.environ.get(MEMORY_CONTEXT_ENV, "").strip().lower() in _TRUE_VALUES


def configured_memory_retriever() -> str:
    """Return the experimental retriever selected for the guarded adapter."""

    configured = os.environ.get(RETRIEVER_ENV, DEFAULT_RETRIEVER).strip() or DEFAULT_RETRIEVER
    if configured not in ALLOWED_RETRIEVERS:
        return DEFAULT_RETRIEVER
    return configured


def raw_memory_retriever_config() -> str:
    """Return the raw retriever env value before production allowlist handling."""

    return os.environ.get(RETRIEVER_ENV, DEFAULT_RETRIEVER).strip() or DEFAULT_RETRIEVER


def production_retrieval_status(vault_dir: Path) -> ProductionRetrievalStatus:
    """Return read-only status for the guarded production retrieval adapter."""

    return ProductionRetrievalStatus(
        enabled=memory_retrieval_enabled(),
        context_enabled=memory_context_enabled(),
        retriever_name=configured_memory_retriever(),
        vault_dir=vault_dir,
        raw_retriever_name=raw_memory_retriever_config(),
        allowed_retrievers=tuple(sorted(ALLOWED_RETRIEVERS)),
    )


def retrieve_with_gated_memory(query: str, vault_dir: Path) -> tuple[RetrievalNode, ...]:
    """Run the selected gated memory retriever for production preview wiring."""

    retriever = build_experimental_retriever(configured_memory_retriever(), vault_dir)
    return tuple(
        node
        for node in retriever.retrieve(query)
        if isinstance(node, RetrievalNode)
    )


def format_retrieval_context(
    nodes: tuple[RetrievalNode, ...],
    node_limit: int = DEFAULT_CONTEXT_NODE_LIMIT,
    text_limit: int = DEFAULT_CONTEXT_TEXT_LIMIT,
) -> str:
    """Format retrieved nodes as compact prompt context text."""

    if node_limit < 1 or not nodes:
        return ""

    lines = ["Relevant memory:"]
    for node in nodes[:node_limit]:
        title = _single_line(node.title)
        lines.append(f"- {node.node_id} [{node.node_type}] {title}")
        if node.parent_slugs:
            lines.append(f"  parents: {', '.join(node.parent_slugs)}")
        snippet = _snippet(node.text, text_limit)
        if snippet:
            lines.append(f"  text: {snippet}")
    return "\n".join(lines)


def _single_line(text: str) -> str:
    return " ".join(text.split())


def _snippet(text: str, max_chars: int) -> str:
    if max_chars < 1:
        return ""
    compact = _single_line(text)
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip() + "..."

"""Memory index contracts for local retrieval backends.

Stage 17 starts with the shape of the boundary, not a storage decision. The
dataclasses in this module describe what Sprockets-Cogs needs from a memory
index whether the implementation remains JSON-backed, moves to SQLite, or later
uses a vector database.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from embeddings import embedding_text_hash, node_embedding_text
from retrieval_eval import RetrievalNode


@dataclass(frozen=True)
class MemoryNodeMetadata:
    """Stable vault metadata stored alongside an indexed memory node."""

    node_id: str
    path: Path
    node_type: str
    title: str
    parent_slugs: tuple[str, ...] = ()
    source_mtime: float | None = None
    text_hash: str = ""


@dataclass(frozen=True)
class VectorMetadata:
    """Embedding metadata needed to decide whether a vector can be reused."""

    model: str
    dimension: int
    text_hash: str
    indexed_at: str | None = None


@dataclass(frozen=True)
class MemoryRecord:
    """A single node record available to a memory index."""

    metadata: MemoryNodeMetadata
    vector: tuple[float, ...] | None = None
    vector_metadata: VectorMetadata | None = None

    @property
    def node_id(self) -> str:
        return self.metadata.node_id


@dataclass(frozen=True)
class MemoryQuery:
    """A structured memory query with optional filters."""

    text: str
    limit: int = 5
    node_types: tuple[str, ...] = ()
    parent_slugs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScoredMemoryResult:
    """A ranked memory hit with readable retrieval reasons."""

    record: MemoryRecord
    score: float
    reasons: tuple[str, ...] = ()

    @property
    def node_id(self) -> str:
        return self.record.node_id


@dataclass(frozen=True)
class RetrievalTrace:
    """Debug information for one memory query."""

    query: MemoryQuery
    retriever_name: str
    result_ids: tuple[str, ...]
    filters_applied: dict[str, tuple[str, ...]] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


class MemoryIndex(Protocol):
    """Storage boundary for Phase 3 memory retrieval."""

    def upsert_nodes(self, records: Iterable[MemoryRecord]) -> None:
        ...

    def delete_missing_node_ids(self, active_ids: Iterable[str]) -> tuple[str, ...]:
        ...

    def get(self, node_id: str) -> MemoryRecord | None:
        ...

    def query(self, query: MemoryQuery) -> tuple[ScoredMemoryResult, ...]:
        ...


def vector_metadata_for(model: str, text_hash: str, vector: Sequence[float]) -> VectorMetadata:
    """Build reusable vector metadata from a generated embedding vector."""

    return VectorMetadata(
        model=model,
        dimension=len(tuple(vector)),
        text_hash=text_hash,
    )


def should_reindex(record: MemoryRecord | None, model: str, text_hash: str) -> bool:
    """Return whether a node needs a fresh embedding for the given model/text."""

    if record is None or record.vector is None or record.vector_metadata is None:
        return True
    metadata = record.vector_metadata
    if metadata.model != model or metadata.text_hash != text_hash:
        return True
    return metadata.dimension != len(record.vector)


def memory_record_from_retrieval_node(
    node: RetrievalNode,
    source_mtime: float | None = None,
) -> MemoryRecord:
    """Convert a Stage 15 retrieval node into the Stage 17 memory record shape."""

    path = Path(node.path)
    if source_mtime is None:
        try:
            source_mtime = path.stat().st_mtime
        except OSError:
            source_mtime = None

    text_hash = embedding_text_hash(node_embedding_text(node))
    return MemoryRecord(
        metadata=MemoryNodeMetadata(
            node_id=node.node_id,
            path=path,
            node_type=node.node_type,
            title=node.title,
            parent_slugs=node.parent_slugs,
            source_mtime=source_mtime,
            text_hash=text_hash,
        )
    )

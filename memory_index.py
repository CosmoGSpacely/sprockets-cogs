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
import re
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


class InMemoryMemoryIndex:
    """Small deterministic MemoryIndex implementation for tests and experiments."""

    def __init__(self, records: Iterable[MemoryRecord] = ()):
        self._records: dict[str, MemoryRecord] = {}
        self.upsert_nodes(records)

    def upsert_nodes(self, records: Iterable[MemoryRecord]) -> None:
        for record in records:
            self._records[record.node_id] = record

    def delete_missing_node_ids(self, active_ids: Iterable[str]) -> tuple[str, ...]:
        active = set(active_ids)
        deleted = tuple(sorted(node_id for node_id in self._records if node_id not in active))
        for node_id in deleted:
            del self._records[node_id]
        return deleted

    def get(self, node_id: str) -> MemoryRecord | None:
        return self._records.get(node_id)

    def query(self, query: MemoryQuery) -> tuple[ScoredMemoryResult, ...]:
        if query.limit < 1:
            return ()

        query_tokens = _tokens(query.text)
        scored: list[ScoredMemoryResult] = []
        for record in self._records.values():
            if query.node_types and record.metadata.node_type not in query.node_types:
                continue
            if query.parent_slugs and not set(query.parent_slugs).issubset(record.metadata.parent_slugs):
                continue

            score, reasons = _score_record(query_tokens, record)
            if score <= 0 and query_tokens:
                continue
            scored.append(ScoredMemoryResult(record=record, score=score, reasons=reasons))

        scored.sort(key=lambda result: (-result.score, result.node_id))
        return tuple(scored[:query.limit])


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


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _score_record(
    query_tokens: set[str],
    record: MemoryRecord,
) -> tuple[float, tuple[str, ...]]:
    metadata = record.metadata
    title_overlap = query_tokens & _tokens(metadata.title)
    id_overlap = query_tokens & _tokens(metadata.node_id.replace("/", " "))
    parent_overlap = query_tokens & _tokens(" ".join(metadata.parent_slugs))

    score = float(len(title_overlap) * 4 + len(id_overlap) * 3 + len(parent_overlap) * 2)
    reasons: list[str] = []
    if title_overlap:
        reasons.append("title")
    if id_overlap:
        reasons.append("node_id")
    if parent_overlap:
        reasons.append("parent")
    if not query_tokens:
        reasons.append("filter")
    return score, tuple(reasons)

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
from retrieval_types import RetrievalNode
from vector_math import cosine_similarity


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
    query_vector: tuple[float, ...] | None = None


@dataclass(frozen=True)
class ScoredMemoryResult:
    """A ranked memory hit with readable retrieval reasons."""

    record: MemoryRecord
    score: float
    reasons: tuple[str, ...] = ()
    score_parts: tuple[tuple[str, float], ...] = ()

    @property
    def node_id(self) -> str:
        return self.record.node_id


@dataclass(frozen=True)
class RetrievalConfidence:
    """Trace-level confidence assessment for a memory query result set."""

    level: str
    action: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalTrace:
    """Debug information for one memory query."""

    query: MemoryQuery
    retriever_name: str
    result_ids: tuple[str, ...]
    filters_applied: dict[str, tuple[str, ...]] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    result_summaries: tuple[str, ...] = ()
    quality_flags: tuple[str, ...] = ()
    confidence: RetrievalConfidence | None = None


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

    def query_with_trace(
        self,
        query: MemoryQuery,
    ) -> tuple[tuple[ScoredMemoryResult, ...], RetrievalTrace]:
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
        results, _trace = self.query_with_trace(query)
        return results

    def query_with_trace(
        self,
        query: MemoryQuery,
    ) -> tuple[tuple[ScoredMemoryResult, ...], RetrievalTrace]:
        if query.limit < 1:
            trace = RetrievalTrace(
                query=query,
                retriever_name="in-memory",
                result_ids=(),
                filters_applied=_filters_applied(query),
                notes=("limit below 1",),
            )
            return (), trace

        query_tokens = _tokens(query.text)
        scored: list[ScoredMemoryResult] = []
        filtered_by_type = 0
        filtered_by_parent = 0
        for record in self._records.values():
            if query.node_types and record.metadata.node_type not in query.node_types:
                filtered_by_type += 1
                continue
            if query.parent_slugs and not set(query.parent_slugs).issubset(record.metadata.parent_slugs):
                filtered_by_parent += 1
                continue

            score, reasons, score_parts = _score_record(query_tokens, query.query_vector, record)
            if score <= 0 and (query_tokens or query.query_vector is not None):
                continue
            scored.append(ScoredMemoryResult(
                record=record,
                score=score,
                reasons=reasons,
                score_parts=score_parts,
            ))

        scored.sort(key=lambda result: (-result.score, result.node_id))
        results = tuple(scored[:query.limit])
        notes = (
            f"records scanned: {len(self._records)}",
            f"filtered by node_type: {filtered_by_type}",
            f"filtered by parent: {filtered_by_parent}",
            f"candidates scored: {len(scored)}",
        )
        quality_flags = _quality_flags(query, results)
        trace = RetrievalTrace(
            query=query,
            retriever_name="in-memory",
            result_ids=tuple(result.node_id for result in results),
            filters_applied=_filters_applied(query),
            notes=notes,
            result_summaries=tuple(_result_summary(result) for result in results),
            quality_flags=quality_flags,
            confidence=_assess_confidence(query, results, quality_flags),
        )
        return results, trace


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
    query_vector: Sequence[float] | None,
    record: MemoryRecord,
) -> tuple[float, tuple[str, ...], tuple[tuple[str, float], ...]]:
    metadata = record.metadata
    title_overlap = query_tokens & _tokens(metadata.title)
    id_overlap = query_tokens & _tokens(metadata.node_id.replace("/", " "))
    parent_overlap = query_tokens & _tokens(" ".join(metadata.parent_slugs))

    score_parts = {
        "title": float(len(title_overlap) * 4),
        "node_id": float(len(id_overlap) * 3),
        "parent": float(len(parent_overlap) * 2),
        "vector": 0.0,
    }
    reasons: list[str] = []
    if title_overlap:
        reasons.append("title")
    if id_overlap:
        reasons.append("node_id")
    if parent_overlap:
        reasons.append("parent")
    if query_vector is not None and record.vector is not None:
        try:
            score_parts["vector"] = cosine_similarity(query_vector, record.vector) * 10.0
        except ValueError:
            score_parts["vector"] = 0.0
        if score_parts["vector"] > 0:
            reasons.append("vector")
    if not query_tokens and query_vector is None:
        reasons.append("filter")
    included_parts = tuple(
        (name, value)
        for name, value in score_parts.items()
        if value > 0
    )
    total_score = sum(value for _name, value in included_parts)
    return total_score, tuple(reasons), included_parts


def _result_summary(result: ScoredMemoryResult) -> str:
    parts = ", ".join(f"{name}={value:.3g}" for name, value in result.score_parts)
    reasons = ",".join(result.reasons) if result.reasons else "none"
    kind = "packet" if result.record.metadata.node_type == "memory/packet" else "source"
    prefix = f"{result.node_id} kind={kind}"
    if parts:
        return f"{prefix} score={result.score:.3g} reasons={reasons} parts={parts}"
    return f"{prefix} score={result.score:.3g} reasons={reasons}"


def _quality_flags(
    query: MemoryQuery,
    results: Sequence[ScoredMemoryResult],
) -> tuple[str, ...]:
    if query.query_vector is None or not results:
        return ()

    flags: list[str] = []
    vector_only_count = sum(1 for result in results if _is_vector_only(result))
    if _is_vector_only(results[0]):
        flags.append("top result is vector-only")
    if vector_only_count >= min(3, len(results)):
        flags.append(f"vector-only cluster: {vector_only_count}/{len(results)} results")
    if len(results) >= 2:
        top_margin = results[0].score - results[1].score
        if top_margin < 0.5:
            flags.append(f"low top margin: {top_margin:.3g}")
    return tuple(flags)


def _is_vector_only(result: ScoredMemoryResult) -> bool:
    return result.reasons == ("vector",)


def _assess_confidence(
    query: MemoryQuery,
    results: Sequence[ScoredMemoryResult],
    quality_flags: Sequence[str],
) -> RetrievalConfidence:
    if not results:
        return RetrievalConfidence(
            level="low",
            action="review",
            reasons=("no results",),
        )

    if query.query_vector is None:
        return RetrievalConfidence(
            level="high",
            action="use",
            reasons=("lexical or filtered retrieval",),
        )

    top_result = results[0]
    if _is_vector_only(top_result):
        return RetrievalConfidence(
            level="low",
            action="review",
            reasons=tuple(quality_flags) or ("top result is vector-only",),
        )

    if quality_flags:
        return RetrievalConfidence(
            level="medium",
            action="use",
            reasons=tuple(quality_flags),
        )

    return RetrievalConfidence(
        level="high",
        action="use",
        reasons=("anchored top result",),
    )


def _filters_applied(query: MemoryQuery) -> dict[str, tuple[str, ...]]:
    filters: dict[str, tuple[str, ...]] = {}
    if query.node_types:
        filters["node_types"] = query.node_types
    if query.parent_slugs:
        filters["parent_slugs"] = query.parent_slugs
    return filters

"""Local embedding primitives for Phase 3 memory work."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import ollama

from specialists.rudi.retrieval_types import RetrievalNode
from specialists.rudi.vector_math import cosine_similarity


DEFAULT_EMBED_MODEL = "nomic-embed-text"
EMBED_MODEL = os.environ.get("SPROCKETS_COGS_EMBED_MODEL", DEFAULT_EMBED_MODEL)
DEFAULT_EMBED_KEEP_ALIVE = "24h"
EMBED_KEEP_ALIVE = os.environ.get("SPROCKETS_COGS_EMBED_KEEP_ALIVE", DEFAULT_EMBED_KEEP_ALIVE)
DEFAULT_EMBED_CACHE_PATH = Path.home() / ".cache" / "sprockets-cogs" / "specialists.rudi.embeddings.json"
EMBED_CACHE_PATH = Path(os.environ.get("SPROCKETS_COGS_EMBED_CACHE_PATH", str(DEFAULT_EMBED_CACHE_PATH)))


class EmbeddingError(RuntimeError):
    """Raised when an embedding response cannot be used safely."""


@dataclass(frozen=True)
class EmbeddedNode:
    """A retrieval node paired with the vector generated from its stable text."""

    node: RetrievalNode
    vector: tuple[float, ...]


class EmbeddingCache(Protocol):
    """Storage boundary for reusable embedding vectors."""

    def get(self, node_id: str, model: str, text_hash: str) -> tuple[float, ...] | None:
        ...

    def set(self, node_id: str, model: str, text_hash: str, vector: Sequence[float]) -> None:
        ...


class JsonEmbeddingCache:
    """Small JSON embedding cache that can later be replaced by another backend."""

    schema_version = 1

    def __init__(self, path: Path = EMBED_CACHE_PATH):
        self.path = path
        self._entries: dict[str, dict[str, object]] | None = None

    @classmethod
    def default(cls) -> "JsonEmbeddingCache":
        return cls(EMBED_CACHE_PATH)

    def _load(self) -> dict[str, dict[str, object]]:
        if self._entries is not None:
            return self._entries
        if not self.path.exists():
            self._entries = {}
            return self._entries

        try:
            raw = json.loads(self.path.read_text())
        except Exception as exc:
            raise EmbeddingError(f"embedding cache unreadable: {self.path}: {exc}") from exc

        if raw.get("schema_version") != self.schema_version:
            self._entries = {}
            return self._entries
        entries = raw.get("entries", {})
        if not isinstance(entries, dict):
            raise EmbeddingError(f"embedding cache entries must be an object: {self.path}")
        self._entries = entries
        return self._entries

    def _save(self) -> None:
        entries = self._load()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {
            "schema_version": self.schema_version,
            "entries": entries,
        }
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        tmp_path.replace(self.path)

    def get(self, node_id: str, model: str, text_hash: str) -> tuple[float, ...] | None:
        entry = self._load().get(node_id)
        if not isinstance(entry, dict):
            return None
        if entry.get("model") != model or entry.get("text_hash") != text_hash:
            return None
        vector = entry.get("vector")
        if vector is None:
            return None
        return tuple(_validate_vector(vector))

    def set(self, node_id: str, model: str, text_hash: str, vector: Sequence[float]) -> None:
        entries = self._load()
        entries[node_id] = {
            "model": model,
            "text_hash": text_hash,
            "vector": _validate_vector(vector),
        }
        self._save()


def embedding_text_hash(text: str) -> str:
    """Return the cache fingerprint for embedding text."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _response_value(response: object, key: str) -> object:
    if isinstance(response, dict):
        return response.get(key)
    return getattr(response, key, None)


def _validate_vector(vector: object) -> list[float]:
    if not isinstance(vector, Sequence) or isinstance(vector, (str, bytes)):
        raise EmbeddingError("embedding vector must be a numeric sequence")
    if not vector:
        raise EmbeddingError("embedding vector cannot be empty")

    values: list[float] = []
    for value in vector:
        if not isinstance(value, (int, float)):
            raise EmbeddingError("embedding vector must contain only numbers")
        values.append(float(value))
    return values


def embed_text(text: str, model: str | None = None) -> list[float]:
    """Return one local embedding vector for text using Ollama."""

    if not text.strip():
        raise ValueError("text cannot be empty")

    try:
        response = ollama.embed(
            model=model or EMBED_MODEL,
            input=text,
            keep_alive=EMBED_KEEP_ALIVE,
        )
    except Exception as exc:
        raise EmbeddingError(f"embedding request failed: {exc}") from exc
    embeddings = _response_value(response, "embeddings")
    if not isinstance(embeddings, Sequence) or isinstance(embeddings, (str, bytes)):
        raise EmbeddingError("embedding response missing embeddings list")
    if len(embeddings) != 1:
        raise EmbeddingError(f"expected exactly one embedding, got {len(embeddings)}")
    return _validate_vector(embeddings[0])


def node_embedding_text(node: RetrievalNode) -> str:
    """Return stable text used to embed a vault retrieval node."""

    parts = [
        f"id: {node.node_id}",
        f"type: {node.node_type}",
        f"title: {node.title}",
    ]
    if node.parent_slugs:
        parts.append(f"parents: {', '.join(node.parent_slugs)}")
    body = node.text.strip()
    if body:
        parts.append(f"text: {body}")
    return "\n".join(parts)


def embed_node(node: RetrievalNode, model: str | None = None) -> list[float]:
    """Embed one retrieval node using its stable node text."""

    return embed_text(node_embedding_text(node), model=model)


def build_embedding_index(
    nodes: Sequence[RetrievalNode],
    model: str | None = None,
    cache: EmbeddingCache | None = None,
) -> tuple[EmbeddedNode, ...]:
    """Build a small in-memory embedding index for retrieval experiments."""

    effective_model = model or EMBED_MODEL
    embedded_nodes: list[EmbeddedNode] = []
    for node in nodes:
        text = node_embedding_text(node)
        text_hash = embedding_text_hash(text)
        vector = cache.get(node.node_id, effective_model, text_hash) if cache else None
        if vector is None:
            vector = tuple(embed_text(text, model=effective_model))
            if cache:
                cache.set(node.node_id, effective_model, text_hash, vector)
        embedded_nodes.append(EmbeddedNode(node=node, vector=tuple(vector)))
    return tuple(embedded_nodes)


def retrieve_by_embedding(
    query: str,
    index: Sequence[EmbeddedNode],
    limit: int = 5,
    model: str | None = None,
) -> list[RetrievalNode]:
    """Return index nodes ranked by cosine similarity to the query embedding."""

    if limit < 1:
        return []

    query_vector = embed_text(query, model=model)
    try:
        ranked = [
            (cosine_similarity(query_vector, item.vector), item.node.node_id, item.node)
            for item in index
        ]
    except ValueError as exc:
        raise EmbeddingError(f"embedding {exc}") from exc
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [node for _, _, node in ranked[:limit]]

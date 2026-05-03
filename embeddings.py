"""Local embedding primitives for Phase 3 memory work."""
from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from math import sqrt

import ollama

from retrieval_eval import RetrievalNode


DEFAULT_EMBED_MODEL = "nomic-embed-text"
EMBED_MODEL = os.environ.get("SPROCKETS_COGS_EMBED_MODEL", DEFAULT_EMBED_MODEL)
DEFAULT_EMBED_KEEP_ALIVE = "24h"
EMBED_KEEP_ALIVE = os.environ.get("SPROCKETS_COGS_EMBED_KEEP_ALIVE", DEFAULT_EMBED_KEEP_ALIVE)


class EmbeddingError(RuntimeError):
    """Raised when an embedding response cannot be used safely."""


@dataclass(frozen=True)
class EmbeddedNode:
    """A retrieval node paired with the vector generated from its stable text."""

    node: RetrievalNode
    vector: tuple[float, ...]


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


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise EmbeddingError(
            f"embedding dimensions do not match: {len(left)} != {len(right)}"
        )

    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0

    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right))
    return dot_product / (left_norm * right_norm)


def build_embedding_index(
    nodes: Sequence[RetrievalNode],
    model: str | None = None,
) -> tuple[EmbeddedNode, ...]:
    """Build a small in-memory embedding index for retrieval experiments."""

    return tuple(
        EmbeddedNode(node=node, vector=tuple(embed_node(node, model=model)))
        for node in nodes
    )


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
    ranked = [
        (_cosine_similarity(query_vector, item.vector), item.node.node_id, item.node)
        for item in index
    ]
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [node for _, _, node in ranked[:limit]]

"""Local embedding primitives for Phase 3 memory work."""
from __future__ import annotations

import os
from collections.abc import Sequence

import ollama


DEFAULT_EMBED_MODEL = "nomic-embed-text"
EMBED_MODEL = os.environ.get("SPROCKETS_COGS_EMBED_MODEL", DEFAULT_EMBED_MODEL)


class EmbeddingError(RuntimeError):
    """Raised when an embedding response cannot be used safely."""


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
        response = ollama.embed(model=model or EMBED_MODEL, input=text)
    except Exception as exc:
        raise EmbeddingError(f"embedding request failed: {exc}") from exc
    embeddings = _response_value(response, "embeddings")
    if not isinstance(embeddings, Sequence) or isinstance(embeddings, (str, bytes)):
        raise EmbeddingError("embedding response missing embeddings list")
    if len(embeddings) != 1:
        raise EmbeddingError(f"expected exactly one embedding, got {len(embeddings)}")
    return _validate_vector(embeddings[0])

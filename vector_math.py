"""Shared vector math helpers for retrieval and embedding code."""
from __future__ import annotations

from collections.abc import Sequence
from math import sqrt


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Return cosine similarity for same-dimension numeric vectors."""

    if len(left) != len(right):
        raise ValueError(f"vector dimensions do not match: {len(left)} != {len(right)}")

    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0

    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right))
    return dot_product / (left_norm * right_norm)

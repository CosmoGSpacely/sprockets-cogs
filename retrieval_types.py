"""Shared retrieval benchmark data shapes."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RetrievalNode:
    """A compact representation of a vault node available for retrieval."""

    node_id: str
    title: str
    node_type: str
    path: Path
    parent_slugs: tuple[str, ...] = ()
    text: str = ""


@dataclass(frozen=True)
class RetrievalCase:
    """A single retrieval expectation for a future memory implementation."""

    name: str
    query: str
    expected_ids: frozenset[str]
    avoid_ids: frozenset[str] = frozenset()
    category: str = "general"
    reason: str = ""

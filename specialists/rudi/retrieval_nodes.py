"""Vault scanning helpers for retrieval benchmark nodes."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import frontmatter

from specialists.rudi.retrieval_types import RetrievalNode
from specialists.sprockets.vault_graph import build_graph, sprockets_dirs


def retrieval_node_counts(nodes: Iterable[RetrievalNode]) -> dict[str, int]:
    """Return node counts by node_type for scan summaries."""

    counts: dict[str, int] = {}
    for node in nodes:
        counts[node.node_type] = counts.get(node.node_type, 0) + 1
    return dict(sorted(counts.items()))


def daily_node_id(path: Path) -> str:
    """Return a stable retrieval node ID for an Obsidian daily note path."""

    date = path.stem
    for fmt in ("%Y-%m-%d %a", "%Y-%m-%d", "%a %d %b %Y"):
        try:
            date = datetime.strptime(path.stem, fmt).strftime("%Y-%m-%d")
            break
        except ValueError:
            continue
    return f"daily/{date}"


def _is_daily_note(path: Path) -> bool:
    """Return true for current ISO-first or legacy daily note filenames."""

    for fmt in ("%Y-%m-%d %a", "%Y-%m-%d", "%a %d %b %Y"):
        try:
            datetime.strptime(path.stem, fmt)
            return True
        except ValueError:
            continue
    return False


def load_retrieval_nodes(vault_dir: Path) -> list[RetrievalNode]:
    """Load compact retrieval candidates from Sprockets nodes and daily notes."""

    graph = build_graph(vault_dir)
    nodes: list[RetrievalNode] = []
    for folder in sprockets_dirs(vault_dir):
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.md")):
            try:
                post = frontmatter.load(str(path))
            except Exception:
                continue
            slug = path.stem
            nodes.append(
                RetrievalNode(
                    node_id=f"{folder.name}/{slug}",
                    title=str(post.get("title", slug)),
                    node_type=str(post.get("node_type", "")),
                    path=path,
                    parent_slugs=tuple(graph.successors(slug)) if graph.has_node(slug) else (),
                    text=post.content.strip(),
                )
            )

    cogs_dir = vault_dir / "Cogs"
    if cogs_dir.exists():
        for path in sorted(cogs_dir.rglob("*.md")):
            if not _is_daily_note(path):
                continue
            nodes.append(
                RetrievalNode(
                    node_id=daily_node_id(path),
                    title=path.stem,
                    node_type="cogs/daily",
                    path=path,
                    text=path.read_text().strip(),
                )
            )
    return nodes

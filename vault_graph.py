"""
vault_graph.py — Build a networkx directed graph from the Sprockets vault.

Nodes: slug (filesystem stem) with attrs {title, node_type, uuid, parent_raw}
Edges: child slug → parent slug (follows `parent` frontmatter wikilink)

Used by resolve_parents() to match parent_hint values from the classifier
against real nodes in the vault. Degrades gracefully — if the vault has no
area/goal/project nodes yet, the graph is empty and all hints go unresolved.
"""
import re
from pathlib import Path

import frontmatter
import networkx as nx
from rapidfuzz import fuzz

VAULT_DIR = Path("/home/cosmo/vault")

SPROCKETS_DIRS = [
    VAULT_DIR / "Sprockets" / "areas",
    VAULT_DIR / "Sprockets" / "goals",
    VAULT_DIR / "Sprockets" / "projects",
    VAULT_DIR / "Sprockets" / "tasks",
    VAULT_DIR / "Sprockets" / "notes",
    VAULT_DIR / "Sprockets" / "contacts",
    VAULT_DIR / "Sprockets" / "entities",
]

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def build_graph() -> nx.DiGraph:
    """Scan all Sprockets .md files and return a directed graph (child → parent edges)."""
    g = nx.DiGraph()

    for folder in SPROCKETS_DIRS:
        if not folder.exists():
            continue
        for path in folder.glob("*.md"):
            try:
                post = frontmatter.load(str(path))
            except Exception:
                continue
            slug = path.stem
            g.add_node(
                slug,
                title=post.get("title", slug),
                node_type=post.get("node_type", ""),
                uuid=post.get("uuid", ""),
                parent_raw=str(post.get("parent", "")),
            )

    # Second pass: add edges after all nodes exist
    for slug, attrs in list(g.nodes(data=True)):
        parent_raw = attrs.get("parent_raw", "")
        if not parent_raw:
            continue
        m = _WIKILINK_RE.search(parent_raw)
        if m:
            parent_slug = m.group(1)
            if g.has_node(parent_slug):
                g.add_edge(slug, parent_slug)

    return g


def find_node_by_title(graph: nx.DiGraph, hint: str, threshold: int = 80) -> tuple[str, str] | None:
    """
    Fuzzy-match a parent_hint string against node titles in the graph.
    Returns (slug, uuid) of the best match above threshold, or None.

    Threshold 80 is looser than the dedup threshold (85) — parent hints
    are often partial titles, not exact matches.
    """
    if not hint or not graph.nodes:
        return None
    best_slug = None
    best_score = 0
    hint_lower = hint.lower()
    for slug, attrs in graph.nodes(data=True):
        title = attrs.get("title", slug).lower()
        score = fuzz.partial_ratio(hint_lower, title)
        if score > best_score:
            best_score = score
            best_slug = slug
    if best_score >= threshold and best_slug is not None:
        uid = graph.nodes[best_slug].get("uuid", "")
        return best_slug, uid
    return None

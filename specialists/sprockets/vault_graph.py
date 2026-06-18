"""
vault_graph.py — Build a networkx directed graph from the Sprockets vault.

Nodes: slug (filesystem stem) with attrs {title, node_type, uuid, parent_raw, parent_value}
Edges: child slug → parent slug (follows `parent` frontmatter wikilink)

Used by resolve_parents() to match parent_hint values from the classifier
against real nodes in the vault. Degrades gracefully — if the vault has no
area/goal/project nodes yet, the graph is empty and all hints go unresolved.
"""
import os
import re
from pathlib import Path

import frontmatter
import networkx as nx
from rapidfuzz import fuzz

VAULT_DIR = Path(os.environ.get("SPROCKETS_COGS_VAULT_DIR", str(Path.home() / "vault")))
SPROCKETS_SUBDIRS = [
    "areas",
    "goals",
    "projects",
    "tasks",
    "notes",
    "contacts",
    "entities",
]
SPROCKETS_DIRS = [VAULT_DIR / "Sprockets" / subdir for subdir in SPROCKETS_SUBDIRS]
HIERARCHY_PARENT_NODE_TYPES = {
    "sprockets/area",
    "sprockets/goal",
    "sprockets/project",
}

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def sprockets_dirs(vault_dir: Path = VAULT_DIR) -> list[Path]:
    """Return the Sprockets folders that participate in parent resolution."""
    return [vault_dir / "Sprockets" / subdir for subdir in SPROCKETS_SUBDIRS]


def _wikilink_target(raw: object) -> str | None:
    """Extract the target slug from an Obsidian wikilink, ignoring aliases/headings."""
    if isinstance(raw, (list, tuple)):
        for item in raw:
            target = _wikilink_target(item)
            if target:
                return target
        return None
    if not isinstance(raw, str):
        return None
    m = _WIKILINK_RE.search(raw)
    if not m:
        clean = raw.split("|", 1)[0].split("#", 1)[0].strip()
        return clean or None
    target = m.group(1).split("|", 1)[0].split("#", 1)[0].strip()
    return target or None


def _parent_value(post: frontmatter.Post) -> object:
    parent = post.get("parent", "")
    if parent is None:
        return ""
    return parent


def _parent_raw(post: frontmatter.Post) -> str:
    parent = _parent_value(post)
    if isinstance(parent, (list, tuple)):
        return ", ".join(str(item) for item in parent)
    return str(parent)


def build_graph(vault_dir: Path = VAULT_DIR) -> nx.DiGraph:
    """Scan all Sprockets .md files and return a directed graph (child → parent edges)."""
    g = nx.DiGraph()

    for folder in sprockets_dirs(vault_dir):
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
                parent_raw=_parent_raw(post),
                parent_value=_parent_value(post),
            )

    # Second pass: add edges after all nodes exist
    for slug, attrs in list(g.nodes(data=True)):
        parent_value = attrs.get("parent_value", "")
        if not parent_value:
            continue
        parent_slug = _wikilink_target(parent_value)
        if parent_slug and g.has_node(parent_slug):
            g.add_edge(slug, parent_slug)

    return g


def _scored_title_matches(
    graph: nx.DiGraph,
    hint: str,
    allowed_node_types: set[str] | None = None,
) -> list[tuple[int, str]]:
    if not hint or not graph.nodes:
        return []
    scored: list[tuple[int, str]] = []
    hint_lower = hint.lower()
    for slug, attrs in graph.nodes(data=True):
        if allowed_node_types is not None and attrs.get("node_type", "") not in allowed_node_types:
            continue
        title = attrs.get("title", slug).lower()
        if title == hint_lower:
            return [(100, slug)]
        score = fuzz.partial_ratio(hint_lower, title)
        scored.append((score, slug))

    scored.sort(reverse=True)
    return scored


def ambiguous_title_matches(
    graph: nx.DiGraph,
    hint: str,
    threshold: int = 80,
    ambiguity_margin: int = 5,
    allowed_node_types: set[str] | None = None,
) -> list[tuple[str, str, int]]:
    """Return close competing title matches for a non-exact hint."""
    scored = _scored_title_matches(graph, hint, allowed_node_types)
    if len(scored) < 2:
        return []
    best_score, best_slug = scored[0]
    second_score, _ = scored[1]
    if best_score < threshold or second_score < threshold:
        return []
    if best_score - second_score >= ambiguity_margin:
        return []
    return [
        (slug, graph.nodes[slug].get("title", slug), score)
        for score, slug in scored
        if score >= threshold and best_score - score < ambiguity_margin
    ]


def find_node_by_title(
    graph: nx.DiGraph,
    hint: str,
    threshold: int = 80,
    ambiguity_margin: int = 5,
    allowed_node_types: set[str] | None = None,
) -> tuple[str, str] | None:
    """
    Fuzzy-match a parent_hint string against node titles in the graph.
    Returns (slug, uuid) of the best match above threshold, or None.

    Threshold 80 is looser than the dedup threshold (85) — parent hints
    are often partial titles, not exact matches.
    """
    scored = _scored_title_matches(graph, hint, allowed_node_types)
    if not scored:
        return None

    best_score, best_slug = scored[0]
    if best_score == 100 or best_score >= threshold:
        if ambiguous_title_matches(
            graph,
            hint,
            threshold,
            ambiguity_margin,
            allowed_node_types,
        ):
            return None
        uid = graph.nodes[best_slug].get("uuid", "")
        return best_slug, uid
    return None

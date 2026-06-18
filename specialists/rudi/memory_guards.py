"""Pure helpers for applying retrieved memory as structural classification guards."""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


class HierarchyNode(Protocol):
    """Minimal shape needed from a retrieved hierarchy node."""

    node_type: str
    title: str


@dataclass(frozen=True)
class MemoryParentTrace:
    """Compact trace of the retrieved node considered for parent linking."""

    retrieved_count: int
    top_node_id: str = ""
    top_node_type: str = ""
    top_title: str = ""
    parent_node_id: str = ""
    parent_node_type: str = ""
    parent_title: str = ""

    @property
    def selected(self) -> bool:
        return bool(self.parent_title)

    @property
    def reason(self) -> str:
        if self.parent_title:
            if self.parent_node_id == self.top_node_id:
                return "top retrieval result is a hierarchy parent"
            return "first hierarchy result selected after non-hierarchy result"
        if self.retrieved_count:
            return "no hierarchy parent in retrieved nodes"
        return "no retrieved nodes"


def top_hierarchy_parent_title(
    retrieved_nodes: Iterable[object],
    hierarchy_parent_node_types: Iterable[str],
) -> str:
    """Return the first retrieved hierarchy title, if present."""

    return memory_parent_trace(
        retrieved_nodes,
        hierarchy_parent_node_types,
    ).parent_title


def memory_parent_trace(
    retrieved_nodes: Iterable[object],
    hierarchy_parent_node_types: Iterable[str],
) -> MemoryParentTrace:
    """Return a compact parent-selection trace for retrieved memory."""

    nodes = tuple(retrieved_nodes)
    allowed_types = set(hierarchy_parent_node_types)
    top = nodes[0] if nodes else None
    if not top:
        return MemoryParentTrace(retrieved_count=0)

    top_node_type = getattr(top, "node_type", "")
    top_title = getattr(top, "title", "").strip()
    parent = next(
        (
            node for node in nodes
            if getattr(node, "node_type", "") in allowed_types
            and getattr(node, "title", "").strip()
        ),
        None,
    )
    return MemoryParentTrace(
        retrieved_count=len(nodes),
        top_node_id=getattr(top, "node_id", ""),
        top_node_type=top_node_type,
        top_title=top_title,
        parent_node_id=getattr(parent, "node_id", "") if parent else "",
        parent_node_type=getattr(parent, "node_type", "") if parent else "",
        parent_title=getattr(parent, "title", "").strip() if parent else "",
    )


def apply_memory_parent_title(classified: list[dict], parent_title: str) -> list[dict]:
    """Attach an already-selected memory parent title to suitable nodes."""

    result = list(classified)
    if not parent_title:
        return result

    for node in result:
        if node.get("parent_hint"):
            continue
        if node.get("node_type") not in {"sprockets/task", "sprockets/note"}:
            continue
        node["parent_hint"] = parent_title
    return result


def ensure_memory_hierarchy_tasks(
    raw_nodes: list[dict],
    classified: list[dict],
    parent_title: str,
    today: str,
) -> tuple[list[dict], tuple[str, ...]]:
    """
    Add Sprockets tasks when memory identifies a parent but classification
    produced only daily items. Returns added task titles for caller-side logging.
    """

    if not parent_title:
        return classified, ()

    result = list(classified)
    existing_task_titles = [
        node.get("title", "").lower()
        for node in result
        if node.get("node_type") == "sprockets/task"
    ]
    added_titles: list[str] = []

    for raw in raw_nodes:
        if raw.get("type_hint") != "task":
            continue
        raw_text = raw.get("raw", "").strip()
        raw_lower = raw_text.lower()
        if not raw_text:
            continue
        if any(title and title in raw_lower for title in existing_task_titles):
            continue

        title = memory_task_title(raw_text)
        result.append({
            "node_type": "sprockets/task",
            "title": title,
            "item_text": title,
            "date": today,
            "status": "active",
            "confidence": "high",
            "parent_hint": parent_title,
        })
        existing_task_titles.append(title.lower())
        added_titles.append(title)

    return result, tuple(added_titles)


def memory_task_title(raw_text: str) -> str:
    """Convert a task-like raw capture into the Sprockets task title."""

    title = re.sub(r"^(need to|remember to|todo:?)\s+", "", raw_text, flags=re.IGNORECASE).strip()
    return title[:1].upper() + title[1:] if title else raw_text

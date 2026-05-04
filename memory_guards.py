"""Pure helpers for applying retrieved memory as structural classification guards."""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol


class HierarchyNode(Protocol):
    """Minimal shape needed from a retrieved hierarchy node."""

    node_type: str
    title: str


def top_hierarchy_parent_title(
    retrieved_nodes: Iterable[object],
    hierarchy_parent_node_types: Iterable[str],
) -> str:
    """Return the first retrieved hierarchy title, if present."""

    allowed_types = set(hierarchy_parent_node_types)
    top = next(iter(retrieved_nodes), None)
    if not top or getattr(top, "node_type", "") not in allowed_types:
        return ""
    return getattr(top, "title", "").strip()


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

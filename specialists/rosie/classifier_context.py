"""Classifier context assembly for Rosie capture/classification."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
import os
from pathlib import Path
from typing import Any

from specialists.cogs.naming import resolve_existing_daily_path
from specialists.rudi.entity_state import get_entities_by_tier
from specialists.rudi.production_retrieval import format_retrieval_context, memory_context_enabled
from specialists.sprockets.specialist import SprocketsSpecialist, SprocketsSpecialistConfig
from specialists.sprockets.vault_graph import build_graph


EntityProvider = Callable[[str], Sequence[dict[str, Any]]]
HierarchyContextBuilder = Callable[[], Sequence[str]]
RetrievalProvider = Callable[[str], Sequence[Any]]

DEFAULT_VAULT_DIR = Path.home() / "vault"
VAULT_DIR_ENV = "SPROCKETS_COGS_VAULT_DIR"


def configured_vault_dir() -> Path:
    return Path(os.environ.get(VAULT_DIR_ENV, str(DEFAULT_VAULT_DIR)))


def configured_daily_dir() -> Path:
    return configured_vault_dir() / "Cogs"


def build_hierarchy_context(
    vault_dir: Path,
    *,
    graph_builder=build_graph,
    max_nodes: int = 30,
) -> list[str]:
    """
    Return compact area/goal/project labels for parent_hint selection.

    Reads frontmatter only through the Sprockets specialist; note bodies stay
    out of classifier context.
    """

    specialist = SprocketsSpecialist(
        SprocketsSpecialistConfig(
            vault_dir=vault_dir,
            graph_builder=graph_builder,
        )
    )
    return specialist.hierarchy_context_lines(max_nodes)


def build_default_hierarchy_context(max_nodes: int = 30) -> list[str]:
    return build_hierarchy_context(configured_vault_dir(), max_nodes=max_nodes)


def build_base_context(
    daily_dir: Path,
    *,
    entity_provider: EntityProvider = get_entities_by_tier,
    hierarchy_context_builder: HierarchyContextBuilder | None = None,
) -> str:
    """
    Build the base classifier context.

    This includes compact operational hints only: today's Cogs checkbox items,
    hot contact/entity names, and hierarchy parent target labels.
    """

    today_iso = datetime.now().strftime("%Y-%m-%d")
    note_path = resolve_existing_daily_path(today_iso, daily_dir)
    if note_path is None or not note_path.exists():
        cogs_line = "Already in today's note: (none)"
    else:
        items = [
            line.strip().lstrip("-").strip().lstrip("[ ]>x-").strip()
            for line in note_path.read_text().splitlines()
            if line.strip().startswith("- [")
        ]
        cogs_line = "Already in today's note: " + (
            "; ".join(items) if items else "(none)"
        )

    hot = entity_provider("hot")
    contacts = [e["title"] for e in hot if e["node_type"] == "sprockets/contact"]
    entities = [e["title"] for e in hot if e["node_type"] == "sprockets/entity"]

    parts = [cogs_line]
    if contacts:
        parts.append("Known contacts: " + ", ".join(contacts))
    if entities:
        parts.append("Known entities: " + ", ".join(entities))
    if hierarchy_context_builder is not None:
        hierarchy_context = hierarchy_context_builder()
        if hierarchy_context:
            parts.append(
                "Known hierarchy parent targets:\n" + "\n".join(hierarchy_context)
            )
    return "\n".join(parts)


def build_default_context() -> str:
    return build_base_context(
        configured_daily_dir(),
        hierarchy_context_builder=build_default_hierarchy_context,
    )


def build_input_context(
    input_text: str,
    *,
    base_context_builder: Callable[[], str],
    retrieval_provider: RetrievalProvider,
) -> str:
    """
    Build classifier context for a specific input.

    Retrieved memory stays behind SPROCKETS_COGS_MEMORY_CONTEXT so prompt
    contamination risk remains opt-in.
    """

    context = base_context_builder()
    if not memory_context_enabled():
        return context

    memory_context = format_retrieval_context(tuple(retrieval_provider(input_text)))
    if not memory_context:
        return context
    return context + "\n\n" + memory_context

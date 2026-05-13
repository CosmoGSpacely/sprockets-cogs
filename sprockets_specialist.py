"""Sprockets specialist facade for Phase 4 orchestration.

Stage 40A keeps this boundary read-only. It delegates to the existing graph
and hierarchy inspection modules so the live write path keeps its current
review-first behavior.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import inspect_hierarchy
import vault_graph


@dataclass(frozen=True)
class SprocketsSpecialistConfig:
    """Filesystem roots owned by the Sprockets specialist."""

    vault_dir: Path = vault_graph.VAULT_DIR


@dataclass(frozen=True)
class SprocketsHierarchyNode:
    """Compact frontmatter-only hierarchy node summary."""

    slug: str
    title: str
    node_type: str
    parent_slug: str = ""
    parent_title: str = ""


@dataclass(frozen=True)
class SprocketsInventoryPreview:
    """Read-only hierarchy inventory result."""

    vault_dir: Path
    nodes: tuple[SprocketsHierarchyNode, ...]
    issues: tuple[str, ...]
    report: str


@dataclass(frozen=True)
class SprocketsParentMatchPreview:
    """Read-only parent-hint match preview."""

    hint: str
    matched: bool
    ambiguous: bool
    slug: str = ""
    title: str = ""
    uuid: str = ""
    matches: tuple[tuple[str, str, int], ...] = ()


class SprocketsSpecialist:
    """Facade for Sprockets hierarchy, parent matching, and future proposals."""

    def __init__(self, config: SprocketsSpecialistConfig | None = None) -> None:
        self.config = config or SprocketsSpecialistConfig()

    def hierarchy_nodes(self) -> tuple[SprocketsHierarchyNode, ...]:
        """Return hierarchy nodes without reading note bodies or writing files."""

        graph = vault_graph.build_graph(self.config.vault_dir)
        nodes: list[SprocketsHierarchyNode] = []
        for slug, attrs in graph.nodes(data=True):
            node_type = attrs.get("node_type", "")
            if node_type not in vault_graph.HIERARCHY_PARENT_NODE_TYPES:
                continue
            parent_slug = ""
            parent_title = ""
            parents = list(graph.successors(slug))
            if parents:
                parent_slug = parents[0]
                parent_title = graph.nodes[parent_slug].get("title", parent_slug)
            nodes.append(
                SprocketsHierarchyNode(
                    slug=slug,
                    title=attrs.get("title", slug),
                    node_type=node_type,
                    parent_slug=parent_slug,
                    parent_title=parent_title,
                )
            )
        nodes.sort(key=lambda node: (_node_type_order(node.node_type), node.title.lower(), node.slug))
        return tuple(nodes)

    def inventory(self) -> SprocketsInventoryPreview:
        """Inspect hierarchy state without writing."""

        lines, issues = inspect_hierarchy.inspect_hierarchy(self.config.vault_dir)
        return SprocketsInventoryPreview(
            vault_dir=self.config.vault_dir,
            nodes=self.hierarchy_nodes(),
            issues=tuple(issues),
            report="\n".join(lines + ["", "Issues:"] + [f"- {issue}" for issue in issues])
            if issues
            else "\n".join(lines + ["", "Issues: none"]),
        )

    def parent_match_preview(self, hint: str) -> SprocketsParentMatchPreview:
        """Preview how an input parent_hint would resolve without mutating nodes."""

        graph = vault_graph.build_graph(self.config.vault_dir)
        ambiguous = tuple(
            vault_graph.ambiguous_title_matches(
                graph,
                hint,
                allowed_node_types=vault_graph.HIERARCHY_PARENT_NODE_TYPES,
            )
        )
        if ambiguous:
            return SprocketsParentMatchPreview(
                hint=hint,
                matched=False,
                ambiguous=True,
                matches=ambiguous,
            )
        match = vault_graph.find_node_by_title(
            graph,
            hint,
            allowed_node_types=vault_graph.HIERARCHY_PARENT_NODE_TYPES,
        )
        if not match:
            return SprocketsParentMatchPreview(hint=hint, matched=False, ambiguous=False)
        slug, uuid = match
        return SprocketsParentMatchPreview(
            hint=hint,
            matched=True,
            ambiguous=False,
            slug=slug,
            title=graph.nodes[slug].get("title", slug),
            uuid=uuid,
        )

    def hierarchy_context_preview(self, max_nodes: int = 30) -> str:
        """Return compact hierarchy labels suitable for classifier context previews."""

        lines: list[str] = []
        labels = {
            "sprockets/area": "Area",
            "sprockets/goal": "Goal",
            "sprockets/project": "Project",
        }
        for node in self.hierarchy_nodes()[:max_nodes]:
            label = labels.get(node.node_type, node.node_type)
            if node.parent_title:
                lines.append(f"{label}: {node.title} (under {node.parent_title})")
            else:
                lines.append(f"{label}: {node.title}")
        return "\n".join(lines) if lines else "(none)"


def _node_type_order(node_type: str) -> int:
    return {
        "sprockets/area": 0,
        "sprockets/goal": 1,
        "sprockets/project": 2,
    }.get(node_type, 99)


def format_sprockets_specialist_preview(
    preview: SprocketsInventoryPreview | SprocketsParentMatchPreview | str,
) -> str:
    """Format a Sprockets specialist preview for operator inspection."""

    if isinstance(preview, SprocketsInventoryPreview):
        return "\n".join(
            [
                "Sprockets specialist inventory preview",
                f"- vault: {preview.vault_dir}",
                f"- hierarchy nodes: {len(preview.nodes)}",
                f"- issues: {len(preview.issues)}",
                "- writes: no",
                "",
                preview.report,
            ]
        )
    if isinstance(preview, SprocketsParentMatchPreview):
        lines = [
            "Sprockets specialist parent match preview",
            f"- hint: {preview.hint}",
            "- writes: no",
        ]
        if preview.ambiguous:
            lines.append("- result: ambiguous")
            lines.extend(f"  - {slug}: {title} ({score})" for slug, title, score in preview.matches)
        elif preview.matched:
            lines.extend(
                [
                    "- result: matched",
                    f"- parent: [[{preview.slug}]]",
                    f"- title: {preview.title}",
                ]
            )
        else:
            lines.append("- result: no match")
        return "\n".join(lines)
    return "\n".join(["Sprockets specialist hierarchy context preview", "- writes: no", "", preview])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Sprockets specialist preview.")
    parser.add_argument(
        "--vault",
        type=Path,
        default=vault_graph.VAULT_DIR,
        help="Obsidian vault root. Defaults to SPROCKETS_COGS_VAULT_DIR or ~/vault.",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=30,
        help="Maximum hierarchy nodes for context preview.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--inventory",
        action="store_true",
        help="Preview hierarchy inventory without writing.",
    )
    mode.add_argument(
        "--parent-match",
        metavar="HINT",
        help="Preview hierarchy parent matching for a parent_hint.",
    )
    mode.add_argument(
        "--context-preview",
        action="store_true",
        help="Preview compact hierarchy context without writing.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    specialist = SprocketsSpecialist(SprocketsSpecialistConfig(vault_dir=args.vault))

    if args.inventory:
        print(format_sprockets_specialist_preview(specialist.inventory()))
    elif args.parent_match:
        print(format_sprockets_specialist_preview(specialist.parent_match_preview(args.parent_match)))
    elif args.context_preview:
        print(format_sprockets_specialist_preview(specialist.hierarchy_context_preview(args.max_nodes)))


if __name__ == "__main__":
    main()

"""Sprockets specialist facade for Phase 4 orchestration.

Stage 40A keeps this boundary read-only. It delegates to the existing graph
and hierarchy inspection modules so the live write path keeps its current
review-first behavior.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import specialists.astro.inspect_hierarchy as inspect_hierarchy
import specialists.sprockets.vault_graph as vault_graph
from slug_utils import slugify


@dataclass(frozen=True)
class SprocketsSpecialistConfig:
    """Filesystem roots owned by the Sprockets specialist."""

    vault_dir: Path = vault_graph.VAULT_DIR
    graph_builder: Callable[[Path], Any] = vault_graph.build_graph


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


@dataclass(frozen=True)
class SprocketsHierarchyProposalPreview:
    """Review-only hierarchy node proposal."""

    node_type: str
    title: str
    slug: str
    parent_hint: str = ""
    parent_slug: str = ""
    parent_title: str = ""
    duplicate_slug: str = ""
    duplicate_title: str = ""
    issues: tuple[str, ...] = ()
    review_required: bool = True


VALID_HIERARCHY_PROPOSAL_TYPES = {
    "area": "sprockets/area",
    "goal": "sprockets/goal",
    "project": "sprockets/project",
    "sprockets/area": "sprockets/area",
    "sprockets/goal": "sprockets/goal",
    "sprockets/project": "sprockets/project",
}

VALID_PROPOSAL_PARENT_TYPES = {
    "sprockets/area": set(),
    "sprockets/goal": {"sprockets/area"},
    "sprockets/project": {"sprockets/area", "sprockets/goal"},
}


class SprocketsSpecialist:
    """Facade for Sprockets hierarchy, parent matching, and future proposals."""

    def __init__(self, config: SprocketsSpecialistConfig | None = None) -> None:
        self.config = config or SprocketsSpecialistConfig()

    def _graph(self) -> Any:
        return self.config.graph_builder(self.config.vault_dir)

    def hierarchy_nodes(self) -> tuple[SprocketsHierarchyNode, ...]:
        """Return hierarchy nodes without reading note bodies or writing files."""

        graph = self._graph()
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

    def hierarchy_titles(self) -> list[str]:
        """Return hierarchy titles ordered longest-first for exact text matching."""

        return sorted(
            [node.title for node in self.hierarchy_nodes() if node.title],
            key=len,
            reverse=True,
        )

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

        graph = self._graph()
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

    def hierarchy_proposal_preview(
        self,
        node_type: str,
        title: str,
        parent_hint: str = "",
    ) -> SprocketsHierarchyProposalPreview:
        """Preview a review-only area/goal/project proposal without writing."""

        normalized_type = VALID_HIERARCHY_PROPOSAL_TYPES.get(node_type.strip().lower(), "")
        clean_title = title.strip()
        issues: list[str] = []
        if not normalized_type:
            issues.append(f"unsupported hierarchy node type: {node_type}")
            normalized_type = node_type.strip()
        if not clean_title:
            issues.append("title is required")

        slug = slugify(clean_title)
        duplicate = self._exact_title_duplicate(clean_title, normalized_type)
        duplicate_slug = duplicate.slug if duplicate else ""
        duplicate_title = duplicate.title if duplicate else ""
        if duplicate:
            issues.append(f"duplicate {normalized_type} title exists: {duplicate.title} ({duplicate.slug})")

        parent_slug = ""
        parent_title = ""
        parent_hint = parent_hint.strip()
        allowed_parents = VALID_PROPOSAL_PARENT_TYPES.get(normalized_type, set())
        if not allowed_parents and parent_hint:
            issues.append(f"{normalized_type} does not accept a parent")
        elif allowed_parents and not parent_hint:
            issues.append(f"{normalized_type} requires a parent")
        elif allowed_parents and parent_hint:
            parent_match = self._parent_match_for_types(parent_hint, allowed_parents)
            if parent_match.ambiguous:
                choices = ", ".join(title for _, title, _ in parent_match.matches)
                issues.append(f"ambiguous parent hint {parent_hint!r}: {choices}")
            elif not parent_match.matched:
                issues.append(f"parent hint did not match an allowed parent: {parent_hint}")
            else:
                parent_slug = parent_match.slug
                parent_title = parent_match.title

        return SprocketsHierarchyProposalPreview(
            node_type=normalized_type,
            title=clean_title,
            slug=slug,
            parent_hint=parent_hint,
            parent_slug=parent_slug,
            parent_title=parent_title,
            duplicate_slug=duplicate_slug,
            duplicate_title=duplicate_title,
            issues=tuple(issues),
        )

    def ambiguous_parent_matches(self, hint: str) -> tuple[tuple[str, str, int], ...]:
        """Return ambiguous area/goal/project title matches for a parent hint."""

        graph = self._graph()
        return tuple(
            vault_graph.ambiguous_title_matches(
                graph,
                hint,
                allowed_node_types=vault_graph.HIERARCHY_PARENT_NODE_TYPES,
            )
        )

    def _parent_match_for_types(
        self,
        hint: str,
        allowed_node_types: set[str],
    ) -> SprocketsParentMatchPreview:
        graph = self._graph()
        ambiguous = tuple(
            vault_graph.ambiguous_title_matches(
                graph,
                hint,
                allowed_node_types=allowed_node_types,
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
            allowed_node_types=allowed_node_types,
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

    def _exact_title_duplicate(
        self,
        title: str,
        node_type: str,
    ) -> SprocketsHierarchyNode | None:
        title_lower = title.lower()
        for node in self.hierarchy_nodes():
            if node.node_type == node_type and node.title.lower() == title_lower:
                return node
        return None

    def hierarchy_context_lines(self, max_nodes: int = 30) -> list[str]:
        """Return compact hierarchy labels suitable for classifier context."""
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
        return lines

    def hierarchy_context_preview(self, max_nodes: int = 30) -> str:
        """Return compact hierarchy labels for operator previews."""

        lines = self.hierarchy_context_lines(max_nodes)
        return "\n".join(lines) if lines else "(none)"


def _node_type_order(node_type: str) -> int:
    return {
        "sprockets/area": 0,
        "sprockets/goal": 1,
        "sprockets/project": 2,
    }.get(node_type, 99)


def format_sprockets_specialist_preview(
    preview: SprocketsInventoryPreview | SprocketsParentMatchPreview | SprocketsHierarchyProposalPreview | str,
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
    if isinstance(preview, SprocketsHierarchyProposalPreview):
        lines = [
            "Sprockets specialist hierarchy proposal preview",
            f"- node type: {preview.node_type}",
            f"- title: {preview.title}",
            f"- slug: {preview.slug}",
            f"- review required: {'yes' if preview.review_required else 'no'}",
            "- writes: no",
        ]
        if preview.parent_hint:
            lines.append(f"- parent hint: {preview.parent_hint}")
        if preview.parent_slug:
            lines.append(f"- parent: [[{preview.parent_slug}]] ({preview.parent_title})")
        if preview.duplicate_slug:
            lines.append(f"- duplicate: [[{preview.duplicate_slug}]] ({preview.duplicate_title})")
        if preview.issues:
            lines.append("- issues:")
            lines.extend(f"  - {issue}" for issue in preview.issues)
        else:
            lines.append("- issues: none")
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
    parser.add_argument(
        "--title",
        default="",
        help="Title for --propose hierarchy preview.",
    )
    parser.add_argument(
        "--parent",
        default="",
        help="Parent title hint for --propose hierarchy preview.",
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
    mode.add_argument(
        "--propose",
        choices=("area", "goal", "project", "sprockets/area", "sprockets/goal", "sprockets/project"),
        help="Preview a review-only hierarchy node proposal without writing.",
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
    elif args.propose:
        print(
            format_sprockets_specialist_preview(
                specialist.hierarchy_proposal_preview(
                    args.propose,
                    args.title,
                    args.parent,
                )
            )
        )


if __name__ == "__main__":
    main()

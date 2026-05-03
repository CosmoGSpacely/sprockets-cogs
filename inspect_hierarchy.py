#!/usr/bin/env python3
"""Read-only Sprockets hierarchy inspection."""
from __future__ import annotations

import argparse
from pathlib import Path

from vault_graph import HIERARCHY_PARENT_NODE_TYPES, build_graph


VALID_PARENT_TYPES = {
    "sprockets/area": set(),
    "sprockets/goal": {"sprockets/area"},
    "sprockets/project": {"sprockets/area", "sprockets/goal"},
}


def inspect_hierarchy(vault_dir: Path) -> tuple[list[str], list[str]]:
    """Return display lines and issue lines for hierarchy nodes in a vault."""
    graph = build_graph(vault_dir)
    counts = {node_type: 0 for node_type in sorted(HIERARCHY_PARENT_NODE_TYPES)}
    issues: list[str] = []
    lines: list[str] = []

    hierarchy_slugs = [
        slug
        for slug, attrs in graph.nodes(data=True)
        if attrs.get("node_type", "") in HIERARCHY_PARENT_NODE_TYPES
    ]

    for slug in hierarchy_slugs:
        attrs = graph.nodes[slug]
        node_type = attrs.get("node_type", "")
        counts[node_type] += 1
        missing = [
            field
            for field in ("node_type", "uuid", "title")
            if not attrs.get(field)
        ]
        if missing:
            issues.append(f"{slug}: missing {', '.join(missing)}")

    for slug in hierarchy_slugs:
        attrs = graph.nodes[slug]
        node_type = attrs.get("node_type", "")
        title = attrs.get("title", slug)
        parents = list(graph.successors(slug))

        if not parents:
            if node_type != "sprockets/area":
                issues.append(f"{slug}: {node_type} has no parent")
            lines.append(f"- {slug} ({node_type}): {title}")
            continue

        for parent_slug in parents:
            parent_type = graph.nodes[parent_slug].get("node_type", "")
            parent_title = graph.nodes[parent_slug].get("title", parent_slug)
            if parent_type not in VALID_PARENT_TYPES[node_type]:
                issues.append(
                    f"{slug}: {node_type} parent {parent_slug} has invalid type {parent_type or '(blank)'}"
                )
            lines.append(
                f"- {slug} ({node_type}): {title} -> {parent_slug} ({parent_type}): {parent_title}"
            )

    header = [
        f"Vault: {vault_dir}",
        "Hierarchy counts:",
        f"- sprockets/area: {counts['sprockets/area']}",
        f"- sprockets/goal: {counts['sprockets/goal']}",
        f"- sprockets/project: {counts['sprockets/project']}",
        f"Graph edges: {graph.number_of_edges()}",
    ]
    if not hierarchy_slugs:
        header.append("No hierarchy nodes found.")

    return header + lines, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path("/home/cosmo/vault"),
        help="Obsidian vault root. Default: /home/cosmo/vault",
    )
    args = parser.parse_args()

    lines, issues = inspect_hierarchy(args.vault)
    print("\n".join(lines))
    if issues:
        print("\nIssues:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("\nIssues: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

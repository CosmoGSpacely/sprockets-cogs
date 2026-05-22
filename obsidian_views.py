"""Read-only preview helpers for Stage 58 Obsidian view notes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from vault import DEFAULT_VAULT_DIR


@dataclass(frozen=True)
class ObsidianViewNote:
    """One proposed Obsidian visualization note."""

    relative_path: Path
    markdown: str

    def target_path(self, vault_dir: Path) -> Path:
        return vault_dir / self.relative_path


def stage_58_view_notes() -> tuple[ObsidianViewNote, ...]:
    """Return the first Stage 58 view-note set without touching the vault."""

    return (
        ObsidianViewNote(Path("HOME.md"), _home_note()),
        ObsidianViewNote(Path("Sprockets/tasks-index.md"), _tasks_index_note()),
        ObsidianViewNote(Path("Sprockets/projects-index.md"), _projects_index_note()),
        ObsidianViewNote(Path("Sprockets/contacts-index.md"), _contacts_index_note()),
        ObsidianViewNote(Path("Sprockets/hierarchy-view.md"), _hierarchy_view_note()),
        ObsidianViewNote(Path("Cogs/cogs-navigation.md"), _cogs_navigation_note()),
    )


def format_view_preview(
    notes: Sequence[ObsidianViewNote],
    *,
    vault_dir: Path = DEFAULT_VAULT_DIR,
) -> str:
    """Format proposed Stage 58 view notes for terminal review."""

    lines = [
        "Obsidian view-note preview",
        "- writes: no",
        f"- vault: {vault_dir}",
        f"- notes: {len(notes)}",
    ]
    for note in notes:
        lines.extend([
            "",
            f"=== {note.target_path(vault_dir)} ===",
            note.markdown.rstrip(),
        ])
    return "\n".join(lines).rstrip() + "\n"


def _home_note() -> str:
    return """# Sprockets-Cogs Home

Today: <% tp.date.now("YYYY-MM-DD") %>

## Cogs

- [[Cogs/daily/<% tp.date.now("ddd DD MMM YYYY") %>|Today's daily note]]
- [[Cogs/weekly/<% tp.date.now("GGGG-[W]WW") %>|This week]]
- [[Cogs/monthly/<% tp.date.now("YYYY-MM") %>|This month]]
- [[Cogs/cogs-navigation|Cogs navigation]]

## Sprockets

- [[Sprockets/tasks-index|Open tasks]]
- [[Sprockets/projects-index|Projects]]
- [[Sprockets/contacts-index|Contacts]]
- [[Sprockets/hierarchy-view|Hierarchy]]

## Recent Sprockets

```dataview
TABLE WITHOUT ID file.link AS Node, node_type AS Type, created AS Created
FROM "Sprockets"
WHERE created
SORT created DESC
LIMIT 10
```

## Review

Jane review surfacing arrives in Stage 60.
"""


def _tasks_index_note() -> str:
    return """# Open Sprockets Tasks

```dataview
TABLE WITHOUT ID file.link AS Task, parent AS Parent, status AS Status, created AS Created, updated AS Updated
FROM "Sprockets/tasks"
WHERE node_type = "sprockets/task" AND status != "complete" AND status != "cancelled"
SORT updated DESC
```
"""


def _projects_index_note() -> str:
    return """# Sprockets Projects

```dataview
TABLE WITHOUT ID file.link AS Project, parent AS Parent, created AS Created, updated AS Updated
FROM "Sprockets/projects"
WHERE node_type = "sprockets/project"
SORT updated DESC
```
"""


def _contacts_index_note() -> str:
    return """# Sprockets Contacts

```dataview
TABLE WITHOUT ID file.link AS Contact, tags AS Tags, updated AS Updated
FROM "Sprockets/contacts"
WHERE node_type = "sprockets/contact"
SORT title ASC
```
"""


def _hierarchy_view_note() -> str:
    return """# Sprockets Hierarchy

This first hierarchy view stays flat and parent-aware while live parent data is
inspected in Obsidian.

```dataview
TABLE WITHOUT ID file.link AS Node, node_type AS Type, parent AS Parent
FROM "Sprockets"
WHERE node_type = "sprockets/area" OR node_type = "sprockets/goal" OR node_type = "sprockets/project" OR node_type = "sprockets/task"
SORT node_type ASC, title ASC
```
"""


def _cogs_navigation_note() -> str:
    return """# Cogs Navigation

## Periods

- [[Cogs/daily|Daily notes]]
- [[Cogs/weekly|Weekly notes]]
- [[Cogs/monthly|Monthly notes]]
- [[Cogs/annual|Annual notes]]

## Recent Daily Notes

```dataview
TABLE WITHOUT ID file.link AS Daily, date AS Date
FROM "Cogs/daily"
WHERE node_type = "cogs/daily" AND date
SORT date DESC
LIMIT 7
```

## Recent Weekly Notes

```dataview
TABLE WITHOUT ID file.link AS Week, week AS Week
FROM "Cogs/weekly"
WHERE node_type = "cogs/weekly"
SORT week DESC
LIMIT 7
```
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview Stage 58 Obsidian view notes without writing the vault.",
    )
    parser.add_argument(
        "--vault-dir",
        type=Path,
        default=DEFAULT_VAULT_DIR,
        help="vault path used only to display proposed target note paths",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    print(format_view_preview(stage_58_view_notes(), vault_dir=args.vault_dir), end="")


if __name__ == "__main__":
    main()

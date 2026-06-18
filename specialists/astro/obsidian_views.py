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


@dataclass(frozen=True)
class ObsidianViewWriteResult:
    """Result of one guarded Stage 58 view-note write."""

    note: ObsidianViewNote
    target_path: Path
    status: str


def stage_58_view_notes() -> tuple[ObsidianViewNote, ...]:
    """Return the first Stage 58 view-note set without touching the vault."""

    return (
        ObsidianViewNote(Path("HOME.md"), _home_note()),
        ObsidianViewNote(Path("Sprockets/tasks-index.md"), _tasks_index_note()),
        ObsidianViewNote(Path("Sprockets/projects-index.md"), _projects_index_note()),
        ObsidianViewNote(Path("Sprockets/contacts-index.md"), _contacts_index_note()),
        ObsidianViewNote(Path("Sprockets/hierarchy-view.md"), _hierarchy_view_note()),
        ObsidianViewNote(Path("Cogs/cogs-navigation.md"), _cogs_navigation_note()),
        ObsidianViewNote(Path("REVIEW.md"), _review_landing_note()),
    )


def stage_59_navigation_notes() -> tuple[ObsidianViewNote, ...]:
    """Return the reviewed Stage 59 navigation notes that may be refreshed."""

    return tuple(
        note
        for note in stage_58_view_notes()
        if note.relative_path in {Path("HOME.md"), Path("Cogs/cogs-navigation.md")}
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


def create_view_notes(
    notes: Sequence[ObsidianViewNote],
    *,
    vault_dir: Path = DEFAULT_VAULT_DIR,
) -> tuple[ObsidianViewWriteResult, ...]:
    """Create missing view notes and preserve existing vault notes."""

    results: list[ObsidianViewWriteResult] = []
    for note in notes:
        target_path = note.target_path(vault_dir)
        if target_path.exists():
            results.append(ObsidianViewWriteResult(note, target_path, "exists"))
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(note.markdown, encoding="utf-8")
        results.append(ObsidianViewWriteResult(note, target_path, "created"))
    return tuple(results)


def refresh_navigation_notes(
    notes: Sequence[ObsidianViewNote],
    *,
    vault_dir: Path = DEFAULT_VAULT_DIR,
) -> tuple[ObsidianViewWriteResult, ...]:
    """Write reviewed navigation notes and report whether each replaced a note."""

    results: list[ObsidianViewWriteResult] = []
    for note in notes:
        target_path = note.target_path(vault_dir)
        status = "updated" if target_path.exists() else "created"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(note.markdown, encoding="utf-8")
        results.append(ObsidianViewWriteResult(note, target_path, status))
    return tuple(results)


def format_view_write_result(results: Sequence[ObsidianViewWriteResult]) -> str:
    """Format guarded Stage 58 view-note creation results."""

    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    summary = ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))
    lines = [
        "Obsidian view-note create",
        "- writes: vault",
        f"- notes: {len(results)}",
        f"- summary: {summary}",
    ]
    for result in results:
        lines.append(f"- {result.status}: {result.target_path}")
    return "\n".join(lines)


def _home_note() -> str:
    return """# Sprockets-Cogs Home

## Cogs

- [[Cogs/cogs-navigation|Cogs navigation]]

## Sprockets

- [[Sprockets/tasks-index|Open tasks]]
- [[Sprockets/projects-index|Projects]]
- [[Sprockets/contacts-index|Contacts]]
- [[Sprockets/hierarchy-view|Hierarchy]]

## Review

- [[REVIEW|Jane review]]
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

## Current Planning

### Today

```dataview
TABLE WITHOUT ID file.link AS Daily, date AS Date
FROM "Cogs/daily"
WHERE node_type = "cogs/daily" AND date = date(today)
LIMIT 1
```

### This Week

```dataview
TABLE WITHOUT ID file.link AS Week, week AS Week
FROM "Cogs/weekly"
WHERE node_type = "cogs/weekly" AND week = dateformat(date(today), "kkkk-'W'WW")
LIMIT 1
```

### This Month and 5WOW

The current 5WOW planning view lives in the current monthly Cogs note.

```dataview
TABLE WITHOUT ID file.link AS Month, link(file.path + "#5WOW", "Open 5WOW") AS "5WOW"
FROM "Cogs/monthly"
WHERE node_type = "cogs/monthly" AND month = dateformat(date(today), "yyyy-MM")
LIMIT 1
```

### Far Horizon

The implemented far-horizon surface is the current annual note for now.

```dataview
TABLE WITHOUT ID file.link AS Year, year AS Year
FROM "Cogs/annual"
WHERE node_type = "cogs/annual" AND string(year) = dateformat(date(today), "yyyy")
LIMIT 1
```

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


def _review_landing_note() -> str:
    return """# Jane Review

This landing page surfaces the canonical `review/` queue in Obsidian.

```dataview
TABLE WITHOUT ID file.link AS Item, created AS Created
FROM "review"
WHERE node_type = "review" AND reviewed = false
SORT created ASC, file.name ASC
```

## Review Boundary

Jane keeps uncertain output review-first. Current decisions still run through
the guarded review tools until Stage 60 packet decisions are promoted.
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
    parser.add_argument(
        "--create",
        action="store_true",
        help="create missing view notes in --vault-dir and preserve existing notes",
    )
    parser.add_argument(
        "--refresh-navigation",
        action="store_true",
        help="write the reviewed Stage 59 HOME and Cogs navigation notes in --vault-dir",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    notes = stage_58_view_notes()
    if args.refresh_navigation:
        print(format_view_write_result(refresh_navigation_notes(stage_59_navigation_notes(), vault_dir=args.vault_dir)))
        return
    if args.create:
        print(format_view_write_result(create_view_notes(notes, vault_dir=args.vault_dir)))
        return
    print(format_view_preview(notes, vault_dir=args.vault_dir), end="")


if __name__ == "__main__":
    main()

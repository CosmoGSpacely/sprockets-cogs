"""Read-only Cogs planning-note and filename previews."""

from __future__ import annotations

import argparse
from pathlib import Path

from cogs_naming import build_daily_rename_plan, planned_note_filenames
from vault import DEFAULT_DAILY_DIR


def format_planning_names(date_iso: str) -> str:
    names = planned_note_filenames(date_iso)
    lines = [f"Planning note names for {date_iso}:"]
    lines.append(f"- daily: {names['daily']}")
    lines.append(f"- weekly: {names['weekly']}")
    lines.append(f"- monthly: {names['monthly']}")
    lines.append(f"- annual: {names['annual']}")
    lines.append(f"- 5WOW: monthly section anchor {names['five_wow_anchor']}")
    return "\n".join(lines)


def format_daily_rename_plan(daily_dir: Path) -> str:
    plan = build_daily_rename_plan(daily_dir)
    if not plan:
        return f"No daily notes found in {daily_dir}."

    counts: dict[str, int] = {}
    for item in plan:
        counts[item.status] = counts.get(item.status, 0) + 1

    summary = ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))
    lines = [f"Daily rename plan for {daily_dir}", f"Summary: {summary}"]
    for item in plan:
        if item.status == "rename":
            lines.append(f"- rename {item.source_path.name} -> {item.target_path.name}")
        elif item.status == "already-current":
            lines.append(f"- keep   {item.source_path.name} ({item.reason})")
        elif item.status == "collision":
            lines.append(f"- block  {item.source_path.name} -> {item.target_path.name} ({item.reason})")
        else:
            lines.append(f"- skip   {item.source_path.name} ({item.reason})")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--names",
        metavar="YYYY-MM-DD",
        help="Preview ISO-first daily/weekly/monthly/annual names for a date.",
    )
    parser.add_argument(
        "--daily-rename-plan",
        action="store_true",
        help="Preview legacy daily-note renames without writing.",
    )
    parser.add_argument(
        "--daily-dir",
        default=str(DEFAULT_DAILY_DIR),
        help="Cogs daily-note directory. Defaults to the real vault daily directory.",
    )
    args = parser.parse_args()

    if args.names:
        print(format_planning_names(args.names))
        return
    if args.daily_rename_plan:
        print(format_daily_rename_plan(Path(args.daily_dir)))
        return

    parser.error("choose --names or --daily-rename-plan")


if __name__ == "__main__":
    main()

"""Nightly Cogs carry safety net.

This script is intentionally mechanical: carry still-open Cogs blocks forward
while respecting any item already acted on by manual or interactive carry.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence

from carry import apply_plan_document, build_plan_document, preview_apply_plan_document, scan_daily_notes
from vault import DEFAULT_DAILY_DIR


def _today() -> datetime:
    return datetime.now()


def default_through_date() -> str:
    return _today().strftime("%Y-%m-%d")


def default_destination_date() -> str:
    return (_today() + timedelta(days=1)).strftime("%Y-%m-%d")


def build_nightly_plan(
    daily_dir: Path = DEFAULT_DAILY_DIR,
    through_date: str | None = None,
    destination_date: str | None = None,
) -> dict:
    """Build a carry-all plan for open Cogs blocks. Does not write."""
    through = through_date or default_through_date()
    destination = destination_date or default_destination_date()
    candidates = scan_daily_notes(daily_dir=daily_dir, through_date=through)
    return build_plan_document(candidates, destination)


def summarize_nightly_plan(plan: dict) -> dict[str, object]:
    """Summarize a nightly carry plan without writing."""
    items = plan.get("items", [])
    if not isinstance(items, list):
        items = []

    action_counts: Counter[str] = Counter()
    source_dates: set[str] = set()
    source_paths: set[str] = set()
    destination_dates: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action", "unknown") or "unknown")
        action_counts[action] += 1
        destination = str(item.get("destination_date", "") or "")
        if destination:
            destination_dates.add(destination)
        source = item.get("source")
        if isinstance(source, dict):
            source_date = str(source.get("date", "") or "")
            source_path = str(source.get("path", "") or "")
            if source_date:
                source_dates.add(source_date)
            if source_path:
                source_paths.add(source_path)

    return {
        "item_count": len(items),
        "action_counts": dict(sorted(action_counts.items())),
        "source_date_count": len(source_dates),
        "source_file_count": len(source_paths),
        "source_dates": sorted(source_dates),
        "destination_dates": sorted(destination_dates),
    }


def format_nightly_report(
    plan: dict,
    daily_dir: Path = DEFAULT_DAILY_DIR,
    through_date: str | None = None,
    destination_date: str | None = None,
) -> str:
    """Format a read-only operator report for the nightly carry job."""
    through = through_date or default_through_date()
    destination = destination_date or str(plan.get("default_destination_date", "") or default_destination_date())
    summary = summarize_nightly_plan(plan)
    action_counts = summary["action_counts"]
    if isinstance(action_counts, dict) and action_counts:
        action_text = ", ".join(f"{action}: {count}" for action, count in action_counts.items())
    else:
        action_text = "none"

    lines = [
        "Nightly carry report",
        f"- daily dir: {daily_dir}",
        f"- through: {through}",
        f"- destination: {destination}",
        f"- open candidates: {summary['item_count']}",
        f"- source files: {summary['source_file_count']}",
        f"- source dates: {summary['source_date_count']}",
        f"- planned actions: {action_text}",
        "- writes: no",
        f"- dry run: scripts/nightly --dry-run --through {through} --to {destination}",
        f"- apply manually: scripts/nightly --through {through} --to {destination}",
    ]
    if summary["item_count"] == 0:
        lines.append("next: no carry actions are pending.")
    else:
        lines.append("next: inspect the dry run before applying or scheduling this job.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--through",
        default=None,
        help="YYYY-MM-DD cutoff for source daily notes. Defaults to today. Read-only with --dry-run or --report.",
    )
    parser.add_argument(
        "--to",
        default=None,
        help="YYYY-MM-DD destination daily note. Defaults to tomorrow. Used for carry actions.",
    )
    parser.add_argument(
        "--daily-dir",
        default=str(DEFAULT_DAILY_DIR),
        help="Cogs daily-note directory. Defaults to the real vault daily directory. Writes unless --dry-run or --report is used.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview nightly carry actions. Read-only; no vault writes.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Summarize the nightly plan. Read-only; no vault writes.",
    )
    args = parser.parse_args(argv)

    if args.report:
        from cogs_specialist import CogsSpecialist, CogsSpecialistConfig

        specialist = CogsSpecialist(
            CogsSpecialistConfig(
                cogs_dir=Path(args.daily_dir).parent,
                daily_dir=Path(args.daily_dir),
            )
        )
        print(specialist.nightly_preview(args.through, args.to).report)
        return

    plan = build_nightly_plan(
        daily_dir=Path(args.daily_dir),
        through_date=args.through,
        destination_date=args.to,
    )
    if args.dry_run:
        print(preview_apply_plan_document(plan))
        return

    results = apply_plan_document(plan)
    print("\n".join(results) if results else "No nightly carry actions applied.")


if __name__ == "__main__":
    main()

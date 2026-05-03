"""Nightly Cogs carry safety net.

This script is intentionally mechanical: carry still-open Cogs blocks forward
while respecting any item already acted on by manual or interactive carry.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--through",
        default=None,
        help="YYYY-MM-DD cutoff for source daily notes. Defaults to today.",
    )
    parser.add_argument(
        "--to",
        default=None,
        help="YYYY-MM-DD destination daily note. Defaults to tomorrow.",
    )
    parser.add_argument(
        "--daily-dir",
        default=str(DEFAULT_DAILY_DIR),
        help="Cogs daily-note directory. Defaults to the real vault daily directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview nightly carry actions without writing.",
    )
    args = parser.parse_args()

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

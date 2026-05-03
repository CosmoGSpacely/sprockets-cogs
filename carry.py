"""Interactive Cogs carry tooling.

Stage 14.5 starts read-only: list open Cogs blocks that are candidates for
deliberate carry review. Later slices add decisions, previews, and writes.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import frontmatter

from vault import CogsBlock, parse_cogs_blocks


VAULT_DIR = Path(os.environ.get("SPROCKETS_COGS_VAULT_DIR", "/home/cosmo/vault"))
DAILY_DIR = VAULT_DIR / "Cogs" / "daily"


@dataclass(frozen=True)
class CarryCandidate:
    path: Path
    date: str
    block: CogsBlock


def _date_from_daily_note(path: Path) -> str:
    post = frontmatter.load(str(path))
    date = str(post.get("date", "") or "")
    if date:
        datetime.strptime(date, "%Y-%m-%d")
        return date
    dt = datetime.strptime(path.stem, "%a %d %b %Y")
    return dt.strftime("%Y-%m-%d")


def scan_daily_notes(
    daily_dir: Path = DAILY_DIR,
    through_date: str | None = None,
) -> list[CarryCandidate]:
    """Return open top-level Cogs blocks from daily notes through through_date."""
    if not daily_dir.exists():
        return []

    cutoff = through_date or datetime.now().strftime("%Y-%m-%d")
    datetime.strptime(cutoff, "%Y-%m-%d")

    candidates: list[CarryCandidate] = []
    for path in sorted(daily_dir.glob("*.md")):
        try:
            date = _date_from_daily_note(path)
        except Exception:
            continue
        if date > cutoff:
            continue
        post = frontmatter.load(str(path))
        for block in parse_cogs_blocks(post.content, states={" "}):
            candidates.append(CarryCandidate(path=path, date=date, block=block))
    candidates.sort(key=lambda item: (item.date, item.path.name, item.block.start_line))
    return candidates


def print_candidates(candidates: list[CarryCandidate]) -> None:
    if not candidates:
        print("No open Cogs carry candidates found.")
        return

    print(f"{len(candidates)} open Cogs carry candidate(s)")
    for i, candidate in enumerate(candidates, start=1):
        print(f"\n[{i}] {candidate.date}  {candidate.path.name}:{candidate.block.start_line + 1}")
        for line in candidate.block.lines:
            print(f"    {line}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list",
        action="store_true",
        help="List open carry candidates. Read-only.",
    )
    parser.add_argument(
        "--through",
        default=None,
        help="YYYY-MM-DD cutoff for scanned daily notes. Defaults to today.",
    )
    args = parser.parse_args()

    if args.list:
        print_candidates(scan_daily_notes(through_date=args.through))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

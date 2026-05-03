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


@dataclass(frozen=True)
class CarryDecision:
    candidate: CarryCandidate
    action: str
    destination_date: str = ""


VALID_ACTIONS = {"carry", "cancel", "skip"}


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


def build_default_plan(
    candidates: list[CarryCandidate],
    destination_date: str,
) -> list[CarryDecision]:
    """Build a dry-run plan that carries every candidate to destination_date."""
    datetime.strptime(destination_date, "%Y-%m-%d")
    return [
        CarryDecision(candidate=candidate, action="carry", destination_date=destination_date)
        for candidate in candidates
    ]


def validate_decision(decision: CarryDecision) -> None:
    if decision.action not in VALID_ACTIONS:
        raise ValueError(f"Unknown carry action: {decision.action!r}")
    if decision.action == "carry":
        if not decision.destination_date:
            raise ValueError("carry decisions require destination_date")
        datetime.strptime(decision.destination_date, "%Y-%m-%d")
    elif decision.destination_date:
        raise ValueError(f"{decision.action} decisions cannot have destination_date")


def preview_plan(decisions: list[CarryDecision]) -> str:
    if not decisions:
        return "No carry decisions to preview."

    lines = [f"{len(decisions)} carry decision(s) pending"]
    for i, decision in enumerate(decisions, start=1):
        validate_decision(decision)
        candidate = decision.candidate
        source = f"{candidate.date} {candidate.path.name}:{candidate.block.start_line + 1}"
        if decision.action == "carry":
            lines.append(
                f"[{i}] carry  {source} -> {decision.destination_date}: {candidate.block.item_text}"
            )
        elif decision.action == "cancel":
            lines.append(f"[{i}] cancel {source}: {candidate.block.item_text}")
        else:
            lines.append(f"[{i}] skip   {source}: {candidate.block.item_text}")
    return "\n".join(lines)


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
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Preview a carry-all plan. Dry-run only.",
    )
    parser.add_argument(
        "--to",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Destination date for --plan carry decisions. Defaults to today.",
    )
    args = parser.parse_args()

    candidates = scan_daily_notes(through_date=args.through)
    if args.list:
        print_candidates(candidates)
    elif args.plan:
        print(preview_plan(build_default_plan(candidates, args.to)))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

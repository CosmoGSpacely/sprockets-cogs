"""Interactive Cogs carry tooling.

Stage 14.5 starts read-only: list open Cogs blocks that are candidates for
deliberate carry review. Later slices add decisions, previews, and writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

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
PLAN_VERSION = 1
PLAN_ACTIONS = {"carry", "schedule", "drop", "done", "skip"}
PLAN_ACTIONS_WITH_DESTINATION = {"carry", "schedule"}


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


def _candidate_id(candidate: CarryCandidate) -> str:
    digest = hashlib.sha1("\n".join(candidate.block.lines).encode("utf-8")).hexdigest()[:10]
    return f"{candidate.date}:{candidate.path.name}:{candidate.block.start_line + 1}:{digest}"


def _candidate_to_plan_item(candidate: CarryCandidate, destination_date: str) -> dict[str, Any]:
    return {
        "id": _candidate_id(candidate),
        "action": "carry",
        "destination_date": destination_date,
        "source": {
            "date": candidate.date,
            "path": str(candidate.path),
            "line": candidate.block.start_line + 1,
        },
        "item_text": candidate.block.item_text,
        "lines": list(candidate.block.lines),
    }


def build_plan_document(
    candidates: list[CarryCandidate],
    destination_date: str,
) -> dict[str, Any]:
    """Build an editable carry plan document. This does not write to the vault."""
    datetime.strptime(destination_date, "%Y-%m-%d")
    return {
        "version": PLAN_VERSION,
        "kind": "sprockets-cogs/carry-plan",
        "default_destination_date": destination_date,
        "items": [
            _candidate_to_plan_item(candidate, destination_date)
            for candidate in candidates
        ],
    }


def write_plan_document(plan: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(plan, indent=2) + "\n")


def load_plan_document(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("carry plan must be a JSON object")
    return raw


def validate_plan_document(plan: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if plan.get("kind") != "sprockets-cogs/carry-plan":
        issues.append("kind must be sprockets-cogs/carry-plan")
    if plan.get("version") != PLAN_VERSION:
        issues.append(f"version must be {PLAN_VERSION}")

    items = plan.get("items")
    if not isinstance(items, list):
        return issues + ["items must be a list"]

    seen_ids: set[str] = set()
    for index, item in enumerate(items, start=1):
        prefix = f"items[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{prefix} must be an object")
            continue

        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            issues.append(f"{prefix}.id must be a non-empty string")
        elif item_id in seen_ids:
            issues.append(f"{prefix}.id duplicates {item_id}")
        else:
            seen_ids.add(item_id)

        action = item.get("action")
        if action not in PLAN_ACTIONS:
            issues.append(f"{prefix}.action must be one of {sorted(PLAN_ACTIONS)}")

        destination_date = item.get("destination_date", "")
        if action in PLAN_ACTIONS_WITH_DESTINATION:
            if not isinstance(destination_date, str) or not destination_date:
                issues.append(f"{prefix}.destination_date is required for {action}")
            else:
                try:
                    datetime.strptime(destination_date, "%Y-%m-%d")
                except ValueError:
                    issues.append(f"{prefix}.destination_date must be YYYY-MM-DD")
        elif destination_date:
            issues.append(f"{prefix}.destination_date must be empty for {action}")

        source = item.get("source")
        if not isinstance(source, dict):
            issues.append(f"{prefix}.source must be an object")
        else:
            if not isinstance(source.get("path"), str) or not source.get("path"):
                issues.append(f"{prefix}.source.path must be a non-empty string")
            if not isinstance(source.get("date"), str) or not source.get("date"):
                issues.append(f"{prefix}.source.date must be a non-empty string")
            else:
                try:
                    datetime.strptime(source["date"], "%Y-%m-%d")
                except ValueError:
                    issues.append(f"{prefix}.source.date must be YYYY-MM-DD")
            if not isinstance(source.get("line"), int) or source.get("line", 0) < 1:
                issues.append(f"{prefix}.source.line must be a positive integer")

        if not isinstance(item.get("item_text"), str) or not item.get("item_text"):
            issues.append(f"{prefix}.item_text must be a non-empty string")
        lines = item.get("lines")
        if not isinstance(lines, list) or not lines:
            issues.append(f"{prefix}.lines must be a non-empty list")
        elif not all(isinstance(line, str) for line in lines):
            issues.append(f"{prefix}.lines must contain only strings")

    return issues


def preview_plan_document(plan: dict[str, Any]) -> str:
    issues = validate_plan_document(plan)
    if issues:
        return "Carry plan is invalid:\n" + "\n".join(f"- {issue}" for issue in issues)

    items = plan["items"]
    if not items:
        return "No carry decisions to preview."

    lines = [f"{len(items)} carry plan item(s) pending"]
    for index, item in enumerate(items, start=1):
        source = item["source"]
        source_ref = f"{source['date']} {Path(source['path']).name}:{source['line']}"
        action = item["action"]
        if action in PLAN_ACTIONS_WITH_DESTINATION:
            lines.append(
                f"[{index}] {action:<8} {source_ref} -> {item['destination_date']}: {item['item_text']}"
            )
        else:
            lines.append(f"[{index}] {action:<8} {source_ref}: {item['item_text']}")
    return "\n".join(lines)


def preview_apply_plan_document(plan: dict[str, Any]) -> str:
    """Describe the exact vault edits a valid carry plan would make. No writes."""
    issues = validate_plan_document(plan)
    if issues:
        return "Carry plan is invalid:\n" + "\n".join(f"- {issue}" for issue in issues)

    items = plan["items"]
    if not items:
        return "No carry actions to apply."

    lines = [f"{len(items)} carry action(s) would be applied"]
    for index, item in enumerate(items, start=1):
        source = item["source"]
        source_ref = f"{source['date']} {Path(source['path']).name}:{source['line']}"
        action = item["action"]
        item_text = item["item_text"]
        if action == "carry":
            lines.append(f"[{index}] mark [>] in {source_ref}: {item_text}")
            lines.append(f"    append [ ] to {item['destination_date']}: {item_text}")
        elif action == "schedule":
            lines.append(f"[{index}] mark [>] in {source_ref}: {item_text}")
            lines.append(f"    schedule [ ] on {item['destination_date']}: {item_text}")
        elif action == "drop":
            lines.append(f"[{index}] mark [-] in {source_ref}: {item_text}")
        elif action == "done":
            lines.append(f"[{index}] mark [x] in {source_ref}: {item_text}")
        else:
            lines.append(f"[{index}] skip unchanged {source_ref}: {item_text}")
    return "\n".join(lines)


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
    parser.add_argument(
        "--out",
        default=None,
        help="Write --plan output to an editable JSON plan file. No vault writes.",
    )
    parser.add_argument(
        "--validate-plan",
        default=None,
        help="Validate an editable JSON carry plan file. No vault writes.",
    )
    parser.add_argument(
        "--preview-plan",
        default=None,
        help="Preview an editable JSON carry plan file. No vault writes.",
    )
    parser.add_argument(
        "--preview-apply",
        default=None,
        help="Preview exact edits from a JSON carry plan file. No vault writes.",
    )
    args = parser.parse_args()

    if args.validate_plan:
        issues = validate_plan_document(load_plan_document(Path(args.validate_plan)))
        if issues:
            print("Carry plan is invalid:")
            for issue in issues:
                print(f"- {issue}")
            raise SystemExit(1)
        print("Carry plan is valid.")
    elif args.preview_plan:
        print(preview_plan_document(load_plan_document(Path(args.preview_plan))))
    elif args.preview_apply:
        print(preview_apply_plan_document(load_plan_document(Path(args.preview_apply))))
    elif args.list:
        candidates = scan_daily_notes(through_date=args.through)
        print_candidates(candidates)
    elif args.plan:
        candidates = scan_daily_notes(through_date=args.through)
        if args.out:
            plan = build_plan_document(candidates, args.to)
            write_plan_document(plan, Path(args.out))
            print(f"Wrote carry plan: {args.out}")
        else:
            print(preview_plan(build_default_plan(candidates, args.to)))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

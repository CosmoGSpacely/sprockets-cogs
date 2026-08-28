"""Interactive Cogs carry tooling.

Stage 14.5 starts read-only: list open Cogs blocks that are candidates for
deliberate carry review. Later slices add decisions, previews, and writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

import frontmatter

from specialists.astro.vault import (
    CogsBlock,
    append_cogs_block,
    append_monthly_carry_block,
    append_weekly_carry_block,
    daily_note_path,
    mark_block_state,
    parse_cogs_blocks,
)
from specialists.cogs.naming import monthly_path, weekly_path
from substrate.time_context import expand_bounded_recurrence, resolve_relative_cogs_horizon
from substrate.cog_appearance_registry import (
    CogAppearance,
    CogAppearanceRegistry,
    load_registry,
    save_registry,
)


VAULT_DIR = Path(os.environ.get("SPROCKETS_COGS_VAULT_DIR", str(Path.home() / "vault")))
DAILY_DIR = VAULT_DIR / "Cogs"


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


@dataclass(frozen=True)
class CarryStatus:
    daily_dir: Path
    open_candidates: int
    marked_candidates: int
    oldest_open_date: str
    oldest_marked_date: str


VALID_ACTIONS = {"carry", "cancel", "skip"}
PLAN_VERSION = 1
PLAN_ACTIONS = {"carry", "schedule", "drop", "done", "skip"}
PLAN_ACTIONS_WITH_DESTINATION = {"carry", "schedule"}
EXPLICIT_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
YEAR_RE = re.compile(r"^20\d{2}$")
MONTH_RE = re.compile(r"^(0[1-9]|1[0-2])$")
WEEK_RE = re.compile(r"^\d{2}$")
WEEKLY_STEM_RE = re.compile(r"^(?P<year>20\d{2})-W(?P<week>\d{2})$")
MONTHLY_STEM_RE = re.compile(r"^(?P<year>20\d{2})-(?P<month>0[1-9]|1[0-2])$")


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
    return _scan_daily_notes_for_states(daily_dir, through_date, {" "})


def scan_marked_carry_notes(
    daily_dir: Path = DAILY_DIR,
    through_date: str | None = None,
) -> list[CarryCandidate]:
    """Return manually marked `[>]` Cogs blocks from daily notes through through_date."""
    return _scan_daily_notes_for_states(daily_dir, through_date, {">"})


def _scan_daily_notes_for_states(
    daily_dir: Path,
    through_date: str | None,
    states: set[str],
) -> list[CarryCandidate]:
    if not daily_dir.exists():
        return []

    cutoff = through_date or datetime.now().strftime("%Y-%m-%d")
    datetime.strptime(cutoff, "%Y-%m-%d")

    candidates: list[CarryCandidate] = []
    for path in sorted(daily_dir.rglob("*.md")):
        try:
            date = _date_from_daily_note(path)
        except Exception:
            continue
        if date > cutoff:
            continue
        post = frontmatter.load(str(path))
        for block in parse_cogs_blocks(post.content, states=states):
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


def build_carry_status(
    daily_dir: Path = DAILY_DIR,
    *,
    through_date: str | None = None,
) -> CarryStatus:
    """Return a compact status summary for carry attention."""

    open_candidates = scan_daily_notes(daily_dir, through_date)
    marked_candidates = scan_marked_carry_notes(daily_dir, through_date)
    return CarryStatus(
        daily_dir=daily_dir,
        open_candidates=len(open_candidates),
        marked_candidates=len(marked_candidates),
        oldest_open_date=open_candidates[0].date if open_candidates else "",
        oldest_marked_date=marked_candidates[0].date if marked_candidates else "",
    )


def format_carry_status(status: CarryStatus) -> str:
    lines = [
        "Cogs carry status",
        "- writes: no",
        f"- daily_dir: {status.daily_dir}",
        f"- open candidates: {status.open_candidates}",
        f"- marked carry candidates: {status.marked_candidates}",
        f"- oldest open date: {status.oldest_open_date or 'none'}",
        f"- oldest marked date: {status.oldest_marked_date or 'none'}",
    ]
    return "\n".join(lines)


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


def _candidate_to_plan_item(
    candidate: CarryCandidate,
    destination_date: str,
    *,
    action: str = "carry",
    rule: str = "carry_default",
    reason: str = "open item carried to selected destination",
) -> dict[str, Any]:
    return {
        "id": _candidate_id(candidate),
        "action": action,
        "destination_date": destination_date,
        "rule": rule,
        "reason": reason,
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


def build_smart_plan_document(
    candidates: list[CarryCandidate],
    destination_date: str,
    *,
    reference_date: str | None = None,
) -> dict[str, Any]:
    """Build a selective carry plan with deterministic rule reasons."""

    datetime.strptime(destination_date, "%Y-%m-%d")
    today = reference_date or datetime.now().strftime("%Y-%m-%d")
    datetime.strptime(today, "%Y-%m-%d")
    items: list[dict[str, Any]] = []
    for candidate in candidates:
        item_text = candidate.block.item_text
        recurrence = expand_bounded_recurrence(item_text, today)
        if recurrence:
            first = recurrence[0]
            items.append(
                _candidate_to_plan_item(
                    candidate,
                    first.date,
                    action="schedule",
                    rule="bounded_recurrence_first_occurrence",
                    reason=(
                        f"bounded recurrence expands to {len(recurrence)} occurrence(s); "
                        "carry plan schedules the first occurrence and keeps full expansion in Rosie"
                    ),
                )
            )
            items[-1]["item_text"] = first.item_text
            items[-1]["destination_lines"] = [f"- [ ] {first.item_text}"]
            items[-1]["recurrence_preview"] = [
                {"date": occurrence.date, "item_text": occurrence.item_text}
                for occurrence in recurrence
            ]
            continue

        explicit = EXPLICIT_DATE_RE.search(item_text)
        if explicit and explicit.group(1) > candidate.date:
            items.append(
                _candidate_to_plan_item(
                    candidate,
                    explicit.group(1),
                    action="schedule",
                    rule="explicit_future_date",
                    reason="item text names a future ISO date",
                )
            )
            continue

        relative = resolve_relative_cogs_horizon(item_text, today)
        if relative:
            resolved_date, phrase, horizon = relative
            action = "schedule" if horizon == "day" else "carry"
            items.append(
                _candidate_to_plan_item(
                    candidate,
                    resolved_date if horizon == "day" else destination_date,
                    action=action,
                    rule=f"relative_{horizon}",
                    reason=f"resolved '{phrase}' against {today}",
                )
            )
            items[-1]["resolved_horizon"] = horizon
            continue

        if "?" in item_text or re.search(r"\b(maybe|someday|later)\b", item_text, re.IGNORECASE):
            items.append(
                _candidate_to_plan_item(
                    candidate,
                    "",
                    action="skip",
                    rule="ambiguous_item",
                    reason="ambiguous carry wording requires human decision",
                )
            )
            continue

        items.append(
            _candidate_to_plan_item(
                candidate,
                destination_date,
                action="carry",
                rule="carry_default",
                reason="open item has no safer deterministic destination",
            )
        )
    return {
        "version": PLAN_VERSION,
        "kind": "sprockets-cogs/carry-plan",
        "default_destination_date": destination_date,
        "reference_date": today,
        "items": items,
    }


def write_plan_document(plan: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(plan, indent=2) + "\n")


def load_plan_document(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("carry plan must be a JSON object")
    return raw


def render_obligation_projection_packet(
    *,
    source_path: Path,
    destination_date: str,
    item_text: str,
    reason: str,
) -> str:
    """Render a review-first Sprockets obligation projection packet."""

    datetime.strptime(destination_date, "%Y-%m-%d")
    if not item_text.strip():
        raise ValueError("item_text cannot be empty")
    if not reason.strip():
        raise ValueError("reason cannot be empty")
    return "\n".join([
        "---",
        "packet_type: sprockets-cogs/obligation-projection",
        "status: pending",
        f"source_path: {source_path}",
        f"destination_date: {destination_date}",
        "---",
        "",
        "# Review Cogs Projection",
        "",
        f"- Source Sprocket: `{source_path}`",
        f"- Proposed Cogs date: `{destination_date}`",
        f"- Proposed item: `{item_text.strip()}`",
        f"- Reason: {reason.strip()}",
        "",
        "## Proposed Command",
        "",
        "```json",
        json.dumps(
            {
                "operation": "create_cog",
                "date": destination_date,
                "item_text": item_text.strip(),
                "source_path": str(source_path),
                "reason": reason.strip(),
            },
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
    ])


def write_obligation_projection_packet(
    *,
    source_path: Path,
    destination_date: str,
    item_text: str,
    reason: str,
    out_path: Path,
) -> None:
    """Write a review-first projection packet for Jane/user decision."""

    if not source_path.exists():
        raise ValueError(f"source Sprocket does not exist: {source_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        render_obligation_projection_packet(
            source_path=source_path,
            destination_date=destination_date,
            item_text=item_text,
            reason=reason,
        ),
        encoding="utf-8",
    )


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
        elif destination_date and not isinstance(destination_date, str):
            issues.append(f"{prefix}.destination_date must be a string when present")

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


def check_plan_sources(plan: dict[str, Any]) -> list[str]:
    """Return source staleness/conflict issues for a valid carry plan."""
    issues = validate_plan_document(plan)
    if issues:
        return issues

    source_issues: list[str] = []
    for index, item in enumerate(plan["items"], start=1):
        source = item["source"]
        path = Path(source["path"])
        if not path.exists():
            source_issues.append(f"items[{index}].source.path does not exist: {path}")
            continue

        try:
            post = frontmatter.load(str(path))
        except Exception as exc:
            source_issues.append(f"items[{index}].source.path cannot be read: {path} ({exc})")
            continue

        body_lines = post.content.splitlines()
        start = source["line"] - 1
        expected_lines = item["lines"]
        actual_lines = body_lines[start:start + len(expected_lines)]
        if actual_lines != expected_lines:
            source_issues.append(
                f"items[{index}] source block changed at {path.name}:{source['line']}"
            )

    return source_issues


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
        reason = item.get("reason", "")
        rule = item.get("rule", "")
        suffix = f" [{rule}: {reason}]" if rule or reason else ""
        if action in PLAN_ACTIONS_WITH_DESTINATION:
            lines.append(
                f"[{index}] {action:<8} {source_ref} -> {item['destination_date']}: {item['item_text']}{suffix}"
            )
        else:
            lines.append(f"[{index}] {action:<8} {source_ref}: {item['item_text']}{suffix}")
    return "\n".join(lines)


def preview_apply_plan_document(plan: dict[str, Any]) -> str:
    """Describe the exact vault edits a valid carry plan would make. No writes."""
    issues = check_plan_sources(plan)
    if issues:
        return "Carry plan cannot be applied:\n" + "\n".join(f"- {issue}" for issue in issues)

    items = plan["items"]
    if not items:
        return "No carry actions to apply."

    lines = [f"{len(items)} carry action(s) would be applied"]
    for index, item in enumerate(items, start=1):
        source = item["source"]
        source_ref = f"{source['date']} {Path(source['path']).name}:{source['line']}"
        action = item["action"]
        item_text = item["item_text"]
        reason = item.get("reason", "")
        reason_suffix = f" ({reason})" if reason else ""
        if action == "carry":
            marker = "keep [>]" if item["lines"][0].startswith("- [>]") else "mark [>]"
            lines.append(f"[{index}] {marker} in {source_ref}: {item_text}{reason_suffix}")
            lines.append(f"    append [ ] to {item['destination_date']}: {item_text}")
            lines.extend(_preview_preserved_lines(item))
        elif action == "schedule":
            marker = "keep [>]" if item["lines"][0].startswith("- [>]") else "mark [>]"
            lines.append(f"[{index}] {marker} in {source_ref}: {item_text}{reason_suffix}")
            lines.append(f"    schedule [ ] on {item['destination_date']}: {item_text}")
            lines.extend(_preview_preserved_lines({"lines": item.get("destination_lines", item["lines"])}))
        elif action == "drop":
            lines.append(f"[{index}] mark [-] in {source_ref}: {item_text}{reason_suffix}")
        elif action == "done":
            lines.append(f"[{index}] mark [x] in {source_ref}: {item_text}{reason_suffix}")
        else:
            lines.append(f"[{index}] skip unchanged {source_ref}: {item_text}{reason_suffix}")
    return "\n".join(lines)


def _preview_preserved_lines(item: dict[str, Any]) -> list[str]:
    preserved = item.get("lines", [])[1:]
    if not preserved:
        return []
    lines = ["    preserve:"]
    lines.extend(f"      {line}" for line in preserved)
    return lines


def _find_current_block(content: str, item: dict[str, Any]) -> CogsBlock:
    source = item["source"]
    expected_lines = item["lines"]
    start_line = source["line"] - 1
    for block in parse_cogs_blocks(content, states={" ", ">"}):
        if block.start_line == start_line and list(block.lines) == expected_lines:
            return block
    raise ValueError(f"source block changed at {Path(source['path']).name}:{source['line']}")


def cogs_root_for_source(source_path: Path) -> Path:
    """Return the Cogs root for a flat or nested daily source note."""

    parent = source_path.parent
    if (
        WEEK_RE.match(parent.name)
        and MONTH_RE.match(parent.parent.name)
        and YEAR_RE.match(parent.parent.parent.name)
    ):
        return parent.parent.parent.parent
    return parent


def _cogs_root_containing(source_path: Path) -> Path:
    for parent in (source_path.parent, *source_path.parents):
        if parent.name == "Cogs":
            return parent
    raise ValueError(f"source is not inside a Cogs directory: {source_path}")


def _next_month(value: date) -> date:
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1, day=1)
    return value.replace(month=value.month + 1, day=1)


def _appearance_text_hash(item_text: str) -> str:
    return hashlib.sha256(item_text.strip().encode("utf-8")).hexdigest()[:16]


def _vault_relative(path: Path, cogs_dir: Path) -> str:
    return str(Path("Cogs") / path.resolve().relative_to(cogs_dir.resolve()))


def _surface_period(path: Path) -> tuple[str, str]:
    if weekly := WEEKLY_STEM_RE.match(path.stem):
        return "week", f"{weekly.group('year')}-W{weekly.group('week')}"
    if monthly := MONTHLY_STEM_RE.match(path.stem):
        return "month", f"{monthly.group('year')}-{monthly.group('month')}"
    return "day", _date_from_daily_note(path)


def _registered_cog_id(
    registry: CogAppearanceRegistry,
    *,
    path: str,
    line: int,
    text_hash: str,
) -> str:
    exact = [
        item
        for item in registry.by_path(path)
        if item.line == line and item.text_hash == text_hash
    ]
    if len(exact) == 1:
        return exact[0].cog_id
    hash_matches = [
        item for item in registry.by_path(path) if item.text_hash == text_hash
    ]
    if len(hash_matches) == 1:
        return hash_matches[0].cog_id
    if len(hash_matches) > 1:
        raise ValueError(
            f"appearance registry has {len(hash_matches)} matching items in {path}; "
            "carry refused until the ambiguous locators are repaired"
        )
    return f"cog-{uuid.uuid4().hex}"


def _find_task_line(path: Path, item_text: str) -> int:
    matches = [
        block.start_line + 1
        for block in parse_cogs_blocks(path.read_text(encoding="utf-8"), states={" "})
        if block.item_text.strip() == item_text.strip()
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one open destination item in {path}, found {len(matches)}"
        )
    return matches[0]


def _record_carry_appearances(
    *,
    cogs_dir: Path,
    source_path: Path,
    source_line: int,
    destination_path: Path,
    destination_line: int,
    item_text: str,
    cog_id: str,
) -> int:
    vault_dir = cogs_dir.parent
    registry = load_registry(vault_dir)
    text_hash = _appearance_text_hash(item_text)
    source_surface, source_period = _surface_period(source_path)
    destination_surface, destination_period = _surface_period(destination_path)
    registry.upsert(
        CogAppearance(
            cog_id=cog_id,
            surface=source_surface,
            period=source_period,
            path=_vault_relative(source_path, cogs_dir),
            line=source_line,
            text_hash=text_hash,
            marker="[>]",
            state="carried",
        )
    )
    registry.upsert(
        CogAppearance(
            cog_id=cog_id,
            surface=destination_surface,
            period=destination_period,
            path=_vault_relative(destination_path, cogs_dir),
            line=destination_line,
            text_hash=text_hash,
            marker="[ ]",
            state="open",
        )
    )
    save_registry(vault_dir, registry)
    return len(registry.by_cog(cog_id))


def carry_current_line(source_path: Path, line_number: int) -> str:
    """Carry one open/current task to the next source-appropriate surface.

    ``line_number`` is one-based and refers to the complete Markdown file, as
    reported by an editor. The source text is preserved; only its task marker is
    changed.
    """

    source_path = source_path.resolve()
    if not source_path.is_file():
        raise ValueError(f"source note does not exist: {source_path}")
    cogs_dir = _cogs_root_containing(source_path)
    raw = source_path.read_text(encoding="utf-8")
    target_index = line_number - 1
    block = next(
        (
            item
            for item in parse_cogs_blocks(raw, states={" ", ">"})
            if item.start_line <= target_index <= item.end_line
        ),
        None,
    )
    if block is None:
        raise ValueError(f"line {line_number} is not an open or carried Cogs item")
    registry = load_registry(cogs_dir.parent)
    source_relative = _vault_relative(source_path, cogs_dir)
    text_hash = _appearance_text_hash(block.item_text)
    cog_id = _registered_cog_id(
        registry,
        path=source_relative,
        line=block.start_line + 1,
        text_hash=text_hash,
    )

    daily_date = ""
    try:
        daily_date = _date_from_daily_note(source_path)
    except Exception:
        pass

    if daily_date:
        destination = (datetime.strptime(daily_date, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
        appended = append_cogs_block(destination, block.lines, cogs_dir)
        destination_path = daily_note_path(destination, cogs_dir)
        destination_label = destination
    elif weekly := WEEKLY_STEM_RE.match(source_path.stem):
        monday = datetime.strptime(
            f"{weekly.group('year')}-W{weekly.group('week')}-1", "%G-W%V-%u"
        ).date()
        destination = (monday + timedelta(days=7)).isoformat()
        appended = append_weekly_carry_block(destination, block.lines, cogs_dir)
        destination_path = weekly_path(destination, cogs_dir)
        destination_label = f"{(monday + timedelta(days=7)).isocalendar().year}-W{(monday + timedelta(days=7)).isocalendar().week:02d} CARRY"
    elif monthly := MONTHLY_STEM_RE.match(source_path.stem):
        current = date(int(monthly.group("year")), int(monthly.group("month")), 1)
        destination_month = _next_month(current)
        appended = append_monthly_carry_block(destination_month.isoformat(), block.lines, cogs_dir)
        destination_path = monthly_path(destination_month.isoformat(), cogs_dir)
        destination_label = f"{destination_month:%Y-%m} CARRY"
    else:
        raise ValueError(
            "current-line carry supports Day, Week, and Month source notes; "
            f"unsupported source: {source_path.name}"
        )

    if block.state != ">":
        source_path.write_text(mark_block_state(raw, block, ">"), encoding="utf-8")
    destination_line = _find_task_line(destination_path, block.item_text)
    appearance_count = _record_carry_appearances(
        cogs_dir=cogs_dir,
        source_path=source_path,
        source_line=block.start_line + 1,
        destination_path=destination_path,
        destination_line=destination_line,
        item_text=block.item_text,
        cog_id=cog_id,
    )
    verb = "appended" if appended else "already existed"
    return (
        f"carried {source_path.name}:{line_number} -> {destination_label} "
        f"({verb}; {appearance_count} registered appearances; {cog_id}): {block.item_text}"
    )


def appearance_summary_for_line(source_path: Path, line_number: int) -> str:
    """Report registered appearances for one current Markdown task."""

    source_path = source_path.resolve()
    if not source_path.is_file():
        raise ValueError(f"source note does not exist: {source_path}")
    cogs_dir = _cogs_root_containing(source_path)
    block = next(
        (
            item
            for item in parse_cogs_blocks(
                source_path.read_text(encoding="utf-8"),
                states={" ", ">", "x", "-"},
            )
            if item.start_line <= line_number - 1 <= item.end_line
        ),
        None,
    )
    if block is None:
        raise ValueError(f"line {line_number} is not a Cogs item")
    registry = load_registry(cogs_dir.parent)
    path = _vault_relative(source_path, cogs_dir)
    cog_id = _registered_cog_id(
        registry,
        path=path,
        line=block.start_line + 1,
        text_hash=_appearance_text_hash(block.item_text),
    )
    appearances = registry.by_cog(cog_id)
    if not appearances:
        return f"No registered appearances for {source_path.name}:{line_number}."
    lines = [f"{len(appearances)} registered appearance(s) for {cog_id}"]
    lines.extend(
        f"- {item.state}: {item.surface} {item.period} {item.path}:{item.line or '?'}"
        for item in appearances
    )
    return "\n".join(lines)


def apply_plan_document(plan: dict[str, Any]) -> list[str]:
    """Apply a validated carry plan to the vault."""
    issues = check_plan_sources(plan)
    if issues:
        raise ValueError("Carry plan cannot be applied:\n" + "\n".join(issues))

    results: list[str] = []
    for index, item in enumerate(plan["items"], start=1):
        source = item["source"]
        source_path = Path(source["path"])
        post = frontmatter.load(str(source_path))
        content = post.content
        action = item["action"]
        item_text = item["item_text"]

        if action == "skip":
            results.append(f"[{index}] skipped {source_path.name}:{source['line']}: {item_text}")
            continue

        block = _find_current_block(content, item)
        if action in {"carry", "schedule"}:
            post.content = mark_block_state(content, block, ">")
            source_path.write_text(frontmatter.dumps(post))
            destination_lines = item.get("destination_lines", item["lines"])
            appended = append_cogs_block(
                item["destination_date"],
                tuple(destination_lines),
                cogs_root_for_source(source_path),
            )
            verb = "appended" if appended else "already existed"
            results.append(
                f"[{index}] carried {source_path.name}:{source['line']} -> "
                f"{item['destination_date']} ({verb}): {item_text}"
            )
        elif action == "drop":
            post.content = mark_block_state(content, block, "-")
            source_path.write_text(frontmatter.dumps(post))
            results.append(f"[{index}] dropped {source_path.name}:{source['line']}: {item_text}")
        elif action == "done":
            post.content = mark_block_state(content, block, "x")
            source_path.write_text(frontmatter.dumps(post))
            results.append(f"[{index}] done {source_path.name}:{source['line']}: {item_text}")

    return results


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


def normalize_cli_args(argv: Sequence[str] | None) -> list[str] | None:
    """Map product-shaped carry subcommands onto the legacy flag parser."""

    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw:
        return raw
    command = raw[0]
    rest = raw[1:]
    if command == "status":
        return ["--status", *rest]
    if command == "plan":
        if "--smart" in rest:
            rest = [item for item in rest if item != "--smart"]
            return ["--smart-plan", *rest]
        return ["--plan", *rest]
    if command == "preview-plan":
        if not rest:
            return ["--preview-plan", ""]
        return ["--preview-plan", rest[0], *rest[1:]]
    if command == "preview-apply":
        if not rest:
            return ["--preview-apply", ""]
        return ["--preview-apply", rest[0], *rest[1:]]
    if command == "check-plan":
        if not rest:
            return ["--check-plan", ""]
        return ["--check-plan", rest[0], *rest[1:]]
    if command == "apply-plan":
        if not rest:
            return ["--apply", ""]
        return ["--apply", rest[0], *rest[1:]]
    if command == "current":
        return ["--current", *rest]
    if command == "appearances":
        return ["--appearances", *rest]
    return raw if argv is not None else None


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--current",
        type=Path,
        default=None,
        help="Carry one Cogs task from this source note to its next Day, Week, or Month surface.",
    )
    parser.add_argument(
        "--line",
        type=int,
        default=None,
        help="One-based editor line for --current.",
    )
    parser.add_argument(
        "--appearances",
        type=Path,
        default=None,
        help="Report registered appearances for a Cogs task in this source note.",
    )
    parser.add_argument(
        "--daily-dir",
        type=Path,
        default=DAILY_DIR,
        help="Cogs daily directory to scan or write. Defaults to the configured vault Cogs directory.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Report carry candidate status. Read-only; no vault writes.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Report open carry candidates. Read-only; no vault writes.",
    )
    parser.add_argument(
        "--marked-list",
        action="store_true",
        help="Report manually marked [>] carry candidates. Read-only; no vault writes.",
    )
    parser.add_argument(
        "--through",
        default=None,
        help="YYYY-MM-DD cutoff for scanned daily notes. Defaults to today. Read-only unless used with --apply.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Preview a carry-all plan. Read-only unless paired with --out.",
    )
    parser.add_argument(
        "--smart-plan",
        action="store_true",
        help="Preview a selective carry plan with deterministic rule reasons. Read-only unless paired with --out.",
    )
    parser.add_argument(
        "--marked-plan",
        action="store_true",
        help="Preview a plan from manually marked [>] carry candidates. Read-only unless paired with --out.",
    )
    parser.add_argument(
        "--to",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Destination date for --plan carry decisions. Defaults to today. Used for preview/plan generation only.",
    )
    parser.add_argument(
        "--reference-date",
        default=None,
        help="YYYY-MM-DD date used to resolve smart-plan relative language. Defaults to today.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write --plan output to an editable JSON plan file. Writes only the requested plan file; no vault writes.",
    )
    parser.add_argument(
        "--validate-plan",
        default=None,
        help="Validate an editable JSON carry plan file. Read-only; exits nonzero if invalid.",
    )
    parser.add_argument(
        "--preview-plan",
        default=None,
        help="Preview an editable JSON carry plan file. Read-only; no vault writes.",
    )
    parser.add_argument(
        "--preview-apply",
        default=None,
        help="Preview exact edits from a JSON carry plan file. Read-only; no vault writes.",
    )
    parser.add_argument(
        "--check-plan",
        default=None,
        help="Check that source blocks in a JSON carry plan still match the vault. Read-only; exits nonzero on mismatch.",
    )
    parser.add_argument(
        "--apply",
        default=None,
        help="Apply a JSON carry plan to the vault after validation and source checks. Writes Cogs daily notes.",
    )
    parser.add_argument(
        "--project-obligation",
        type=Path,
        default=None,
        help="Write a review-first Sprockets obligation projection packet for this source Sprocket.",
    )
    parser.add_argument(
        "--item-text",
        default="",
        help="Projected Cogs item text for --project-obligation.",
    )
    parser.add_argument(
        "--reason",
        default="",
        help="Projection reason for --project-obligation.",
    )
    args = parser.parse_args(normalize_cli_args(argv))

    if args.appearances:
        if args.line is None or args.line < 1:
            parser.error("--appearances requires --line with a positive one-based line number")
        try:
            print(appearance_summary_for_line(args.appearances, args.line))
        except ValueError as exc:
            print(exc)
            raise SystemExit(1) from exc
    elif args.current:
        if args.line is None or args.line < 1:
            parser.error("--current requires --line with a positive one-based line number")
        try:
            print(carry_current_line(args.current, args.line))
        except ValueError as exc:
            print(exc)
            raise SystemExit(1) from exc
    elif args.status:
        print(format_carry_status(build_carry_status(args.daily_dir, through_date=args.through)))
    elif args.validate_plan:
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
    elif args.check_plan:
        issues = check_plan_sources(load_plan_document(Path(args.check_plan)))
        if issues:
            print("Carry plan source check failed:")
            for issue in issues:
                print(f"- {issue}")
            raise SystemExit(1)
        print("Carry plan sources match the vault.")
    elif args.apply:
        try:
            results = apply_plan_document(load_plan_document(Path(args.apply)))
        except ValueError as exc:
            print(exc)
            raise SystemExit(1) from exc
        print("\n".join(results) if results else "No carry actions applied.")
    elif args.project_obligation:
        if not args.out:
            parser.error("--project-obligation requires --out")
        if not args.item_text:
            parser.error("--project-obligation requires --item-text")
        if not args.reason:
            parser.error("--project-obligation requires --reason")
        try:
            write_obligation_projection_packet(
                source_path=args.project_obligation,
                destination_date=args.to,
                item_text=args.item_text,
                reason=args.reason,
                out_path=Path(args.out),
            )
        except ValueError as exc:
            print(exc)
            raise SystemExit(1) from exc
        print(f"Wrote obligation projection packet: {args.out}")
    elif args.list:
        candidates = scan_daily_notes(args.daily_dir, through_date=args.through)
        print_candidates(candidates)
    elif args.marked_list:
        candidates = scan_marked_carry_notes(args.daily_dir, through_date=args.through)
        print_candidates(candidates)
    elif args.plan:
        candidates = scan_daily_notes(args.daily_dir, through_date=args.through)
        if args.out:
            plan = build_plan_document(candidates, args.to)
            write_plan_document(plan, Path(args.out))
            print(f"Wrote carry plan: {args.out}")
        else:
            print(preview_plan(build_default_plan(candidates, args.to)))
    elif args.smart_plan:
        candidates = scan_daily_notes(args.daily_dir, through_date=args.through)
        plan = build_smart_plan_document(
            candidates,
            args.to,
            reference_date=args.reference_date,
        )
        if args.out:
            write_plan_document(plan, Path(args.out))
            print(f"Wrote smart carry plan: {args.out}")
        else:
            print(preview_plan_document(plan))
    elif args.marked_plan:
        candidates = scan_marked_carry_notes(args.daily_dir, through_date=args.through)
        plan = build_plan_document(candidates, args.to)
        if args.out:
            write_plan_document(plan, Path(args.out))
            print(f"Wrote carry plan: {args.out}")
        else:
            print(preview_apply_plan_document(plan))
    else:
        parser.error(
            "choose --list, --plan, --status, --smart-plan, --marked-list, --marked-plan, "
            "--validate-plan, --preview-plan, --preview-apply, --check-plan, --apply, "
            "--current, --appearances, or --project-obligation"
        )


if __name__ == "__main__":
    main()

"""Correction command parsing and safe Cogs correction helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from specialists.astro.vault import (
    CorrectionResult,
    append_cogs_item_text,
    daily_note_path,
    mark_blocks_corrected_by_text,
    replace_open_cog_text,
)


MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

TEXT_CORRECTION_RE = re.compile(r"^\s*(?P<new>.+?)\s+not\s+(?P<old>.+?)\s*$", re.IGNORECASE)
MOVE_RANGE_RE = re.compile(
    r"^\s*remove\s+(?P<label>.+?)\s+"
    r"(?P<old_month>[A-Za-z]+)\s+(?P<old_start>\d{1,2})\s*-\s*(?P<old_end>\d{1,2})"
    r"\s*,?\s*(?:it'?s|it\s+is)\s+"
    r"(?P<new_month>[A-Za-z]+)\s+(?P<new_start>\d{1,2})\s*-\s*(?P<new_end>\d{1,2})\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedCorrection:
    kind: str
    old_text: str = ""
    new_text: str = ""
    label: str = ""
    old_start: str = ""
    old_end: str = ""
    new_start: str = ""
    new_end: str = ""


def parse_correction_command(text: str, source_date: str) -> ParsedCorrection | None:
    """Parse narrow correction/removal commands used by the pilot loop."""

    move_match = MOVE_RANGE_RE.match(text.strip())
    if move_match:
        year = datetime.strptime(source_date, "%Y-%m-%d").year
        old_start, old_end = _month_range(
            year,
            move_match.group("old_month"),
            move_match.group("old_start"),
            move_match.group("old_end"),
        )
        new_start, new_end = _month_range(
            year,
            move_match.group("new_month"),
            move_match.group("new_start"),
            move_match.group("new_end"),
        )
        return ParsedCorrection(
            kind="move_date_range",
            label=move_match.group("label").strip(),
            old_start=old_start,
            old_end=old_end,
            new_start=new_start,
            new_end=new_end,
        )

    text_match = TEXT_CORRECTION_RE.match(text.strip())
    if text_match:
        return ParsedCorrection(
            kind="replace_text",
            old_text=text_match.group("old").strip(),
            new_text=text_match.group("new").strip(),
        )

    return None


def apply_correction_command(
    correction: ParsedCorrection,
    daily_dir: Path,
) -> CorrectionResult:
    """Apply a parsed correction command to Cogs daily notes."""

    if correction.kind == "replace_text":
        return replace_open_cog_text(correction.old_text, correction.new_text, daily_dir)
    if correction.kind == "move_date_range":
        return move_date_range(
            correction.label,
            correction.old_start,
            correction.old_end,
            correction.new_start,
            correction.new_end,
            daily_dir,
        )
    return CorrectionResult("review", f"unsupported correction kind {correction.kind!r}")


def move_date_range(
    label: str,
    old_start: str,
    old_end: str,
    new_start: str,
    new_end: str,
    daily_dir: Path,
) -> CorrectionResult:
    """Mark old date-range Cogs corrected and add the label to the new range."""

    old_dates = list(_date_range(old_start, old_end))
    new_dates = list(_date_range(new_start, new_end))
    item_text = label.strip().upper()
    changed = 0
    for date_iso in old_dates:
        path = daily_note_path(date_iso, daily_dir)
        if path.exists():
            changed += mark_blocks_corrected_by_text(path, item_text, f"moved to {new_start}..{new_end}")
    for date_iso in new_dates:
        append_cogs_item_text(date_iso, item_text, daily_dir)
    return CorrectionResult(
        "corrected",
        f"moved {item_text!r} from {old_start}..{old_end} to {new_start}..{new_end}; old entries corrected={changed}",
        source_path=daily_note_path(old_start, daily_dir),
        target_path=daily_note_path(new_start, daily_dir),
    )


def _month_range(year: int, month_name: str, start_day: str, end_day: str) -> tuple[str, str]:
    month = MONTHS[month_name.lower()]
    start = datetime(year, month, int(start_day)).date().isoformat()
    end = datetime(year, month, int(end_day)).date().isoformat()
    return start, end


def _date_range(start: str, end: str):
    current = datetime.strptime(start, "%Y-%m-%d").date()
    final = datetime.strptime(end, "%Y-%m-%d").date()
    while current <= final:
        yield current.isoformat()
        current += timedelta(days=1)

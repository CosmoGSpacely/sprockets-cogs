"""Deterministic runtime date context for ordinary capture."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Mapping, Sequence


WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

_NEXT_WEEKDAY_RE = re.compile(
    r"\bnext\s+("
    r"mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?"
    r")\b",
    re.IGNORECASE,
)
_BARE_WEEKDAY_RE = re.compile(
    r"\b("
    r"mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?"
    r")\b",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(
    r"\bin\s+(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?P<unit>days?|weeks?|months?)\b",
    re.IGNORECASE,
)
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


@dataclass(frozen=True)
class RuntimeDateDecision:
    """A deterministic date correction applied before validation."""

    index: int
    original_date: str
    resolved_date: str
    phrase: str
    horizon: str = "day"


def parse_iso_date(value: str) -> date:
    """Parse a YYYY-MM-DD date string."""

    return datetime.strptime(value, "%Y-%m-%d").date()


def resolve_relative_date(text: str, processing_date: str) -> tuple[str, str] | None:
    """Return `(date_iso, phrase)` when text has a supported relative date."""

    resolved = resolve_relative_cogs_horizon(text, processing_date)
    if not resolved:
        return None
    return resolved[0], resolved[1]


def resolve_relative_cogs_horizon(text: str, processing_date: str) -> tuple[str, str, str] | None:
    """Return `(date_iso, phrase, horizon)` for Cogs relative-date language."""

    source = parse_iso_date(processing_date)
    lowered = text.lower()

    if re.search(r"\b(today|tonight|this morning|this afternoon|this evening)\b", lowered):
        return source.isoformat(), "today", "day"
    if re.search(r"\btomorrow\b", lowered):
        return (source + timedelta(days=1)).isoformat(), "tomorrow", "day"

    if re.search(r"\bthis\s+weekend\b", lowered):
        target_weekday = 6 if re.search(r"\bsun(?:day)?\b", lowered) else 5
        days = (target_weekday - source.weekday()) % 7
        return (source + timedelta(days=days)).isoformat(), "this weekend", "day"

    if re.search(r"\bnext\s+weekend\b", lowered):
        start_of_week = source - timedelta(days=source.weekday())
        saturday_next_week = start_of_week + timedelta(days=12)
        return saturday_next_week.isoformat(), "next weekend", "day"

    if re.search(r"\b(next|this)\s+week\b", lowered):
        return source.isoformat(), "next week" if "next week" in lowered else "this week", "week"

    if re.search(r"\b(next|upcoming)\s+month\b", lowered):
        return _add_months(source.replace(day=1), 1).isoformat(), "next month", "month"

    if re.search(r"\b(this|later\s+this)\s+month\b", lowered):
        phrase = "later this month" if "later this month" in lowered else "this month"
        return source.replace(day=1).isoformat(), phrase, "month"

    duration_match = _DURATION_RE.search(lowered)
    if duration_match:
        count = _duration_count(duration_match.group("count"))
        unit = duration_match.group("unit").lower()
        if unit.startswith("day"):
            return (source + timedelta(days=count)).isoformat(), duration_match.group(0), "day"
        if unit.startswith("week"):
            return (source + timedelta(weeks=count)).isoformat(), duration_match.group(0), "day"
        return _add_months(source, count).isoformat(), duration_match.group(0), "month"

    next_match = _NEXT_WEEKDAY_RE.search(lowered)
    if next_match:
        weekday = WEEKDAYS[_normalize_weekday(next_match.group(1))]
        days = (weekday - source.weekday()) % 7
        if days == 0:
            days = 7
        return (source + timedelta(days=days)).isoformat(), f"next {next_match.group(1).lower()}", "day"

    bare_match = _BARE_WEEKDAY_RE.search(lowered)
    if bare_match:
        weekday = WEEKDAYS[_normalize_weekday(bare_match.group(1))]
        days = (weekday - source.weekday()) % 7
        return (source + timedelta(days=days)).isoformat(), bare_match.group(1).lower(), "day"

    return None


def apply_runtime_date_context(
    raw_nodes: Sequence[Mapping[str, object]],
    classified: Sequence[Mapping[str, object]],
    processing_date: str,
) -> tuple[list[dict], list[RuntimeDateDecision]]:
    """
    Resolve supported relative dates on cogs/daily nodes before validation.

    The classifier can still choose types and item text, but obvious relative
    date words are resolved from the runtime processing date. This prevents the
    local model from writing an event to a stale model-relative day.
    """

    result = [dict(node) for node in classified]
    decisions: list[RuntimeDateDecision] = []
    for index, node in enumerate(result):
        if node.get("node_type") != "cogs/daily":
            continue
        texts = [
            _string(raw_nodes[index].get("raw")) if index < len(raw_nodes) else "",
            _string(node.get("item_text")),
            _string(node.get("title")),
        ]
        resolved = resolve_relative_cogs_horizon(" ".join(texts), processing_date)
        if not resolved:
            continue
        resolved_date, phrase, horizon = resolved
        original = _string(node.get("date"))
        original_horizon = _string(node.get("horizon")) or "day"
        if original == resolved_date and original_horizon == horizon:
            continue
        node["date"] = resolved_date
        if horizon != "day":
            node["horizon"] = horizon
        elif "horizon" in node:
            node.pop("horizon", None)
        decisions.append(
            RuntimeDateDecision(
                index=index,
                original_date=original,
                resolved_date=resolved_date,
                phrase=phrase,
                horizon=horizon,
            )
        )
    return result, decisions


def _normalize_weekday(value: str) -> str:
    lower = value.lower()
    for name, weekday in WEEKDAYS.items():
        if lower == name:
            return name
        if name.startswith(lower) and len(lower) >= 3:
            return name
    raise KeyError(value)


def _duration_count(value: str) -> int:
    return int(value) if value.isdigit() else _NUMBER_WORDS[value.lower()]


def _add_months(value: date, count: int) -> date:
    month_index = value.month - 1 + count
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""

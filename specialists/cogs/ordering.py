"""Planner-order helpers for Cogs daily and weekly surfaces."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


_TIME_RE = re.compile(r"\b(?P<hour>1[0-2]|[1-9])(?P<minute>:[0-5]\d)?(?P<suffix>[ap])\b", re.IGNORECASE)
_SPAN_RE = re.compile(
    r"\b(?P<start>(?:1[0-2]|[1-9])(?:\:[0-5]\d)?[ap])-"
    r"(?P<end>(?:1[0-2]|[1-9])(?:\:[0-5]\d)?[ap])\b",
    re.IGNORECASE,
)

_DAYPARTS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\b(breakfast|early morning)\b", re.IGNORECASE), 8 * 60),
    (re.compile(r"\b(morning)\b", re.IGNORECASE), 9 * 60),
    (re.compile(r"\b(lunch|midday|noon)\b", re.IGNORECASE), 12 * 60),
    (re.compile(r"\b(afternoon)\b", re.IGNORECASE), 15 * 60),
    (re.compile(r"\b(dinner|supper)\b", re.IGNORECASE), 18 * 60),
    (re.compile(r"\b(evening)\b", re.IGNORECASE), 19 * 60),
    (re.compile(r"\b(night|tonight)\b", re.IGNORECASE), 21 * 60),
)
_BUSINESS_HOURS_RE = re.compile(r"\b(call|phone|bank|post office|pharmacy|doctor|dentist)\b", re.IGNORECASE)
_ERRAND_RE = re.compile(r"\b(store|market|walmart|napa|harbor freight|grocery|errand|pickup|pick up)\b", re.IGNORECASE)
_RISK_ORDER_RE = re.compile(
    r"\b(before|after|deadline|due|surgery|medication|medicine|flight|airport|filing|submit)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, order=True)
class PlannerSortKey:
    """Stable planner sort key: bucket, minute, original index."""

    bucket: int
    minute: int
    index: int


def planner_sort_key(item_text: str, index: int = 0) -> PlannerSortKey:
    """Return a light Cogs planner-order key for one item."""

    span = _SPAN_RE.search(item_text)
    if span:
        return PlannerSortKey(0, _time_to_minutes(span.group("start")), index)

    explicit = _TIME_RE.search(item_text)
    if explicit:
        return PlannerSortKey(0, _time_to_minutes(explicit.group(0)), index)

    for pattern, minute in _DAYPARTS:
        if pattern.search(item_text):
            return PlannerSortKey(1, minute, index)

    if _BUSINESS_HOURS_RE.search(item_text):
        return PlannerSortKey(1, 13 * 60, index)
    if _ERRAND_RE.search(item_text):
        return PlannerSortKey(1, 14 * 60, index)
    return PlannerSortKey(9, 24 * 60, index)


def sort_cogs_items(items: Iterable[str]) -> list[str]:
    """Sort Cogs item text by planner order while preserving stable ties."""

    indexed = list(enumerate(items))
    return [item for index, item in sorted(indexed, key=lambda pair: planner_sort_key(pair[1], pair[0]))]


def ordering_needs_review(item_text: str) -> bool:
    """Return true when ordering language implies consequence or dependency."""

    return bool(_RISK_ORDER_RE.search(item_text))


def _time_to_minutes(token: str) -> int:
    match = _TIME_RE.search(token)
    if not match:
        return 24 * 60
    hour = int(match.group("hour")) % 12
    if match.group("suffix").lower() == "p":
        hour += 12
    minute_text = match.group("minute") or ":00"
    return hour * 60 + int(minute_text[1:])

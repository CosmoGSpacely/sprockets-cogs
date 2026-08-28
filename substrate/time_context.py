"""Deterministic runtime date context for ordinary capture."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Mapping, Sequence

from substrate.format import normalize_cogs_time_text


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
_WEEKS_FROM_WEEKDAY_RE = re.compile(
    r"\b(?P<count>a|an|one|two|three|four)\s+weeks?\s+from\s+(?P<weekday>"
    r"mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?"
    r")\b",
    re.IGNORECASE,
)
#: An explicit YYYY-MM-DD already in the text. More specific than any weekday
#: word beside it, so it suppresses the weekday branches (finding 56).
_EXPLICIT_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
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

_TIME_TEXT = r"(?:1[0-2]|0?[1-9])(?:\:[0-5]\d)?\s*[ap]\.?\s*m?\.?"
_RECURRENCE_WEEKDAY = (
    r"mon(?:day)?s?|tue(?:s|sdays?)?|wed(?:nesday)?s?|"
    r"thu(?:r|rs|rsday)?s?|fri(?:day)?s?|sat(?:urday)?s?|sun(?:day)?s?"
)
_NEXT_COUNT_WEEKDAY_RE = re.compile(
    rf"^\s*(?P<label>.+?)\s+next\s+"
    rf"(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    rf"(?P<weekday>{_RECURRENCE_WEEKDAY})\s+at\s+(?P<time>{_TIME_TEXT})\s*$",
    re.IGNORECASE,
)
_TIME_FIRST_NEXT_COUNT_WEEKDAY_RE = re.compile(
    rf"^\s*(?P<label>.+?)\s+(?:is\s+)?(?P<time>{_TIME_TEXT})\s+"
    rf"(?:the\s+)?next\s+"
    rf"(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    rf"(?P<weekday>{_RECURRENCE_WEEKDAY})\s*$",
    re.IGNORECASE,
)
_EVERY_WEEKDAY_FOR_RE = re.compile(
    rf"^\s*(?P<label>.+?)\s+every\s+(?P<weekday>{_RECURRENCE_WEEKDAY})\s+"
    rf"for\s+(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    rf"weeks?\s+at\s+(?P<time>{_TIME_TEXT})\s*$",
    re.IGNORECASE,
)
_MULTI_WEEKDAY_FOR_RE = re.compile(
    rf"^\s*(?P<label>.+?)\s+(?P<weekdays>{_RECURRENCE_WEEKDAY}"
    rf"(?:\s*(?:,|and)\s*{_RECURRENCE_WEEKDAY})+)\s+for\s+"
    rf"(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    rf"weeks?\s+at\s+(?P<time>{_TIME_TEXT})\s*$",
    re.IGNORECASE,
)
MAX_BOUNDED_RECURRENCE_OCCURRENCES = 16


@dataclass(frozen=True)
class RuntimeDateDecision:
    """A deterministic date correction applied before validation."""

    index: int
    original_date: str
    resolved_date: str
    phrase: str
    horizon: str = "day"


@dataclass(frozen=True)
class BoundedRecurrenceOccurrence:
    """One deterministic occurrence generated from bounded recurrence text."""

    date: str
    item_text: str


@dataclass(frozen=True)
class BoundedRecurrenceDecision:
    """A bounded recurrence expansion applied before recurrence review."""

    index: int
    phrase: str
    occurrence_count: int


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

    # Must precede the weekday branches below. Both of those match the bare
    # weekday inside "a week from Friday" and silently discard the offset,
    # which turned a one-day model miss into a seven-day error (finding 43).
    weeks_from = _WEEKS_FROM_WEEKDAY_RE.search(lowered)
    if weeks_from:
        weekday = WEEKDAYS[_normalize_weekday(weeks_from.group("weekday"))]
        count = _NUMBER_WORDS.get(weeks_from.group("count").lower(), 1)
        days = (weekday - source.weekday()) % 7
        return (
            (source + timedelta(days=days, weeks=count)).isoformat(),
            weeks_from.group(0),
            "day",
        )

    next_match = _NEXT_WEEKDAY_RE.search(lowered)
    if next_match:
        # "next Saturday" is the SECOND Saturday after today, not the first.
        # Doctrine set by the product owner 2026-08-28 and applied uniformly to
        # every weekday: the bare weekday means the next occurrence, and the
        # "next" qualifier adds a further week. Before this, both resolved
        # identically and the qualifier was silently discarded (finding 48),
        # which booked the user a week early.
        weekday = WEEKDAYS[_normalize_weekday(next_match.group(1))]
        days = (weekday - source.weekday()) % 7
        if days == 0:
            days = 7
        return (
            (source + timedelta(days=days, weeks=1)).isoformat(),
            f"next {next_match.group(1).lower()}",
            "day",
        )

    # Only the BARE weekday steps aside for an explicit date. Extract emits
    # both signals together in two different shapes and they need opposite
    # precedence (finding 56, corrected in 3e-fix):
    #
    #   "YOGA Saturday 2026-06-21"        bare word + date -> the date wins,
    #       because "Saturday" is generic and matching it collapses every
    #       occurrence in a series onto one day.
    #   "Dentist next Tuesday (2027-01-05)"  qualified phrase + date -> the
    #       phrase wins, because it carries meaning the date cannot ("next"
    #       is the second occurrence) and the parenthetical is the model
    #       showing its arithmetic, which is what the resolver exists to
    #       correct.
    #
    # Placing the guard here rather than above the qualified branches is the
    # whole distinction; putting it earlier cost four fixtures.
    if _EXPLICIT_ISO_DATE_RE.search(lowered):
        return None

    bare_match = _BARE_WEEKDAY_RE.search(lowered)
    if bare_match:
        weekday = WEEKDAYS[_normalize_weekday(bare_match.group(1))]
        days = (weekday - source.weekday()) % 7
        return (source + timedelta(days=days)).isoformat(), bare_match.group(1).lower(), "day"

    return None


_MATCH_STOPWORDS = {
    "a", "an", "and", "at", "for", "from", "in", "of", "on", "re", "the", "to",
    "with", "is", "it", "my", "need", "about", "up",
}

#: Below this, an overlap is coincidence rather than evidence of shared origin.
_MATCH_MIN_SCORE = 0.15


def _match_words(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z0-9:]+", text.lower())
        if word not in _MATCH_STOPWORDS
    }


def _match_raw_index(
    node: Mapping[str, object],
    raw_nodes: Sequence[Mapping[str, object]],
) -> int | None:
    """Find the raw item a classified node came from, by content not position.

    `classify_nodes` does not emit one node per raw item: the named-person rule
    yields two, and a multi-day setting yields one per workday. Pairing by index
    therefore reads the wrong item's text as soon as either rule fires, which
    moved a date onto an unrelated node (Stage 139 finding 42).

    Returns None when nothing matches well enough, or when the best two
    candidates tie - both mean "no evidence", and using the node's own text
    alone is safer than guessing between them.
    """

    node_words = _match_words(
        f"{_string(node.get('title'))} {_string(node.get('item_text'))}"
    )
    if not node_words:
        return None

    scored: list[tuple[float, int]] = []
    for index, raw in enumerate(raw_nodes):
        raw_words = _match_words(_string(raw.get("raw")))
        if not raw_words:
            continue
        overlap = node_words & raw_words
        if not overlap:
            continue
        scored.append((len(overlap) / len(node_words | raw_words), index))

    if not scored:
        return None
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    best_score, best_index = scored[0]
    if best_score < _MATCH_MIN_SCORE:
        return None
    if len(scored) > 1 and scored[1][0] == best_score:
        return None
    return best_index


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
        raw_index = _match_raw_index(node, raw_nodes)
        texts = [
            _string(raw_nodes[raw_index].get("raw")) if raw_index is not None else "",
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


def expand_bounded_recurrence(
    text: str,
    processing_date: str,
    *,
    max_occurrences: int = MAX_BOUNDED_RECURRENCE_OCCURRENCES,
) -> list[BoundedRecurrenceOccurrence]:
    """Expand plain bounded Cogs recurrences into dated item occurrences."""

    source = parse_iso_date(processing_date)
    for parser in (
        _expand_multi_weekday_for_weeks,
        _expand_time_first_next_count_weekday,
        _expand_next_count_weekday,
        _expand_every_weekday_for_weeks,
    ):
        occurrences = parser(text, source)
        if occurrences:
            if len(occurrences) > max_occurrences:
                return []
            return occurrences
    return []


def apply_bounded_recurrence_context(
    raw_nodes: Sequence[Mapping[str, object]],
    classified: Sequence[Mapping[str, object]],
    processing_date: str,
) -> tuple[list[dict], list[BoundedRecurrenceDecision]]:
    """Expand safe bounded recurrence Cogs before the recurrence guard."""

    result: list[dict] = []
    decisions: list[BoundedRecurrenceDecision] = []
    for index, node in enumerate(classified):
        if node.get("node_type") != "cogs/daily":
            result.append(dict(node))
            continue
        raw_index = _match_raw_index(node, raw_nodes)
        texts = [
            _string(raw_nodes[raw_index].get("raw")) if raw_index is not None else "",
            _string(node.get("item_text")),
            _string(node.get("title")),
        ]
        phrase = _first_expandable_phrase(texts, processing_date)
        if not phrase:
            result.append(dict(node))
            continue
        occurrences = expand_bounded_recurrence(phrase, processing_date)
        if not occurrences:
            result.append(dict(node))
            continue
        for occurrence in occurrences:
            expanded = dict(node)
            expanded["date"] = occurrence.date
            expanded["item_text"] = occurrence.item_text
            if "title" in expanded:
                expanded["title"] = occurrence.item_text
            expanded.pop("horizon", None)
            expanded["_bounded_recurrence"] = True
            result.append(expanded)
        decisions.append(
            BoundedRecurrenceDecision(
                index=index,
                phrase=phrase,
                occurrence_count=len(occurrences),
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


def _normalize_recurrence_weekday(value: str) -> str:
    lower = value.lower().strip()
    if lower.endswith("sdays"):
        lower = lower[:-1]
    elif lower.endswith("days"):
        lower = lower[:-1]
    elif lower.endswith("s") and lower not in {"tues", "thurs"}:
        lower = lower[:-1]
    return _normalize_weekday(lower)


def _duration_count(value: str) -> int:
    return int(value) if value.isdigit() else _NUMBER_WORDS[value.lower()]


def _add_months(value: date, count: int) -> date:
    month_index = value.month - 1 + count
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def _format_occurrence(label: str, time_text: str) -> str:
    return normalize_cogs_time_text(f"{time_text} {label.strip().upper()}").strip()


def _next_weekday_after(source: date, weekday: int) -> date:
    days = (weekday - source.weekday()) % 7
    if days == 0:
        days = 7
    return source + timedelta(days=days)


def _upcoming_weekday_on_or_after(source: date, weekday: int) -> date:
    return source + timedelta(days=(weekday - source.weekday()) % 7)


def _expand_next_count_weekday(text: str, source: date) -> list[BoundedRecurrenceOccurrence]:
    match = _NEXT_COUNT_WEEKDAY_RE.match(text)
    if not match:
        return []
    count = _duration_count(match.group("count"))
    weekday = WEEKDAYS[_normalize_recurrence_weekday(match.group("weekday"))]
    first = _next_weekday_after(source, weekday)
    item_text = _format_occurrence(match.group("label"), match.group("time"))
    return [
        BoundedRecurrenceOccurrence((first + timedelta(weeks=i)).isoformat(), item_text)
        for i in range(count)
    ]


def _expand_time_first_next_count_weekday(text: str, source: date) -> list[BoundedRecurrenceOccurrence]:
    match = _TIME_FIRST_NEXT_COUNT_WEEKDAY_RE.match(text)
    if not match:
        return []
    count = _duration_count(match.group("count"))
    weekday = WEEKDAYS[_normalize_recurrence_weekday(match.group("weekday"))]
    first = _next_weekday_after(source, weekday)
    item_text = _format_occurrence(match.group("label"), match.group("time"))
    return [
        BoundedRecurrenceOccurrence((first + timedelta(weeks=i)).isoformat(), item_text)
        for i in range(count)
    ]


def _expand_every_weekday_for_weeks(text: str, source: date) -> list[BoundedRecurrenceOccurrence]:
    match = _EVERY_WEEKDAY_FOR_RE.match(text)
    if not match:
        return []
    count = _duration_count(match.group("count"))
    weekday = WEEKDAYS[_normalize_recurrence_weekday(match.group("weekday"))]
    first = _upcoming_weekday_on_or_after(source, weekday)
    item_text = _format_occurrence(match.group("label"), match.group("time"))
    return [
        BoundedRecurrenceOccurrence((first + timedelta(weeks=i)).isoformat(), item_text)
        for i in range(count)
    ]


def _expand_multi_weekday_for_weeks(text: str, source: date) -> list[BoundedRecurrenceOccurrence]:
    tail_match = re.search(
        rf"\s+for\s+(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        rf"weeks?\s+at\s+(?P<time>{_TIME_TEXT})\s*$",
        text,
        re.IGNORECASE,
    )
    if not tail_match:
        return []
    prefix = text[:tail_match.start()].strip()
    weekday_matches = list(re.finditer(_RECURRENCE_WEEKDAY, prefix, re.IGNORECASE))
    if len(weekday_matches) < 2:
        return []
    label = prefix[:weekday_matches[0].start()].strip()
    if not label:
        return []
    count = _duration_count(tail_match.group("count"))
    weekday_names = [match.group(0) for match in weekday_matches]
    weekdays = sorted({WEEKDAYS[_normalize_recurrence_weekday(day)] for day in weekday_names})
    item_text = _format_occurrence(label, tail_match.group("time"))
    week_start = source - timedelta(days=source.weekday())
    occurrences: list[BoundedRecurrenceOccurrence] = []
    for week in range(count):
        for weekday in weekdays:
            occurrence = week_start + timedelta(weeks=week, days=weekday)
            if occurrence < source:
                continue
            occurrences.append(BoundedRecurrenceOccurrence(occurrence.isoformat(), item_text))
    return occurrences


def _first_expandable_phrase(texts: Sequence[str], processing_date: str) -> str:
    for text in texts:
        phrase = text.strip()
        if phrase and expand_bounded_recurrence(phrase, processing_date):
            return phrase
    return ""


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""

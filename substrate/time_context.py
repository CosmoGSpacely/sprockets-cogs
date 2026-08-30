"""Deterministic runtime date context for ordinary capture."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Mapping, Sequence

from substrate.format import normalize_cogs_time_text
from substrate.node_matching import match_raw_index, match_words, raw_text_for


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
#: "the 3rd", "on the 15th". Excludes "the 3rd Saturday", which is an ordinal
#: weekday and means something else entirely (finding 45).
_DAY_OF_MONTH_RE = re.compile(
    r"\bthe\s+(?P<day>\d{1,2})(?:st|nd|rd|th)\b"
    r"(?!\s+(?:mon|tue|wed|thu|fri|sat|sun))",
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

    day_of_month = _DAY_OF_MONTH_RE.search(lowered)
    if day_of_month:
        resolved = _next_day_of_month(source, int(day_of_month.group("day")))
        if resolved is not None:
            return resolved.isoformat(), day_of_month.group(0), "day"

    bare_match = _BARE_WEEKDAY_RE.search(lowered)
    if bare_match:
        weekday = WEEKDAYS[_normalize_weekday(bare_match.group(1))]
        days = (weekday - source.weekday()) % 7
        return (source + timedelta(days=days)).isoformat(), bare_match.group(1).lower(), "day"

    return None


#: Node-to-raw pairing moved to `substrate/node_matching.py` in Stage 142
#: slice 4, when `substrate/format.py` became the third call site (finding 80).
#: Re-exported under the old private names so existing callers here are
#: unchanged.
_match_words = match_words
_match_raw_index = match_raw_index


def states_a_date(text: str, processing_date: str) -> bool:
    """Whether the text names a day at all.

    Stage 142 C8: a task spawns its companion Cog only when the capture stated
    a day, so a dateless standing task is not dumped onto today. That question
    has to be answered from the source text rather than from the node's date
    field, because `normalize_raw_node` fills a missing date with the
    processing date - by which point "stated" and "defaulted" are
    indistinguishable.

    Explicit ISO dates are checked separately: `resolve_relative_cogs_horizon`
    deliberately declines them (it has nothing to resolve), so relying on it
    alone would read "2026-07-03" as stating no date.
    """

    if not text:
        return False
    if _EXPLICIT_ISO_DATE_RE.search(text):
        return True
    return resolve_relative_cogs_horizon(text, processing_date) is not None


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


def _next_day_of_month(source: date, day: int) -> date | None:
    """The next occurrence of a day-of-month, today counting as itself.

    Rolls forward past months that are too short, so "the 31st" in February
    lands on the next month that actually has one rather than erroring or
    silently clamping to the 28th. Returns None for a day no month has.
    """

    if not 1 <= day <= 31:
        return None
    candidate_month = source.replace(day=1)
    for _ in range(13):
        try:
            candidate = candidate_month.replace(day=day)
        except ValueError:
            candidate_month = _add_months(candidate_month, 1)
            continue
        if candidate >= source:
            return candidate
        candidate_month = _add_months(candidate_month, 1)
    return None


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


# ── Multi-day settings (Stage 142 slice 5a) ───────────────────────────────────
#
# Finding 77: `EXTRACT_SYSTEM` and `CLASSIFY_SYSTEM` both instruct the model to
# expand "all next week" into one item per workday, the model does it badly -
# a contiguous 19-day run including weekends on the one fixture that tests it -
# and **no code did it at all**. This is the missing capability. The prompt
# rule can only be removed once this exists, or the behaviour disappears
# entirely, which is exactly what `preserve-extract` demonstrated by emitting
# three nodes where ten belonged.

#: Which week a phrase points at, relative to the capture's week.
_WEEK_OFFSETS = (
    (re.compile(r"\bthe\s+(?:week\s+after\s+next|following\s+week)\b", re.I), 2),
    (re.compile(r"\ball\s+next\s+week\b", re.I), 1),
    (re.compile(r"\bnext\s+week\b", re.I), 1),
    (re.compile(r"\b(?:all|this)\s+week\b", re.I), 0),
)

#: "until Thursday", "through Wed" - truncates the span short of Friday.
_UNTIL_WEEKDAY_RE = re.compile(
    r"\b(?:until|through|thru|to)\s+(?P<weekday>"
    r"mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b",
    re.IGNORECASE,
)

#: A span is workdays unless the text says otherwise. Cosmo's captures are
#: work context ("Full loom", "WFH"), and a weekend in a WFH span is noise the
#: user then has to delete.
WORKDAYS_IN_WEEK = 5


@dataclass(frozen=True)
class MultiDaySpan:
    """One multi-day setting phrase and the dates it covers."""

    phrase: str
    dates: tuple[str, ...]


#: Phrases that make a week reference cover every day in it, rather than name
#: a week to act within. "all next week" spans; a bare "next week" does not.
#: This is the distinction finding 82 turned on - "Call Tom next week" became
#: five daily copies - and slice 5a drew it with `type_hint == "setting"`
#: instead, which finding 86 then showed does not reach a spanning item the
#: model typed as a task.
_SPAN_MARKER_RES = (
    re.compile(r"\ball\s+(?:next\s+|this\s+|the\s+following\s+)?week\b", re.I),
    re.compile(r"\ball\s+(?:day|week)\s+long\b", re.I),
    _UNTIL_WEEKDAY_RE,
)


def states_a_day_span(text: str) -> bool:
    """Whether the text says a week reference covers all of its days.

    The span is a property of the phrase, not of the item's type. "Full loom
    all next week" spans whether the model called it a setting or a task; "Call
    Tom next week" spans under neither.
    """

    return any(pattern.search(text) for pattern in _SPAN_MARKER_RES)


def multi_day_spans(text: str, processing_date: str) -> list[MultiDaySpan]:
    """Every multi-day setting span in the text, in order of appearance.

    A capture can hold more than one - "all next week and the following week
    until Thursday" is two - so this returns a list rather than the first
    match. Each span is independent: they may have different lengths and
    neither constrains the other.
    """

    if not text:
        return []
    try:
        source = parse_iso_date(processing_date)
    except (ValueError, TypeError):
        return []

    this_monday = source - timedelta(days=source.weekday())
    spans: list[MultiDaySpan] = []
    consumed: list[tuple[int, int]] = []

    for pattern, offset in _WEEK_OFFSETS:
        for match in pattern.finditer(text):
            if any(start <= match.start() < end for start, end in consumed):
                continue
            consumed.append((match.start(), match.end()))
            monday = this_monday + timedelta(weeks=offset)
            last = _span_last_weekday(text, match.end())
            dates = tuple(
                (monday + timedelta(days=day)).isoformat()
                for day in range(last + 1)
            )
            if dates:
                spans.append(MultiDaySpan(match.group(0).lower(), dates))

    spans.sort(key=lambda span: text.lower().find(span.phrase))
    return spans


def _span_last_weekday(text: str, from_index: int) -> int:
    """Index of the span's final weekday: 4 (Friday) unless "until X" cuts it.

    Only looks *after* the week phrase, and only as far as the next one, so
    "all next week and the following week until Thursday" does not let the
    Thursday truncate the first span as well.
    """

    tail = text[from_index:]
    for pattern, _ in _WEEK_OFFSETS:
        following = pattern.search(tail)
        if following:
            tail = tail[: following.start()]
    match = _UNTIL_WEEKDAY_RE.search(tail)
    if not match:
        return WORKDAYS_IN_WEEK - 1
    return WEEKDAYS[_normalize_weekday(match.group("weekday"))]


@dataclass(frozen=True)
class MultiDayDecision:
    """One multi-day setting expanded by code rather than by the model."""

    index: int
    phrase: str
    occurrence_count: int


def apply_multi_day_setting_context(
    raw_nodes: Sequence[Mapping[str, object]],
    classified: Sequence[Mapping[str, object]],
    processing_date: str,
) -> tuple[list[dict], list[MultiDayDecision]]:
    """Expand a multi-day setting the model left as a single node.

    **Guarded, deliberately.** Both prompts still instruct the model to expand
    these itself, so this fires only when it did not - otherwise the two would
    compound and produce twice the nodes, which is the failure mode already
    measured at 20 nodes for an expected 10.

    That makes this step inert on most captures today and load-bearing the
    moment slice 6 removes the prompt rule. Landing it live but guarded is
    what stops it being preview code that nothing imports, while keeping the
    capability and the instruction from firing at once.
    """

    result = [dict(node) for node in classified]
    decisions: list[MultiDayDecision] = []

    for index, node in enumerate(list(result)):
        if node.get("node_type") != "cogs/daily":
            continue
        raw_index = match_raw_index(node, raw_nodes)
        if raw_index is None:
            continue
        raw = raw_nodes[raw_index]
        raw_text = _string(raw.get("raw"))
        if not raw_text:
            continue
        # "Full loom all next week" applies to every day; "Call Tom next week"
        # is one action to do sometime that week. A setting always spans its
        # week; anything else must say so (finding 86 - the model typed a
        # spanning item as a task, and keying on the type alone missed it).
        spans_the_days = states_a_day_span(raw_text)
        if _string(raw.get("type_hint")).lower() != "setting" and not spans_the_days:
            continue
        # A week-horizon node is deliberately one item for the whole week -
        # `apply_runtime_date_context` decided that a step earlier, and it goes
        # to the weekly carry. Expanding it would replace one carry entry with
        # five daily copies, which is finding 82.
        #
        # **Unless the text says it covers every day of that week** (finding
        # 95). "all next week" resolves to a week horizon *and* states a span,
        # and the guard silently won - which is why `multi-day-setting-holiday`
        # expanded only its second span, the one whose "until Thursday" made
        # the resolver call it a day horizon. The two signals answer different
        # questions: the horizon says *when to act*, the span says *how many
        # days it covers*.
        if _string(node.get("horizon")) not in ("", "day") and not spans_the_days:
            continue
        spans = multi_day_spans(raw_text, processing_date)
        if not spans:
            continue

        covered = {_string(other.get("date")) for other in result}
        for position, span in enumerate(spans):
            missing = [day for day in span.dates if day not in covered]
            # The model already produced this span: leave it alone rather than
            # topping it up, since a partial overlap more likely means it chose
            # different days than that it stopped early.
            if len(missing) < len(span.dates) - 1:
                continue
            if position == 0:
                # The first span reuses the node, which carries the model's
                # title, item_text and confidence; later spans clone it.
                node["date"] = span.dates[0]
                covered.add(span.dates[0])
            for day in span.dates:
                if day in covered:
                    continue
                clone = dict(node)
                clone["date"] = day
                result.append(clone)
                covered.add(day)
            decisions.append(
                MultiDayDecision(index, span.phrase, len(span.dates))
            )

    return result, decisions

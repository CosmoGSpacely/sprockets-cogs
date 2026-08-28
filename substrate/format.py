"""Cogs item text formatting helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence


TIME_TOKEN_RE = re.compile(
    r"\b(?P<hour>1[0-2]|0?[1-9])(?P<minute>:[0-5]\d)?\s*"
    r"(?P<suffix>[ap])(?:\.?\s*m\.?|\.)?\b",
    re.IGNORECASE,
)
TIME_SPAN_RE = re.compile(
    r"\b(?P<start>(?:1[0-2]|0?[1-9])(?:\:[0-5]\d)?\s*[ap](?:\.?\s*m\.?|\.)?)"
    r"\s*(?:to|through|until|-|–|—)\s*"
    r"(?P<end>(?:1[0-2]|0?[1-9])(?:\:[0-5]\d)?\s*[ap](?:\.?\s*m\.?|\.)?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CogsFormatDecision:
    """A Cogs item text/title normalization applied before validation."""

    index: int
    original_text: str
    formatted_text: str
    reason: str


def format_cogs_time_token(token: str) -> str:
    """Format one time token in the paper Cogs dialect: 10a, 3:30p."""

    match = TIME_TOKEN_RE.fullmatch(token.strip())
    if not match:
        return token
    hour = str(int(match.group("hour")))
    minute = match.group("minute") or ""
    suffix = match.group("suffix").lower()
    return f"{hour}{minute}{suffix}"


def normalize_cogs_time_text(text: str) -> str:
    """Normalize times and spans in free Cogs item text."""

    def span_repl(match: re.Match[str]) -> str:
        return f"{format_cogs_time_token(match.group('start'))}-{format_cogs_time_token(match.group('end'))}"

    text = TIME_SPAN_RE.sub(span_repl, text)
    return TIME_TOKEN_RE.sub(lambda match: format_cogs_time_token(match.group(0)), text)


def cogs_time_span_from_text(text: str) -> str:
    """Return the first normalized Cogs time span from text, or empty string."""

    match = TIME_SPAN_RE.search(text)
    if not match:
        return ""
    return f"{format_cogs_time_token(match.group('start'))}-{format_cogs_time_token(match.group('end'))}"


def apply_cogs_item_format(
    raw_nodes: Sequence[Mapping[str, object]],
    classified: Sequence[Mapping[str, object]],
) -> tuple[list[dict], list[CogsFormatDecision]]:
    """Normalize cogs/daily item text and restore spans visible in raw input."""

    result = [dict(node) for node in classified]
    decisions: list[CogsFormatDecision] = []
    for index, node in enumerate(result):
        if node.get("node_type") != "cogs/daily":
            continue
        raw_text = _string(raw_nodes[index].get("raw")) if index < len(raw_nodes) else ""
        original = _string(node.get("item_text") or node.get("title"))
        if not original:
            continue
        formatted = normalize_cogs_time_text(original)
        raw_span = cogs_time_span_from_text(raw_text)
        if raw_span:
            formatted = _ensure_span(formatted, raw_span)
        formatted = _move_leading_time_to_front(formatted)
        formatted = _strip_cogs_date_locator_residue(formatted)
        if formatted == original:
            continue
        node["item_text"] = formatted
        if _string(node.get("title")) == original or not _string(node.get("title")):
            node["title"] = formatted
        decisions.append(
            CogsFormatDecision(
                index=index,
                original_text=original,
                formatted_text=formatted,
                reason="span" if raw_span else "time",
            )
        )
    return result, decisions


def _ensure_span(text: str, span: str) -> str:
    if span in text:
        return text
    start, _, _end = span.partition("-")
    if start and re.search(rf"\b{re.escape(start)}\b", text):
        return re.sub(rf"\b{re.escape(start)}\b", span, text, count=1)
    return f"{text} {span}".strip()


def _move_leading_time_to_front(text: str) -> str:
    """Move a Cogs time or span token to the front of the item."""

    normalized = text.strip()
    if not normalized:
        return normalized
    token_re = re.compile(r"\b(?P<token>(?:1[0-2]|[1-9])(?:\:[0-5]\d)?[ap](?:-(?:1[0-2]|[1-9])(?:\:[0-5]\d)?[ap])?)\b")
    match = token_re.search(normalized)
    if not match or match.start() == 0:
        return normalized
    token = match.group("token")
    before = normalized[:match.start()].strip()
    after = normalized[match.end():].strip()
    remainder = " ".join(part for part in [before, after] if part)
    return f"{token} {remainder}".strip()


def _strip_cogs_date_locator_residue(text: str) -> str:
    """Remove date words that should locate the Cog, not appear in its label."""

    cleaned = text.strip()
    if not cleaned:
        return cleaned

    cleaned = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", cleaned)
    cleaned = re.sub(
        r"\b(?:today|tonight|tomorrow|this\s+weekend|next\s+weekend|"
        r"this\s+week|next\s+week|this\s+month|later\s+this\s+month|"
        r"next\s+month|upcoming\s+month)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:next\s+)?(?:mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|"
        r"thu(?:r|rs|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(?:at|on|by|for)\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""

"""Raw node normalization before Pydantic validation.

This module owns operational defaults that need context, such as the processing
date. Pydantic models still validate structure; they do not infer "today".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def is_iso_date(value: object) -> bool:
    """Return True when value is a YYYY-MM-DD calendar date string."""

    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def normalize_raw_node(
    raw: Mapping[str, Any],
    *,
    default_cogs_date: str | None = None,
    reject_non_default_cogs_date: bool = False,
) -> dict[str, Any]:
    """
    Return a normalized raw node copy before schema validation.

    For cogs/daily nodes, a missing or empty date is an operational default: use
    the source/processing date supplied by the caller. Explicit dates remain
    explicit unless the caller marks the path as strict, which is useful for
    fallback-generated review candidates that may hallucinate old dates.
    """

    normalized = dict(raw)
    if normalized.get("node_type") != "cogs/daily" or not default_cogs_date:
        return normalized
    if not is_iso_date(default_cogs_date):
        raise ValueError(f"default_cogs_date must be YYYY-MM-DD, got {default_cogs_date!r}")

    raw_date = normalized.get("date")
    date_text = raw_date.strip() if isinstance(raw_date, str) else ""
    if not date_text:
        normalized["date"] = default_cogs_date
        return normalized

    if reject_non_default_cogs_date and date_text != default_cogs_date:
        raise ValueError(
            "suspicious cogs/daily date "
            f"{date_text!r}; expected source/processing date {default_cogs_date!r}"
        )
    return normalized


def review_reason_requires_strict_cogs_date(reason: str) -> bool:
    """Return True for review sources where explicit dates are not trusted."""

    return reason.startswith("openai_fallback_candidate") or reason.startswith("openai_fallback_invalid")

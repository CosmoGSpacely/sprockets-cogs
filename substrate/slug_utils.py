"""Shared slug helpers for filesystem-safe Sprockets-Cogs names."""

from __future__ import annotations

import re


def slugify(text: str, max_length: int = 60) -> str:
    """Return a filesystem-safe slug from a title."""

    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:max_length].strip("-")

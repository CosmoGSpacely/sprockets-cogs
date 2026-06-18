"""Astro owns vault-facing render and manual work surfaces."""

from specialists.catalog import get_specialist

DEFINITION = get_specialist("astro")

__all__ = ["DEFINITION"]

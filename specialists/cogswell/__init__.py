"""Cogswell deterministic collection/database bridge."""

from specialists.catalog import get_specialist

DEFINITION = get_specialist("cogswell")

__all__ = ["DEFINITION"]

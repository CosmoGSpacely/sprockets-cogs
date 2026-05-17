"""Visible Phase 4 specialist map.

The implementation modules still live at the repository root. This package is a
small, importable index for docs, tests, and future status surfaces.
"""

from specialists.catalog import SPECIALISTS, SpecialistDefinition, get_specialist, iter_specialists

__all__ = [
    "SPECIALISTS",
    "SpecialistDefinition",
    "get_specialist",
    "iter_specialists",
]


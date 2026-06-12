"""Visible specialist map and package-owned promotion surfaces.

Legacy implementation modules still exist at repository root, but new promoted
specialist behavior should live inside this package whenever practical.
"""

from specialists.catalog import SPECIALISTS, SpecialistDefinition, get_specialist, iter_specialists

__all__ = [
    "SPECIALISTS",
    "SpecialistDefinition",
    "get_specialist",
    "iter_specialists",
]

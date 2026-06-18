"""Visible specialist map and package-owned agentic boundaries.

Specialist behavior lives in this package. Cross-boundary contracts live in
``substrate/``; root Python modules are not ownership homes.
"""

from specialists.catalog import SPECIALISTS, SpecialistDefinition, get_specialist, iter_specialists

__all__ = [
    "SPECIALISTS",
    "SpecialistDefinition",
    "get_specialist",
    "iter_specialists",
]

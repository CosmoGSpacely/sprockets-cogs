"""Orbit source-normalization boundary.

Orbit is the named agentic boundary for external source adapters. The current
implementation remains in `specialists.adapters`; this facade gives the pattern
a stable name without a disruptive package rename.
"""

from specialists.adapters import rich_inputs, source_surfaces, telegram_polling
from specialists.catalog import get_specialist

DEFINITION = get_specialist("orbit")

__all__ = ["DEFINITION", "rich_inputs", "source_surfaces", "telegram_polling"]

"""Orbit source-normalization boundary.

Orbit is the named agentic boundary for external source adapters. The current
implementation remains in `specialists.adapters`; this facade gives the pattern
a stable name without a disruptive package rename.
"""

from specialists.adapters import rich_inputs, source_surfaces, telegram_polling

__all__ = ["rich_inputs", "source_surfaces", "telegram_polling"]

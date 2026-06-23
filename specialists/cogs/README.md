# Cogs

Cogs is the planning, carry, migration, and time-horizon specialist.

## Responsibility

Cogs owns daily operational items, weekly/monthly/annual planning notes, 5WOW
and 12MF window file logic, carry decisions, and carry reconciliation.

## Runtime Form

Cogs is command-driven. Uniblab/substrate schedules services; Astro owns vault
horizon materialization.

## Current Implementation

- `specialist.py`
- `planning.py`
- `naming.py`
- `format.py`
- `time_context.py`
- `carry.py`
- `nightly.py`
- `scripts/cogs-specialist`
- `scripts/cogs-planning`
- `scripts/carry`
- `scripts/nightly`

## Boundaries

- Planning-note maintenance is not part of Rosie's live input loop.
- Carry/apply workflows should remain previewable and source-checked.
- ISO-first daily naming is preview-first unless explicitly migrated.
- The midnight service is substrate-scheduled; Cogs is the carry handoff, not
  the service owner.

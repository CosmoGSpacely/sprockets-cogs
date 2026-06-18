# Cogs

Cogs is the planning, carry, migration, and time-horizon specialist.

## Responsibility

Cogs owns daily operational items, weekly/monthly/annual planning notes, 5WOW
views, carry decisions, nightly reconciliation, and planning-horizon movement.

## Runtime Form

Cogs is command-driven and scheduled. It does not need to run continuously.

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
- `systemd/user/sprockets-cogs-nightly.service`
- `systemd/user/sprockets-cogs-nightly.timer`

## Boundaries

- Planning-note maintenance is not part of Rosie's live input loop.
- Carry/apply workflows should remain previewable and source-checked.
- ISO-first daily naming is preview-first unless explicitly migrated.

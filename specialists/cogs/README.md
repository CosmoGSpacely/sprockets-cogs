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

## Carry Surface

`scripts/sc carry` is the operator carry surface.

Useful forms:

```bash
scripts/sc carry status
scripts/sc carry plan --smart --to 2026-06-25 --out carry-plan.json
scripts/sc carry preview-plan carry-plan.json
scripts/sc carry preview-apply carry-plan.json
scripts/sc carry apply-plan carry-plan.json
```

Smart carry plans stay deterministic. They add rule/reason fields, schedule
obvious future-dated items, preview bounded recurrence, and skip ambiguous
wording instead of letting a model move Cogs.

Sprockets obligation projection is review-first: Cogs can write a projection
packet for Jane/user approval, but it does not write the projected Cog directly.

## Boundaries

- Planning-note maintenance is not part of Rosie's live input loop.
- Carry/apply workflows should remain previewable and source-checked.
- ISO-first daily naming is preview-first unless explicitly migrated.
- The midnight service is substrate-scheduled; Cogs is the carry handoff, not
  the service owner.

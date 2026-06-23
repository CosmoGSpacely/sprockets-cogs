# Uniblab

Uniblab is the operations, health, status, and readiness specialist.

## Responsibility

Uniblab owns service status, timer status, scheduled service harnesses, local
model checks, embedding model checks, runtime path posture, review count,
backup/sync visibility, and future readiness checks.

## Runtime Form

Uniblab is command-driven for now. It may later gain scheduled health checks if
that proves useful.

## Current Implementation

- `system_status.py`
- `job_status.py`
- `job_supervisor.py`
- `friction.py`
- `scripts/sc`
- `scripts/status`
- `scripts/job-status`
- `scripts/job-supervisor`
- `scripts/friction`
- `scripts/friction-promote`
- `scripts/sc-backup --preview`
- `scripts/sc-backup --status`
- `scripts/sc-backup --create`

## Boundaries

- Uniblab reports and previews operational actions before changing runtime
  state.
- `scripts/sc` is a thin dispatcher. It delegates to owner scripts and does not
  duplicate specialist logic or merge independent services.
- SC backup creation writes only to an explicit or default backup directory; it
  never processes `.input` files or mutates the vault.
- Model warmup and residency policy should be explicit before it becomes
  automated.
- Friction records are operational JSONL outside the vault; they turn repeated
  pilot failures into reviewable fixture, guard, or test candidates.

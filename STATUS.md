# Sprockets-Cogs Status

Sprockets-Cogs is a working local prototype and learning project. It is not yet a
turnkey public application.

## Current Maturity

The project has completed its Phase 2 hardening work, Phase 3 memory groundwork,
and Stage 25 public-readiness MVP:

- typed Sprockets/Cogs writes;
- deterministic smoke test and unit tests;
- review-first fallback behavior;
- semantic memory benchmark harness;
- guarded production retrieval;
- retrieval traces and reports;
- memory tool-call readiness probe;
- public README, design note, license, CI workflow, and sensitive-data audit.
- Stage 26 planning-note maintenance helpers for current weekly/monthly/annual
  notes.

## Current Runtime Posture

- The service runs the file-based `agentic_loop.py` watcher.
- Local classification uses the configured Ollama model.
- OpenAI fallback is review-first when configured.
- Semantic memory retrieval can be enabled for compact post-classification guards.
- Prompt-appended memory context remains disabled.
- Nightly Cogs carry exists as a script but is not scheduled by the service.
- `scripts/cogs-planning` previews Stage 26 naming choices, planning inventory,
  monthly seven-day calendar grids plus vertical 5WOW tables,
  weekly/monthly/annual templates, planning-note creation plans, and daily
  rename plans without writing to the vault.
- `scripts/cogs-planning --create ... --kind ...` can create missing planning
  notes and refuses to overwrite existing files.
- `scripts/cogs-planning --ensure-current` creates the current weekly, monthly,
  and annual planning notes when missing and preserves existing files.
- `scripts/job-status` reports read-only maintenance job supervision state. It
  currently tracks the planned nightly user service/timer and shows the report,
  dry-run, and log commands without installing or enabling automation.
- `scripts/nightly --report` summarizes the nightly carry plan without writing:
  daily directory, through/destination dates, candidate count, source counts,
  planned actions, and the exact dry-run/apply commands.
- User-systemd templates for the future nightly timer live in `systemd/user/`.
  They are committed for review but are not installed or enabled yet.

## Known Limitations

- Public setup and configuration examples are intentionally deferred.
- Weekly, monthly, annual, and 5WOW planning notes are maintained manually or
  through `scripts/cogs-planning`; they are not maintained by the live loop.
- The nightly user timer is not installed yet. Stage 27A-C only add observation,
  preflight reporting, and committed templates; scheduling remains disabled
  until preview/install/recovery slices are built.
- ISO-first daily naming is preview-only. Existing daily-note writes still use
  compatible lookup and preserve current legacy naming unless an ISO-first file
  already exists.
- Current live planning notes exist at `/home/cosmo/vault/Cogs/weekly/2026-W20.md`,
  `/home/cosmo/vault/Cogs/monthly/2026-05.md`, and
  `/home/cosmo/vault/Cogs/annual/2026.md`. The monthly note puts the seven-day
  `Calendar` grid before the vertical weekday `5WOW` table.
- Higher-level hierarchy nodes are human-authored or review-approved.
- Native local tool calling is not production-ready for the current model tag.
- Memory packets and graph-expanded retrieval remain benchmark/preview features.
- The sensitive-data audit passed before the public repository flip.

## Verification

The main local gate is:

```bash
scripts/check
```

The latest Stage 27C gate passed 296 tests, smoke test, fallback contract, and
review count 0.

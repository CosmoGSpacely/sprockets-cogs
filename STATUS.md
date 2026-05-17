# Sprockets-Cogs Status

Sprockets-Cogs is a working local prototype and learning project. It is not yet a
turnkey public application.

## Current Maturity

The project has completed its Phase 2 hardening work, Phase 3 memory groundwork,
Stage 25 public-readiness MVP, Phase 3.5 productization bridge, and most of
Phase 4's specialist-boundary work:

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
- Phase 4 specialist previews for Rosie, RUDI, Cogs, Sprockets, Jane, and
  Uniblab.

## Current Runtime Posture

- The service runs Rosie, the file-based `agentic_loop.py` watcher.
- Local classification uses the configured Ollama model.
- OpenAI fallback is review-first when configured.
- RUDI owns reasoning/orchestration previews and semantic memory retrieval for
  compact post-classification guards.
- Prompt-appended memory context remains disabled.
- Nightly Cogs carry is scheduled by a user-level systemd timer.
- `scripts/cogs-planning` previews Stage 26 naming choices, planning inventory,
  monthly seven-day calendar grids plus vertical 5WOW tables,
  weekly/monthly/annual templates, planning-note creation plans, and daily
  rename plans without writing to the vault.
- `scripts/cogs-planning --create ... --kind ...` can create missing planning
  notes and refuses to overwrite existing files.
- `scripts/cogs-planning --ensure-current` creates the current weekly, monthly,
  and annual planning notes when missing and preserves existing files.
- `scripts/job-status` reports read-only maintenance job supervision state. It
  tracks the installed nightly user service/timer and shows the report,
  dry-run, and log commands. If the user systemd bus is unavailable from a
  sandboxed process, it now reports that explicitly instead of implying the
  timer is missing.
- `scripts/nightly --report` summarizes the nightly carry plan without writing:
  daily directory, through/destination dates, candidate count, source counts,
  planned actions, and the exact dry-run/apply commands.
- User-systemd templates for the nightly timer live in `systemd/user/`.
- `scripts/job-supervisor --preview-install nightly` shows the exact future
  install targets and `systemctl --user` commands without writing.
- `scripts/job-supervisor --preview-disable nightly` and
  `--preview-recovery nightly` show pause/recovery commands before live
  scheduling exists.
- `sprockets-cogs-nightly.timer` is installed and enabled as a user timer. The
  next run can be inspected with `scripts/job-status`.
- Stage 27G host verification confirmed the timer is loaded, enabled, and
  active/waiting for `2026-05-12 04:30 EDT`; the manual oneshot service result
  remains `success` with exit status 0.
- Stage 27H live rehearsal created one harmless test input, verified extraction
  and classification through the live service, restarted the service to confirm
  model/env reload, and left exactly one open Cogs item for the first scheduled
  nightly timer run to carry.
- Stage 27 scheduled-job supervision is complete: the first scheduled run on
  `2026-05-12 04:30 EDT` succeeded, carried six open Cogs items to `2026-05-13`,
  left `scripts/nightly --report` with 0 open candidates, and kept review count
  at 0.
- Phase 4's message bus is a handoff contract and rehearsal surface only. It is
  not a live dispatch engine.

## Known Limitations

- Public setup and configuration examples are intentionally deferred.
- Weekly, monthly, annual, and 5WOW planning notes are maintained manually or
  through `scripts/cogs-planning`; they are not maintained by the live loop.
- The nightly timer is now installed and enabled. Prompt-appended memory context
  remains disabled, and planning-note maintenance is still manual/script-driven.
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
- Phase 3.5 closeout added public-facing `EVAL.md`, `DECISIONS.md`, and
  `DEMO.md` as a bounded portfolio checkpoint before Phase 4.

## Verification

The main local gate is:

```bash
scripts/check
```

The latest Phase 4 gate passed 431 tests, smoke test, fallback contract, and
review count 0.

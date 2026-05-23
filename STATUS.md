# Sprockets-Cogs Status

Sprockets-Cogs is a working local prototype and learning project. It is not yet a
turnkey public application.

## Current Maturity

The project has completed its Phase 2 hardening work, Phase 3 memory groundwork,
Stage 25 public-readiness MVP, Phase 3.5 productization bridge, Phase 4
specialist-boundary work, and Phase 5 codebase-maturity work:

- typed Sprockets/Cogs writes;
- deterministic smoke test and unit tests;
- review-first fallback behavior;
- semantic memory benchmark harness;
- guarded production retrieval;
- retrieval traces and reports;
- memory tool-call readiness probe;
- planning-note maintenance helpers for current weekly/monthly/annual notes;
- scheduled nightly carry supervision;
- Phase 4 specialist previews for Rosie, RUDI, Cogs, Sprockets, Jane, and
  Uniblab;
- public README, design note, license, CI workflow, sensitive-data audit,
  developer map, and CLI posture documentation.

## Current Runtime Posture

- The service runs Rosie, the file-based `agentic_loop.py` watcher.
- Local classification uses the configured Ollama model.
- OpenAI fallback is review-first when configured.
- RUDI owns reasoning/orchestration previews and semantic memory retrieval for
  compact post-classification guards.
- Prompt-appended memory context remains disabled.
- Nightly Cogs carry is scheduled by a user-level systemd timer.
- `scripts/cogs-planning` previews planning names, planning inventory, monthly
  seven-day calendar grids plus vertical 5WOW tables, weekly/monthly/annual
  templates, planning-note creation plans, and daily rename plans.
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
  `--preview-recovery nightly` show pause/recovery commands.
- `sprockets-cogs-nightly.timer` is installed and enabled as a user timer. The
  next run can be inspected with `scripts/job-status`.
- Phase 4's message bus is a handoff contract and rehearsal surface only. It is
  not a live dispatch engine.
- `DEVELOPMENT.md` now maps public entry points, module responsibilities,
  runtime data flow, CLI posture, tests, safe refactor boundaries, and direct
  CLI testability patterns.
- `scripts/input-adapter-preview` previews adapter-produced `.input` files and
  can explicitly write one `.input` file to a chosen input directory.
- `scripts/telegram-adapter-preview` previews local Telegram update JSON as a
  Rosie `.input` file and only writes when the update is allowlisted and
  `--write --input-dir` are explicit.
- `scripts/telegram-update-probe` reports Telegram token/allowlist readiness
  without printing the token and can fetch updates for local preview.
- `scripts/telegram-response` previews conservative Telegram responses and can
  manually send only with explicit `--send`; Rosie does not automatically reply
  to bot messages.
- `scripts/markitdown-preview` previews text/Markdown document ingestion as a
  `.input` file and can explicitly write one converted document to a chosen
  input directory.
- `scripts/markitdown-batch` inventories a folder of documents and can
  explicitly apply a bounded, idempotent batch as `.input` files.

## Known Limitations

- Public setup and configuration examples are intentionally minimal.
- Weekly, monthly, annual, and 5WOW planning notes are maintained manually or
  through `scripts/cogs-planning`; they are not maintained by the live loop.
- The nightly timer is now installed and enabled. Prompt-appended memory context
  remains disabled, and planning-note maintenance is still manual/script-driven.
- Daily-note writes prefer ISO-first daily names. Compatible lookup still
  accepts legacy daily names if older vault data is imported later.
- Current planning notes are expected under the configured vault's
  `Cogs/weekly/`, `Cogs/monthly/`, and `Cogs/annual/` directories. Monthly
  notes put the seven-day `Calendar` grid before the vertical weekday `5WOW`
  table.
- Higher-level hierarchy nodes are human-authored or review-approved.
- Native local tool calling is not production-ready for the current model tag.
- Memory packets and graph-expanded retrieval remain benchmark/preview features.
- More complete packaging, onboarding, and non-local deployment polish remain
  future work.
- The Telegram adapter has no live polling loop yet; current bot work provides
  token-safe update probing, local update normalization, allowlist checks,
  preview/write rehearsal, and manual response preview/send.
- Automatic bot replies are not wired into the live service.
- Rich PDF/Office document ingestion requires the optional `markitdown`
  dependency; current document adapter tests and previews cover text/Markdown
  files without that dependency.
- Batch document ingestion reports rich-format candidates as requiring
  MarkItDown when the optional dependency is not installed.

## Verification

The main local gate is:

```bash
scripts/check
```

The latest local gate passed 536 tests, smoke test, fallback contract, and
review count 0.

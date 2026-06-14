# Development

This repo is the runtime product. Planning journals and phase reviews belong in
the builder repo, not in public code docs.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

The common runtime paths can be overridden with:

```text
SPROCKETS_COGS_SC_ROOT
SPROCKETS_COGS_INPUT_DIR
SPROCKETS_COGS_PROCESSING_DIR
SPROCKETS_COGS_ARCHIVE_DIR
SPROCKETS_COGS_OUTPUT_DIR
SPROCKETS_COGS_VAULT_DIR
SPROCKETS_COGS_MODEL
```

OpenAI fallback is off unless `OPENAI_API_KEY` is present.

## Main Gate

```bash
scripts/check
```

This is the publish gate. It runs unit tests, smoke coverage, fallback contract
checks, and review-count inspection.

Use narrower commands while iterating:

```bash
scripts/smoke
scripts/status
scripts/pilot3-status
scripts/review --count
python -m unittest tests.test_stage106_pilot3_hardening
```

## Current Runtime Flow

```text
Orbit/source adapter
  -> .input file
  -> agentic_loop.py / Rosie
  -> extraction and classification
  -> validation, guards, routing
  -> vault/runtime/review writes
  -> archive and optional source acknowledgement
```

Tests should use temp paths or environment overrides. Do not use the live vault
as a fixture.

## Module Ownership

| Boundary | Code homes | Owns |
| --- | --- | --- |
| Orbit | `source_adapters.py`, `telegram_adapter.py`, `rich_input.py`, `specialists/orbit/` | Source normalization and `.input` creation. |
| Rosie | `agentic_loop.py`, `capture_preview.py`, `prompts.py`, `models.py`, `intents/` | Extraction, classification, and ordinary capture flow. |
| Sprockets | `sprockets_specialist.py`, `graph/`, `specialists/sprockets/` | Durable graph structure and hierarchy. |
| Cogs | `cogs_specialist.py`, `cogs_planning.py`, `carry.py`, `nightly.py`, `specialists/cogs/` | Time-oriented work, carry, close/drop behavior. |
| Astro | vault write helpers and daily/planning surfaces | Human-readable vault surface and manual carry affordances. |
| Cogswell | `collections_*`, `specialists/cogswell/` | Database and collection graph bridge. |
| Jane | `review.py`, `review_specialist.py`, `specialists/jane/` | Review packets and user decisions. |
| RUDI | `memory_*`, `retrieval_*`, `orchestrator_*`, `specialists/rudi/` | Memory, retrieval, reasoning, orchestration preview. |
| Uniblab | `system_status.py`, `job_status.py`, `sc_backup.py`, `specialists/uniblab/` | Status, jobs, backups, readiness. |

The repo still has legacy root modules. When touching behavior, prefer moving
clear ownership into the relevant boundary instead of adding another layer of
old-module gravity.

## Command Posture

Safe read-only commands:

```bash
scripts/status
scripts/pilot3-status
scripts/adapter-status
scripts/review --count
scripts/memory-demo "tractor tire"
scripts/specialist-route
scripts/sc-backup --status
```

Guarded source writers:

```bash
scripts/pilot3-telegram-once
scripts/pilot3-telegram-watch
scripts/input-adapter-preview --write --input-dir /path/to/input
scripts/rich-input-proof --help
```

Guarded vault/runtime writers:

```bash
scripts/carry --apply
scripts/nightly
scripts/cogs-planning --ensure-current
scripts/sc-backup --create
scripts/review
```

Write commands should have a preview, status, dry-run, or explicit target path.

## Testing Rules

- Put new behavior under `tests/`.
- Prefer fixture-level assertions over broad snapshots.
- Use temp directories for vault/runtime writes.
- Test failure paths, not only happy paths.
- Keep model-calling tests out of the default unit gate unless they are mocked or
  explicitly designed as probes.

## Model And Prompt Rules

- Keep routine inference local-first.
- Keep prompts small and structured.
- Keep prompt-appended memory off unless a future measured design proves it safe.
- Hosted fallback must route to review.
- Do not treat JSON-shaped model output as authority until schemas validate.

## Review And Mutation Rules

Models may propose:

- extracted text;
- intent;
- candidate Sprockets/Cogs;
- candidate review packets;
- candidate source/resource metadata.

Code owns:

- validation;
- dedupe;
- route choice;
- locator and write paths;
- graph mutation;
- vault mutation;
- acknowledgement.

## Refactor Pressure

The current product problem is not a lack of ideas. It is getting real behavior
into owned boundaries quickly enough to support a daily pilot.

When implementing:

1. Make the smallest useful product behavior real.
2. Put it behind the right boundary.
3. Add a focused test.
4. Update only public docs that changed.
5. Avoid new planning surfaces unless a user decision is actually needed.

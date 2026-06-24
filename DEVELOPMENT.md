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
  -> specialists.rosie.loop / Rosie
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
| Orbit | `specialists/orbit/`, `specialists/orbit/adapters/` | Source normalization and `.input` creation. |
| Rosie | `specialists/rosie/`, `intents/`, `substrate/` | Extraction, classification, and ordinary capture flow. |
| Sprockets | `specialists/sprockets/`, `graph/` | Durable graph structure and hierarchy. |
| Cogs | `specialists/cogs/` | Time-oriented work, carry, close/drop behavior. |
| Astro | `specialists/astro/` | Human-readable vault surface and manual carry affordances. |
| Cogswell | `collections_*`, `specialists/cogswell/` | Database and collection graph bridge. |
| Jane | `specialists/jane/` | Review packets and user decisions. |
| RUDI | `specialists/rudi/` | Memory, retrieval, reasoning, orchestration preview. |
| Uniblab | `specialists/uniblab/` | Status, jobs, backups, readiness. |

Root Python files are not ownership homes. Shared contracts belong in
`substrate/`; specialist behavior belongs under `specialists/`.

## Command Posture

Safe read-only commands:

```bash
scripts/sc
scripts/sc status
scripts/sc review --count
scripts/sc friction
scripts/status
scripts/pilot3-status
scripts/adapter-status
scripts/review --count
scripts/memory-demo "tractor tire"
scripts/specialist-route
scripts/sc-backup --status
scripts/sc vault-backup --preview
scripts/sc retention
scripts/sc ops
scripts/sc adapters status
```

Guarded source writers:

```bash
scripts/pilot3-telegram-once
scripts/pilot3-telegram-watch
scripts/sc adapters ingest --source discord --text "Capture this"
scripts/sc adapters reject --source discord --reason "not allowlisted" --text "..."
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
`scripts/sc` is a dispatcher only; it delegates to owner scripts and does not
merge specialist services.

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

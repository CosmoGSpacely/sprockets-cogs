# Sprockets-Cogs

![tests](https://github.com/CosmoGSpacely/sprockets-cogs/actions/workflows/test.yml/badge.svg)

Sprockets-Cogs is a local-first agentic planning and knowledge system. It turns
plain inputs into reviewable Sprockets, time-oriented Cogs, and vault surfaces
without giving a model silent authority over the user's working memory.

The project is also a practical AI systems lab: small local models, typed
contracts, guarded review, source adapters, semantic memory, and database/graph
bridges are tested against a real personal workflow instead of toy prompts.

## Current Shape

The live path is intentionally simple:

```text
source adapter
  -> guarded .input file
  -> Rosie extraction and classification
  -> typed validation and routing
  -> Sprockets, Cogs, Astro, Cogswell, Jane, RUDI, or Uniblab boundary
  -> vault/runtime write or review packet
  -> source acknowledgement when available
```

The main source adapter today is Telegram through Orbit. Local files, document
previews, Discord proofing, Open WebUI proofing, and rich image/document probes
share the same `.input` boundary.

## Named Boundaries

- **Orbit** owns source adapters: Telegram, Discord, document conversion, rich
  resource intake, and future multimodal input.
- **Rosie** owns ordinary extraction and intent classification.
- **Sprockets** owns durable graph structure: areas, goals, projects, tasks,
  contacts, organizations, places, and references.
- **Cogs** owns time-oriented operational work: appointments, settings, actions,
  carry, close, and drop behavior.
- **Astro** owns the vault surface: rendered pages, manual carry affordances,
  and human-readable traces.
- **Cogswell** owns database and collection bridges.
- **Jane** owns review packets and user decisions.
- **RUDI** owns reasoning, memory, retrieval, and orchestration previews.
- **Uniblab** owns status, checks, backups, jobs, and operational readiness.

These are code boundaries, not a pile of always-on daemons. The project earns
new services only when the substrate is durable enough.

## What Works Now

- File-based `.input` capture and archive flow.
- Telegram one-shot and foreground watch intake with allowlist, offset state,
  duplicate suppression, and processed acknowledgements.
- Local model extraction/classification with typed Pydantic validation.
- Review-first fallback behavior.
- Sprockets and Cogs schema, mutation, validation, and fixture coverage.
- Daily Cogs writes and pilot-facing status commands.
- Read-only memory and retrieval surfaces.
- Cogswell collection/database bridge probes.
- Rich input proofing for images/documents as resources.
- Operational backup helpers for the runtime directory.
- Unit, smoke, fallback, retrieval, and pilot-oriented checks.

## Current Focus

The current work is hardening and refactoring, not inventing more architecture.
The near-term product goal is a pilotable loop:

- Telegram input is easy enough to use daily.
- Relative dates, time spans, and recurrence are handled conservatively.
- Review packets are useful and not overwhelming.
- Astro/vault output supports manual carry, not just passive ledger rendering.
- Cogswell proves that a knowledge graph can curate database-backed collections.
- Multimodal resources can be captured without unsafe structural mutation.

## Try It

Run the main local gate:

```bash
scripts/check
```

Useful operator commands:

```bash
scripts/status
scripts/pilot3-status
scripts/pilot3-telegram-once
scripts/pilot3-telegram-watch
scripts/review --count
scripts/sc-backup --status
```

Useful preview/probe commands:

```bash
scripts/specialist-route
scripts/memory-demo "tractor tire"
scripts/rich-input-proof --help
scripts/collections-bridge --help
scripts/adapter-status
```

## Repository Map

- `specialists/` - public specialist package map and boundary facades.
- `specialists/rosie/loop.py` - Rosie watcher and processing pipeline.
- `specialists/orbit/` - Orbit intake, Telegram, rich-source, and shared
  `.input` source envelopes.
- `specialists/orbit/adapters/` - source-specific adapter implementations.
- `specialists/cogs/` - Cogs planning, carry, daily reliability, and time
  helpers.
- `specialists/astro/` - vault write helpers and human-facing ledger surfaces.
- `specialists/sprockets/` - Sprockets hierarchy and graph read surfaces.
- `specialists/jane/` - review queue and packet tools.
- `specialists/rudi/` - memory, retrieval, reasoning, and orchestration
  preview.
- `specialists/uniblab/` - status, jobs, backups, readiness, and model probes.
- `specialists/cogswell/` - database/collection bridge.
- `substrate/` - shared product contracts and small cross-boundary helpers.
- `graph/` - product graph models, fixtures, validators, and mutations.
- `intents/` - input intent models and routing contracts.
- Root Python files are not used for specialist ownership or substrate.
- `scripts/` - venv-aware command wrappers.
- `tests/` - focused coverage for product behavior and probes.

## Public Docs

- `DESIGN.md` explains the current architecture.
- `STATUS.md` gives the current maturity and limitations.
- `DEVELOPMENT.md` maps setup, commands, modules, and contribution posture.
- `EVAL.md` explains verification and model/retrieval evaluation.
- `DEMO.md` walks through the pilot loop.
- `DECISIONS.md` records stable public design decisions.

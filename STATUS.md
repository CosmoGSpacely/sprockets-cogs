# Sprockets-Cogs Status

Sprockets-Cogs is a working local prototype under active hardening. It is not
yet a turnkey public application, but it is no longer just a planning exercise:
the repo has live source intake, local inference, validation, vault writes,
review surfaces, memory probes, and database bridge probes.

## Runtime Posture

- Rosie watches `.input` files and runs extraction/classification.
- Orbit can place Telegram messages into the same `.input` contract.
- Telegram Pilot 3 commands support one-shot polling, foreground watch mode,
  duplicate suppression, offset state, allowlist checks, and processed replies.
- The model path is local-first through Ollama. Hosted fallback is review-first.
- Typed code validates and constrains model output before any write.
- Sprockets and Cogs graph contracts exist beside the older runtime schemas.
- Astro/vault output is still being hardened so manual carry is a first-class
  product surface, not just a rendered log.
- Cogswell has collection/database bridge probes and needs a more product-shaped
  database-to-graph workflow.
- RUDI memory is read-only/guarded; prompt-appended memory remains off.
- Uniblab scripts cover status, checks, jobs, and operational backup.

## Current Product Goal

The immediate goal is a credible daily pilot loop:

```text
Telegram input
  -> Orbit .input
  -> Rosie local extraction
  -> guarded specialist routing
  -> Cogs/Sprockets/Astro/Cogswell/Jane behavior
  -> short Telegram acknowledgement
```

Phase 9 hardening should reduce friction, not add speculative surfaces.

## Solid Enough To Use

- `scripts/check` as the main local gate.
- `scripts/pilot3-status` for Telegram/Orbit readiness.
- `scripts/pilot3-telegram-once` and `scripts/pilot3-telegram-watch` for
  supervised intake.
- `scripts/review --count` for review queue inspection.
- `scripts/sc-backup --create|--status|--verify` for runtime snapshots.
- `scripts/memory-demo` for read-only retrieval evidence.
- `scripts/collections-*` for Cogswell bridge experiments.
- `scripts/rich-input-proof` for multimodal/resource intake proofing.

## Known Hardening Work

- Relative dates and natural time spans need stronger conservative handling.
- Recurrence needs review-first behavior instead of accidental expansion.
- Telegram needs better operator ergonomics and error reporting.
- Astro needs explicit manual carry and close/drop/carry affordances.
- Cogswell needs a stronger database/graph bridge story.
- Review packets must stay small enough to process in daily use.
- Specialist code boundaries still need refactor pressure so real behavior does
  not keep accreting in the old runtime modules.

## Verification

Run:

```bash
scripts/check
```

Use narrower commands when iterating:

```bash
scripts/smoke
scripts/status
scripts/pilot3-status
scripts/review --count
```

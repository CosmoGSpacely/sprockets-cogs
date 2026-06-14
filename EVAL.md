# Evaluation

Sprockets-Cogs uses repeatable product checks instead of one giant benchmark.
The goal is to catch regressions before they affect the live vault or daily
pilot loop.

## Main Gate

```bash
scripts/check
```

The gate covers:

- unit tests;
- deterministic smoke behavior;
- fallback contract behavior;
- review queue count.

Do not preserve old pass counts in docs. The current count belongs in command
output, CI, or release notes, not permanent documentation.

## Product Probes

Use probes when changing a boundary:

```bash
scripts/pilot3-status
scripts/pilot3-telegram-once
scripts/specialist-route
scripts/memory-demo "tractor tire"
scripts/rich-input-proof --help
scripts/collections-bridge --help
scripts/model-capability-probe --help
```

These probes are not all equivalent to passing tests. They exist to expose
runtime shape, model behavior, source readiness, and operator friction.

## Retrieval And Memory

RUDI memory should be evaluated separately from live writing:

```bash
scripts/retrieval-eval --help
scripts/retrieval-preview --status
scripts/retrieval-traces --help
```

Production memory remains guarded. Benchmark-only retrieval features stay out of
live writes until they have a measured reason, preview output, and traceable
safety boundary.

## Model Evaluation

Model choice is practical, not aesthetic. A useful local model must handle:

- intent classification;
- concise structured extraction;
- review-packet reasoning;
- rich input/resource description when supported;
- small context windows reliably;
- predictable failure modes.

Compare models with fixtures and real pilot inputs. Do not promote a model
because it sounds impressive on a single prompt.

## Pilot Evaluation

The pilot loop is evaluated by friction:

- Did Telegram input arrive?
- Did the system acknowledge it?
- Did it become the right kind of item?
- Was review necessary?
- Was review understandable?
- Could the user carry/close/drop the resulting work in the vault?

Those questions matter more than abstract benchmark points.

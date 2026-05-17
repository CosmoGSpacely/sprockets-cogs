# Rosie

Rosie is the live intake and classifier specialist.

## Responsibility

Rosie watches for `.input` files, extracts useful candidate items, classifies
them into typed Sprockets-Cogs schemas, validates them, writes safe immediate
artifacts, routes uncertain outputs to review, and archives processed inputs.

Rosie is intentionally narrow: it should not perform broad reasoning, invent
long-lived hierarchy nodes, or coordinate multi-step specialist workflows.

## Runtime Form

Rosie is currently the only always-on real-time service.

## Current Implementation

- `agentic_loop.py`
- `extractor_classifier.py`
- `capture_preview.py`
- `scripts/capture-preview`

## Boundaries

- Hosted fallback remains review-first.
- Higher-level hierarchy creation remains human-authored or review-approved.
- Memory is applied through guarded post-classification code, not prompt context.


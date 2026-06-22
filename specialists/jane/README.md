# Jane

Jane is the human-in-the-loop review specialist.

## Responsibility

Jane owns review packet presentation, decision import previews, guarded apply
previews, and uncertainty handling. Jane decision values are `approve`,
`reject`, `edit`, and `skip`; `discard` remains a compatibility alias for
`reject`.

Jane is where the system makes ambiguity visible instead of hiding it inside
automation.

## Runtime Form

Jane is command-driven. Live apply behavior remains intentionally guarded and
preview-first. Astro owns the vault action surface that carries Jane decisions
back from human-edited packets.

## Current Implementation

- `specialist.py`
- `review.py`
- `scripts/review-specialist`
- `scripts/review`

## Boundaries

- Review remains the safety boundary for malformed outputs, low confidence,
  hosted fallback candidates, and uncertain hierarchy writes.
- Apply behavior should stay source-checked and previewable.

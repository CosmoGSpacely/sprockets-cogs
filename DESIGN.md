# Sprockets-Cogs Design

Sprockets-Cogs is designed around a small promise: capture ordinary life and
work inputs, turn them into durable structure or time-oriented action, and keep
the user in control of every structural decision that could reshape the graph.

## Product Model

The system has two first-class product objects:

- **Sprockets** are durable graph items: areas, goals, projects, tasks, contacts,
  organizations, places, references, and related knowledge.
- **Cogs** are time-oriented operational items: appointments, settings, actions,
  carry items, closed work, and dropped work.

The bridge between them is explicit. A task Sprocket can spawn Cogs; Cogs can
build evidence that a Sprocket task is complete. Neither silently transforms
into the other.

## Runtime Model

The runtime loop keeps model authority narrow:

```text
adapter input
  -> normalized .input
  -> model proposes extraction/classification
  -> Pydantic validates shape
  -> deterministic guards constrain authority
  -> writes or review packets are produced
```

The model proposes. Code validates, routes, and writes.

## Specialist Boundaries

- **Orbit** owns external sources and rich input normalization.
- **Rosie** owns ordinary extraction and classification.
- **Sprockets** owns durable graph structure.
- **Cogs** owns time horizons, carry, and operational action.
- **Astro** owns vault rendering and manual vault interaction.
- **Cogswell** owns database-backed collections and catalog bridges.
- **Jane** owns review packets and user decisions.
- **RUDI** owns retrieval, reasoning, memory, and orchestration preview.
- **Uniblab** owns operational readiness.

These names are meant to clarify ownership. They do not imply a separate service
for every boundary.

## Vault Surface

The vault is not just a ledger. It is the human work surface where a user can
see, carry, close, drop, and adjust Cogs. Astro owns that surface.

Rendered pages must preserve:

- the active item;
- where it belongs now;
- enough locator information to close/drop/carry safely;
- human-readable traces of prior appearances;
- manual editing affordances that can be reconciled back into the system.

The project may use Obsidian-compatible Markdown, but the architecture is the
vault surface, not Obsidian itself.

## Review Boundary

Review packets exist when the system lacks authority. Typical triggers:

- creating or changing hierarchy nodes;
- ambiguous contact/place/entity resolution;
- recurrence or future schedule expansion;
- low-confidence extraction;
- external fallback output;
- structural mutations that would surprise the user.

Review should be concise. A good system reduces review volume through better
guards and better defaults, not by letting models write more freely.

## Memory Boundary

Memory is support infrastructure, not a second author of the graph.

Current posture:

- read-only retrieval is safe;
- prompt-appended memory is off;
- memory can provide compact evidence and candidates;
- code gates whether a memory hint is used;
- memory decisions should be traceable without exposing private input.

## Database Boundary

Cogswell exists because many useful knowledge systems begin as databases,
catalogs, inventories, or collections. The database owns deterministic facts;
the graph owns meaning, relationships, review, and workflow.

The long-term product idea is not just a personal planner. It is an extensible
way to curate structured knowledge through guarded graph proposals.

## Local-First Model Posture

Local models should handle routine inference whenever practical. Hosted models
may be used for comparison or fallback, but they should not have equal write
authority. External fallback routes to review.

The system should prefer:

- small structured prompts;
- deterministic pre/post processing;
- model-agnostic contracts;
- narrow prompt chains only when fixtures prove they help;
- prompt caching where repeated doctrine/context makes it worthwhile.

## Non-Goals

- Do not multiply first-class graph types just because a model can name them.
- Do not split into a LangGraph repo until the common substrate works live.
- Do not let adapters, fallback models, or review helpers write directly to the
  vault.
- Do not treat the vault as passive output; it is a product surface.

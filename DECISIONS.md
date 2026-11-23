# Design Decisions

Restarted 2026-11-23. The decisions before the restart are at the tag
`pre-restart-2026-11-23` (also `0.2.0-alpha`). None carries over unless it is
restated here.

**Givens:** Sprockets, Cogs, and the resident Gemma model. Everything else is
open.

## Vertices and Edges

### Everything Is A Sprocket Or A Cog (2026-11-23, restated from 2026-08-31)

There is no third family. A Sprocket is durable structure; a Cog is something
placed in time.

### Settings Are The Centre (2026-11-23)

A **setting Sprocket** is a recurring context: WALMART, MILWAUKEE, DATE,
DENTIST, YOGA. Setting is one vertex kind. Place, mode of work and occasion
differ in **what the setting holds**, not in type.

Hierarchy (area, goal, project, task) and people, places and things (contact,
entity, note) are well-trodden ground. How they relate to settings is not, and
that relationship is what distinguishes the product.

### A Setting Holds Its Own Context (2026-11-23)

A setting Sprocket stores what Cosmo associates with it:

- **What happens there.** WALMART: coffee, tea, yogurt.
- **Who and what is there.** MILWAUKEE: Rocco; Oak Creek Diner.
- **What an occurrence needs.** YOGA needs a time.

This is how the model "understands" a setting. To place an item, it reads each
candidate setting's stored context as evidence, rather than knowing anything
about Milwaukee itself.

### Learning Is Stored In The Setting, Not Recomputed (2026-11-23)

What the system learns about a setting from use is written into the setting
Sprocket as it is learned. Occurrences read the stored context. They never
re-derive it from history.

### A Setting Cog Is An Occurrence; Its Open Items Surface On It (2026-11-23)

A setting Cog is one occurrence of its setting in time: Saturday's WALMART run,
Tuesday's DENTIST visit. When a setting occurs, its open items surface on that
occurrence. An undated item that belongs to a setting goes to the setting's next
occurrence. That placement rule is restated from 2026-10-04.

### An Appointment Creates Its Setting (2026-11-23)

There is no appointment without a setting. "Dentist Tuesday 3pm" with no
DENTIST setting creates:

- the DENTIST setting;
- its link to a contact (the dentist) and/or an entity (the practice), creating
  whichever is missing;
- the Tuesday 3pm occurrence.

Appointment is therefore not a separate Cog kind. Creating a setting on first
mention is routine, not a structural exception needing review.

## Open

- **Cogs without a setting.** Does any Cog have no setting? Test cases: "call
  Jon", "pay the propane bill".
- **The form of a setting's stored context.** Structured fields, prose, or
  both. A recommendation is due.
- **Edge meanings.** A setting is linked *with* a person and *at* a place or
  organisation. Decide whether these are labelled edges or one edge type.
- **Identity.** How a mention resolves to an existing contact or entity ("Dr.
  Patel" against "Patel Family Dental"), and when a new one is made instead.
- **Next:** a settings fixture world (settings, their stored context, and a few
  weeks of Cog history) to test these decisions before any code.

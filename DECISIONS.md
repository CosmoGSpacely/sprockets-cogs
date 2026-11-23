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

### Every Cog Is An Occurrence Of A Setting; No Cog Subtypes (2026-11-23)

A Cog is one occurrence of a setting: Saturday's WALMART run, Tuesday's DENTIST
visit. There is one Cog kind and **no subtypes**. What used to be subtypes are
attributes and links:

- **An appointment** is an occurrence with a `time`.
- **A task** is an occurrence that links to a task Sprocket.
- **A note** is details carried on an occurrence (the car and hotel
  reservations on a trip), or a link to a note Sprocket.

"WALMART: coffee, tea, yogurt" is **one** Cog with a list attribute, not four.
Four Cogs would be a hidden hierarchy, and Cogs link to Sprockets, never to
Cogs.

**Calendar rule:** an occurrence shows its own attributes and the key details of
what it links to, inline. The DENTIST occurrence shows the time, the dentist's
number and "bring insurance card" without anything being opened.

### Structure Lives In Each Setting's Attribute Schema (2026-11-23)

Each setting defines the attributes its occurrences carry:

- YOGA: a time.
- TRAVEL: from, to, departure.
- WALMART: a list.
- ANYWHERE: an optional due date.

This is the structure a small local model needs, moved from a global type list
into the setting. Gemma picks a setting from a short list, then fills that
setting's fields from the capture's own words. It never invents structure.

### Code Expands Series And Trips (2026-11-23)

"YOGA next eight Wednesdays at 5:30pm" is eight YOGA occurrences. A trip to
Milwaukee is three occurrences of two settings: **TRAVEL** (to MKE), then
**MILWAUKEE**, then **TRAVEL** (home). Gemma names the pattern and fills the
fields; code expands it. Small models handle fan-out badly.

### Recurring Dates And Deadlines (2026-11-23)

- **BIRTHDAY** is a setting, linked to the person's contact.
- **A deadline** ("registration renewal by March 3") is an ANYWHERE occurrence
  with a due-date attribute.

### Occurrences Without A Day Sit On Carry Surfaces (2026-11-23)

As in the paper system, carry surfaces collect occurrences. An occurrence is
always placed, at a horizon: a day, a week's carry, or a month's carry.
"WALMART sometime this week" is a WALMART occurrence on this week's carry
until it is given a day. A deadline is carried with its due date. No open list
is kept on the setting Sprocket, and no occurrence is given a day it does not
have.

### An Appointment Creates Its Setting (2026-11-23)

There is no appointment without a setting. "Dentist Tuesday 3pm" with no
DENTIST setting creates:

- the DENTIST setting;
- its link to a contact (the dentist) and/or an entity (the practice), creating
  whichever is missing;
- the Tuesday 3pm occurrence.

Appointment is therefore not a separate Cog kind. Creating a setting on first
mention is routine, not a structural exception needing review.

### Every Cog Has A Setting (2026-11-23)

Every Cog belongs to a setting. When no setting fits and a new one cannot be
made, the Cog goes to one of two built-in settings:

- **ANYWHERE:** doable in any context ("call Jon", "pay the propane bill
  online").
- **UNKNOWN:** the system could not tell. These are open questions for Cosmo
  to resolve, not a resting place.

## Open

- **Unfinished list entries.** When "tea" is not checked off, it either moves
  to the next occurrence or goes to carry. To be decided in use.
- **List entries that reference Sprockets.** Can a list entry link to a task
  Sprocket (for example "patch the rear wall" on a GARAGE occurrence)? To be
  decided in use.
- **Watch:** the share of items landing in ANYWHERE. If it is most of them, the
  setting model has quietly become the old task list.
- **Settings beyond 16.** Code must shortlist candidates before the readout,
  and duplicates (WALMART against WALMART RT 30) must be matched.
- **The form of a setting's stored context.** Structured fields, prose, or
  both. A recommendation is due.
- **Edge meanings.** A setting is linked *with* a person and *at* a place or
  organisation. Decide whether these are labelled edges or one edge type.
- **Identity.** How a mention resolves to an existing contact or entity ("Dr.
  Patel" against "Patel Family Dental"), and when a new one is made instead.
- **Next:** a settings fixture world (settings, their stored context, and a few
  weeks of Cog history) to test these decisions before any code.

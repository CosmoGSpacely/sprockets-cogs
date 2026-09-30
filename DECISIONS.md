# Design Decisions

This file records stable public decisions for the runtime repo. Stage journals
and planning reviews live in the builder repo.

## Local First, Review First

Routine inference should run locally. Hosted fallback is optional and
review-first. Fallback output is validated locally and routed to review instead
of being written directly.

## The Model Proposes; Code Writes

Models extract, classify, summarize, or compare. Python code validates schemas,
checks confidence, resolves authority, applies mutations, and writes files.

## Minimal Graph, Strong Substrate

The product graph stays intentionally small: Sprockets, Cogs, and one edge type
(see *One Edge Type, With A Reserved Core* below). Complexity belongs in
validators, review packets, rendered surfaces, fixtures, and audit logs.

## Sprockets And Cogs Do Not Transform

A Sprocket can spawn Cogs. A Cog can contribute to completing a Sprocket. They
do not change type in place.

## Astro Owns The Vault Surface

The vault is more than a rendered ledger. It is where the user sees work, makes
manual carry decisions, and interacts with open Cogs. Astro owns that behavior.

## Orbit Owns Source Adapters

Telegram, Discord, Open WebUI, documents, images, audio, and future intake
surfaces enter through Orbit. Adapters normalize input and preserve source
metadata; they do not create structural graph mutations directly.

## Rosie Does Not Route To Jane Directly

Rosie classifies and proposes. The orchestrator and specialist boundaries decide
whether a result becomes a write, a review packet, or a rejection.

## Jane Presents Decisions

Jane does not secretly resolve packets. Jane presents reviewable decisions and
records accepted/rejected/modified outcomes.

## RUDI Memory Is Guarded

Prompt-appended memory remains off. RUDI can retrieve evidence and candidates,
but deterministic guards decide whether memory affects a mutation.

## Cogswell Bridges Databases To Graphs

Databases own deterministic catalog facts. The graph owns meaning, relationships,
workflow, and review. Cogswell is a product boundary, not a side experiment.

## LangGraph Split Waits

A future LangGraph implementation is useful for learning, portfolio value,
stateful orchestration, and comparison. It should wait until the common
substrate works live enough that a split will not double the chaos.

## Sync Is Not Backup

Sync tools replicate current state. Backups need point-in-time snapshots and
restore previews. The runtime backup helper protects SC operational data; vault
backup is a separate policy.

## Gemma Stays Resident

**2026-09-30.** Gemma 4 12B stays loaded as the capture model because it
decodes image and audio input natively, which voice and photo capture depend
on. Its VRAM is spent regardless, so it is the default extractor, and a second
model competes only where it fits beside it (~3 GB) or on CPU - in practice,
for classify's closed questions. An alternative must be better at a specific
job, not merely cheaper. Mapping Gemma's strengths and weaknesses job by job is
itself part of the project's learning and portfolio goals.

---

# Graph Substrate Decisions, 2026-08-29 to 2026-09-01

Product-owner decisions made during the Phase 14 assumption audit (builder
Stage 147). Each entry says what was decided, why, what it replaced, and
whether the code matches yet. Most do not: the code catching up is scheduled
construction work, not an open question.

## Everything Is A Sprocket Or A Cog

**2026-08-31.** There are two node families and no third. Settings, segments
and collections, the three cases that pressed for a third family, all resolve
inside the two (entries below).

- **Why:** it is the central simplification, and it held under every case the
  audit could find.
- **Replaced:** pressure to add a vertex type for settings, segments and
  collections.
- **Code:** consistent, but see *One Graph* - Cogs are not yet graph vertices.

## Settings Are Sprockets, And A Setting Is A Context

**2026-08-31.** A setting is a `sprockets/setting` node that spawns
setting-dependent Cogs. It is a context, not a place: DATE or TRAVEL can occupy
a segment or a day, and neither is a location. A setting occupies time, so a
day with too many settings is a variant of a day with too many tasks.

- **Why:** what is possible or appropriate depends on context; that is durable
  knowledge, not a daily action.
- **Replaced:** settings as daily Cogs (`WFH`/`ONSITE`/`HOLIDAY` in the
  classify enum), settings as locations, and typographic setting detection in
  the renderer.
- **Code:** not yet. `sprockets/setting` does not exist.

## Segments Are A Surface; Placement Is A Date

**2026-08-31.** Segments of a day are a surface, like days of the week and
weeks of the year - derived from placement, never stored as nodes. Placement
stays a date, and the segment is derived from it the way "Tuesday" is. An
appointment is a Cog with a time.

- **Why:** a way of looking at placement is not a thing in the graph.
- **Replaced:** a segment vertex, and placement as date plus slot.
- **Code:** consistent.

## Sprocket Types Are A Closed Enum Of Eight

**2026-08-31.** `area`, `goal`, `project`, `task`, `setting`, `note`,
`contact`, `entity`. Two policies sit over the one list: *review-first*
(area, goal, project are created by review only) and *capture-emittable* (the
subset classify may emit). A policy subset is not a competing list.

- **Why:** there were four competing lists and none was authoritative.
- **Replaced:** those four lists, the `sprockets/reference` type, and a
  `collection` subtype drafted and withdrawn the same day.
- **Code:** not yet. `sprockets/setting` is missing; `sprockets/reference` is
  still written.

## Pointer Sprockets Are Notes; The Vault Is The Graph

**2026-08-31.** A Sprocket that points at a file, table, image or PDF is a
`note`. A collection is a `note` pointing at a table: its rows stay in SQLite,
and only rows with actionable state (for example `owned: no`) become Cogs. The
vault is the graph; a database is something a Sprocket points at.

- **Why:** pointing at something is not a reason for a new type, and a
  200-row checklist rendered as 200 vertices swamps the graph.
- **Replaced:** `sprockets/reference`, and one rendered file per collection
  row.
- **Code:** not yet. Cogswell still renders a file per row.

## Same Name Across Types Is Legitimate

**2026-08-31.** The setting WALMART where groceries are bought and the entity
Walmart one might apply to are two nodes with the same name, optionally linked.
A node still has exactly one subtype.

- **Why:** they are different things; the name collision is a requirement to
  support.
- **Replaced:** treating cross-type name collisions as defects to prevent.
  Consequence: text cannot be identity, so title-matched `parent_hint` cannot
  be the linking mechanism.
- **Code:** not yet. Linkage is by slug and title.

## One Word, Subtype

**2026-08-31.** Both families use the word `subtype`, and `node_type` is
uniformly `family/subtype`. Time horizon is a separate field: a Cog is
`cogs/task` with `horizon: day`, never `cogs/daily`.

- **Why:** where a thing appears is a surface, not part of its type.
- **Replaced:** `subtype` for Sprockets, `kind` for Cogs, and `node_type`
  encoding the horizon on the Cogs side.
- **Code:** not yet. This is a migration; `cogs/daily` is widespread.

## Cog Subtypes Are Closed At Four

**2026-09-01.** `setting`, `appointment`, `task`, `note`. `appointment` covers
opportunities (`Flea market 8a-2p`) as well as obligations (`DENTIST 8a`):
both are occasions bounded in time. A note can give a setting context - a
shopping list, a reservation number, an itinerary.

- **Why:** an open set ending in "or similar" cannot become a `node_type`.
- **Replaced:** the open Cog kind list.
- **Code:** not yet.

## One Edge Type, With A Reserved Core

**2026-08-31.** There is one edge type, carrying a relationship attribute that
describes the relationship, instead of a closed enum of relationship types.
Two relationships are reserved and enforced by code: `parent`, and the
Sprocket-Cog bridge (role `primary` or `context`, exactly one `primary` per
bridged Cog). Everything else is model-proposed and review-first, with the
labels already in the graph supplied as context to limit drift.

- **Why:** labels should help the model traverse the graph without a fixed
  vocabulary (unmeasured - see below); the reserved core stays in code because a misspelled structural
  label silently orphans a node.
- **Replaced:** two edge classes in `graph/models.py`, and a live graph built
  only from `parent`.
- **Code:** not yet. `graph/` has no production imports.

## One Graph For Sprockets And Cogs

**2026-09-01.** Sprockets and Cogs live in one graph.

- **Why:** a bridge edge needs a Cog endpoint, and the model's placement
  context is built from the graph - a Cog history that is not in the graph
  cannot be seen.
- **Replaced:** the de facto design, where the graph holds Sprockets and Cogs
  are files beside it.
- **Code:** not yet. The graph builder reads Sprocket directories only.

## An Orphan Is An Unanswered Question

**2026-09-01.** Every Cog needs a bridge *decision*, not a bridge. There are
three outcomes: bridged, standalone by decision, and unresolved. Standalone is
fine; silently standalone is not. An unresolved bridge is evidence that a
Sprocket may be missing, and is the trigger for proposing structure.

- **Why:** an orphan and a correctly standalone Cog were indistinguishable, so
  the empty graph was invisible.
- **Replaced:** "every Cog serves a Sprocket", and silently dropping unmatched
  parent hints.
- **Code:** not yet.

## Carry Gives Every Open Item A Place In Time

**2026-08-29.** The day surface holds today's plan only. Every open item not
for today goes to a future day or a future carry block, chosen by what the
item is - not a backlog. After a fixed number of carries an item is demoted to
a carry block. Rules decide the destination automatically; carry is not an
approval queue.

- **Why:** unconditional copy-forward made the day surface a pile instead of
  an assertion of what is being done today.
- **Replaced:** unconditional copy-forward.
- **Code:** not yet. The carry count and destination rules are open questions
  in the carry stage.

## Capacity Exists

**2026-08-30.** A day has a capacity, and the rule of three is its baseline, as
a soft target.

- **Why:** without capacity the system cannot help the user get through the
  day.
- **Replaced:** no capacity concept.
- **Code:** not yet. Where capacity lives (day attribute, computed over the
  surface, or supplied by settings) is undecided.

## Capture May Propose Structure

**2026-09-29.** Capture may propose new structure - areas, goals, projects,
settings - for review, instead of only attaching to structure that exists. A
hosted fallback model is admissible for this job.

- **Why:** a capture that can only create leaves keeps the graph empty, and
  the attempt is worth making even where the local model falls short.
- **Replaced:** "the model must never invent structure".
- **Code:** not yet. Proposals stay review-first, per *Local First, Review
  First*.

## One Parent, Plus Labelled Edges (Provisional)

**2026-09-29, provisional.** A node has at most one `parent`. A second
affiliation - a truck repair that is both Farm and Vehicle Maintenance work -
is a labelled edge, not a second parent. New fixtures may reopen this.

- **Why:** the one-edge-type design already expresses a second affiliation
  without making hierarchy ambiguous.
- **Replaced:** an open question.
- **Code:** partly. `parent` is scalar, but a list-valued `parent` is silently
  truncated to its first element instead of being rejected.

## Not Yet Decided

Recorded so they are not mistaken for decisions: whether the model can create
node types safely (untested); whether relationship labels measurably help
traversal (untested); and whether Cog subtype determines carry behavior (a
prediction).

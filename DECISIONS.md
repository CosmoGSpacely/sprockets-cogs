# Design Decisions

This file summarizes public-facing design decisions. The fuller project diary
and builder review trail live outside the runtime repo.

## Local First, Review First

Routine capture uses a local Ollama model. Hosted fallback is optional and
review-first: fallback candidates are validated locally and routed to review
rather than written directly to the vault.

Why: the system writes into a personal knowledge/work vault, so autonomy needs a
visible safety boundary.

## The Model Proposes; Code Writes

The language model extracts and classifies candidate nodes. Python code owns the
safety-critical steps: schema validation, duplicate checks, parent resolution,
confidence routing, and Markdown writes.

Why: model output is useful but not authoritative. Deterministic guards make the
system easier to test and debug.

## Prompt-Appended Memory Is Off

Semantic memory is owned by RUDI, the reasoning/orchestration specialist, but it
is not pasted into the classifier prompt in production. Earlier rehearsals
showed that retrieved context could contaminate generated fields.

The current production memory path is post-classification:

1. classify and validate the input;
2. retrieve compact memory candidates;
3. apply constrained parent/task hints in code;
4. log selected or skipped decisions.

Why: this gives useful memory behavior without asking the classifier to mix
retrieved context into structured output perfectly.

## Specialist Boundaries Are Visible Before Services Multiply

Phase 4 uses named specialist boundaries:

- Rosie for live intake/classification;
- RUDI for reasoning, orchestration, and memory/retrieval;
- Cogs for planning and carry;
- Sprockets for graph/hierarchy;
- Jane for review;
- Uniblab for operations.

Only Rosie is currently an always-on service. The other specialists are commands,
scheduled jobs, preview harnesses, or library providers.

Why: the project needs clear multi-agent architecture for public and portfolio
readers, but multiple live services would add retry, ordering, idempotency, and
failure-handling complexity before those costs are justified.

## Message Bus Is A Contract, Not Dispatch

The local message bus is a schema and rehearsal surface for specialist handoffs.
It is not a live queue and does not automatically execute recipients.

Why: handoff contracts are useful now; live dispatch should wait until
specialist commands are idempotent and review boundaries are explicit.

## Hierarchy Nodes Are Human Authored Or Review Approved

Areas, goals, and projects are supported, but the live capture loop does not
freely invent them.

Why: hierarchy nodes shape the long-lived graph. They should be deliberate
because downstream retrieval, planning, and review behavior depends on them.

## Cogs Planning Is A Separate Operational Tool

Daily Cogs items are written by the loop. Weekly, monthly, annual, and 5WOW
planning notes are maintained by `scripts/cogs-planning` and supervised through
status checks.

Why: planning horizon maintenance is a product workflow, not a reason to make
the core input loop larger.

## Nightly Carry Is A Scheduled Job

The nightly carry process runs through a user-level systemd timer instead of
inside the capture service.

Why: scheduled reconciliation has different failure modes and observability
needs than file-based capture.

## Graph And Packet Retrieval Stay Preview Or Benchmark First

Graph-aware retrieval and memory packets are useful benchmark tools. They are
not automatically promoted into production retrieval.

Why: richer context can improve recall but also increases explanation and
contamination risk. Preview and trace quality come before live use.

## Native Tool Calls Are Deferred

Stage 24 found that the current local model endpoint does not support native
Ollama tool calls, and JSON-contract imitation was not strict enough for
production tool use.

Why: tool use should be validated as a reliable interface, not inferred from a
plausible JSON blob.

## Syncthing Is Sync, Not Backup

Syncthing keeps files available across machines, but it is not treated as
point-in-time backup. GitHub protects committed repo history, not the live vault
or runtime queue.

Why: a sync mistake can replicate quickly. The vault and runtime directories
still need a separate backup strategy.

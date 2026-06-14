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

The product graph stays intentionally small: Sprockets, Cogs, hierarchy edges,
and bridge edges. Complexity belongs in validators, review packets, rendered
surfaces, fixtures, and audit logs.

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

# Sprockets-Cogs

Sprockets-Cogs is a local-first agentic capture loop for turning plain-language
inputs into an Obsidian-compatible knowledge/work system.

It watches an input folder for `.input` files, extracts useful work and knowledge
items, validates them with typed schemas, and writes Markdown nodes into a vault.
The project is also a learning lab for practical agentic AI design: local model
operation, review-first fallbacks, semantic memory, retrieval traces, and careful
automation around a personal information system.

## What It Produces

The loop currently writes two related kinds of Markdown:

- **Sprockets**: longer-lived structured nodes such as tasks, notes, contacts,
  and entities.
- **Cogs**: daily bullet-journal style items that capture what needs attention
  now.

Higher-level hierarchy nodes such as areas, goals, and projects are supported by
the schema and retrieval layer, but they are intentionally human-authored or
review-approved. The system does not freely invent the long-lived hierarchy.

## How The Loop Works

At a high level:

```text
.input file arrives
  -> extract candidate nodes
  -> classify them into typed Sprockets/Cogs schemas
  -> validate locally with Pydantic
  -> resolve safe parent links
  -> apply guarded memory hints when enabled
  -> write Markdown files
  -> archive the input
```

The classifier is local-first. OpenAI fallback is available only as a
review-first rescue path when configured; fallback candidates are routed to
review rather than silently written to the vault.

## Current Capabilities

- File-based capture queue for natural-language inputs.
- Typed validation for Sprockets and Cogs outputs.
- Duplicate-aware Markdown writes.
- Daily Cogs creation and append behavior.
- Manual review queue and review CLI.
- Local semantic memory using Ollama embeddings.
- Guarded production retrieval for parent/task linking.
- Retrieval preview and trace-reporting tools.
- Read-only benchmark harness for retrieval quality.
- Deterministic smoke test and unit test suite.

## Important Boundaries

Sprockets-Cogs is not yet a packaged application. It is a working local system
and portfolio project with active hardening underway.

Current boundaries:

- Prompt-appended memory context is disabled because earlier rehearsals showed
  prompt contamination risk.
- Native Ollama tool calls are not wired into production for the current local
  model endpoint.
- Weekly/monthly/annual planning notes are roadmap work, not current loop output.
- The nightly carry script exists, but scheduling is not part of the service yet.
- Public setup examples and external deployment polish are still in progress.

## Repository Map

- `agentic_loop.py` - watcher and processing pipeline.
- `models.py` - Pydantic schemas for generated nodes.
- `prompts.py` - local-model prompts and structured schemas.
- `openai_fallback.py` - review-first OpenAI fallback.
- `memory_index.py` - semantic memory contracts and in-memory index.
- `production_retrieval.py` - guarded production retrieval adapter.
- `memory_guards.py` - post-classification parent/task guard behavior.
- `retrieval_eval.py` - retrieval benchmark CLI facade.
- `retrieval_*` modules - retrieval cases, strategies, nodes, memory bridges, and reports.
- `carry.py` and `nightly.py` - Cogs carry/reconciliation tooling.
- `review.py` - review queue CLI.
- `scripts/` - venv-aware operational wrappers.
- `tests/` - focused unittest coverage.

## Checks

Run the project gate:

```bash
scripts/check
```

That runs:

- unit tests;
- deterministic temp-vault smoke test;
- fallback contract evaluation;
- pending review count.

Useful narrower commands:

```bash
scripts/smoke
scripts/review --count
scripts/retrieval-eval --retriever memory-embedding-gated-vault --case-set real-vault
scripts/retrieval-preview --status
```

## Status

See `STATUS.md` for the current maturity level and known limitations.

See `DESIGN.md` for the architecture and design decisions behind the current
agentic loop.

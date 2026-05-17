# Sprockets-Cogs Development

Agentic loop that processes natural-language inputs and writes Obsidian-compatible
Markdown files to a configured vault directory.

## Files
- `specialists/` — visible Phase 4 specialist map; README/index surfaces only
- `agentic_loop.py` — Rosie file watcher + processing pipeline
- `orchestrator_contract.py` — RUDI route decisions and handoff contracts
- `orchestrated_rehearsal.py` — read-only end-to-end RUDI rehearsal
- `agent_message_bus.py` — handoff contract/message-bus preview, not live dispatch
- `cogs_specialist.py` — Cogs specialist preview facade
- `sprockets_specialist.py` — Sprockets specialist preview facade
- `memory_specialist.py` — RUDI memory/retrieval specialist facade
- `review_specialist.py` — Jane review specialist preview/import/apply safety facade
- `system_status.py` and `job_status.py` — Uniblab operational status helpers
- `models.py`       — Pydantic schemas per node type (Stage 5)
- `prompts.py`      — Qwen3 system prompts and few-shot examples (Stage 4)
- `openai_fallback.py` — review-first OpenAI fallback using Responses API structured output
- `entity_state.py` — JSON working memory for recently seen contacts/entities
- `vault_graph.py`  — NetworkX graph builder for testable Sprockets parent resolution
- `review.py`       — interactive CLI for approving/discarding review items
- `scripts/review`  — venv-aware wrapper for review count/list/report/interactive modes
- `scripts/smoke`   — venv-aware wrapper for deterministic temp-vault smoke test
- `scripts/check`   — operational sanity check: tests + smoke + review count
- `smoke_test.py`   — deterministic temp-vault smoke test with model calls stubbed
- `tools.py`        — date/time tool definitions (Stage 4)
- `tests/`          — focused unittest coverage for parent resolution and operational hardening
- `requirements.txt`— Python dependencies

## Operational data
Lives under the configured SC runtime directory — not in this repo.

Runtime paths can be overridden for tests/dry-runs with environment variables:
`SPROCKETS_COGS_SC_ROOT`, `SPROCKETS_COGS_INPUT_DIR`,
`SPROCKETS_COGS_PROCESSING_DIR`, `SPROCKETS_COGS_ARCHIVE_DIR`,
`SPROCKETS_COGS_OUTPUT_DIR`, `SPROCKETS_COGS_VAULT_DIR`, and
`SPROCKETS_COGS_ENTITY_STATE_PATH`.

OpenAI fallback is disabled unless `OPENAI_API_KEY` is set. Override the fallback
model with `OPENAI_FALLBACK_MODEL`; default is `gpt-4o-mini`.

## Pipeline (two local-model calls per input)
startup scan / watchdog input/ → Rosie extract_nodes() → Rosie classify_nodes()
       → validate_output() → resolve_parents() → guarded RUDI memory hint
       → write_node() → append_reflection() → archive/

## Phase 4 specialist posture

- Rosie is the only always-on service.
- RUDI owns reasoning, orchestration previews, and memory/retrieval support.
- Cogs, Sprockets, Jane, and Uniblab are command/scheduled/review-first
  specialists.
- The message bus is a handoff contract and rehearsal surface, not live
  dispatch.
- The `specialists/` directories are public entry points, not a package move;
  root modules remain the implementation source of truth for now.

## Review commands
- `scripts/review --count` — count pending review items
- `scripts/review --list` — show pending review summaries
- `scripts/review --report` — summarize pending review items by source/type/confidence/reason
- `scripts/review --packet-preview` — render an Obsidian-readable Markdown preview
- `scripts/review` or `scripts/review --interactive` — approve/discard/skip
- `scripts/status` — read-only status summary for runtime paths, review queue, memory retrieval, and maintenance jobs

## Operational checks
- `scripts/check` — run unit tests, temp-vault smoke test, and review count
- `scripts/smoke` — run only the temp-vault smoke test
- `systemctl --user restart sprockets-cogs.service` — restart the watcher service
- `systemctl --user status sprockets-cogs.service` — inspect service state
- `journalctl --user -u sprockets-cogs.service -n 100` — inspect recent logs

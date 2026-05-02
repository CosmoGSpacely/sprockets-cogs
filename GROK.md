# sprockets-cogs — Code Repository

Agentic loop that processes natural-language inputs and writes Obsidian-compatible
Markdown files to the vault at /home/cosmo/vault/.

## Files
- `agentic_loop.py` — file watcher + processing pipeline
- `models.py`       — Pydantic schemas per node type (Stage 5)
- `prompts.py`      — Qwen3 system prompts and few-shot examples (Stage 4)
- `openai_fallback.py` — review-first OpenAI fallback using Responses API structured output
- `entity_state.py` — JSON working memory for recently seen contacts/entities
- `vault_graph.py`  — NetworkX graph builder for testable Sprockets parent resolution
- `review.py`       — interactive CLI for approving/discarding review items
- `scripts/review`  — venv-aware wrapper for review count/list/interactive modes
- `scripts/smoke`   — venv-aware wrapper for deterministic temp-vault smoke test
- `scripts/check`   — operational sanity check: tests + smoke + review count
- `smoke_test.py`   — deterministic temp-vault smoke test with model calls stubbed
- `tools.py`        — date/time tool definitions (Stage 4)
- `tests/`          — focused unittest coverage for parent resolution and operational hardening
- `requirements.txt`— Python dependencies

## Operational data
Lives in /home/cosmo/sc/ — not in this repo.

Runtime paths can be overridden for tests/dry-runs with environment variables:
`SPROCKETS_COGS_SC_ROOT`, `SPROCKETS_COGS_INPUT_DIR`,
`SPROCKETS_COGS_PROCESSING_DIR`, `SPROCKETS_COGS_ARCHIVE_DIR`,
`SPROCKETS_COGS_OUTPUT_DIR`, `SPROCKETS_COGS_VAULT_DIR`, and
`SPROCKETS_COGS_ENTITY_STATE_PATH`.

OpenAI fallback is disabled unless `OPENAI_API_KEY` is set. Override the fallback
model with `OPENAI_FALLBACK_MODEL`; default is `gpt-4o-mini`.

## Pipeline (two Qwen3 calls per input)
startup scan / watchdog input/ → extract_nodes() → classify_nodes() → validate_output()
       → resolve_parents() → write_node() → append_reflection() → archive/

## Review commands
- `scripts/review --count` — count pending review items
- `scripts/review --list` — show pending review summaries
- `scripts/review` or `scripts/review --interactive` — approve/discard/skip

## Operational checks
- `scripts/check` — run unit tests, temp-vault smoke test, and review count
- `scripts/smoke` — run only the temp-vault smoke test
- `systemctl --user restart sprockets-cogs.service` — restart the watcher service
- `systemctl --user status sprockets-cogs.service` — inspect service state
- `journalctl --user -u sprockets-cogs.service -n 100` — inspect recent logs

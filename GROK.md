# sprockets-cogs — Code Repository

Agentic loop that processes natural-language inputs and writes Obsidian-compatible
Markdown files to the vault at /home/cosmo/vault/.

## Files
- `agentic_loop.py` — file watcher + processing pipeline
- `models.py`       — Pydantic schemas per node type (Stage 5)
- `prompts.py`      — Qwen3 system prompts and few-shot examples (Stage 4)
- `entity_state.py` — JSON working memory for recently seen contacts/entities
- `vault_graph.py`  — NetworkX graph builder for Sprockets parent resolution
- `review.py`       — interactive CLI for approving/discarding review items
- `tools.py`        — date/time tool definitions (Stage 4)
- `tests/`          — focused unittest coverage for operational hardening
- `requirements.txt`— Python dependencies

## Operational data
Lives in /home/cosmo/sc/ — not in this repo.

Runtime paths can be overridden for tests/dry-runs with environment variables:
`SPROCKETS_COGS_SC_ROOT`, `SPROCKETS_COGS_INPUT_DIR`,
`SPROCKETS_COGS_PROCESSING_DIR`, `SPROCKETS_COGS_ARCHIVE_DIR`,
`SPROCKETS_COGS_OUTPUT_DIR`, `SPROCKETS_COGS_VAULT_DIR`, and
`SPROCKETS_COGS_ENTITY_STATE_PATH`.

## Pipeline (two Qwen3 calls per input)
startup scan / watchdog input/ → extract_nodes() → classify_nodes() → validate_output()
       → resolve_parents() → write_node() → append_reflection() → archive/

# Sprockets-Cogs Development

Agentic loop that processes natural-language inputs and writes Obsidian-compatible
Markdown files to a configured vault directory.

## Files
- `specialists/` — visible Phase 4 specialist map and importable catalog
- `specialists/catalog.py` — stable specialist metadata for docs/tests/status surfaces
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
- The `specialists/` directories are public entry points and a small catalog,
  not a package move; root modules remain the implementation source of truth for now.

## Entry points

Stage 46A maps the repo's public front doors before any Phase 5 refactor work.
Use this table to decide where a change belongs and whether a command is safe to
run while exploring.

| Entry point | Module or unit | Owner | Purpose | Writes by default? |
|---|---|---|---|---|
| `sprockets-cogs.service` | `agentic_loop.py` | Rosie | Always-on `.input` watcher and live capture pipeline. | Yes: vault, archive, review, operational output. |
| `sprockets-cogs-nightly.timer` | `systemd/user/sprockets-cogs-nightly.timer` | Cogs / Uniblab | Schedules the nightly carry safety net. | Starts a writer service on schedule. |
| `sprockets-cogs-nightly.service` | `systemd/user/sprockets-cogs-nightly.service` → `scripts/nightly` | Cogs | Runs nightly carry/reconciliation. | Yes unless invoked with dry-run/report flags. |
| `scripts/check` | `unittest`, `smoke_test.py`, `scripts/review --count` | Uniblab | Full local verification gate. | Uses temp vault for smoke; does not write production vault. |
| `scripts/status` | `system_status.py` | Uniblab | Read-only operational status, specialist map, review and job posture. | No. |
| `scripts/job-status` | `job_status.py` | Uniblab | Read-only timer/job status. | No. |
| `scripts/job-supervisor` | `job_supervisor.py` | Uniblab | Preview install/disable/recovery commands for maintenance jobs. | No. |
| `scripts/smoke` | `smoke_test.py` | Uniblab | Deterministic temp-vault smoke test. | Temp files only. |
| `scripts/capture-preview` | `capture_preview.py` | Rosie | Preview extraction/classification without live writes. | No. |
| `scripts/orchestrator-route` | `orchestrator_contract.py` | RUDI | Preview route decisions and handoff contracts. | No. |
| `scripts/orchestrated-rehearsal` | `orchestrated_rehearsal.py` | RUDI | End-to-end read-only multi-specialist rehearsal. | No. |
| `scripts/agent-message-bus` | `agent_message_bus.py` | RUDI | Inspect or append local JSONL handoff messages. | Mixed: status/list are read-only; append writes JSONL. |
| `scripts/retrieval-preview` | `retrieval_preview.py` | RUDI | Preview retrieval, production payload, and memory guard behavior. | No. |
| `scripts/retrieval-eval` | `retrieval_eval.py` | RUDI | Run retrieval benchmarks. | May populate embedding cache; no vault writes. |
| `scripts/retrieval-traces` | `retrieval_trace_report.py` | RUDI | Report recent memory-parent traces from logs or JSONL. | No. |
| `scripts/memory-specialist` | `memory_specialist.py` | RUDI | Inventory/cache/benchmark preview facade for memory work. | May read/write embedding cache; no vault writes. |
| `scripts/memory-packets` | `memory_packets_cli.py` | RUDI | Preview deterministic memory packets. | No. |
| `scripts/memory-tool-probe` | `memory_tool_probe.py` | RUDI | Probe local model tool-call readiness. | No. |
| `scripts/fallback-eval` | `fallback_eval.py` | RUDI / Jane | Evaluate OpenAI fallback behavior. | No vault writes; may call OpenAI if configured. |
| `scripts/cogs-specialist` | `cogs_specialist.py` | Cogs | Read-only Cogs inventory/preview facade. | No. |
| `scripts/cogs-planning` | `cogs_planning.py` | Cogs | Planning note inventory, naming, and guarded creation. | Mixed: inventory/names are read-only; ensure/create writes planning notes. |
| `scripts/carry` | `carry.py` | Cogs | Carry plan list/plan/check/apply workflow. | Mixed: list/plan/check are read-only; apply writes vault. |
| `scripts/nightly` | `nightly.py` | Cogs | Nightly carry safety net. | Yes unless report/dry-run mode is used. |
| `scripts/sprockets-specialist` | `sprockets_specialist.py` | Sprockets | Hierarchy inventory/proposal preview facade. | No live hierarchy writes by default. |
| `scripts/hierarchy` | `inspect_hierarchy.py` | Sprockets | Inspect hierarchy and graph state. | No. |
| `scripts/review` | `review.py` | Jane | Count/list/report/packet/interactive review queue. | Mixed: report/count are read-only; interactive approve/discard changes queue and may write vault. |
| `scripts/review-specialist` | `review_specialist.py` | Jane | Review inventory, packet write, decision import/apply preview. | Mixed: preview/import checks are read-only; packet write writes operational output. |

Runtime directories are outside the repo under the configured SC root, usually
`/home/cosmo/sc`: `input/`, `processing/`, `archive/`, `review/`, and
`output/`. The vault is also outside the repo. Tests and dry-runs should use
environment overrides rather than writing to live paths.

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

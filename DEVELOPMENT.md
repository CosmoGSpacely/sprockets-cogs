# Sprockets-Cogs Development

Agentic loop that processes natural-language inputs and writes Obsidian-compatible
Markdown files to a configured vault directory.

## Developer Reading Path

If you are new to the repo, read in this order:

1. `README.md` for the project shape and current capabilities.
2. `DESIGN.md` for the local-first, review-first architecture decisions.
3. `DEVELOPMENT.md` for entry points, module ownership, CLI posture, and safe
   refactor boundaries.
4. `STATUS.md` for current runtime posture and known limitations.
5. `EVAL.md` for the verification gate and retrieval benchmark posture.

Then run:

```bash
scripts/check
```

That is the main local confidence gate. It runs unit tests, a temp-vault smoke
test, fallback contract checks, and review-count inspection.

Safe exploration commands:

```bash
scripts/status
scripts/review --count
scripts/capture-preview "Need to follow up with Alex tomorrow"
scripts/retrieval-preview --status
scripts/orchestrated-rehearsal --source cli --request-id docs-tour "check service status"
```

Development rules:

- Prefer read-only previews before live writes.
- Keep tests and smoke runs pointed at temp/runtime override paths.
- Do not use the live vault as a test fixture.
- Keep prompt-appended memory context disabled unless a future design proves it
  safe.
- Treat `scripts/check` as the gate before publishing or merging changes.

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
- `sc_backup.py` — Uniblab SC runtime backup inventory/preview helper
- `input_adapter.py` — normalized external-input envelope and `.input` rendering/writing helpers
- `input_adapter_preview.py` — read-only/guarded preview CLI for adapter-produced `.input` files
- `telegram_adapter.py` — Telegram update normalization and allowlist checks before `.input` creation
- `telegram_adapter_preview.py` — local Telegram update preview/write CLI with no network dependency
- `telegram_update_probe.py` — token-safe Telegram getUpdates status/fetch helper
- `response_routing.py` — source-aware response envelope and conservative route decisions
- `telegram_response.py` — token-safe Telegram response preview/manual-send helper
- `markitdown_adapter.py` — document-to-Markdown `.input` preview/write helper
- `markitdown_batch.py` — bounded document batch inventory/apply helper
- `models.py`       — Pydantic schemas per node type
- `prompts.py`      — Qwen3 system prompts and few-shot examples
- `openai_fallback.py` — review-first OpenAI fallback using Responses API structured output
- `entity_state.py` — JSON working memory for recently seen contacts/entities
- `vault_graph.py`  — NetworkX graph builder for testable Sprockets parent resolution
- `review.py`       — interactive CLI for approving/discarding review items
- `scripts/review`  — venv-aware wrapper for review count/list/report/interactive modes
- `scripts/smoke`   — venv-aware wrapper for deterministic temp-vault smoke test
- `scripts/check`   — operational sanity check: tests + smoke + review count
- `smoke_test.py`   — deterministic temp-vault smoke test with model calls stubbed
- `tools.py`        — date/time tool definitions
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
| `scripts/input-adapter-preview` | `input_adapter_preview.py` | Rosie | Preview or explicitly write adapter-produced `.input` files. | Mixed: preview is read-only; `--write --input-dir` writes one `.input` file. |
| `scripts/telegram-adapter-preview` | `telegram_adapter_preview.py` | Rosie | Preview or explicitly write a Telegram update as a `.input` file. | Mixed: preview is read-only; `--write --input-dir` writes one allowlisted `.input` file. |
| `scripts/telegram-update-probe` | `telegram_update_probe.py` | Rosie | Inspect Telegram token/allowlist readiness and optionally fetch updates without printing the token. | Mixed: status/fetch are read-only; `--write-update-json` writes one local JSON file for preview. |
| `scripts/telegram-response` | `telegram_response.py` | Rosie / output adapter | Preview or explicitly send a conservative Telegram acknowledgement/status response. | Mixed: preview is read-only; `--send` contacts Telegram after route guards pass. |
| `scripts/markitdown-preview` | `markitdown_adapter.py` | Rosie / adapter layer | Preview or explicitly write converted document Markdown as a `.input` file. | Mixed: preview is read-only; `--write --input-dir` writes one `.input` file. |
| `scripts/markitdown-batch` | `markitdown_batch.py` | Rosie / Uniblab-visible adapter layer | Inventory a folder of documents and explicitly apply a bounded batch as `.input` files. | Mixed: plan is read-only; `--apply --input-dir` writes bounded `.input` files. |
| `scripts/job-status` | `job_status.py` | Uniblab | Read-only timer/job status. | No. |
| `scripts/job-supervisor` | `job_supervisor.py` | Uniblab | Preview install/disable/recovery commands for maintenance jobs. | No. |
| `scripts/sc-backup` | `sc_backup.py` | Uniblab | Preview SC operational backup scope before any archive/restore work. | No. |
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

Runtime directories are outside the repo under the configured SC root:
`input/`, `processing/`, `archive/`, `review/`, and `output/`. The vault is also
outside the repo. Tests and dry-runs should use environment overrides rather
than writing to live paths.

## CLI posture inventory

Stage 50A groups script commands by their operational posture. This is the
starting point for help text, exit behavior, and error-message cleanup.

| Posture | Commands | Rule of thumb |
|---|---|---|
| Read-only reports | `scripts/status`, `scripts/job-status`, `scripts/sc-backup --preview`, `scripts/hierarchy`, `scripts/retrieval-traces`, `scripts/telegram-update-probe --status`, `scripts/sprockets-specialist --inventory`, `scripts/cogs-specialist --inventory`, `scripts/memory-specialist --inventory`, `scripts/review-specialist --inventory` | Safe to run during exploration. Empty reports should usually exit successfully and explain that there is nothing to show. |
| Read-only previews | `scripts/capture-preview`, `scripts/input-adapter-preview`, `scripts/telegram-adapter-preview`, `scripts/telegram-response` without `--send`, `scripts/markitdown-preview`, `scripts/markitdown-batch`, `scripts/retrieval-preview`, `scripts/orchestrator-route`, `scripts/orchestrated-rehearsal`, `scripts/cogs-specialist --carry-preview`, `scripts/cogs-specialist --planning-preview`, `scripts/sprockets-specialist --propose`, `scripts/review-specialist --apply-preview` | Should say "preview" or "without writing" in help text and output. |
| Benchmarks and probes | `scripts/check`, `scripts/smoke`, `scripts/retrieval-eval`, `scripts/fallback-eval`, `scripts/memory-tool-probe`, `scripts/memory-specialist --benchmark`, `scripts/memory-specialist --cache-coverage` | May use temp files, model calls, API calls, or embedding cache, but should not write the live vault. |
| Operational-output writers | `scripts/review-specialist --write-packet`, `scripts/agent-message-bus --append`, `scripts/telegram-update-probe --write-update-json ...`, memory trace JSONL written by the service | Write outside the vault under SC output/message-bus paths. Help text should name the target path when practical. |
| Guarded vault writers | `scripts/carry --apply`, `scripts/nightly`, `scripts/cogs-planning --create`, `scripts/cogs-planning --ensure-current`, `scripts/review` interactive apply/discard flows | Should have a dry-run, preview, report, or source-check path before writes. Validation failures should exit nonzero. |
| Guarded input writers | `scripts/input-adapter-preview --write --input-dir ...`, `scripts/telegram-adapter-preview --write --input-dir ...`, `scripts/markitdown-preview --write --input-dir ...`, `scripts/markitdown-batch --apply --input-dir ...` | Writes only `.input` files into an explicitly selected input directory; refuses existing final files. |
| Guarded source replies | `scripts/telegram-response --send ...` | Contacts Telegram only after response-route guards pass. Review-required/operator-report/local-reflection outputs stay local. |
| Service and job controls | `systemctl --user ...`, commands previewed by `scripts/job-supervisor` | `scripts/job-supervisor` remains preview-only; actual service/timer changes happen through explicit system commands. |

Naming guidance:

- `preview` means no live writes.
- `report`, `status`, `inventory`, and `list` should be read-only.
- `apply`, `create`, `ensure`, `append`, and `write-packet` signal writes and
  should say where they write.
- Validation or source-check failures should exit nonzero; "nothing to do" should
  usually be a successful, explicit result.

CLI implementation guidance:

- Prefer `main(argv: Sequence[str] | None = None)` for script modules so tests
  can exercise parser behavior without mutating `sys.argv`.
- Use `parser.error(...)` for invalid CLI input. It gives a consistent usage
  summary and exits with code 2.
- Use `SystemExit(1)` for valid command syntax that discovers an operational
  failure, such as an invalid plan or stale source check.
- Catch parse errors at the CLI boundary when the default exception would show a
  traceback for ordinary user input, such as invalid JSON passed to `--payload`.
- Keep read-only command output explicit about zero-result success. A clean
  "No items found" is better than silence.

## Input adapter contract

Phase 6 introduces a shared adapter boundary for non-file inputs. Bots,
MarkItDown, future voice input, and other source adapters should all normalize
external content into `.input` files for Rosie. They should not call the
classifier directly, write vault files directly, or bypass the existing
processing/archive/review behavior.

Current contract:

- use `InputEnvelope` for normalized external content;
- use `InputAttachment` for metadata-only attachment references;
- use `render_input_file()` to produce frontmatter plus body text;
- use `input_filename()` for deterministic `.input` names;
- use `write_input_file()` for atomic writes into a chosen input directory;
- use `scripts/input-adapter-preview` before writing.

The rendered `.input` file includes adapter metadata such as `source`,
`session_id`, `modality`, `source_id`, `idempotency_key`, `metadata`, and
`attachments`. Rosie currently consumes only the body text and `session_id`;
the rest is preserved for audit, future routing, and response work.

Safety rules:

- default adapter CLI behavior is read-only;
- writes require `--write --input-dir`;
- writes use a temporary sibling file and then rename to the final `.input`
  path;
- existing final files are refused by the CLI;
- adapters must write only to `input/`, never directly to `processing/`,
  `archive/`, the vault, or the review queue;
- response routing is source-aware, conservative, and does not change adapter
  input writes.

Useful examples:

```bash
scripts/input-adapter-preview --source cli --session-id demo "Capture this"
scripts/input-adapter-preview --json --source markitdown --modality document "Summarize this"
scripts/input-adapter-preview --write --input-dir /tmp/sc/input --source cli --session-id demo "Capture this"
```

## Telegram input adapter

Stage 54 starts the first bot-style source with Telegram polling as the intended
runtime model. The committed code does not contain secrets and the preview CLI
does not call Telegram. It works from a local `getUpdates`-style JSON object so
the transformation can be tested without network access.

Private runtime settings live outside the repo:

- `SPROCKETS_COGS_TELEGRAM_BOT_TOKEN` — bot token from BotFather;
- `SPROCKETS_COGS_TELEGRAM_ALLOWED_USER_IDS` — comma-separated allowed user ids;
- `SPROCKETS_COGS_TELEGRAM_ALLOWED_CHAT_IDS` — comma-separated allowed chat ids;
- `SPROCKETS_COGS_TELEGRAM_POLLING=1` — records that polling, not webhooks, is
  the Stage 54 posture.

Safety rules:

- no allowlist means no Telegram writes;
- preview mode can show whether a local update would be accepted;
- `--write` still requires an explicit `--input-dir`;
- Telegram adapters write `.input` files only and do not bypass Rosie;
- automatic bot replies are deferred; manual replies use the response/output
  routing helper.

Useful example:

```bash
scripts/telegram-update-probe --status
scripts/telegram-update-probe --fetch --limit 5 --write-update-json /tmp/telegram-update.json
scripts/telegram-adapter-preview --update-json /tmp/telegram-update.json
```

## Telegram response/output routing

Stage 55 adds source-aware response routing without changing Rosie’s live
service behavior. The live `send_response()` function still appends a local
daily Cog reflection. It does not inspect Telegram metadata and does not call
the Telegram response adapter.

The response contract separates response intent from delivery:

- `acknowledgement`, `processed`, and `error` may become short Telegram replies
  when the source is Telegram and a chat id is present;
- `review_required`, `local_reflection`, and `operator_report` stay local and
  review-first;
- non-Telegram sources stay local until a future source-specific adapter is
  deliberately added.

The Telegram response helper defaults to preview mode and prints no token:

```bash
scripts/telegram-response --chat-id 783798616 "Queued."
scripts/telegram-response --input-file /path/to/telegram.input "Queued."
```

Actual sends require explicit `--send`:

```bash
scripts/telegram-response --chat-id 783798616 --send "Queued."
```

Safety rules:

- no automatic replies from `sprockets-cogs.service`;
- no review-required or operator-only output is sent to Telegram;
- no raw review packet, retrieval trace, vault path, model debug output, or
  token value should be sent or printed;
- reply text should be short status text, not model-generated reasoning;
- automatic bot acknowledgement is a future stage, not part of Stage 55.

## MarkItDown document adapter

Stage 56 starts document ingestion as an adapter layer. Documents are converted
to Markdown and wrapped in the same `InputEnvelope` contract used by other
sources. The adapter does not classify content and does not write directly to
the vault.

The current command can preview or explicitly write one `.input` file:

```bash
scripts/markitdown-preview /path/to/document.md
scripts/markitdown-preview /path/to/document.md --write --input-dir /tmp/sc/input
```

Text and Markdown files work without an extra dependency. PDF, Office, and
other rich document formats require the optional `markitdown` package to be
installed in the environment.

Safety rules:

- preview is the default;
- writes require `--write --input-dir`;
- large files are rejected before conversion;
- long converted Markdown is truncated and marked `review_recommended`;
- converted content enters through `.input`, not through a direct vault write;
- source path, file hash, converter, truncation, and review metadata are
  preserved in frontmatter for Jane/future audit.

## MarkItDown batch adapter

Stage 57 adds a batch wrapper around the same single-document adapter. It does
not add a separate ingestion core and does not write directly to the vault.

Dry-run inventory is the default:

```bash
scripts/markitdown-batch /path/to/documents
scripts/markitdown-batch /path/to/documents --recursive --json
```

Apply is explicit, bounded, and idempotent:

```bash
scripts/markitdown-batch /path/to/documents --apply --input-dir /tmp/sc/input --limit 5
```

Safety rules:

- plans report ready, unsupported, too-large, conversion-error, and
  requires-MarkItDown files;
- rich PDF/Office/image candidates are reported as requiring MarkItDown when
  the optional dependency is not installed;
- apply attempts only ready files up to `--limit`;
- existing deterministic `.input` outputs are skipped instead of duplicated;
- unsupported files are reported clearly and never written;
- generated files still enter through Rosie as `.input`.

## Runtime data flow

Stage 46B maps the live Rosie pipeline before refactoring it.

```text
sprockets-cogs.service
  -> agentic_loop.main()
  -> ensure_runtime_dirs()
  -> watchdog Observer on SC input/
  -> process_existing_inputs() for startup backlog
  -> InputHandler.on_created() for new *.input files
  -> process_input(path)
```

`process_input()` is the central live write path:

```text
SC input/<name>.input
  -> move to SC processing/<name>.input
  -> parse frontmatter/content/session_id
  -> build_context_for_input(content)
       -> build_context()
          -> today's Cogs items
          -> hot contact/entity hints
          -> hierarchy parent target titles
       -> optional prompt-appended memory context only if
          SPROCKETS_COGS_MEMORY_CONTEXT=1
  -> extract_nodes(content)
  -> classify_nodes(raw_nodes, context)
  -> apply_explicit_hierarchy_hints()
  -> ensure_hierarchy_tasks()
  -> memory_parent_trace(content)
       -> retrieve_relevant_nodes(content) if memory retrieval is enabled
       -> select first retrieved hierarchy parent, if any
       -> log compact trace
       -> append JSONL trace under SC output/
  -> ensure_memory_hierarchy_tasks()
  -> apply_memory_parent_title()
  -> ensure_cogs_companions()
  -> validate_output()
```

After validation, the flow branches:

| Branch | Condition | Destination |
|---|---|---|
| Low confidence | Valid shape but `confidence: low` | OpenAI fallback if enabled; otherwise vault `review/`. |
| Invalid shape | Pydantic/model validation failed | One local retry with error context, then OpenAI fallback if enabled, otherwise vault `review/`. |
| OpenAI fallback candidate | Fallback returns candidate nodes | Always routed to vault `review/`; never direct-write. |
| Ambiguous hierarchy parent | Valid node has unresolved ambiguous `parent_hint` | Vault `review/`. |
| Valid resolved node | Valid and not routed to review | Cogs daily append or Sprockets node write. |
| Duplicate resolved node | Same node key already seen in current input | Skipped with a warning. |
| Successful input | Write loop completes | Reflection appended to today's Cogs note; input moved to SC `archive/`. |
| Unexpected exception | Any unhandled processing error | Input remains in SC `processing/` for inspection. |

Live write destinations:

- Cogs daily items: `VAULT_DIR/Cogs/daily/` via `vault.ensure_daily_note()` and
  `vault.append_cogs_item_text()`.
- Sprockets task/contact/entity/note files: `VAULT_DIR/Sprockets/...`.
- Review packets: `VAULT_DIR/review/`.
- Memory-parent trace JSONL: `SC output/memory-parent-traces.jsonl` or
  `SPROCKETS_COGS_MEMORY_TRACE_PATH`.
- Entity working memory: configured by `SPROCKETS_COGS_ENTITY_STATE_PATH`.
- Processed input archive: `SC archive/`.

Important safety boundaries:

- Prompt-appended memory context is off by default and should remain off unless
  a future contamination-resistant design is proven.
- Production retrieval is used only as a post-classification structural guard.
- OpenAI fallback is review-first only.
- The message bus is not part of the live `process_input()` path.
- If processing fails unexpectedly, the source input is not archived; it stays
  in `processing/` so the failure is inspectable.

## Classifier context seam

Stage 49 extracted classifier context assembly from the live loop while
preserving behavior.

Current behavior:

- `classifier_context.py` owns base classifier context assembly and
  input-specific memory-context appending.
- `agentic_loop.build_context()` and `agentic_loop.build_context_for_input()`
  remain live-loop wrappers around the context seam.
- Base context includes today's Cogs checkbox items, hot contact/entity names,
  and compact hierarchy parent targets from Sprockets frontmatter.
- `_build_hierarchy_context()` delegates through the Sprockets specialist facade
  and reads frontmatter only; note bodies stay out of classifier context.
- `agentic_loop.build_context_for_input(input_text)` starts with base context
  and appends compact retrieved memory only when
  `SPROCKETS_COGS_MEMORY_CONTEXT` is enabled.
- `capture_preview.py` imports `classifier_context.build_default_context()` for
  read-only previews, while tests can still pass an explicit `context=`
  override or patch `capture_preview.build_context`.

Boundary rules:

- Keep `agentic_loop.py` as the live orchestration owner.
- Keep capture preview read-only and pointed at the context seam, not the live
  watcher.
- Preserve the default safety posture: prompt-appended memory context remains
  disabled unless explicitly enabled.

Tests that protect the seam:

- `test_stage_49_classifier_context.py` covers base context composition,
  memory-context empty behavior, and capture preview's context seam.
- `test_stage_10a_parent_resolution.py` covers hierarchy context content.
- `test_stage_17_production_retrieval.py` covers memory-context disabled/enabled
  behavior for `build_context_for_input()`.
- `test_stage_38_extractor_classifier.py` covers capture preview using the
  context builder and explicit context injection.

## Module responsibility map

Stage 46C groups modules by ownership before any package or import refactor. Use
this map to find the right starting point for a change.

### Specialist-owned modules

| Owner | Modules | Responsibility |
|---|---|---|
| Rosie | `agentic_loop.py`, `extractor_classifier.py`, `capture_preview.py` | Live intake, local extraction/classification calls, capture preview, and the central processing pipeline. |
| RUDI | `orchestrator_contract.py`, `orchestrated_rehearsal.py`, `agent_message_bus.py` | Route decisions, handoff contracts, read-only orchestration rehearsal, and message-bus contract/preview behavior. |
| RUDI memory | `memory_specialist.py`, `memory_index.py`, `memory_guards.py`, `memory_packets.py`, `memory_packets_cli.py`, `memory_trace_log.py`, `memory_tool_probe.py`, `production_retrieval.py`, `embeddings.py`, `retrieval_*.py`, `vector_math.py` | Retrieval, embeddings, memory cache/index contracts, benchmark strategies, packet previews, traces, and post-classification memory guards. |
| Cogs | `cogs_specialist.py`, `cogs_planning.py`, `cogs_naming.py`, `carry.py`, `nightly.py`, `vault.py` | Planning notes, daily note naming, carry/reconciliation, nightly behavior, and Cogs daily-note primitives. |
| Sprockets | `sprockets_specialist.py`, `vault_graph.py`, `inspect_hierarchy.py` | Hierarchy graph reading, parent resolution previews, graph inspection, and proposal/review-first structural behavior. |
| Jane | `review.py`, `review_specialist.py` | Review queue reporting, packet preview/write, decision import preview, guarded apply preview, and interactive review. |
| Uniblab | `system_status.py`, `job_status.py`, `job_supervisor.py`, `smoke_test.py` | Operational status, timer/job visibility, maintenance previews, and smoke-test verification. |

### Shared foundation modules

| Module | Shared role | Notes |
|---|---|---|
| `models.py` | Pydantic node schemas and validation | Used across live processing, review, specialists, and tests. Treat changes as schema changes. |
| `prompts.py` | Local-model prompt contracts and structured examples | Changes affect Rosie extraction/classification behavior. Add benchmark or preview coverage. |
| `openai_fallback.py`, `fallback_eval.py` | Review-first OpenAI fallback path and evaluator | Must remain review-first unless a separate safety decision changes it. |
| `entity_state.py` | Contact/entity working memory | Supports context hints and dedupe behavior. |
| `slug_utils.py` | Shared slug behavior | Keep filename/title truncation consistency here rather than duplicating slug rules. |
| `tools.py` | Date/time tool definitions | Currently a small legacy surface for model/tool-related work. |
| `specialists/catalog.py` | Importable specialist metadata | Public/status map, not a runtime ownership switch. |

### Test responsibility map

| Test group | Protects |
|---|---|
| `test_stage_10a_parent_resolution.py`, `test_stage_40_sprockets_specialist.py` | Sprockets hierarchy and parent matching behavior. |
| `test_stage_14_5_*`, `test_stage_26_cogs_naming.py`, `test_stage_27_*`, `test_stage_39_cogs_specialist.py` | Cogs carry, planning, naming, nightly, and scheduled-job behavior. |
| `test_stage_15_*` through `test_stage_24_*`, `test_stage_41_memory_specialist.py` | RUDI memory/retrieval, embeddings, vector math, traces, packets, and tool-call readiness. |
| `test_stage_37_*`, `test_stage_43_*`, `test_stage_44_*` | RUDI orchestration contracts, message bus, and end-to-end rehearsal. |
| `test_stage_38_extractor_classifier.py` | Rosie extraction/classification boundary. |
| `test_stage_42_review_specialist.py` | Jane review facade, packets, decision import, and guarded apply preview. |
| `test_stage_32_system_status.py`, `test_stage_45_specialist_catalog.py`, `test_model_config.py` | Uniblab/status, specialist catalog, and model configuration surfaces. |
| `test_slug_utils.py`, `smoke_test.py` | Shared filename behavior and deterministic whole-loop smoke coverage. |

Responsibility rule of thumb: change the owning specialist module first, shared
foundation modules second, and `agentic_loop.py` only when a live-pipeline seam
must be adjusted. If a change crosses multiple owners, add or update a test at
the boundary before moving behavior.

## Dependency tour

Stage 46D records the current import direction before any dependency cleanup.
This is a map, not a refactor request.

### Healthy dependency spine

Most imports follow this shape:

```text
scripts/*
  -> CLI/facade modules
  -> specialist modules
  -> shared foundations
  -> standard library / third-party libraries
```

Useful foundation modules:

- `models.py` is the schema/validation anchor.
- `slug_utils.py`, `vector_math.py`, and `cogs_naming.py` are small shared
  utility modules.
- `vault.py` owns low-level Cogs daily-note primitives.
- `vault_graph.py` owns Sprockets graph reads.
- `retrieval_types.py` owns retrieval dataclasses shared by retrieval modules.
- `prompts.py` owns local-model prompt contracts.

Specialist facades generally sit one layer above these foundations:

- Cogs facades import `carry.py`, `cogs_planning.py`, `nightly.py`, and
  `vault.py`.
- Sprockets facades import `vault_graph.py`, `inspect_hierarchy.py`, and
  `slug_utils.py`.
- RUDI memory facades import retrieval, embeddings, trace, and preview modules.
- Jane facades import `review.py` and `models.py`.
- Uniblab status modules import other modules to summarize posture, not to own
  their behavior.

### Cross-boundary seams to watch

| Import seam | Current reason | Later refactor thought |
|---|---|---|
| `review.py` imports `agentic_loop.ARCHIVE_DIR`, `REVIEW_DIR`, and `write_node` | Interactive approve/discard reuses the live write path and paths. | A future Jane apply module could depend on a smaller write/review-path interface instead of the whole live loop. |
| `capture_preview.py` imports `agentic_loop.build_context` | Preview wants the same classifier context as Rosie. | If context building is extracted, preview and Rosie can share it without importing the live watcher module. |
| `system_status.py` imports `agentic_loop`, `review`, retrieval, embeddings, and job modules | Uniblab summarizes current runtime configuration and paths. | This is acceptable for read-only status, but keep it from becoming a behavior owner. |
| `production_retrieval.py` imports `retrieval_eval` | Production adapter reuses benchmark retriever construction. | If retrieval grows, extract shared retriever construction out of the eval facade. |
| `retrieval_preview.py` imports `retrieval_eval` and `production_retrieval` | Preview compares experimental and production retrieval surfaces. | Acceptable while preview-only; avoid making production depend on preview. |
| `retrieval_eval.py` imports `agentic_loop` for the `current` retriever mode | Benchmarks compare against production behavior. | Keep this one-way from eval to production; do not let live code depend on eval-only cases. |
| `nightly.py` imports `cogs_specialist` inside a report path while `cogs_specialist.py` imports `nightly.py` | Keeps existing CLI behavior while adding specialist report delegation. | Watch for circular import pressure; prefer explicit facade seams if this grows. |

### Dependency rules for Phase 5 refactors

- Prefer extracting a small shared module when two specialists need the same
  behavior.
- Keep live writes behind narrow functions that tests can exercise.
- Keep production modules from depending on benchmark or preview facades unless
  the dependency is deliberately temporary and documented.
- Read-only status/report modules may import broadly, but they should not become
  write owners.
- Avoid moving files into `specialists/*` until imports are boring enough that a
  package move is mostly mechanical.

## Test coverage and fixtures

Stage 46E maps the current safety net before improving it.

Run the full local gate with:

```bash
scripts/check
```

That command runs `python -m unittest discover -v`, the deterministic smoke
test, fallback contract checks, and the pending review count.

### Test suite shape

The suite currently uses `unittest`, not `pytest`. Most tests are named by the
stage that introduced the behavior. That history is useful, but Phase 5 may add
more behavior-oriented names when it clarifies long-lived contracts.

| Test cluster | Main files | Protects |
|---|---|---|
| Live loop and hardening | `test_stage_10a_parent_resolution.py`, `test_stage_13_5.py`, `test_model_config.py`, `smoke_test.py` | Parent resolution, review routing, fallback posture, runtime env/model config, and whole-loop temp-vault behavior. |
| Cogs planning/carry/jobs | `test_stage_14_5_carry.py`, `test_stage_14_5_nightly.py`, `test_stage_26_cogs_naming.py`, `test_stage_27_job_status.py`, `test_stage_27_job_supervisor.py`, `test_stage_39_cogs_specialist.py` | Cogs note parsing, carry apply safety, nightly/report behavior, naming, planning notes, timer/job status, and Cogs specialist facade. |
| Retrieval and memory | `test_stage_15_retrieval_eval.py`, `test_stage_16_embeddings.py`, `test_stage_17_*`, `test_stage_19_*`, `test_stage_20_graph_retrieval.py`, `test_stage_22_memory_packets.py`, `test_stage_24_memory_tool_probe.py`, `test_stage_41_memory_specialist.py` | Retrieval benchmark behavior, embeddings/cache, memory index, production retrieval guard, traces, graph/packet retrieval, tool-call probes, and memory specialist facade. |
| Orchestration and specialists | `test_stage_37_orchestrator_contract.py`, `test_stage_38_extractor_classifier.py`, `test_stage_40_sprockets_specialist.py`, `test_stage_42_review_specialist.py`, `test_stage_43_agent_message_bus.py`, `test_stage_44_orchestrated_rehearsal.py`, `test_stage_45_specialist_catalog.py` | Route contracts, model-call boundary, hierarchy facade, review facade, message-bus contract, end-to-end rehearsal, and specialist catalog. |
| Shared utilities | `test_slug_utils.py`, `test_stage_17_5_vector_math.py`, `test_stage_17_5_memory_guards.py` | Filename slug behavior, vector scoring, and pure memory guard helpers. |

### Common fixture patterns

- `tempfile.TemporaryDirectory()` is the dominant filesystem fixture.
- Tests build temporary vaults and SC roots directly with `Path`.
- `unittest.mock.patch` stubs model calls, embedding calls, subprocess calls,
  environment variables, and CLI arguments.
- Smoke testing imports `agentic_loop` after setting temporary environment
  variables so the module-level paths point at test directories.
- Retrieval tests frequently patch `embeddings.build_embedding_index()` and
  `embeddings.embed_text()` so they do not need a live Ollama embedding call.
- Review/Cogs/Sprockets tests create small Markdown/frontmatter fixtures rather
  than using the real vault.

### Testing gaps to keep in mind

- There is no shared temp-vault fixture module yet; many tests repeat similar
  `TemporaryDirectory()` setup.
- Many tests are stage-named. That is good history, but some long-lived behavior
  would be easier to find with behavior-oriented test names.
- `agentic_loop.py` is protected by several tests and the smoke test, but its
  internal seams are still broad. Extracting behavior should add focused tests
  beside the extracted module.
- Some CLI behavior is tested through patched `sys.argv` and `print`; broader
  subprocess-style CLI tests should be added only where they catch real risk.
- Retrieval benchmark tests are intentionally large because they preserve
  measured behavior. Refactor them carefully and keep benchmark outputs stable.

Phase 5 testing rule: before moving behavior, identify the existing test that
protects it. If the protection is indirect or only smoke-level, add a focused
test first.

## Refactor candidate register

Stage 46F turns the codebase map into a ranked shortlist for safe Phase 5
refactors. This is a planning register, not a promise to move every file.
Candidates are ranked by:

- risk: how likely the change is to alter live behavior accidentally;
- learning value: how much the change teaches about Python structure, seams,
  and tests;
- user value: how directly the change improves reliability, readability, or
  future feature work.

### Recommended first candidates

| Rank | Candidate | Why | Risk | Learning value | User value | Safety net | Recommendation |
|---|---|---|---|---|---|---|---|
| 1 | Shared slug/title truncation cleanup | Live write paths and specialist helpers should agree on filename slug behavior. This is already a known review finding. | Low | Medium | High | `test_slug_utils.py`, Sprockets specialist tests, focused regression tests for canonical truncation. | Do first in Stage 47. |
| 2 | Context-building seam extraction | `capture_preview.py` imports `agentic_loop.build_context`; Rosie and preview need the same context without coupling preview to the live watcher. | Medium | High | Medium | Existing smoke test plus new focused tests for context output with memory context disabled/enabled. | Good early Phase 5 seam after slug cleanup. |
| 3 | Review apply/write seam | `review.py` imports live loop paths and `write_node`; Jane should depend on a smaller write/review interface. | Medium | High | Medium | Review specialist tests, review source-check tests, smoke test. | Do after context extraction, keeping live apply behavior unchanged. |
| 4 | Shared temp-vault test fixtures | Many tests repeat `TemporaryDirectory()` vault and SC-root setup. | Low | High | Medium | Add fixture helpers while preserving existing tests; migrate only a few tests at first. | Good Stage 48 learning slice. |
| 5 | Retriever construction seam | `production_retrieval.py` reuses benchmark retriever construction from `retrieval_eval`. | Medium | Medium | Medium | Retrieval benchmark tests, production retrieval tests, preview tests. | Defer until retrieval behavior changes again. |

### Watch list

| Candidate | Why to watch | Current recommendation |
|---|---|---|
| `agentic_loop.py` broad extraction | The live loop is still the largest behavior owner, but broad extraction would touch the riskiest path in the app. | Extract one pure seam at a time only after focused tests exist. |
| `nightly.py` / `cogs_specialist.py` report delegation seam | There is contained circular-import pressure around report behavior. | Leave alone unless Stage 27/Phase 6 planning work expands the interface. |
| CLI output/help consistency | Many scripts are user-facing and could share formatting conventions. | Useful polish, but lower priority than behavior seams. |
| Package moves into `specialists/*` | Visual separation helps explain the multi-agent design, but moving implementation too early increases import churn. | Keep `specialists/` as the visible role map until imports are boring enough for mechanical moves. |

### Stage 47 recommendation

The best first refactor is the shared slug/title truncation cleanup. It is
small, testable, already queued from review, and gives a good Python lesson:
extract one shared utility, align callers, add regression tests, and preserve
all live behavior.

### Slug/title boundary inspection

Stage 47A found that the canonical slug behavior already lives in
`slug_utils.slugify(text, max_length=60)`.

Current callers:

- `agentic_loop.py` uses slugging for live Sprockets filenames and fuzzy
  duplicate checks.
- `sprockets_specialist.py` uses slugging for review-only hierarchy proposal
  previews.
- `entity_state.py` uses slugging for contact/entity working-memory keys.

Current finding:

- There is no observed live-vs-preview truncation mismatch right now; the live
  writer and Sprockets proposal preview both route through `slug_utils.slugify`.
- Stage 47B added regression tests proving preview/live/entity-state slug
  behavior stays aligned for long titles.
- Stage 47C removed thin local `_slugify()` wrappers where they added no
  behavior.
- Stage 47D closed the slug cleanup as the right-sized module-boundary refactor
  and left larger seams for later stages.

## How to use this developer map

Stage 46G closes the map by turning it into a reading path for future work.

When changing the codebase, start here:

1. Identify the entry point in `Entry points`.
2. Follow the live or preview path in `Runtime data flow`.
3. Locate the owning specialist/domain in `Module responsibility map`.
4. Check import direction in `Dependency tour`.
5. Find the relevant safety net in `Test coverage and fixtures`.
6. If the work is a cleanup, compare it with `Refactor candidate register`.

Use this rule of thumb:

| Question | First section to read |
|---|---|
| Which command or service runs this behavior? | `Entry points` |
| Can this path write to the vault or runtime queues? | `Entry points`, then `Runtime data flow` |
| Which specialist owns this behavior? | `Module responsibility map` |
| Is this import direction healthy? | `Dependency tour` |
| Which tests protect the change? | `Test coverage and fixtures` |
| Is this a good Phase 5 refactor? | `Refactor candidate register` |

Before a behavior-changing refactor:

- Write down the behavior being preserved.
- Run or add the focused test that protects that behavior.
- Keep the first patch small enough to revert easily.
- Run `scripts/check` before committing.

For documentation-only map updates, `git diff --check` is usually enough. For
code changes, use `scripts/check` as the local gate.

## Test architecture notes

Stage 48 began the test architecture pass by inspecting repeated setup before
creating shared helpers.

Current findings:

- The suite should remain on `unittest` for now. A pytest migration may be
  useful later, but switching frameworks is larger than the current Phase 5
  goal.
- `TemporaryDirectory()` setup is repeated heavily across the suite. The
  repetition is sometimes valuable because each test shows its filesystem
  contract plainly.
- Several test files define nearly identical `write_node()` helpers for
  Sprockets Markdown fixtures:
  - `test_stage_10a_parent_resolution.py`
  - `test_stage_15_retrieval_eval.py`
  - `test_stage_20_graph_retrieval.py`
  - `test_stage_40_sprockets_specialist.py`
- Runtime directory setup is also repeated in live-loop/status tests:
  `input/`, `processing/`, `archive/`, `review/`, `output/`, and temporary
  vault roots.

Current helper rule:

- Use `tests.helpers.write_sprockets_node()` when a test needs a simple
  `Sprockets/<folder>/<slug>.md` fixture.
- Omit `body` when the fixture should be a heading-style note body:
  `# <slug>`.
- Pass `body=` explicitly when the test needs custom note text.
- Keep local setup when the fixture is testing a production writer, a mock
  boundary, or a one-off malformed file.
- Do not hide important runtime directories behind broad helpers yet. Repeated
  `TemporaryDirectory()` setup is acceptable when it makes a test's contract
  easier to read.

Stage 48 added the shared Sprockets node writer and migrated the heading-style
fixtures in the Stage 10A parent-resolution tests and Stage 40 Sprockets
specialist tests. Retrieval benchmark fixtures were left local for now because
they use custom bodies and are easier to review separately.

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

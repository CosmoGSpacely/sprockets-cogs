# Evaluation

Sprockets-Cogs uses small, repeatable checks rather than one large benchmark.
The goal is to catch regressions in the agentic loop, review safety, and memory
retrieval before they affect the live vault.

## Main Gate

Run:

```bash
scripts/check
```

Current local result on 2026-05-18:

- unit tests: 453 passing
- smoke test: passed
- fallback contract: passed
- review queue: 0 items

The smoke test creates a temporary vault and verifies the core path:

```text
.input -> extract/classify -> validate -> write Sprockets/Cogs Markdown -> archive
```

## Retrieval Benchmarks

Retrieval is benchmarked separately from live writing. This is intentional:
benchmark modes can be explored without silently changing production behavior.

Useful commands:

```bash
scripts/retrieval-eval --retriever memory-embedding-gated-vault --case-set real-vault
scripts/retrieval-eval --retriever memory-embedding-graph-gated-vault --case-set real-vault
scripts/retrieval-eval --retriever memory-packet-embedding-gated-vault --case-set real-vault
```

Recent live-vault retrieval result from Phase 4 closeout:

| Retriever | Nodes | Result |
| --- | ---: | ---: |
| `memory-embedding-gated-vault` | 47 | 5/7 |
| `memory-embedding-graph-gated-vault` | 47 | 5/7 |
| `memory-packet-embedding-gated-vault` | 59 | 5/7 |

The current misses are useful rather than alarming:

- contact/entity benchmark targets shifted as the real vault evolved;
- the recent-Cogs benchmark expected an older daily note that is no longer in
  the top five after newer live notes were added.

Earlier Stage 20-23 checkpoints scored 7/7 on the then-current vault. The drop
to 5/7 is a reminder that real-vault benchmarks are living tests: they expose
benchmark drift as well as retrieval quality.

## Production Memory Safety

Production memory retrieval is guarded and compact. In the Phase 4 specialist
map, this is RUDI's memory function: retrieval informs post-classification
guards and previews, but it does not directly write to the vault.

Current live posture:

- `SPROCKETS_COGS_MEMORY_RETRIEVAL=1`
- `SPROCKETS_COGS_MEMORY_CONTEXT=0`

Prompt-appended memory context remains disabled because earlier rehearsals showed
contamination risk. The successful production pattern is post-classification
memory linking, where ordinary Python code applies constrained parent/task
hints after model output has already been validated.

Useful preview commands:

```bash
scripts/retrieval-preview --status
scripts/retrieval-preview --production-return "Need to write retrieval trace notes for Phase 3 - Memory Enhancement"
scripts/retrieval-preview --memory-guard "Need to write retrieval trace notes for Phase 3 - Memory Enhancement"
scripts/retrieval-traces --jsonl "$SPROCKETS_COGS_SC_ROOT/output/memory-parent-traces.jsonl" --limit 10
```

## Operational Status

Run:

```bash
scripts/status
```

Current operational status is inspected with `scripts/status`. A healthy local
deployment should report:

- service active/running;
- local model installed;
- embedding model installed;
- pending `.input` files: 0;
- review queue: 0;
- current weekly, monthly, and annual Cogs planning notes exist;
- nightly timer active/waiting;
- SC backup status visible through `scripts/sc-backup --status`;
- latest SC snapshot verifies with `scripts/sc-backup --verify`;
- vault backup still treated as separate point-in-time backup work beyond sync.

## Promotion Rule

New retrieval or autonomy features should be promoted only when they improve a
measured miss or make an existing safe behavior easier to inspect. Benchmark-only
features should stay benchmark-only until they have preview output, traces, and a
clear production safety boundary.

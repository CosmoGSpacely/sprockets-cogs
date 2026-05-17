# Evaluation

Sprockets-Cogs uses small, repeatable checks rather than one large benchmark.
The goal is to catch regressions in the agentic loop, review safety, and memory
retrieval before they affect the live vault.

## Main Gate

Run:

```bash
scripts/check
```

Current Phase 4 result on 2026-05-17:

- unit tests: 437 passing
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

Current closeout result on 2026-05-12 over the live vault:

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
scripts/retrieval-traces --jsonl /home/cosmo/sc/output/memory-parent-traces.jsonl --limit 10
```

## Operational Status

Run:

```bash
scripts/status
```

Current sampled result on 2026-05-12:

- service active/running;
- local model installed;
- embedding model installed;
- pending `.input` files: 0;
- review queue: 0;
- current weekly, monthly, and annual Cogs planning notes exist;
- nightly timer active/waiting;
- backup gap visible: vault and `/home/cosmo/sc` need point-in-time backup
  beyond Syncthing.

## Promotion Rule

New retrieval or autonomy features should be promoted only when they improve a
measured miss or make an existing safe behavior easier to inspect. Benchmark-only
features should stay benchmark-only until they have preview output, traces, and a
clear production safety boundary.

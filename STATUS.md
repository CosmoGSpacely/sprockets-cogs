# Sprockets-Cogs Status

Sprockets-Cogs is a working local prototype and learning project. It is not yet a
turnkey public application.

## Current Maturity

The project has completed its Phase 2 hardening work, Phase 3 memory groundwork,
and Stage 25 public-readiness MVP:

- typed Sprockets/Cogs writes;
- deterministic smoke test and unit tests;
- review-first fallback behavior;
- semantic memory benchmark harness;
- guarded production retrieval;
- retrieval traces and reports;
- memory tool-call readiness probe;
- public README, design note, license, CI workflow, and sensitive-data audit.

## Current Runtime Posture

- The service runs the file-based `agentic_loop.py` watcher.
- Local classification uses the configured Ollama model.
- OpenAI fallback is review-first when configured.
- Semantic memory retrieval can be enabled for compact post-classification guards.
- Prompt-appended memory context remains disabled.
- Nightly Cogs carry exists as a script but is not scheduled by the service.

## Known Limitations

- Public setup and configuration examples are intentionally deferred.
- Weekly, monthly, annual, and 5W planning notes are not maintained by the live
  loop.
- Higher-level hierarchy nodes are human-authored or review-approved.
- Native local tool calling is not production-ready for the current model tag.
- Memory packets and graph-expanded retrieval remain benchmark/preview features.
- The sensitive-data audit passed before the public repository flip.

## Verification

The main local gate is:

```bash
scripts/check
```

The latest Stage 25 gate covers unit tests, smoke test, fallback contract, and
review count.

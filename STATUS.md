# Sprockets-Cogs Status

Sprockets-Cogs is a working local prototype and learning project. It is not yet a
turnkey public application.

## Current Maturity

The project has completed its Phase 2 hardening work and most of the Phase 3
memory groundwork:

- typed Sprockets/Cogs writes;
- deterministic smoke test and unit tests;
- review-first fallback behavior;
- semantic memory benchmark harness;
- guarded production retrieval;
- retrieval traces and reports;
- memory tool-call readiness probe.

Stage 25 is focused on public and portfolio readiness.

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
- The project still needs a sensitive-data audit before a public repository flip.

## Verification

The main local gate is:

```bash
scripts/check
```

At the start of Stage 25, this gate covered unit tests, smoke test, fallback
contract, and review count.

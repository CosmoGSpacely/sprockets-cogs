# Demo Walkthrough

This is a text demo of the current local workflow. It is meant to show the shape
of the system without requiring access to the author's private vault.

## 1. Submit An Input

Create a `.input` file in the configured input directory:

```text
Need to write retrieval trace notes for Phase 3 - Memory Enhancement.
```

In the local setup, the service watches the configured SC input directory.

## 2. Rosie Processes It

Rosie, the live intake/classifier service:

1. moves the file into processing;
2. extracts candidate items;
3. classifies them into typed Sprockets/Cogs schemas;
4. validates with Pydantic;
5. applies guarded memory parent hints;
6. writes Markdown;
7. archives the input.

For this kind of input, the expected result is:

- a Cogs daily item for the current work;
- a Sprockets task;
- a parent link to the existing `Phase 3 - Memory Enhancement` project, if the
  memory guard selects it confidently.

## 3. Ask RUDI To Preview Memory Before A Live Write

Use the preview command before trusting a memory-linked live write:

```bash
scripts/retrieval-preview --memory-guard "Need to write retrieval trace notes for Phase 3 - Memory Enhancement"
```

This shows whether the guard would select a hierarchy parent, skip parenting, or
add no memory-derived task.

RUDI owns this reasoning/retrieval preview role. In production, the retrieved
memory remains compact and guarded rather than being appended directly into the
classifier prompt.

## 4. Ask Uniblab To Inspect The System

Run:

```bash
scripts/status
```

The status command reports service state, runtime queues, local model
availability, review count, planning-note presence, nightly timer posture, and
backup/sync gaps.

## 5. Jane Handles Review Safety

If the model output is malformed, low-confidence, ambiguous, or produced by
OpenAI fallback, the item is routed to the review queue instead of being written
silently.

Useful commands:

```bash
scripts/review --count
scripts/review --report
scripts/review --packet-preview
```

## 6. Run The Gate

Run:

```bash
scripts/check
```

The current local gate passes 449 tests, a temp-vault smoke test, fallback
contract checks, and review count 0.

## What This Demonstrates

This demo path demonstrates the project's core design: a local-first
multi-agent loop where Rosie captures and classifies, RUDI retrieves and
reasons, Jane guards uncertainty, Uniblab reports operational posture, and
deterministic code validates, writes, and explains the result.

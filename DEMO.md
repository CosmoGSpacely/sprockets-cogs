# Demo Walkthrough

This is a text demo of the current local workflow. It is meant to show the shape
of the system without requiring access to the author's private vault.

## 1. Submit An Input

Create a `.input` file in the configured input directory:

```text
Need to write retrieval trace notes for Phase 3 - Memory Enhancement.
```

In the live setup, the service watches `/home/cosmo/sc/input`.

## 2. The Service Processes It

The loop:

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

## 3. Preview Memory Before A Live Write

Use the preview command before trusting a memory-linked live write:

```bash
scripts/retrieval-preview --memory-guard "Need to write retrieval trace notes for Phase 3 - Memory Enhancement"
```

This shows whether the guard would select a hierarchy parent, skip parenting, or
add no memory-derived task.

## 4. Inspect The System

Run:

```bash
scripts/status
```

The status command reports service state, runtime queues, local model
availability, review count, planning-note presence, nightly timer posture, and
backup/sync gaps.

## 5. Review Safety

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

The current closeout gate passes 318 tests, a temp-vault smoke test, fallback
contract checks, and review count 0.

## What This Demonstrates

This demo path demonstrates the project's core design: a local-first agentic loop
where the model proposes useful structure, but deterministic code validates,
guards, writes, and explains the result.

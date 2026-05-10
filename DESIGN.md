# Sprockets-Cogs Design

Sprockets-Cogs is designed around one practical question: how much useful
agentic behavior can a local-first system provide while still remaining
inspectable, reversible, and safe enough to write into a personal vault?

The answer so far is a deliberately narrow loop: capture text, extract typed
nodes, validate them, write Markdown, and use memory only through guarded seams.

## Core Loop

The production loop is file based. Source adapters or a person place `.input`
files into the configured input directory. The service moves each file through
processing and archive directories so there is a durable audit trail.

Processing has two model calls:

1. **Extract**: identify candidate tasks, contacts, entities, notes, or Cogs
   items from the raw input.
2. **Classify**: convert candidates into typed Sprockets-Cogs schemas.

After the model calls, ordinary Python code owns the safety-critical work:

- Pydantic validation rejects malformed outputs.
- Low-confidence outputs route to review.
- Duplicate checks avoid repeated node files.
- Parent resolution is constrained to existing hierarchy nodes.
- Markdown writes happen only after validation.

This split is intentional. The model proposes; the code validates, constrains,
and writes.

## Sprockets And Cogs

Sprockets are durable knowledge/work nodes: tasks, notes, contacts, entities, and
human-curated hierarchy nodes such as areas, goals, and projects.

Cogs are daily operational items. They are closer to a bullet journal: what is
open, carried, done, cancelled, or scheduled for attention.

The live loop currently writes classifier-created tasks, notes, contacts,
entities, and daily Cogs items. Higher-level hierarchy nodes are not invented by
ordinary capture text; they are human-authored or review-approved because they
shape the long-lived graph.

## Local-First Model Posture

The main classifier path uses a local Ollama model. This keeps routine capture
private, low-latency, and independent from hosted APIs.

OpenAI fallback is supported, but it is review-first:

- used only when configured;
- triggered by validation failure, retry failure, or low confidence;
- validated locally;
- routed to review rather than written directly to the vault.

That design treats hosted models as a rescue and comparison layer, not as an
unseen authority over the vault.

## Memory Design

Sprockets-Cogs has a semantic memory layer, but it is not simply pasted into the
classifier prompt.

Earlier rehearsals showed that prompt-appended memory could contaminate generated
fields: the model might copy retrieved context into the wrong place. The current
production design keeps prompt memory context off and uses memory after
classification through guarded code paths.

The safer memory path is:

1. Build compact retrieval candidates from the vault.
2. Score them with lexical, vector, and graph-aware strategies.
3. Gate results by confidence and trace quality.
4. After classification, use memory to choose safe parent/task links.
5. Log selected or skipped decisions without raw input text.

This gives the system useful memory behavior without asking the classifier to
read a pile of retrieved text and stay perfectly disciplined.

## Retrieval Architecture

The retrieval layer is benchmarked independently from production behavior.

Important pieces:

- `MemoryIndex` protocol for future storage backends.
- `InMemoryMemoryIndex` for current lexical/vector scoring.
- local embeddings from Ollama `nomic-embed-text`;
- JSON embedding cache keyed by node, model, and text hash;
- real-vault benchmark cases;
- preview commands for exact production retrieval payloads;
- JSONL trace records for memory parent guard decisions.

Current production retrieval is guarded and compact. Benchmark-only modes explore
graph expansion and memory packets, but those richer modes are not automatically
promoted into production.

## Tool-Call Boundary

Stage 24 tested whether the current local model endpoint could reliably choose
explicit memory tools.

It could not. Native Ollama tool calls returned an unsupported-tools error for
the current model tag, and JSON-contract imitation produced a plausible tool
choice while omitting a required argument.

The resulting design decision is conservative:

- do not wire memory tools into the live service yet;
- do not treat tool-shaped JSON as reliable tool use;
- keep semantic retrieval and post-classification guards as the production memory
  path;
- revisit tool calls only with repeated strict validation and a model endpoint
  that supports the required behavior.

## Review And Traceability

The project favors reviewable automation over silent autonomy.

Review surfaces include:

- review queue for malformed or low-confidence model outputs;
- `scripts/review` for manual review operations;
- retrieval preview commands;
- service-log trace parsing;
- JSONL memory-parent trace records.

This is especially important because Sprockets-Cogs writes to a personal vault.
The system should be able to explain why it linked a task to a project, or why it
declined to do so.

## Why Markdown

Markdown keeps the vault human-readable and editor-native. Obsidian is the main
interface, but the files remain ordinary text.

The tradeoff is that code must be careful about idempotence, duplicate detection,
frontmatter, and link semantics. The current design accepts that cost because the
human-readable substrate is central to the project.

## Future Direction

Near-term maturity work focuses on public readiness and productization:

- cleaner public documentation;
- sensitive-data audit;
- scheduled nightly/carry workflows;
- planning-note maintenance;
- review workflow improvements;
- memory index maintenance;
- optional future vector backend only when measured need appears.

The long-term research direction is a more capable local agent, but the current
system earns that by keeping each new autonomous behavior measured, traceable,
and reversible.

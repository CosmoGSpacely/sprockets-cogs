# Specialists

Phase 4 makes Sprockets-Cogs visibly multi-agent without splitting the runtime
into multiple daemons.

Only **Rosie** is currently always on. The other specialists are commands,
scheduled jobs, preview harnesses, or library-backed facades. This folder is the
public map of those agent boundaries; the core implementation modules remain at
the repository root until a deeper import-safe refactor is justified.

## Current Map

| Specialist | Role | Runtime form |
| --- | --- | --- |
| [Rosie](rosie/) | Intake and classification | Always-on file watcher service |
| [RUDI](rudi/) | Reasoning, orchestration, memory/retrieval | Commands, previews, library provider |
| [Cogs](cogs/) | Planning, carry, reconciliation | Commands and scheduled jobs |
| [Sprockets](sprockets/) | Hierarchy, graph, durable structure | Commands and review-first previews |
| [Jane](jane/) | Human-in-the-loop review | Commands and guarded apply previews |
| [Uniblab](uniblab/) | Operations, health, status | Commands, possible scheduled health checks |

## Message Bus Posture

The local message bus is a handoff contract and rehearsal surface. It is not a
live dispatch engine yet.

That means specialist handoffs can be previewed and tested without
automatically executing recipients or writing to the vault.


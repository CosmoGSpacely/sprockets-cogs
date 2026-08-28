# Specialists

Sprockets-Cogs uses named agentic boundaries without splitting the runtime into
multiple daemons too early.

Only **Rosie** is currently always on. The other boundaries are commands,
scheduled jobs, preview harnesses, or library-backed facades. This folder is the
public map and implementation home for those boundaries. Specialist-owned logic
belongs here; cross-boundary contracts belong in `substrate/`.

`substrate.time_context` and `substrate.format` hold date computation and Cogs
item formatting. They live in `substrate/` rather than under a specialist
because they are pure functions imported by Rosie, Cogs, and the capture
harness alike; a module three specialists depend on is a contract, not
specialist-owned logic. Temporal *policy* stays with Cogs.

`specialists.catalog` is the importable version of this map. It is safe to use
for docs, tests, and status displays, and it names the package-owned
implementation files.

`specialists.orbit.adapters` contains Orbit's source-adapter implementations.
Adapters feed Rosie by writing `.input` files; they do not write to the vault or
approve review packets.

`specialists.orbit` is the stable named facade for the Orbit boundary. Orbit is
not a decision-making specialist; it is the source-normalization layer in front
of Rosie.

`specialists.cogswell` is the package-owned database/collection bridge. It
connects deterministic catalog data to graph-visible resources without putting
database import into Rosie's intake loop.

`specialists.astro` owns the vault-facing surface: rendered notes, manual carry
affordances, and human-readable inspection views.

## Current Map

| Specialist | Role | Runtime form |
| --- | --- | --- |
| [Orbit](orbit/) | Source normalization and adapters | Adapter commands and foreground polling |
| [Rosie](rosie/) | Intake and classification | Always-on file watcher service |
| [RUDI](rudi/) | Reasoning, orchestration, memory/retrieval | Commands, previews, library provider |
| [Cogs](cogs/) | Planning, carry, reconciliation | Commands and scheduled jobs |
| [Sprockets](sprockets/) | Hierarchy, graph, durable structure | Commands and review-first previews |
| [Astro](astro/) | Vault surface and manual carry affordances | Library provider and vault-facing commands |
| [Cogswell](cogswell/) | Database and collection bridge | Commands and SQLite-backed graph resources |
| [Jane](jane/) | Human-in-the-loop review | Commands and guarded apply previews |
| [Uniblab](uniblab/) | Operations, health, status | Commands, possible scheduled health checks |

Supporting package boundaries:

- [Orbit adapters](orbit/adapters/) normalize Telegram, Discord, Open WebUI,
  and rich image/document source inputs into `.input` files for Rosie.
- `substrate/` is not a specialist. It holds shared product contracts and small
  cross-boundary helpers.

## Importable Catalog

```python
from specialists import iter_specialists

for specialist in iter_specialists():
    print(specialist.display_name, specialist.runtime_form)
```

## Message Bus Posture

The local message bus is a handoff contract and rehearsal surface. It is not a
live dispatch engine yet.

That means specialist handoffs can be previewed and tested without
automatically executing recipients or writing to the vault.

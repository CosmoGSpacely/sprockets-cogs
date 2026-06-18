# Specialists

Sprockets-Cogs uses named agentic boundaries without splitting the runtime into
multiple daemons too early.

Only **Rosie** is currently always on. The other boundaries are commands,
scheduled jobs, preview harnesses, or library-backed facades. This folder is the
public map and implementation home for those boundaries. Root modules may remain
as compatibility aliases, but specialist-owned logic belongs here.

`specialists.catalog` is the importable version of this map. It is safe to use
for docs, tests, and status displays, and it names the package-owned
implementation files.

`specialists.routing` is the cross-specialist read-only route probe used by
`scripts/specialist-route`. It exists here, rather than at repository root, so
all-specialist routing remains tied to the specialist boundary it exercises.

`specialists.adapters` contains Orbit's source-adapter promotion surfaces.
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
| [Rosie](rosie/) | Intake and classification | Always-on file watcher service |
| [RUDI](rudi/) | Reasoning, orchestration, memory/retrieval | Commands, previews, library provider |
| [Cogs](cogs/) | Planning, carry, reconciliation | Commands and scheduled jobs |
| [Sprockets](sprockets/) | Hierarchy, graph, durable structure | Commands and review-first previews |
| [Astro](astro/) | Vault surface and manual carry affordances | Library provider and vault-facing commands |
| [Jane](jane/) | Human-in-the-loop review | Commands and guarded apply previews |
| [Uniblab](uniblab/) | Operations, health, status | Commands, possible scheduled health checks |

Adjacent package-owned boundaries:

- [Source adapters](adapters/) normalize Telegram, Discord, Open WebUI, and
  rich image/document source inputs into `.input` files for Rosie.
- [Orbit](orbit/) names the source-normalization boundary that owns those
  adapters.
- [Cogswell](cogswell/) imports structured collection CSV data into SQLite,
  renders graph-visible Markdown resources, and preserves human notes.

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

# Sprockets

Sprockets is the hierarchy, graph, and durable structure specialist.

## Responsibility

Sprockets owns areas, goals, projects, hierarchy validation, parent matching,
graph inspection, and structural repair previews.

## Runtime Form

Sprockets is command-driven and review-first for higher-level hierarchy changes.

## Current Implementation

- `specialist.py`
- `vault_graph.py`
- `inspect_hierarchy.py`
- `models.py`
- `scripts/sprockets-specialist`
- `scripts/hierarchy`

## Boundaries

- Rosie should not freely invent areas, goals, or projects.
- Sprockets should propose and validate structural changes before any live write.
- Ambiguous or consequential hierarchy changes belong in Jane's review boundary.

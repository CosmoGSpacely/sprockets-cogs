# Cogswell

Cogswell is the deterministic collection/database bridge.

It is not part of Rosie's live intake loop. It imports structured collection
CSV data into SQLite, exposes query commands, and renders database rows into
graph-visible Markdown resources while preserving human-written body notes.

## Current Implementation

- `specialists/cogswell/collections.py`
- `scripts/collections-init`
- `scripts/collections-import`
- `scripts/collections-query`
- `scripts/collections-sync`
- `scripts/collections-bridge`

## Authority Split

- SQLite owns catalog facts.
- Markdown exposes stable identity and graph navigation.
- Markdown body text is human-authored and preserved on sync.
- LLM inference is not used for deterministic catalog import.

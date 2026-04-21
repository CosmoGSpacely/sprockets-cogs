# sprockets-cogs

Agentic loop for Sprockets (second-brain graph) and Cogs (calendar/diary/todo).
Obsidian-compatible Markdown files written by a local Qwen3 model on Rosie.

## Structure
- agentic_loop.py  — main loop, watchdog file watcher
- models.py        — Pydantic schemas for all node types
- prompts.py       — system prompts and few-shot examples
- tools.py         — date/time tool definitions for Qwen3

## Operational directories (/home/cosmo/sc/)
- sc/input/       — drop .input files here to trigger the loop
- sc/processing/  — files being actively processed
- sc/archive/     — processed inputs, audit trail
- sc/output/      — responses waiting for source adapters

## Vault
/home/cosmo/vault/ — Obsidian vault, synced via Syncthing

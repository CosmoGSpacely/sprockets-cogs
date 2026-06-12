# Source Adapters

Adapters normalize external sources into the shared `.input` contract.

They do not write to the vault, approve reviews, or bypass Rosie. Their job is
to create source-aware input files, preview acknowledgements, and expose adapter
status/rejection pressure.

## Current Implementation

- `specialists/adapters/telegram_polling.py`
- `specialists/adapters/source_surfaces.py`
- `scripts/telegram-poll`
- `scripts/discord-input-proof`
- `scripts/open-webui-input-proof`
- `scripts/source-ack`
- `scripts/adapter-status`

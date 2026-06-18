# Source Adapters / Orbit

Orbit is the named source-normalization boundary. The implementation lives here
in `specialists/orbit/adapters/`.

Adapters normalize external sources into the shared `.input` contract.

They do not write to the vault, approve reviews, or bypass Rosie. Their job is
to create source-aware input files, preview acknowledgements, and expose adapter
status/rejection pressure.

Orbit is not a decision-making specialist. It is an agentic boundary in front
of Rosie: external source -> Orbit -> `.input` -> Rosie.

## Current Implementation

- `specialists/orbit/adapters/telegram_polling.py`
- `specialists/orbit/adapters/source_surfaces.py`
- `specialists/orbit/adapters/rich_inputs.py`
- `scripts/telegram-poll`
- `scripts/discord-input-proof`
- `scripts/open-webui-input-proof`
- `scripts/rich-input-proof`
- `scripts/source-ack`
- `scripts/adapter-status`

`rich_inputs.py` preserves image/document resources, distinguishes extracted
text from ordinary resource input, and writes only `.input` records. It does not
create Cogs, appointments, bridge edges, or vault writes directly.

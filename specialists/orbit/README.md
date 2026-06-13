# Orbit

Orbit is the source-normalization boundary for Sprockets-Cogs.

It turns external signals into the shared `.input` contract:

- Telegram messages
- Discord proof messages
- Open WebUI proof messages
- image/document resources
- future audio and richer media sources

Orbit does not interpret meaning, approve reviews, write the vault, create Cogs,
or mutate the graph. It only preserves source context, applies source guards,
and writes `.input` files for Rosie.

Current implementation lives in `specialists/adapters/`. This package is the
stable named facade so the agentic design can say:

```text
Orbit -> normalize source
Rosie -> interpret input
RUDI -> reason/orchestrate
Sprockets/Cogs -> structure and time surfaces
Jane -> review
Uniblab -> operations
```

## Pilot 3 Commands

Pilot 3 uses Telegram as the representative live intake path:

```text
Telegram -> Orbit -> .input -> Rosie -> review/vault/archive
```

Readiness check:

```bash
scripts/pilot3-status
```

One foreground Telegram pass:

```bash
scripts/pilot3-telegram-once --wait-seconds 30 --limit 10 --timeout 0
```

The command contacts Telegram, writes only allowlisted text messages into the
shared `.input` queue, and can wait for Rosie to move the generated input into
archive. If no fresh allowlisted update exists, that is Pilot 3 friction rather
than success.

Foreground always-on pilot loop:

```bash
scripts/pilot3-telegram-once --watch --wait-seconds 30 --timeout 20
```

The watch loop stores the next Telegram update offset in
`/home/cosmo/sc/output/telegram-offset.json` by default and skips inputs already
present in `input/`, `processing/`, or `archive/`. It is an operator foreground
loop for Pilot 3, not a daemon.

Telegram-origin inputs also carry response metadata into Rosie. After a
successful processing pass, Rosie sends a compact processed acknowledgement back
to the originating Telegram chat. Review-required and operator-report messages
stay local until those decision channels are explicitly designed.

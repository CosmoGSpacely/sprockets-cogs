# Demo Walkthrough

This is a text walkthrough of the current product loop. It avoids private vault
content and focuses on the shape of the system.

## 1. Send Input

During Pilot 3, the preferred input is Telegram:

```text
Call Tom tomorrow about the tractor tires
```

Orbit polls Telegram, checks the allowlist, suppresses duplicates, persists the
offset, and writes a guarded `.input` file.

For local testing, a developer can also place a `.input` file directly into the
configured input directory.

## 2. Rosie Processes It

Rosie:

1. moves the `.input` into processing;
2. extracts candidate work;
3. classifies the intent and item shape;
4. validates typed output;
5. routes to Cogs, Sprockets, review, or another boundary;
6. archives the source input.

The expected safe result is a time-oriented Cog candidate or review packet. If
"Tom" is ambiguous, the system should prefer review over inventing authority.

## 3. The Vault Shows Work

Astro owns the vault surface. The user should eventually be able to see the Cog,
carry it, close it, drop it, or correct it from the human-readable surface.

The vault is not merely a historical ledger. It is the manual workbench.

## 4. Jane Handles Uncertainty

If a mutation is ambiguous, low-confidence, externally generated, or structural,
Jane presents a review packet. Jane does not secretly approve work.

Useful commands:

```bash
scripts/review --count
scripts/review --report
```

## 5. RUDI Can Show Evidence

RUDI owns retrieval and reasoning previews:

```bash
scripts/memory-demo "Tom tractor tires"
```

This helps explain what the system knows without granting memory direct write
authority.

## 6. Uniblab Checks The Loop

```bash
scripts/status
scripts/pilot3-status
scripts/check
```

The demo is successful when input, routing, review, vault output, and
acknowledgement are all visible and boring.

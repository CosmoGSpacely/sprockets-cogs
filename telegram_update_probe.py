"""Safe Telegram update status/probe CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from telegram_adapter import (
    DEFAULT_TELEGRAM_ENV_FILE,
    TELEGRAM_ALLOWED_CHATS_ENV,
    TELEGRAM_ALLOWED_USERS_ENV,
    TELEGRAM_POLLING_ENV,
    TELEGRAM_TOKEN_ENV,
    fetch_telegram_updates,
    merged_env_with_file,
    parse_id_list,
    summarize_update,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect Telegram bot input readiness without printing the token.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_TELEGRAM_ENV_FILE,
        help="private env file containing Telegram token and allowlist values",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="show token/allowlist readiness without contacting Telegram",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="fetch recent Telegram updates using the configured token",
    )
    parser.add_argument(
        "--offset",
        type=int,
        help="Telegram update offset for getUpdates",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="maximum update count for getUpdates",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="Telegram long-poll timeout in seconds",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print fetched Telegram payload as JSON; may include message text",
    )
    parser.add_argument(
        "--write-update-json",
        type=Path,
        help="write the first supported update object to this path for adapter preview",
    )
    return parser


def format_status(env: dict[str, str], env_file: Path) -> str:
    users = parse_id_list(env.get(TELEGRAM_ALLOWED_USERS_ENV, ""))
    chats = parse_id_list(env.get(TELEGRAM_ALLOWED_CHATS_ENV, ""))
    return "\n".join([
        "Telegram update probe",
        "- writes: no",
        "- contacts Telegram: no",
        f"- env file: {env_file}",
        f"- token configured: {'yes' if env.get(TELEGRAM_TOKEN_ENV, '').strip() else 'no'}",
        f"- polling enabled: {'yes' if env.get(TELEGRAM_POLLING_ENV, '').strip() == '1' else 'no'}",
        f"- allowed user ids configured: {len(users)}",
        f"- allowed chat ids configured: {len(chats)}",
    ])


def first_supported_update(updates: list[object]) -> dict[str, object] | None:
    for update in updates:
        if not isinstance(update, dict):
            continue
        summary = summarize_update(update)
        if summary.get("kind") == "message":
            return update
    return None


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.status and not args.fetch:
        args.status = True

    env = merged_env_with_file(env_file=args.env_file)

    if args.status:
        print(format_status(env, args.env_file))
        if not args.fetch:
            return
        print()

    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.timeout < 0:
        parser.error("--timeout cannot be negative")

    token = env.get(TELEGRAM_TOKEN_ENV, "").strip()
    try:
        payload = fetch_telegram_updates(
            token,
            offset=args.offset,
            limit=args.limit,
            timeout=args.timeout,
        )
    except Exception as exc:
        parser.error(f"telegram fetch failed: {exc}")

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        updates = payload.get("result", [])
        if not isinstance(updates, list):
            parser.error("telegram response result must be a list")
        print("\n".join([
            "Telegram update fetch",
            "- writes: no",
            "- token printed: no",
            f"- ok: {payload.get('ok')}",
            f"- update count: {len(updates)}",
        ]))
        for update in updates:
            if isinstance(update, dict):
                summary = summarize_update(update)
                fields = ", ".join(
                    f"{key}={value}"
                    for key, value in summary.items()
                    if value
                )
                print(f"- {fields}")

    if args.write_update_json:
        updates = payload.get("result", [])
        if not isinstance(updates, list):
            parser.error("telegram response result must be a list")
        update = first_supported_update(updates)
        if update is None:
            parser.error("no supported text message update found")
        args.write_update_json.parent.mkdir(parents=True, exist_ok=True)
        args.write_update_json.write_text(
            json.dumps(update, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"wrote update json: {args.write_update_json}")


if __name__ == "__main__":
    main()

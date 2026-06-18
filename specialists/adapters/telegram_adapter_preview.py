"""Read-only preview CLI for Telegram bot input updates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from specialists.adapters.input_adapter import (
    input_filename,
    input_session_id,
    preview_input_file,
    write_input_file,
)
from specialists.adapters.telegram_adapter import (
    DEFAULT_TELEGRAM_ENV_FILE,
    TELEGRAM_ALLOWED_CHATS_ENV,
    TELEGRAM_ALLOWED_USERS_ENV,
    merged_env_with_file,
    parse_telegram_update,
    parse_id_list,
    telegram_envelope,
    telegram_message_is_allowed,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview a Telegram update as a Rosie .input file.",
    )
    parser.add_argument(
        "--update-json",
        type=Path,
        required=True,
        help="path to a Telegram getUpdates-style JSON object for preview",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_TELEGRAM_ENV_FILE,
        help="private env file containing Telegram allowlist values",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the rendered .input file to --input-dir if allowlisted",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="target input directory for --write; required when writing",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        update = json.loads(args.update_json.read_text(encoding="utf-8"))
        message = parse_telegram_update(update)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))

    env = merged_env_with_file(env_file=args.env_file)
    allowed_user_ids = parse_id_list(env.get(TELEGRAM_ALLOWED_USERS_ENV, ""))
    allowed_chat_ids = parse_id_list(env.get(TELEGRAM_ALLOWED_CHATS_ENV, ""))
    allowed = telegram_message_is_allowed(
        message,
        allowed_user_ids=allowed_user_ids,
        allowed_chat_ids=allowed_chat_ids,
    )
    envelope = telegram_envelope(message)

    if args.write:
        if args.input_dir is None:
            parser.error("--input-dir is required with --write")
        if not allowed:
            parser.error("telegram message is not allowlisted")
        try:
            result = write_input_file(envelope, args.input_dir)
        except FileExistsError as exc:
            parser.error(str(exc))
        print("\n".join([
            "Telegram adapter write",
            "- writes: input",
            f"- path: {result.path}",
            f"- allowed: {'yes' if allowed else 'no'}",
            f"- session_id: {input_session_id(envelope)}",
            f"- filename: {input_filename(envelope)}",
        ]))
        return

    print("\n".join([
        "Telegram adapter preview",
        "- writes: no",
        f"- allowed: {'yes' if allowed else 'no'}",
        "",
        preview_input_file(envelope),
    ]))


if __name__ == "__main__":
    main()

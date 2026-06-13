"""Foreground Telegram polling proof for Stage 103."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from input_adapter import InputWriteResult, input_filename, write_input_file
from telegram_adapter import (
    DEFAULT_TELEGRAM_ENV_FILE,
    TELEGRAM_ALLOWED_CHATS_ENV,
    TELEGRAM_ALLOWED_USERS_ENV,
    TELEGRAM_TOKEN_ENV,
    fetch_telegram_updates,
    merged_env_with_file,
    parse_id_list,
    parse_telegram_update,
    telegram_envelope,
    telegram_message_is_allowed,
)


@dataclass(frozen=True)
class TelegramPollResult:
    fetched: int
    supported: int
    allowed: int
    written: tuple[InputWriteResult, ...]
    ignored: tuple[str, ...]
    next_offset: int | None


def _next_offset(updates: Sequence[Mapping[str, Any]]) -> int | None:
    ids: list[int] = []
    for update in updates:
        try:
            ids.append(int(update.get("update_id")))
        except (TypeError, ValueError):
            continue
    if not ids:
        return None
    return max(ids) + 1


def poll_telegram_once(
    *,
    token: str,
    input_dir: Path,
    allowed_user_ids: frozenset[int],
    allowed_chat_ids: frozenset[int],
    offset: int | None = None,
    limit: int = 10,
    timeout: int = 0,
    duplicate_dirs: Sequence[Path] = (),
    opener=fetch_telegram_updates,
) -> TelegramPollResult:
    """Fetch Telegram updates once and write allowlisted messages as `.input`."""

    payload = opener(token, offset=offset, limit=limit, timeout=timeout)
    raw_updates = payload.get("result", [])
    if not isinstance(raw_updates, list):
        raise ValueError("telegram response result must be a list")

    updates = [update for update in raw_updates if isinstance(update, Mapping)]
    written: list[InputWriteResult] = []
    ignored: list[str] = []
    supported = 0
    allowed = 0
    for update in updates:
        try:
            message = parse_telegram_update(update)
        except ValueError as exc:
            ignored.append(f"update {update.get('update_id', '?')}: {exc}")
            continue
        supported += 1
        if not telegram_message_is_allowed(
            message,
            allowed_user_ids=allowed_user_ids,
            allowed_chat_ids=allowed_chat_ids,
        ):
            ignored.append(f"update {message.update_id}: not allowlisted")
            continue
        allowed += 1
        envelope = telegram_envelope(message)
        filename = input_filename(envelope)
        if any((directory / filename).exists() for directory in duplicate_dirs):
            ignored.append(f"update {message.update_id}: duplicate {filename}")
            continue
        try:
            written.append(write_input_file(envelope, input_dir))
        except FileExistsError:
            ignored.append(f"update {message.update_id}: duplicate {filename}")

    return TelegramPollResult(
        fetched=len(updates),
        supported=supported,
        allowed=allowed,
        written=tuple(written),
        ignored=tuple(ignored),
        next_offset=_next_offset(updates),
    )


def format_poll_result(result: TelegramPollResult) -> str:
    lines = [
        "Telegram foreground poll",
        "- contacts Telegram: yes",
        "- token printed: no",
        f"- updates fetched: {result.fetched}",
        f"- text messages supported: {result.supported}",
        f"- allowlisted messages: {result.allowed}",
        f"- inputs written: {len(result.written)}",
        f"- next offset: {result.next_offset if result.next_offset is not None else 'none'}",
    ]
    for write in result.written:
        lines.append(f"- wrote: {write.path}")
    for item in result.ignored:
        lines.append(f"- ignored: {item}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Poll Telegram once in the foreground and write allowlisted .input files.",
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_TELEGRAM_ENV_FILE)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--offset", type=int)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=0)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.timeout < 0:
        parser.error("--timeout cannot be negative")

    env = merged_env_with_file(env_file=args.env_file)
    token = env.get(TELEGRAM_TOKEN_ENV, "").strip()
    if not token:
        parser.error("telegram token is not configured")
    users = parse_id_list(env.get(TELEGRAM_ALLOWED_USERS_ENV, ""))
    chats = parse_id_list(env.get(TELEGRAM_ALLOWED_CHATS_ENV, ""))
    if not users and not chats:
        parser.error("telegram allowlist is not configured")

    try:
        result = poll_telegram_once(
            token=token,
            input_dir=args.input_dir,
            allowed_user_ids=users,
            allowed_chat_ids=chats,
            offset=args.offset,
            limit=args.limit,
            timeout=args.timeout,
        )
    except Exception as exc:
        parser.error(f"telegram poll failed: {exc}")

    print(format_poll_result(result))


if __name__ == "__main__":
    main()

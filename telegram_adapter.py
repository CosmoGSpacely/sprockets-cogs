"""Telegram-specific adapter helpers for producing Rosie `.input` envelopes."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping, Any

from input_adapter import InputEnvelope


TELEGRAM_SOURCE = "telegram"
TELEGRAM_TOKEN_ENV = "SPROCKETS_COGS_TELEGRAM_BOT_TOKEN"
TELEGRAM_ALLOWED_USERS_ENV = "SPROCKETS_COGS_TELEGRAM_ALLOWED_USER_IDS"
TELEGRAM_ALLOWED_CHATS_ENV = "SPROCKETS_COGS_TELEGRAM_ALLOWED_CHAT_IDS"


@dataclass(frozen=True)
class TelegramMessage:
    """Normalized subset of a Telegram update needed for input capture."""

    update_id: int
    message_id: int
    chat_id: int
    from_user_id: int
    text: str
    username: str = ""
    chat_type: str = ""


def _as_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"telegram {field_name} must be an integer") from exc


def parse_telegram_update(update: Mapping[str, Any]) -> TelegramMessage:
    """Parse a Telegram update into a normalized text message."""

    message = update.get("message")
    if not isinstance(message, Mapping):
        raise ValueError("telegram update does not include a message")

    chat = message.get("chat")
    if not isinstance(chat, Mapping):
        raise ValueError("telegram message does not include chat")

    sender = message.get("from")
    if not isinstance(sender, Mapping):
        raise ValueError("telegram message does not include sender")

    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("telegram message text cannot be empty")

    return TelegramMessage(
        update_id=_as_int(update.get("update_id"), "update_id"),
        message_id=_as_int(message.get("message_id"), "message_id"),
        chat_id=_as_int(chat.get("id"), "chat.id"),
        from_user_id=_as_int(sender.get("id"), "from.id"),
        username=str(sender.get("username") or ""),
        chat_type=str(chat.get("type") or ""),
        text=text.strip(),
    )


def parse_id_list(value: str) -> frozenset[int]:
    """Parse a comma-separated allowlist of Telegram ids."""

    ids: set[int] = set()
    for item in value.split(","):
        stripped = item.strip()
        if not stripped:
            continue
        ids.add(_as_int(stripped, "allowlist id"))
    return frozenset(ids)


def telegram_allowlist_from_env(
    env: Mapping[str, str] | None = None,
) -> tuple[frozenset[int], frozenset[int]]:
    """Return allowed Telegram user and chat ids from environment values."""

    values = env if env is not None else os.environ
    return (
        parse_id_list(values.get(TELEGRAM_ALLOWED_USERS_ENV, "")),
        parse_id_list(values.get(TELEGRAM_ALLOWED_CHATS_ENV, "")),
    )


def telegram_message_is_allowed(
    message: TelegramMessage,
    *,
    allowed_user_ids: frozenset[int],
    allowed_chat_ids: frozenset[int],
) -> bool:
    """Return whether a Telegram message passes the configured allowlist."""

    if not allowed_user_ids and not allowed_chat_ids:
        return False
    if allowed_user_ids and message.from_user_id not in allowed_user_ids:
        return False
    if allowed_chat_ids and message.chat_id not in allowed_chat_ids:
        return False
    return True


def telegram_envelope(message: TelegramMessage) -> InputEnvelope:
    """Convert a normalized Telegram message into the shared input envelope."""

    source_id = f"chat-{message.chat_id}-message-{message.message_id}"
    return InputEnvelope(
        content=message.text,
        source=TELEGRAM_SOURCE,
        session_id=f"telegram-chat-{message.chat_id}",
        modality="text",
        source_id=source_id,
        idempotency_key=f"telegram:{message.chat_id}:{message.message_id}",
        metadata={
            "telegram_update_id": str(message.update_id),
            "telegram_message_id": str(message.message_id),
            "telegram_chat_id": str(message.chat_id),
            "telegram_from_user_id": str(message.from_user_id),
            "telegram_username": message.username,
            "telegram_chat_type": message.chat_type,
        },
    )

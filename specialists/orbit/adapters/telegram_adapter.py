"""Telegram-specific adapter helpers for producing Rosie `.input` envelopes."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping, Any
from urllib.parse import urlencode
from urllib.request import urlopen

from specialists.orbit.adapters.input_adapter import InputEnvelope


TELEGRAM_SOURCE = "telegram"
TELEGRAM_TOKEN_ENV = "SPROCKETS_COGS_TELEGRAM_BOT_TOKEN"
TELEGRAM_ALLOWED_USERS_ENV = "SPROCKETS_COGS_TELEGRAM_ALLOWED_USER_IDS"
TELEGRAM_ALLOWED_CHATS_ENV = "SPROCKETS_COGS_TELEGRAM_ALLOWED_CHAT_IDS"
TELEGRAM_POLLING_ENV = "SPROCKETS_COGS_TELEGRAM_POLLING"
DEFAULT_TELEGRAM_ENV_FILE = Path.home() / ".config" / "sprockets-cogs" / "env"
TELEGRAM_API_BASE = "https://api.telegram.org"


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


def load_env_file(path: Path) -> dict[str, str]:
    """Load simple KEY=VALUE lines from an env file without shell evaluation."""

    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip().strip("\"'")
    return values


def merged_env_with_file(
    *,
    env_file: Path = DEFAULT_TELEGRAM_ENV_FILE,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return env-file values overlaid by the process environment."""

    process_env = env if env is not None else os.environ
    values = load_env_file(env_file)
    values.update(process_env)
    return values


def telegram_token_configured(env: Mapping[str, str] | None = None) -> bool:
    """Return whether a Telegram bot token is present without exposing it."""

    values = env if env is not None else os.environ
    return bool(values.get(TELEGRAM_TOKEN_ENV, "").strip())


def build_get_updates_url(
    token: str,
    *,
    offset: int | None = None,
    limit: int = 10,
    timeout: int = 0,
) -> str:
    """Build the Telegram getUpdates URL without logging the token."""

    query: dict[str, int] = {"limit": limit, "timeout": timeout}
    if offset is not None:
        query["offset"] = offset
    return f"{TELEGRAM_API_BASE}/bot{token}/getUpdates?{urlencode(query)}"


def fetch_telegram_updates(
    token: str,
    *,
    offset: int | None = None,
    limit: int = 10,
    timeout: int = 0,
    opener=urlopen,
) -> dict[str, Any]:
    """Fetch Telegram updates using the Bot API."""

    if not token.strip():
        raise ValueError("telegram token is not configured")
    url = build_get_updates_url(
        token,
        offset=offset,
        limit=limit,
        timeout=timeout,
    )
    with opener(url, timeout=timeout + 10) as response:
        data = response.read()
    import json

    payload = json.loads(data.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("telegram response must be a JSON object")
    return payload


def summarize_update(update: Mapping[str, Any]) -> dict[str, str]:
    """Return a token-free compact summary for a Telegram update."""

    try:
        message = parse_telegram_update(update)
    except ValueError as exc:
        return {
            "update_id": str(update.get("update_id", "")),
            "kind": "unsupported",
            "reason": str(exc),
        }
    return {
        "update_id": str(message.update_id),
        "kind": "message",
        "message_id": str(message.message_id),
        "chat_id": str(message.chat_id),
        "from_user_id": str(message.from_user_id),
        "username": message.username,
        "chat_type": message.chat_type,
        "text_excerpt": message.text[:80],
    }

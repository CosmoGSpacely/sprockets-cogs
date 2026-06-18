"""Telegram response adapter for conservative source replies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import frontmatter

from specialists.rudi.response_routing import (
    ResponseContext,
    ResponseEnvelope,
    ResponseType,
    format_response_preview,
    response_context_from_frontmatter,
    route_response,
)
from specialists.orbit.adapters.telegram_adapter import (
    DEFAULT_TELEGRAM_ENV_FILE,
    TELEGRAM_API_BASE,
    TELEGRAM_TOKEN_ENV,
    merged_env_with_file,
)


def response_context_from_input_file(path: Path) -> ResponseContext:
    """Build response context from adapter `.input` frontmatter."""

    post = frontmatter.load(path)
    return response_context_from_frontmatter(
        post.metadata,
        fallback_session_id=path.stem,
    )


def telegram_response_envelope(
    *,
    chat_id: str,
    text: str,
    response_type: ResponseType,
    session_id: str = "",
) -> ResponseEnvelope:
    """Build a Telegram response envelope from explicit CLI-style values."""

    stripped_chat_id = chat_id.strip()
    if not stripped_chat_id:
        raise ValueError("telegram chat id cannot be empty")
    return ResponseEnvelope(
        context=ResponseContext(
            source="telegram",
            session_id=session_id.strip() or f"telegram-chat-{stripped_chat_id}",
            metadata={"telegram_chat_id": stripped_chat_id},
        ),
        response_type=response_type,
        text=text,
    )


def build_send_message_request(
    *,
    token: str,
    chat_id: str,
    text: str,
) -> Request:
    """Build a Telegram sendMessage request without logging the token."""

    if not token.strip():
        raise ValueError("telegram token is not configured")
    if not chat_id.strip():
        raise ValueError("telegram chat id cannot be empty")
    if not text.strip():
        raise ValueError("telegram response text cannot be empty")

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    data = urlencode({
        "chat_id": chat_id.strip(),
        "text": text.strip(),
    }).encode("utf-8")
    return Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )


def send_telegram_response(
    envelope: ResponseEnvelope,
    *,
    token: str,
    opener=urlopen,
) -> Mapping[str, Any]:
    """Send a route-approved Telegram response."""

    route = route_response(envelope)
    if route.sink != "telegram" or not route.would_send:
        raise ValueError(f"response is not sendable to Telegram: {route.reason}")
    request = build_send_message_request(
        token=token,
        chat_id=route.target,
        text=envelope.text,
    )
    with opener(request, timeout=10) as response:
        data = response.read()
    payload = json.loads(data.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("telegram send response must be a JSON object")
    return payload


def format_telegram_response_preview(envelope: ResponseEnvelope, *, token_configured: bool) -> str:
    """Format a token-safe Telegram response preview."""

    return "\n".join([
        "Telegram response preview",
        "- contacts Telegram: no",
        "- token printed: no",
        f"- token configured: {'yes' if token_configured else 'no'}",
        "",
        format_response_preview(envelope),
    ])


def _response_type(value: str) -> ResponseType:
    try:
        return ResponseType(value)
    except ValueError as exc:
        choices = ", ".join(item.value for item in ResponseType)
        raise argparse.ArgumentTypeError(
            f"invalid response type {value!r}; choose one of: {choices}"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or explicitly send a conservative Telegram response.",
    )
    parser.add_argument(
        "text",
        nargs="*",
        help="response text to preview/send",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_TELEGRAM_ENV_FILE,
        help="private env file containing the Telegram bot token",
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        help="adapter-produced .input file whose frontmatter supplies routing metadata",
    )
    parser.add_argument(
        "--chat-id",
        help="Telegram chat id for direct operator rehearsal",
    )
    parser.add_argument(
        "--session-id",
        default="",
        help="optional session id for direct operator rehearsal",
    )
    parser.add_argument(
        "--response-type",
        type=_response_type,
        default=ResponseType.ACKNOWLEDGEMENT,
        help="response type; defaults to acknowledgement",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="actually call Telegram sendMessage; preview is the default",
    )
    return parser


def _build_envelope(args: argparse.Namespace, parser: argparse.ArgumentParser) -> ResponseEnvelope:
    text = " ".join(args.text).strip()
    if not text:
        parser.error("response text is required")

    if args.input_file and args.chat_id:
        parser.error("use either --input-file or --chat-id, not both")
    if args.input_file:
        context = response_context_from_input_file(args.input_file)
        return ResponseEnvelope(
            context=context,
            response_type=args.response_type,
            text=text,
        )
    if args.chat_id:
        try:
            return telegram_response_envelope(
                chat_id=args.chat_id,
                session_id=args.session_id,
                response_type=args.response_type,
                text=text,
            )
        except ValueError as exc:
            parser.error(str(exc))
    parser.error("either --input-file or --chat-id is required")


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    envelope = _build_envelope(args, parser)
    env = merged_env_with_file(env_file=args.env_file)
    token = env.get(TELEGRAM_TOKEN_ENV, "").strip()

    if not args.send:
        print(format_telegram_response_preview(envelope, token_configured=bool(token)))
        return

    try:
        payload = send_telegram_response(envelope, token=token)
    except Exception as exc:
        parser.error(f"telegram response send failed: {exc}")

    result = payload.get("result", {})
    message_id = ""
    if isinstance(result, Mapping):
        message_id = str(result.get("message_id") or "")
    print("\n".join([
        "Telegram response send",
        "- contacts Telegram: yes",
        "- token printed: no",
        f"- ok: {payload.get('ok')}",
        f"- message_id: {message_id}",
    ]))


if __name__ == "__main__":
    main()

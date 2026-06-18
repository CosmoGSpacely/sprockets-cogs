"""Read-only response routing contracts for source-aware output."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


LOCAL_SOURCE = "local"
TELEGRAM_SOURCE = "telegram"


class ResponseType(StrEnum):
    """Allowed response intents."""

    ACKNOWLEDGEMENT = "acknowledgement"
    PROCESSED = "processed"
    REVIEW_REQUIRED = "review_required"
    ERROR = "error"
    LOCAL_REFLECTION = "local_reflection"
    OPERATOR_REPORT = "operator_report"


@dataclass(frozen=True)
class ResponseContext:
    """Source metadata preserved from an adapter-produced `.input` file."""

    session_id: str
    source: str = LOCAL_SOURCE
    source_id: str = ""
    idempotency_key: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if not self.source.strip():
            raise ValueError("source cannot be empty")


@dataclass(frozen=True)
class ResponseEnvelope:
    """Normalized response before it is routed to a sink."""

    context: ResponseContext
    response_type: ResponseType
    text: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("response text cannot be empty")


@dataclass(frozen=True)
class ResponseRoute:
    """Read-only route decision for a response envelope."""

    sink: str
    writes: bool
    would_send: bool
    reason: str
    target: str = ""


def response_context_from_frontmatter(
    frontmatter: Mapping[str, Any],
    *,
    fallback_session_id: str,
) -> ResponseContext:
    """Extract response metadata from `.input` frontmatter."""

    metadata = frontmatter.get("metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    return ResponseContext(
        session_id=str(frontmatter.get("session_id") or fallback_session_id),
        source=str(frontmatter.get("source") or LOCAL_SOURCE),
        source_id=str(frontmatter.get("source_id") or ""),
        idempotency_key=str(frontmatter.get("idempotency_key") or ""),
        metadata=dict(metadata),
    )


def telegram_chat_id(context: ResponseContext) -> str:
    """Return the Telegram chat id preserved in adapter metadata, if present."""

    value = context.metadata.get("telegram_chat_id", "")
    return str(value).strip()


def route_response(envelope: ResponseEnvelope) -> ResponseRoute:
    """Return the conservative route decision for a response envelope."""

    context = envelope.context
    if context.source == TELEGRAM_SOURCE:
        chat_id = telegram_chat_id(context)
        if not chat_id:
            return ResponseRoute(
                sink="local",
                writes=True,
                would_send=False,
                reason="telegram source missing chat id; record local reflection only",
            )
        if envelope.response_type in {
            ResponseType.ACKNOWLEDGEMENT,
            ResponseType.PROCESSED,
            ResponseType.ERROR,
        }:
            return ResponseRoute(
                sink="telegram",
                writes=True,
                would_send=True,
                reason=f"telegram {envelope.response_type.value} reply allowed",
                target=chat_id,
            )
        return ResponseRoute(
            sink="local",
            writes=True,
            would_send=False,
            reason=f"{envelope.response_type.value} stays local/review-first",
        )
    return ResponseRoute(
        sink="local",
        writes=True,
        would_send=False,
        reason=f"{context.source} has no source reply adapter",
    )


def format_response_preview(envelope: ResponseEnvelope) -> str:
    """Format a read-only response route preview."""

    route = route_response(envelope)
    lines = [
        "Response route preview",
        "- writes: no",
        f"- source: {envelope.context.source}",
        f"- session_id: {envelope.context.session_id}",
        f"- response_type: {envelope.response_type.value}",
        f"- sink: {route.sink}",
        f"- would_send: {'yes' if route.would_send else 'no'}",
        f"- route_writes_when_applied: {'yes' if route.writes else 'no'}",
    ]
    if route.target:
        lines.append(f"- target: {route.target}")
    lines.extend([
        f"- reason: {route.reason}",
        "",
        envelope.text.strip(),
    ])
    return "\n".join(lines)

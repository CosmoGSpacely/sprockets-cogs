"""Local message/shared-state contract for Phase 4 specialists.

Stage 43 starts with a tiny JSONL-backed bus. It is deliberately inspectable and
replayable, and it is not wired into the live agentic loop.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Sequence
from uuid import uuid4


SC_ROOT_ENV = "SPROCKETS_COGS_SC_ROOT"
DEFAULT_MESSAGE_BUS_PATH = (
    Path(os.environ.get(SC_ROOT_ENV, str(Path.home() / "sc"))) / "output" / "agent-messages.jsonl"
)

MessageStatus = Literal["pending", "done", "failed"]


@dataclass(frozen=True)
class AgentMessage:
    """Durable message shape for local specialist coordination."""

    message_id: str
    trace_id: str
    idempotency_key: str
    sender: str
    recipient: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: MessageStatus = "pending"
    created_at: str = ""

    def __post_init__(self) -> None:
        for field_name in ("message_id", "trace_id", "idempotency_key", "sender", "recipient", "kind"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required")
        if self.status not in {"pending", "done", "failed"}:
            raise ValueError(f"unknown message status: {self.status!r}")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")


@dataclass(frozen=True)
class MessageAppendResult:
    """Result of appending or deduping a message."""

    path: Path
    message: AgentMessage
    appended: bool


@dataclass(frozen=True)
class MessageBusStatus:
    """Small operational summary for the local message bus."""

    path: Path
    total: int
    pending: int
    done: int
    failed: int


class FileMessageBus:
    """JSONL-backed message bus with idempotent append semantics."""

    def __init__(self, path: Path = DEFAULT_MESSAGE_BUS_PATH) -> None:
        self.path = path

    def append(self, message: AgentMessage) -> MessageAppendResult:
        """Append a message unless its idempotency key already exists."""

        existing = self.find_by_idempotency_key(message.idempotency_key)
        if existing is not None:
            return MessageAppendResult(path=self.path, message=existing, appended=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(message_to_dict(message), sort_keys=True) + "\n")
        return MessageAppendResult(path=self.path, message=message, appended=True)

    def messages(
        self,
        *,
        recipient: str = "",
        status: MessageStatus | None = None,
    ) -> tuple[AgentMessage, ...]:
        """Read messages, optionally filtering by recipient and status."""

        messages = read_messages(self.path)
        if recipient:
            messages = tuple(message for message in messages if message.recipient == recipient)
        if status:
            messages = tuple(message for message in messages if message.status == status)
        return messages

    def find_by_idempotency_key(self, idempotency_key: str) -> AgentMessage | None:
        for message in self.messages():
            if message.idempotency_key == idempotency_key:
                return message
        return None

    def status(self) -> MessageBusStatus:
        messages = self.messages()
        return MessageBusStatus(
            path=self.path,
            total=len(messages),
            pending=sum(1 for message in messages if message.status == "pending"),
            done=sum(1 for message in messages if message.status == "done"),
            failed=sum(1 for message in messages if message.status == "failed"),
        )


def new_message(
    *,
    sender: str,
    recipient: str,
    kind: str,
    payload: dict[str, Any] | None = None,
    trace_id: str = "",
    idempotency_key: str = "",
    status: MessageStatus = "pending",
) -> AgentMessage:
    """Create a message with generated identity fields where needed."""

    message_id = uuid4().hex
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return AgentMessage(
        message_id=message_id,
        trace_id=trace_id or message_id,
        idempotency_key=idempotency_key or message_id,
        sender=sender,
        recipient=recipient,
        kind=kind,
        payload=payload or {},
        status=status,
        created_at=created_at,
    )


def message_to_dict(message: AgentMessage) -> dict[str, Any]:
    return asdict(message)


def message_from_dict(raw: dict[str, Any]) -> AgentMessage:
    return AgentMessage(
        message_id=str(raw.get("message_id", "")),
        trace_id=str(raw.get("trace_id", "")),
        idempotency_key=str(raw.get("idempotency_key", "")),
        sender=str(raw.get("sender", "")),
        recipient=str(raw.get("recipient", "")),
        kind=str(raw.get("kind", "")),
        payload=raw.get("payload") if isinstance(raw.get("payload"), dict) else {},
        status=raw.get("status", "pending"),
        created_at=str(raw.get("created_at", "")),
    )


def read_messages(path: Path) -> tuple[AgentMessage, ...]:
    """Read all valid messages from a JSONL file."""

    if not path.exists():
        return ()
    messages: list[AgentMessage] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        messages.append(message_from_dict(json.loads(line)))
    return tuple(messages)


def format_message_bus_status(status: MessageBusStatus) -> str:
    return "\n".join(
        [
            "Agent message bus status",
            f"- path: {status.path}",
            f"- total: {status.total}",
            f"- pending: {status.pending}",
            f"- done: {status.done}",
            f"- failed: {status.failed}",
        ]
    )


def format_messages(messages: Sequence[AgentMessage]) -> str:
    lines = ["Agent message bus preview", f"- messages: {len(messages)}"]
    if not messages:
        lines.append("No messages found.")
        return "\n".join(lines)
    lines.append("")
    for message in messages:
        lines.append(
            f"- {message.message_id} trace={message.trace_id} "
            f"{message.sender}->{message.recipient} kind={message.kind} status={message.status}"
        )
    return "\n".join(lines)


def format_append_result(result: MessageAppendResult) -> str:
    action = "appended" if result.appended else "deduped"
    return "\n".join(
        [
            "Agent message append",
            f"- path: {result.path}",
            f"- action: {action}",
            f"- message_id: {result.message.message_id}",
            f"- trace_id: {result.message.trace_id}",
            f"- idempotency_key: {result.message.idempotency_key}",
            f"- sender: {result.message.sender}",
            f"- recipient: {result.message.recipient}",
            f"- kind: {result.message.kind}",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or append local Phase 4 message-bus records.")
    parser.add_argument("--path", type=Path, default=DEFAULT_MESSAGE_BUS_PATH, help="JSONL message bus path. Defaults under SC output/.")
    parser.add_argument("--recipient", default="", help="Filter messages by recipient for --list.")
    parser.add_argument("--status-filter", choices=("pending", "done", "failed"), default=None, help="Filter messages by status for --list.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true", help="Report message bus status. Read-only.")
    mode.add_argument("--list", action="store_true", help="List messages. Read-only.")
    mode.add_argument("--append", action="store_true", help="Append one message idempotently. Writes the JSONL bus file, not the vault.")
    parser.add_argument("--sender", default="orchestrator", help="Sender for --append.")
    parser.add_argument("--to", default="review", help="Recipient for --append.")
    parser.add_argument("--kind", default="preview", help="Message kind for --append.")
    parser.add_argument("--trace-id", default="", help="Trace id for --append.")
    parser.add_argument("--idempotency-key", default="", help="Idempotency key for --append.")
    parser.add_argument("--payload", default="{}", help="JSON object payload for --append.")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    bus = FileMessageBus(args.path)
    if args.status:
        print(format_message_bus_status(bus.status()))
    elif args.list:
        print(format_messages(bus.messages(recipient=args.recipient, status=args.status_filter)))
    elif args.append:
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as exc:
            parser.error(f"--payload must be valid JSON: {exc.msg}")
        if not isinstance(payload, dict):
            parser.error("--payload must be a JSON object")
        result = bus.append(
            new_message(
                sender=args.sender,
                recipient=args.to,
                kind=args.kind,
                payload=payload,
                trace_id=args.trace_id,
                idempotency_key=args.idempotency_key,
            )
        )
        print(format_append_result(result))


if __name__ == "__main__":
    main()

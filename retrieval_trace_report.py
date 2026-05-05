"""Review memory parent guard decisions from service logs."""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Iterable

from memory_trace_log import read_memory_parent_trace_records


SERVICE_NAME = "sprockets-cogs.service"
DEFAULT_SINCE = "24 hours ago"

_SELECTED_RE = re.compile(
    r"Memory parent guard selected: "
    r"parent=(?P<parent>.+?) "
    r"node_id=(?P<node_id>\S+) "
    r"node_type=(?P<node_type>\S+) "
    r"retrieved=(?P<retrieved>\d+)"
)
_SKIPPED_RE = re.compile(
    r"Memory parent guard skipped: "
    r"reason=(?P<reason>.+?) "
    r"top_node_id=(?P<top_node_id>\S+) "
    r"top_node_type=(?P<top_node_type>\S+) "
    r"retrieved=(?P<retrieved>\d+)"
)


@dataclass(frozen=True)
class MemoryGuardLogEvent:
    """A parsed memory parent guard decision from service logs."""

    timestamp: str
    decision: str
    retrieved_count: int
    parent_title: str = ""
    parent_node_id: str = ""
    parent_node_type: str = ""
    reason: str = ""
    top_node_id: str = ""
    top_node_type: str = ""


def parse_memory_guard_log_line(line: str) -> MemoryGuardLogEvent | None:
    """Parse one service log line, returning None for unrelated lines."""

    selected = _SELECTED_RE.search(line)
    if selected:
        return MemoryGuardLogEvent(
            timestamp=_timestamp_from_line(line),
            decision="selected",
            parent_title=_unquote_parent(selected.group("parent")),
            parent_node_id=selected.group("node_id"),
            parent_node_type=selected.group("node_type"),
            retrieved_count=int(selected.group("retrieved")),
        )

    skipped = _SKIPPED_RE.search(line)
    if skipped:
        return MemoryGuardLogEvent(
            timestamp=_timestamp_from_line(line),
            decision="skipped",
            reason=skipped.group("reason"),
            top_node_id=skipped.group("top_node_id"),
            top_node_type=skipped.group("top_node_type"),
            retrieved_count=int(skipped.group("retrieved")),
        )

    return None


def parse_memory_guard_log(lines: Iterable[str]) -> tuple[MemoryGuardLogEvent, ...]:
    """Parse memory parent guard decisions from service log lines."""

    events: list[MemoryGuardLogEvent] = []
    for line in lines:
        event = parse_memory_guard_log_line(line)
        if event is not None:
            events.append(event)
    return tuple(events)


def fetch_service_log_lines(
    since: str = DEFAULT_SINCE,
    service_name: str = SERVICE_NAME,
) -> tuple[str, ...]:
    """Return recent user-service log lines for trace review."""

    result = subprocess.run(
        [
            "journalctl",
            "--user",
            "-u",
            service_name,
            "--since",
            since,
            "--no-pager",
            "--output",
            "short-iso",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return tuple(result.stdout.splitlines())


def format_memory_guard_report(
    events: Iterable[MemoryGuardLogEvent],
    limit: int | None = None,
) -> str:
    """Format parsed memory guard events as a compact review report."""

    event_list = tuple(events)
    if limit is not None and limit >= 0:
        event_list = event_list[-limit:]

    lines = [
        "Sprockets-Cogs memory guard log report",
        f"- events: {len(event_list)}",
    ]
    if not event_list:
        lines.append("- no selected/skipped memory parent guard events found")
        return "\n".join(lines)

    for event in event_list:
        lines.append(f"{event.timestamp or '(unknown time)'} {event.decision}")
        lines.append(f"  retrieved: {event.retrieved_count}")
        if event.decision == "selected":
            lines.append(f"  parent: {event.parent_title}")
            lines.append(
                f"  parent node: {event.parent_node_id} [{event.parent_node_type}]"
            )
        else:
            lines.append(f"  reason: {event.reason}")
            lines.append(f"  top node: {event.top_node_id} [{event.top_node_type}]")
    return "\n".join(lines)


def format_memory_guard_jsonl_report(
    lines: Iterable[str],
    limit: int | None = None,
) -> str:
    """Format memory guard events from the durable JSONL trace sink."""

    events = tuple(
        MemoryGuardLogEvent(
            timestamp=record.created_at,
            decision=record.decision,
            parent_title=record.parent_title,
            parent_node_id=record.parent_node_id,
            parent_node_type=record.parent_node_type,
            reason=record.reason,
            top_node_id=record.top_node_id,
            top_node_type=record.top_node_type,
            retrieved_count=record.retrieved_count,
        )
        for record in read_memory_parent_trace_records(lines)
    )
    return format_memory_guard_report(events, limit=limit)


def _timestamp_from_line(line: str) -> str:
    """Extract the journal timestamp prefix without assuming one output format."""

    stripped = line.strip()
    if not stripped:
        return ""
    marker_index = stripped.find("Memory parent guard ")
    prefix = stripped[:marker_index].strip() if marker_index >= 0 else stripped
    parts = prefix.split()
    if not parts:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}", parts[0]):
        return parts[0]
    if len(parts) >= 3:
        return " ".join(parts[:3])
    return parts[0]


def _unquote_parent(value: str) -> str:
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return value
    return parsed if isinstance(parsed, str) else value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review recent memory parent guard decisions from service logs.",
    )
    parser.add_argument(
        "--since",
        default=DEFAULT_SINCE,
        help="journalctl --since value. Defaults to '24 hours ago'.",
    )
    parser.add_argument(
        "--service",
        default=SERVICE_NAME,
        help=f"systemd user service name. Defaults to {SERVICE_NAME}.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of most recent events to show. Defaults to 20.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Parse a log file instead of calling journalctl.",
    )
    parser.add_argument(
        "--jsonl",
        type=Path,
        help="Parse a durable memory trace JSONL file instead of service logs.",
    )
    args = parser.parse_args()

    if args.jsonl:
        lines = (
            args.jsonl.read_text(encoding="utf-8").splitlines()
            if args.jsonl.exists()
            else ()
        )
        print(format_memory_guard_jsonl_report(lines, limit=args.limit))
        return
    if args.file:
        lines = args.file.read_text(encoding="utf-8").splitlines()
    else:
        lines = fetch_service_log_lines(args.since, args.service)
    print(format_memory_guard_report(parse_memory_guard_log(lines), limit=args.limit))


if __name__ == "__main__":
    main()

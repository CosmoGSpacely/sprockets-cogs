"""Durable operational logging for memory parent guard decisions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Iterable

from memory_guards import MemoryParentTrace


TRACE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class MemoryParentTraceRecord:
    """A durable, input-free record of a memory parent guard decision."""

    created_at: str
    decision: str
    retrieved_count: int
    parent_title: str = ""
    parent_node_id: str = ""
    parent_node_type: str = ""
    reason: str = ""
    top_node_id: str = ""
    top_node_type: str = ""
    schema_version: int = TRACE_SCHEMA_VERSION


def memory_parent_trace_record(
    trace: MemoryParentTrace,
    created_at: datetime | None = None,
) -> MemoryParentTraceRecord:
    """Convert an in-process guard trace into a JSONL-safe record."""

    timestamp = (
        created_at.isoformat(timespec="seconds")
        if created_at is not None
        else datetime.now().astimezone().isoformat(timespec="seconds")
    )
    if trace.selected:
        return MemoryParentTraceRecord(
            created_at=timestamp,
            decision="selected",
            parent_title=trace.parent_title,
            parent_node_id=trace.parent_node_id,
            parent_node_type=trace.parent_node_type,
            retrieved_count=trace.retrieved_count,
        )
    return MemoryParentTraceRecord(
        created_at=timestamp,
        decision="skipped",
        reason=trace.reason,
        top_node_id=trace.top_node_id,
        top_node_type=trace.top_node_type,
        retrieved_count=trace.retrieved_count,
    )


def append_memory_parent_trace(
    trace: MemoryParentTrace,
    path: Path,
    created_at: datetime | None = None,
) -> MemoryParentTraceRecord:
    """Append one memory guard trace to a JSONL file and return the record."""

    record = memory_parent_trace_record(trace, created_at=created_at)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.__dict__, sort_keys=True) + "\n")
    return record


def read_memory_parent_trace_records(
    lines: Iterable[str],
) -> tuple[MemoryParentTraceRecord, ...]:
    """Read valid memory parent trace records from JSONL lines."""

    records: list[MemoryParentTraceRecord] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if payload.get("schema_version") != TRACE_SCHEMA_VERSION:
            continue
        try:
            records.append(MemoryParentTraceRecord(
                created_at=str(payload.get("created_at", "")),
                decision=str(payload.get("decision", "")),
                retrieved_count=int(payload.get("retrieved_count", 0)),
                parent_title=str(payload.get("parent_title", "")),
                parent_node_id=str(payload.get("parent_node_id", "")),
                parent_node_type=str(payload.get("parent_node_type", "")),
                reason=str(payload.get("reason", "")),
                top_node_id=str(payload.get("top_node_id", "")),
                top_node_type=str(payload.get("top_node_type", "")),
                schema_version=int(payload.get("schema_version", TRACE_SCHEMA_VERSION)),
            ))
        except (TypeError, ValueError):
            continue
    return tuple(records)

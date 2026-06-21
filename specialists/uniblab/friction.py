"""Structured friction records for pilot learning and hardening."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

SC_ROOT = Path(os.environ.get("SPROCKETS_COGS_SC_ROOT", str(Path.home() / "sc")))
DEFAULT_FRICTION_LOG = Path(
    os.environ.get("SPROCKETS_COGS_FRICTION_LOG", str(SC_ROOT / "output" / "friction.jsonl"))
)
DEFAULT_CANDIDATE_DIR = Path(
    os.environ.get("SPROCKETS_COGS_FRICTION_CANDIDATE_DIR", str(SC_ROOT / "output"))
)

OPEN_STATUSES = {"open"}
KNOWN_FIXES = {"guard", "fixture", "prompt-change", "test", "deferred"}
KNOWN_STATUSES = {"open", "promoted", "killed"}


@dataclass(frozen=True)
class FrictionRecord:
    """One correctable pattern observed in the live product loop."""

    record_id: str
    created_at: str
    source: str
    pattern: str
    proposed_fix: str
    evidence: str
    status: str = "open"
    frequency: int = 1
    details: str = ""


@dataclass(frozen=True)
class FrictionSummary:
    source: str
    pattern: str
    proposed_fix: str
    status: str
    count: int
    evidence: tuple[str, ...]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_pattern(value: str) -> str:
    text = " ".join(str(value or "").strip().split())
    text = re.sub(r"\b\d{8}_\d{6}_\d{6}\b", "<review-id>", text)
    text = re.sub(r"\btelegram\d+\b", "telegram<id>", text)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "<date>", text)
    return text[:240] or "unspecified friction"


def record_id_for(*parts: object) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part).encode("utf-8", errors="replace"))
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def build_friction_record(
    *,
    source: str,
    pattern: str,
    evidence: str,
    proposed_fix: str = "fixture",
    status: str = "open",
    details: str = "",
    created_at: str | None = None,
) -> FrictionRecord:
    proposed_fix = proposed_fix.strip() or "fixture"
    status = status.strip() or "open"
    if proposed_fix not in KNOWN_FIXES:
        raise ValueError(f"unknown proposed fix: {proposed_fix}")
    if status not in KNOWN_STATUSES:
        raise ValueError(f"unknown friction status: {status}")
    normalized = normalize_pattern(pattern)
    timestamp = created_at or now_iso()
    return FrictionRecord(
        record_id=record_id_for(timestamp, source, normalized, evidence),
        created_at=timestamp,
        source=source.strip() or "unknown",
        pattern=normalized,
        proposed_fix=proposed_fix,
        evidence=str(evidence),
        status=status,
        details=" ".join(str(details or "").split()),
    )


def append_friction_record(record: FrictionRecord, log_path: Path = DEFAULT_FRICTION_LOG) -> Path:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
    return log_path


def append_record(
    *,
    source: str,
    pattern: str,
    evidence: str,
    proposed_fix: str = "fixture",
    details: str = "",
    log_path: Path = DEFAULT_FRICTION_LOG,
) -> FrictionRecord:
    record = build_friction_record(
        source=source,
        pattern=pattern,
        proposed_fix=proposed_fix,
        evidence=evidence,
        details=details,
    )
    append_friction_record(record, log_path)
    return record


def load_friction_records(log_path: Path = DEFAULT_FRICTION_LOG) -> tuple[FrictionRecord, ...]:
    if not log_path.exists():
        return ()
    records: list[FrictionRecord] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        records.append(FrictionRecord(**data))
    return tuple(records)


def summarize_records(records: Iterable[FrictionRecord], *, open_only: bool = True) -> tuple[FrictionSummary, ...]:
    grouped: dict[tuple[str, str, str, str], list[FrictionRecord]] = defaultdict(list)
    for record in records:
        if open_only and record.status not in OPEN_STATUSES:
            continue
        grouped[(record.source, record.pattern, record.proposed_fix, record.status)].append(record)

    summaries: list[FrictionSummary] = []
    for (source, pattern, proposed_fix, status), group in grouped.items():
        evidence: list[str] = []
        seen: set[str] = set()
        for record in group:
            if record.evidence in seen:
                continue
            evidence.append(record.evidence)
            seen.add(record.evidence)
        summaries.append(
            FrictionSummary(
                source=source,
                pattern=pattern,
                proposed_fix=proposed_fix,
                status=status,
                count=sum(record.frequency for record in group),
                evidence=tuple(evidence[:5]),
            )
        )
    return tuple(sorted(summaries, key=lambda item: (-item.count, item.source, item.pattern)))


def format_friction_summary(records: Sequence[FrictionRecord], *, open_only: bool = True) -> str:
    summaries = summarize_records(records, open_only=open_only)
    status_counts = Counter(record.status for record in records)
    lines = [
        "Sprockets-Cogs friction summary",
        "- writes: no",
        f"- records: {len(records)}",
        f"- open records: {status_counts.get('open', 0)}",
        "",
    ]
    if not summaries:
        lines.append("No friction records found.")
        return "\n".join(lines)
    lines.extend([
        "| Count | Source | Proposed fix | Pattern | Evidence |",
        "|---:|---|---|---|---|",
    ])
    for item in summaries:
        evidence = "<br>".join(_markdown_cell(path, 80) for path in item.evidence)
        lines.append(
            f"| {item.count} | {_markdown_cell(item.source, 32)} | "
            f"{_markdown_cell(item.proposed_fix, 24)} | {_markdown_cell(item.pattern, 100)} | {evidence} |"
        )
    return "\n".join(lines)


def candidate_markdown(summary: FrictionSummary) -> str:
    evidence_lines = "\n".join(f"- `{path}`" for path in summary.evidence)
    return "\n".join([
        "---",
        "type: friction-candidate",
        "status: proposed",
        f"source: {summary.source}",
        f"proposed_fix: {summary.proposed_fix}",
        f"frequency: {summary.count}",
        "---",
        "",
        "# Friction Candidate",
        "",
        f"Pattern: {summary.pattern}",
        "",
        "## Evidence",
        "",
        evidence_lines or "- (none)",
        "",
        "## Promotion Decision",
        "",
        "- [ ] promote to fixture",
        "- [ ] promote to guard",
        "- [ ] kill",
        "- [ ] defer with trigger",
        "",
    ])


def write_top_candidate(
    records: Sequence[FrictionRecord],
    *,
    candidate_dir: Path = DEFAULT_CANDIDATE_DIR,
) -> Path:
    summaries = summarize_records(records)
    if not summaries:
        raise ValueError("no open friction summary available")
    top = summaries[0]
    candidate_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", top.pattern.lower()).strip("-")[:64] or "friction"
    path = candidate_dir / f"friction-candidate-{slug}.md"
    path.write_text(candidate_markdown(top), encoding="utf-8")
    return path


def record_review_discard(
    *,
    review_file: Path,
    reason: str,
    node_type: str,
    title: str,
    item_text: str,
    log_path: Path = DEFAULT_FRICTION_LOG,
) -> FrictionRecord:
    label = item_text if item_text and item_text != "?" else title
    return append_record(
        source="review-discard",
        pattern=f"discarded {node_type or '?'} review item: {reason}",
        evidence=str(review_file),
        proposed_fix="fixture",
        details=label,
        log_path=log_path,
    )


def record_review_apply_error(
    *,
    review_file: Path,
    reason: str,
    error: Exception,
    log_path: Path = DEFAULT_FRICTION_LOG,
) -> FrictionRecord:
    return append_record(
        source="review-apply-error",
        pattern=f"review approval failed validation/write: {reason}",
        evidence=str(review_file),
        proposed_fix="guard",
        details=str(error),
        log_path=log_path,
    )


def record_processing_failure(
    *,
    input_file: Path,
    error: Exception,
    log_path: Path = DEFAULT_FRICTION_LOG,
) -> FrictionRecord:
    return append_record(
        source="processing-failure",
        pattern=f"input processing failed: {type(error).__name__}",
        evidence=str(input_file),
        proposed_fix="test",
        details=str(error),
        log_path=log_path,
    )


def _markdown_cell(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text.replace("|", "\\|")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or write Sprockets-Cogs friction records.")
    parser.add_argument("--log", type=Path, default=DEFAULT_FRICTION_LOG)
    parser.add_argument("--all", action="store_true", help="include promoted and killed records")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--add", action="store_true", help="append one friction record")
    mode.add_argument("--write-candidate", action="store_true", help="write a candidate note for the top open pattern")
    parser.add_argument("--source", default="manual")
    parser.add_argument("--pattern")
    parser.add_argument("--evidence", default="")
    parser.add_argument("--proposed-fix", default="fixture", choices=sorted(KNOWN_FIXES))
    parser.add_argument("--details", default="")
    parser.add_argument("--candidate-dir", type=Path, default=DEFAULT_CANDIDATE_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.add:
        if not args.pattern:
            parser.error("--add requires --pattern")
        record = append_record(
            source=args.source,
            pattern=args.pattern,
            evidence=args.evidence,
            proposed_fix=args.proposed_fix,
            details=args.details,
            log_path=args.log,
        )
        print(f"Wrote friction record {record.record_id} to {args.log}")
        return
    records = load_friction_records(args.log)
    if args.write_candidate:
        path = write_top_candidate(records, candidate_dir=args.candidate_dir)
        print(f"Wrote friction candidate: {path}")
        return
    print(format_friction_summary(records, open_only=not args.all))


if __name__ == "__main__":
    main()

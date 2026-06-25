"""Review specialist facade for Jane review operations.

Most Jane commands preview inventory, packets, and decision effects. The packet
apply path stays explicit and source-checked for approved packet decisions.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import specialists.rosie.loop as agentic_loop
import frontmatter
import specialists.jane.review as review
from substrate.models import validate_node
from specialists.uniblab.friction import record_review_discard

SC_ROOT_ENV = "SPROCKETS_COGS_SC_ROOT"
DEFAULT_REVIEW_PACKET_PATH = Path(os.environ.get(SC_ROOT_ENV, str(Path.home() / "sc"))) / "output" / "review-packet.md"
DEFAULT_REVIEW_APPLY_AUDIT_PATH = (
    Path(os.environ.get(SC_ROOT_ENV, str(Path.home() / "sc"))) / "output" / "review-apply-audit.jsonl"
)


@dataclass(frozen=True)
class ReviewSpecialistConfig:
    """Filesystem roots owned by the Review specialist."""

    review_dir: Path = review.REVIEW_DIR
    packet_path: Path = DEFAULT_REVIEW_PACKET_PATH
    archive_dir: Path = agentic_loop.ARCHIVE_DIR
    audit_path: Path = DEFAULT_REVIEW_APPLY_AUDIT_PATH


@dataclass(frozen=True)
class ReviewInventoryPreview:
    """Read-only review queue inventory."""

    review_dir: Path
    total: int
    parseable: int
    unparseable: int
    by_source: dict[str, int]
    by_node_type: dict[str, int]
    by_confidence: dict[str, int]
    by_reason: dict[str, int]


@dataclass(frozen=True)
class ReviewDecisionRow:
    """One parsed decision row from an editable review decision template."""

    file: str
    decision: str
    notes: str = ""
    valid: bool = True
    issue: str = ""


@dataclass(frozen=True)
class ReviewDecisionImportPreview:
    """Read-only preview of a review decision import file."""

    review_dir: Path
    packet_path: Path
    rows: tuple[ReviewDecisionRow, ...]
    actionable_count: int
    pending_count: int
    invalid_count: int


@dataclass(frozen=True)
class ReviewDecisionApplyAction:
    """One read-only apply-preview action for an edited decision packet."""

    file: str
    decision: str
    effect: str
    notes: str = ""
    valid: bool = True
    issue: str = ""


@dataclass(frozen=True)
class ReviewDecisionApplyPreview:
    """Read-only preview of how review decisions would affect the queue."""

    review_dir: Path
    packet_path: Path
    actions: tuple[ReviewDecisionApplyAction, ...]
    approve_count: int
    discard_count: int
    edit_count: int
    skip_count: int
    pending_count: int
    rejected_count: int


@dataclass(frozen=True)
class ReviewPacketWriteResult:
    """Result of writing an operational review packet."""

    review_dir: Path
    packet_path: Path
    item_count: int
    bytes_written: int


@dataclass(frozen=True)
class ReviewPacketApplyResult:
    """Result of an explicitly confirmed Jane packet apply."""

    review_dir: Path
    packet_path: Path
    archive_dir: Path
    audit_path: Path
    approved_files: tuple[str, ...]
    audit_record: dict[str, Any]
    discarded_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewActionPreview:
    """Read-only preview for one direct Jane review action."""

    review_dir: Path
    target: str
    matched_files: tuple[str, ...]
    action: str
    effect: str
    valid: bool = True
    issue: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ReviewActionResult:
    """Result of one confirmed direct Jane review action."""

    review_dir: Path
    archive_dir: Path
    audit_path: Path
    target: str
    file: str
    action: str
    effect: str
    audit_record: dict[str, Any]
    reason: str = ""


class ReviewSpecialist:
    """Facade for human review reports and packet previews."""

    def __init__(self, config: ReviewSpecialistConfig | None = None) -> None:
        self.config = config or ReviewSpecialistConfig()

    def inventory(self) -> ReviewInventoryPreview:
        """Return a read-only summary of the canonical review queue."""

        report = review.review_report(self.config.review_dir)
        return ReviewInventoryPreview(
            review_dir=self.config.review_dir,
            total=_int(report.get("total")),
            parseable=_int(report.get("parseable")),
            unparseable=_int(report.get("unparseable")),
            by_source=_dict_str_int(report.get("by_source")),
            by_node_type=_dict_str_int(report.get("by_node_type")),
            by_confidence=_dict_str_int(report.get("by_confidence")),
            by_reason=_dict_str_int(report.get("by_reason")),
        )

    def pending_items(self) -> tuple[dict[str, Any], ...]:
        """Return read-only per-item summaries from the canonical review queue."""

        return tuple(review.list_pending(self.config.review_dir))

    def action_preview(self, target: str, action: str, *, reason: str = "") -> ReviewActionPreview:
        """Preview a direct per-item review action without writing."""

        normalized_action = _normalize_direct_action(action)
        matches = _resolve_review_target(target, self.config.review_dir)
        if not matches:
            return ReviewActionPreview(
                review_dir=self.config.review_dir,
                target=target,
                matched_files=(),
                action=normalized_action,
                effect="reject",
                valid=False,
                issue="no review item matched target",
                reason=reason,
            )
        if len(matches) > 1:
            return ReviewActionPreview(
                review_dir=self.config.review_dir,
                target=target,
                matched_files=tuple(path.name for path in matches),
                action=normalized_action,
                effect="reject",
                valid=False,
                issue="target is ambiguous",
                reason=reason,
            )
        review_path = matches[0]
        if normalized_action == "approve":
            issue = _approval_preview_issue(review_path) or _approval_collision_issue(review_path)
            if issue:
                return ReviewActionPreview(
                    review_dir=self.config.review_dir,
                    target=target,
                    matched_files=(review_path.name,),
                    action=normalized_action,
                    effect="reject",
                    valid=False,
                    issue=issue,
                    reason=reason,
                )
        return ReviewActionPreview(
            review_dir=self.config.review_dir,
            target=target,
            matched_files=(review_path.name,),
            action=normalized_action,
            effect=normalized_action,
            reason=reason,
        )

    def apply_action(
        self,
        target: str,
        action: str,
        *,
        reason: str = "",
        confirm: bool = False,
    ) -> ReviewActionResult:
        """Apply one confirmed direct review action through Jane's guarded backend."""

        if not confirm:
            raise ValueError("direct review action requires explicit confirmation")
        preview = self.action_preview(target, action, reason=reason)
        if not preview.valid:
            raise ValueError(f"direct review action rejected: {preview.issue}")
        if len(preview.matched_files) != 1:
            raise ValueError("direct review action requires exactly one matched file")
        file_name = preview.matched_files[0]
        review_path = self.config.review_dir / file_name
        approved_files: tuple[str, ...] = ()
        discarded_files: tuple[str, ...] = ()
        if preview.action == "approve":
            raw = _approval_raw(review_path)
            node = validate_node(raw)
            review.write_node(node)
            approved_files = (file_name,)
        elif preview.action == "reject":
            post = frontmatter.load(str(review_path))
            raw = review._extract_json(post.content) or {}
            review_reason = review._extract_reason(post.content)
            record_review_discard(
                review_file=review_path,
                reason=f"{review_reason}; operator: {reason}" if reason else review_reason,
                node_type=str(raw.get("node_type", "?")),
                title=str(raw.get("title", "?")),
                item_text=str(raw.get("item_text", "?")),
            )
            discarded_files = (file_name,)
        else:
            raise ValueError(f"unsupported direct review action: {preview.action}")

        _archive_review_file(review_path, self.config.archive_dir)
        audit_record = append_review_apply_audit(
            packet_path=Path(f"direct:{preview.action}:{target}"),
            review_dir=self.config.review_dir,
            approved_files=approved_files,
            discarded_files=discarded_files,
            audit_path=self.config.audit_path,
            decision=preview.action,
            command="direct-review-action",
            target=target,
            reason=reason,
        )
        return ReviewActionResult(
            review_dir=self.config.review_dir,
            archive_dir=self.config.archive_dir,
            audit_path=self.config.audit_path,
            target=target,
            file=file_name,
            action=preview.action,
            effect=preview.effect,
            audit_record=audit_record,
            reason=reason,
        )

    def packet_preview(self) -> str:
        """Return an Obsidian-readable review packet preview without writing."""

        return review.review_packet_markdown(self.config.review_dir)

    def decision_template(self) -> str:
        """Return an editable decision template without writing it anywhere."""

        return review_decision_template(self.config.review_dir)

    def decision_import_preview(self, packet_path: Path) -> ReviewDecisionImportPreview:
        """Parse a decision template and validate it against the current queue."""

        rows = parse_review_decision_template(packet_path.read_text())
        known_files = {item["file"] for item in review.list_pending(self.config.review_dir)}
        checked: list[ReviewDecisionRow] = []
        for row in rows:
            if not row.valid:
                checked.append(row)
            elif row.file not in known_files:
                checked.append(_replace_row(row, valid=False, issue="file is not in the current review queue"))
            else:
                checked.append(row)

        return ReviewDecisionImportPreview(
            review_dir=self.config.review_dir,
            packet_path=packet_path,
            rows=tuple(checked),
            actionable_count=sum(1 for row in checked if row.valid and row.decision in VALID_REVIEW_DECISIONS),
            pending_count=sum(1 for row in checked if row.valid and row.decision == "pending"),
            invalid_count=sum(1 for row in checked if not row.valid),
        )

    def packet_decision_import_preview(self, packet_path: Path) -> ReviewDecisionImportPreview:
        """Parse packet frontmatter status after source-checking the queue."""

        rows = packet_decision_rows(packet_path, self.config.review_dir)
        return ReviewDecisionImportPreview(
            review_dir=self.config.review_dir,
            packet_path=packet_path,
            rows=rows,
            actionable_count=sum(1 for row in rows if row.valid and row.decision in VALID_REVIEW_DECISIONS),
            pending_count=sum(1 for row in rows if row.valid and row.decision == "pending"),
            invalid_count=sum(1 for row in rows if not row.valid),
        )

    def packet_apply_preview(self, packet_path: Path) -> ReviewDecisionApplyPreview:
        """Preview guarded effects from a source-checked review packet."""

        import_preview = self.packet_decision_import_preview(packet_path)
        actions = tuple(_packet_apply_action(row, self.config) for row in import_preview.rows)
        return _apply_preview_from_actions(self.config.review_dir, packet_path, actions)

    def apply_approved_packet(self, packet_path: Path, *, confirm: bool = False) -> ReviewPacketApplyResult:
        """Apply an explicitly confirmed source-checked packet with audit."""

        if not confirm:
            raise ValueError("packet apply requires explicit confirmation")
        packet = frontmatter.load(str(packet_path))
        if packet.get("status") != "approved":
            raise ValueError("packet status must be approved for apply")

        preview = self.packet_apply_preview(packet_path)
        if preview.rejected_count:
            issues = "; ".join(action.issue for action in preview.actions if action.issue)
            raise ValueError(f"packet apply rejected: {issues}")
        if preview.edit_count:
            raise ValueError("packet apply rejected: edit decisions require manual packet rewrite")
        if preview.approve_count + preview.discard_count == 0:
            raise ValueError("packet apply found no approve/discard actions")

        approved_files: list[str] = []
        discarded_files: list[str] = []
        for action in preview.actions:
            if action.effect in {"pending", "skip"}:
                continue
            review_path = self.config.review_dir / action.file
            if action.effect == "approve":
                raw = _approval_raw(review_path)
                node = validate_node(raw)
                review.write_node(node)
                approved_files.append(action.file)
            elif action.effect == "discard":
                discarded_files.append(action.file)
            _archive_review_file(review_path, self.config.archive_dir)

        audit_record = append_review_apply_audit(
            packet_path=packet_path,
            review_dir=self.config.review_dir,
            approved_files=tuple(approved_files),
            discarded_files=tuple(discarded_files),
            audit_path=self.config.audit_path,
        )
        packet["status"] = "applied"
        packet["applied_at"] = audit_record["created_at"]
        packet["audit_path"] = str(self.config.audit_path)
        packet_path.write_text(frontmatter.dumps(packet), encoding="utf-8")
        return ReviewPacketApplyResult(
            review_dir=self.config.review_dir,
            packet_path=packet_path,
            archive_dir=self.config.archive_dir,
            audit_path=self.config.audit_path,
            approved_files=tuple(approved_files),
            audit_record=audit_record,
            discarded_files=tuple(discarded_files),
        )

    def decision_apply_preview(self, packet_path: Path) -> ReviewDecisionApplyPreview:
        """Preview guarded decision effects without applying them."""

        import_preview = self.decision_import_preview(packet_path)
        seen_files: set[str] = set()
        actions: list[ReviewDecisionApplyAction] = []
        for row in import_preview.rows:
            if not row.valid:
                actions.append(_action_from_row(row, effect="reject", valid=False, issue=row.issue))
                continue
            if row.file in seen_files:
                actions.append(
                    _action_from_row(
                        row,
                        effect="reject",
                        valid=False,
                        issue="duplicate decision row for review file",
                    )
                )
                continue
            seen_files.add(row.file)
            if row.decision == "pending":
                actions.append(_action_from_row(row, effect="pending"))
            elif row.decision == "approve":
                issue = _approval_preview_issue(self.config.review_dir / row.file)
                if issue:
                    actions.append(_action_from_row(row, effect="reject", valid=False, issue=issue))
                else:
                    actions.append(_action_from_row(row, effect="approve"))
            elif row.decision in DISCARD_DECISIONS:
                actions.append(_action_from_row(row, effect="discard"))
            elif row.decision == "edit":
                actions.append(_action_from_row(row, effect="edit"))
            elif row.decision == "skip":
                actions.append(_action_from_row(row, effect="skip"))

        return _apply_preview_from_actions(self.config.review_dir, packet_path, tuple(actions))

    def operational_packet_markdown(self) -> str:
        """Return the complete operational packet intended for file output."""

        return review_operational_packet_markdown(self.config.review_dir)

    def write_operational_packet(self, packet_path: Path | None = None) -> ReviewPacketWriteResult:
        """Write an idempotent operational packet outside the vault."""

        destination = packet_path or self.config.packet_path
        content = self.operational_packet_markdown()
        return _write_packet_content(
            review_dir=self.config.review_dir,
            destination=destination,
            content=content,
        )

    def write_review_packet(self, packet_path: Path | None = None) -> ReviewPacketWriteResult:
        """Write the importable Jane review packet outside the vault."""

        destination = packet_path or self.config.packet_path
        content = self.packet_preview()
        return _write_packet_content(
            review_dir=self.config.review_dir,
            destination=destination,
            content=content,
        )


def _write_packet_content(
    *,
    review_dir: Path,
    destination: Path,
    content: str,
) -> ReviewPacketWriteResult:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return ReviewPacketWriteResult(
        review_dir=review_dir,
        packet_path=destination,
        item_count=len(review.list_pending(review_dir)),
        bytes_written=len(content.encode("utf-8")),
    )


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _dict_str_int(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): count for key, count in value.items() if isinstance(count, int)}


VALID_REVIEW_DECISIONS = {"approve", "reject", "discard", "edit", "skip"}
DISCARD_DECISIONS = {"reject", "discard"}
DIRECT_REVIEW_ACTIONS = {"approve", "reject", "show"}
PACKET_STATUS_DECISIONS = {
    "pending": "pending",
    "approved": "approve",
    "rejected": "reject",
    "deferred": "skip",
}


def _normalize_direct_action(action: str) -> str:
    normalized = action.strip().lower()
    if normalized == "discard":
        normalized = "reject"
    if normalized not in DIRECT_REVIEW_ACTIONS:
        raise ValueError("direct review action must be approve, reject, or show")
    return normalized


def _resolve_review_target(target: str, review_dir: Path) -> tuple[Path, ...]:
    """Resolve exact review filename or unique title/item_text match."""

    needle = " ".join(target.strip().lower().split())
    if not needle:
        return ()
    exact = review_dir / target
    if exact.exists() and exact.is_file():
        return (exact,)

    matches: list[Path] = []
    for item in review.list_pending(review_dir):
        path = review_dir / item["file"]
        fields = [
            item.get("file", ""),
            item.get("title", ""),
            item.get("item_text", ""),
        ]
        normalized_fields = {" ".join(str(field).strip().lower().split()) for field in fields}
        if needle in normalized_fields:
            matches.append(path)
    return tuple(matches)


def _apply_preview_from_actions(
    review_dir: Path,
    packet_path: Path,
    actions: tuple[ReviewDecisionApplyAction, ...],
) -> ReviewDecisionApplyPreview:
    return ReviewDecisionApplyPreview(
        review_dir=review_dir,
        packet_path=packet_path,
        actions=actions,
        approve_count=sum(1 for action in actions if action.effect == "approve"),
        discard_count=sum(1 for action in actions if action.effect == "discard"),
        edit_count=sum(1 for action in actions if action.effect == "edit"),
        skip_count=sum(1 for action in actions if action.effect == "skip"),
        pending_count=sum(1 for action in actions if action.effect == "pending"),
        rejected_count=sum(1 for action in actions if action.effect == "reject"),
    )


def _packet_apply_action(
    row: ReviewDecisionRow,
    config: ReviewSpecialistConfig,
) -> ReviewDecisionApplyAction:
    if not row.valid:
        return _action_from_row(row, effect="reject", valid=False, issue=row.issue)
    if row.decision != "approve":
        if row.decision in DISCARD_DECISIONS:
            return _action_from_row(row, effect="discard")
        effect = "pending" if row.decision == "pending" else row.decision
        return _action_from_row(row, effect=effect)
    review_path = config.review_dir / row.file
    issue = _approval_preview_issue(review_path) or _approval_collision_issue(review_path)
    if issue:
        return _action_from_row(row, effect="reject", valid=False, issue=issue)
    archive_path = config.archive_dir / row.file
    if archive_path.exists():
        return _action_from_row(row, effect="reject", valid=False, issue="review archive file already exists")
    return _action_from_row(row, effect="approve")


def _replace_row(
    row: ReviewDecisionRow,
    *,
    valid: bool | None = None,
    issue: str | None = None,
) -> ReviewDecisionRow:
    return ReviewDecisionRow(
        file=row.file,
        decision=row.decision,
        notes=row.notes,
        valid=row.valid if valid is None else valid,
        issue=row.issue if issue is None else issue,
    )


def _action_from_row(
    row: ReviewDecisionRow,
    *,
    effect: str,
    valid: bool = True,
    issue: str = "",
) -> ReviewDecisionApplyAction:
    return ReviewDecisionApplyAction(
        file=row.file,
        decision=row.decision,
        notes=row.notes,
        effect=effect,
        valid=valid,
        issue=issue,
    )


def _approval_preview_issue(path: Path) -> str:
    try:
        post = frontmatter.load(str(path))
        raw = review._extract_json(post.content)
    except OSError as exc:
        return f"cannot read review file: {exc}"
    if not raw:
        return "review item is unparseable"
    raw = dict(raw)
    raw["confidence"] = "high"
    reason = review._extract_reason(post.content)
    try:
        raw = review.normalize_review_raw(
            raw,
            reason=reason,
            source_date=review._review_source_date(post),
        )
        validate_node(raw)
    except Exception as exc:
        return f"approval would fail validation: {exc}"
    return ""


def _approval_raw(path: Path) -> dict[str, Any]:
    post = frontmatter.load(str(path))
    raw = review._extract_json(post.content)
    if not raw:
        raise ValueError(f"review item is unparseable: {path.name}")
    normalized = dict(raw)
    normalized["confidence"] = "high"
    return review.normalize_review_raw(
        normalized,
        reason=review._extract_reason(post.content),
        source_date=review._review_source_date(post),
    )


def _approval_collision_issue(path: Path) -> str:
    raw = _approval_raw(path)
    node = validate_node(raw)
    folder = agentic_loop.SPROCKETS_FOLDERS.get(node.node_type)
    if folder is None:
        return ""
    duplicate = agentic_loop._find_duplicate(node.title, folder)
    if duplicate is not None:
        return f"approval would collide with existing node: {duplicate.name}"
    return ""


def _archive_review_file(path: Path, archive_dir: Path) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    destination = archive_dir / path.name
    if destination.exists():
        raise ValueError(f"review archive file already exists: {destination.name}")
    shutil.move(str(path), destination)
    return destination


def append_review_apply_audit(
    *,
    packet_path: Path,
    review_dir: Path,
    approved_files: tuple[str, ...],
    audit_path: Path,
    discarded_files: tuple[str, ...] = (),
    decision: str = "approved",
    command: str = "packet-apply",
    target: str = "",
    reason: str = "",
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Append one JSONL record for a successful Jane packet apply."""

    timestamp = (
        created_at.astimezone().isoformat(timespec="seconds")
        if created_at is not None
        else datetime.now().astimezone().isoformat(timespec="seconds")
    )
    record: dict[str, Any] = {
        "schema_version": 1,
        "created_at": timestamp,
        "packet_path": str(packet_path),
        "review_dir": str(review_dir),
        "decision": decision,
        "command": command,
        "target": target,
        "reason": reason,
        "approved_files": list(approved_files),
        "discarded_files": list(discarded_files),
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def _format_counter(label: str, values: dict[str, int]) -> list[str]:
    if not values:
        return [f"- {label}: (none)"]
    return [f"- {label}: " + ", ".join(f"{key}={count}" for key, count in values.items())]


def format_review_inventory(preview: ReviewInventoryPreview) -> str:
    """Format a read-only Review specialist inventory."""

    lines = [
        "Review specialist inventory preview",
        f"- review dir: {preview.review_dir}",
        f"- total: {preview.total}",
        f"- parseable: {preview.parseable}",
        f"- unparseable: {preview.unparseable}",
    ]
    lines.extend(_format_counter("by source", preview.by_source))
    lines.extend(_format_counter("by node_type", preview.by_node_type))
    lines.extend(_format_counter("by confidence", preview.by_confidence))
    lines.extend(_format_counter("by reason", preview.by_reason))
    lines.append("- writes: no")
    return "\n".join(lines)


def format_review_items(items: Sequence[dict[str, Any]]) -> str:
    """Format read-only review item summaries."""

    lines = ["Review specialist item preview", "- writes: no"]
    if not items:
        lines.append("Nothing in review/. All clear.")
        return "\n".join(lines)
    for item in items:
        parse_note = "" if item.get("parseable") else " [UNPARSEABLE]"
        lines.extend(
            [
                f"{item.get('file', '?')}{parse_note}",
                f"  source:     {item.get('source', '?')}",
                f"  reason:     {item.get('reason', '?')}",
                f"  node_type:  {item.get('node_type', '?')}",
                f"  title:      {item.get('title', '?')}",
                f"  item_text:  {item.get('item_text', '?')}",
                f"  date:       {item.get('date', '?')}",
                f"  confidence: {item.get('confidence', '?')}",
            ]
        )
    return "\n".join(lines)


def format_action_preview(preview: ReviewActionPreview) -> str:
    """Format a direct review action preview."""

    lines = [
        "Review specialist direct action preview",
        f"- review dir: {preview.review_dir}",
        f"- target: {preview.target}",
        f"- action: {preview.action}",
        f"- effect: {preview.effect}",
        f"- matched files: {len(preview.matched_files)}",
        f"- valid: {'yes' if preview.valid else 'no'}",
        "- vault writes: no",
        "- review queue writes: no",
    ]
    lines.extend(f"- match: {file_name}" for file_name in preview.matched_files)
    if preview.reason:
        lines.append(f"- reason: {preview.reason}")
    if preview.issue:
        lines.append(f"- issue: {preview.issue}")
    return "\n".join(lines)


def format_action_result(result: ReviewActionResult) -> str:
    """Format a confirmed direct review action result."""

    return "\n".join(
        [
            "Review specialist direct action applied",
            f"- review dir: {result.review_dir}",
            f"- target: {result.target}",
            f"- file: {result.file}",
            f"- action: {result.action}",
            f"- effect: {result.effect}",
            f"- review archive: {result.archive_dir}",
            f"- audit JSONL: {result.audit_path}",
            "- vault writes: yes" if result.action == "approve" else "- vault writes: no",
            "- review queue writes: yes",
        ]
    )


def format_packet_preview(packet: str) -> str:
    """Format an Obsidian review packet preview through the Review boundary."""

    return "\n".join(
        [
            "Review specialist packet preview",
            "- writes: no",
            "",
            packet,
        ]
    )


def review_decision_template(review_dir: Path = review.REVIEW_DIR) -> str:
    """Return an editable decision table generated from the canonical queue."""

    items = review.list_pending(review_dir)
    lines = [
        "# Sprockets-Cogs Review Decision Template",
        "",
        "> Preview/import contract only. This template does not approve, reject,",
        "> edit, archive, or write anything by itself. Use decisions `approve`,",
        "> `reject`, `edit`, or `skip`; leave blank for pending. `discard`",
        "> remains a compatibility alias for `reject`.",
        "",
        "| File | Decision | Notes |",
        "|---|---|---|",
    ]
    for item in items:
        lines.append(f"| {_markdown_cell(item.get('file', '?'))} |  |  |")
    if not items:
        lines.append("| (none) |  |  |")
    lines.append("")
    return "\n".join(lines)


def review_operational_packet_markdown(review_dir: Path = review.REVIEW_DIR) -> str:
    """Return a regenerated packet combining queue preview and decision template."""

    return "\n".join(
        [
            "# Sprockets-Cogs Review Operations Packet",
            "",
            "> Generated from the canonical review queue. The queue in `review/`",
            "> remains the source of truth until a guarded apply path exists.",
            "",
            "## Queue Preview",
            "",
            review.review_packet_markdown(review_dir),
            "",
            "## Decision Template",
            "",
            review_decision_template(review_dir),
        ]
    )


def packet_decision_rows(packet_path: Path, review_dir: Path = review.REVIEW_DIR) -> tuple[ReviewDecisionRow, ...]:
    """Build decision rows from a source-checked review packet frontmatter."""

    try:
        post = frontmatter.load(str(packet_path))
    except OSError as exc:
        return (_packet_error(f"cannot read packet: {exc}"),)
    if post.get("type") != "review-packet":
        return (_packet_error("packet type must be review-packet"),)
    if post.get("queue") != "review":
        return (_packet_error("packet queue must be review"),)

    status = str(post.get("status", "")).strip().lower()
    if status not in PACKET_STATUS_DECISIONS:
        return (_packet_error("packet status must be pending, approved, rejected, or deferred"),)

    review_files = post.get("review_files")
    if not isinstance(review_files, list) or not all(isinstance(name, str) and name for name in review_files):
        return (_packet_error("packet review_files must be a list of review filenames"),)

    queue_items = review.list_pending(review_dir)
    queue_files = [item["file"] for item in queue_items]
    if review_files != queue_files:
        return (_packet_error("packet review_files do not match the current review queue"),)
    if post.get("item_count") != len(queue_items):
        return (_packet_error("packet item_count does not match the current review queue"),)
    if post.get("queue_fingerprint") != review.review_queue_fingerprint(review_dir):
        return (_packet_error("packet queue_fingerprint does not match current review files"),)

    decision_rows = parse_review_decision_template(post.content)
    if decision_rows:
        known_files = set(review_files)
        seen_files: set[str] = set()
        checked: list[ReviewDecisionRow] = []
        for row in decision_rows:
            if not row.valid:
                checked.append(row)
            elif row.file not in known_files:
                checked.append(_replace_row(row, valid=False, issue="file is not in packet review_files"))
            elif row.file in seen_files:
                checked.append(_replace_row(row, valid=False, issue="duplicate decision row for review file"))
            else:
                seen_files.add(row.file)
                checked.append(row)
        missing = [file_name for file_name in review_files if file_name not in seen_files]
        checked.extend(ReviewDecisionRow(file=file_name, decision="pending") for file_name in missing)
        return tuple(checked)

    decision = PACKET_STATUS_DECISIONS[status]
    return tuple(
        ReviewDecisionRow(file=file_name, decision=decision, notes=f"packet status: {status}")
        for file_name in review_files
    )


def _packet_error(issue: str) -> ReviewDecisionRow:
    return ReviewDecisionRow(file="(packet)", decision="", valid=False, issue=issue)


def parse_review_decision_template(markdown: str) -> tuple[ReviewDecisionRow, ...]:
    """Parse the simple decision table used by review decision templates."""

    rows: list[ReviewDecisionRow] = []
    in_table = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line == "| File | Decision | Notes |":
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            if rows:
                break
            continue
        if set(line.replace("|", "").strip()) <= {"-", ":"}:
            continue
        cells = _split_markdown_row(line)
        if len(cells) != 3:
            rows.append(ReviewDecisionRow(file="", decision="", valid=False, issue="decision row must have 3 columns"))
            continue
        file_name, decision, notes = cells
        decision = decision.lower()
        if file_name == "(none)":
            continue
        if not file_name:
            rows.append(ReviewDecisionRow(file=file_name, decision=decision, notes=notes, valid=False, issue="file is required"))
        elif not decision:
            rows.append(ReviewDecisionRow(file=file_name, decision="pending", notes=notes))
        elif decision not in VALID_REVIEW_DECISIONS:
            rows.append(
                ReviewDecisionRow(
                    file=file_name,
                    decision=decision,
                    notes=notes,
                    valid=False,
                    issue="decision must be approve, reject, edit, skip, discard, or blank",
                )
            )
        else:
            rows.append(ReviewDecisionRow(file=file_name, decision=decision, notes=notes))
    return tuple(rows)


def _markdown_cell(value: object) -> str:
    return str(value or "").replace("|", "\\|")


def _split_markdown_row(line: str) -> list[str]:
    text = line.strip().strip("|")
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return cells


def format_decision_template(template: str) -> str:
    """Format an editable decision template preview."""

    return "\n".join(
        [
            "Review specialist decision template preview",
            "- writes: no",
            "",
            template,
        ]
    )


def format_decision_import_preview(preview: ReviewDecisionImportPreview) -> str:
    """Format a read-only decision import preview."""

    lines = [
        "Review specialist decision import preview",
        f"- review dir: {preview.review_dir}",
        f"- packet: {preview.packet_path}",
        f"- rows: {len(preview.rows)}",
        f"- actionable: {preview.actionable_count}",
        f"- pending: {preview.pending_count}",
        f"- invalid: {preview.invalid_count}",
        "- writes: no",
    ]
    if not preview.rows:
        lines.append("No decision rows found.")
        return "\n".join(lines)
    lines.append("")
    for row in preview.rows:
        status = "ok" if row.valid else f"invalid: {row.issue}"
        lines.append(f"- {row.file}: {row.decision} ({status})")
    return "\n".join(lines)


def format_decision_apply_preview(preview: ReviewDecisionApplyPreview) -> str:
    """Format guarded decision effects without applying them."""

    lines = [
        "Review specialist guarded apply preview",
        f"- review dir: {preview.review_dir}",
        f"- packet: {preview.packet_path}",
        f"- rows: {len(preview.actions)}",
        f"- would approve: {preview.approve_count}",
        f"- would discard: {preview.discard_count}",
        f"- would edit: {preview.edit_count}",
        f"- would skip: {preview.skip_count}",
        f"- pending: {preview.pending_count}",
        f"- rejected: {preview.rejected_count}",
        "- vault writes: no",
        "- review queue writes: no",
    ]
    if not preview.actions:
        lines.append("No decision rows found.")
        return "\n".join(lines)
    lines.append("")
    for action in preview.actions:
        if action.effect == "reject":
            detail = f"reject: {action.issue}"
        elif action.effect == "pending":
            detail = "pending: no action"
        elif action.effect == "edit":
            detail = "edit requested: leave in review for manual packet rewrite"
        else:
            detail = f"would {action.effect}"
        lines.append(f"- {action.file}: {action.decision} -> {detail}")
    return "\n".join(lines)


def format_packet_apply_result(result: ReviewPacketApplyResult) -> str:
    """Format an explicitly confirmed packet apply."""

    lines = [
        "Review specialist approved packet apply",
        f"- review dir: {result.review_dir}",
        f"- packet: {result.packet_path}",
        f"- archived review items: {len(result.approved_files) + len(result.discarded_files)}",
        f"- approved: {len(result.approved_files)}",
        f"- discarded: {len(result.discarded_files)}",
        f"- review archive: {result.archive_dir}",
        f"- audit JSONL: {result.audit_path}",
        "- packet status: applied",
        "- vault writes: yes",
        "- review queue writes: yes",
    ]
    lines.extend(f"- approved: {file_name}" for file_name in result.approved_files)
    lines.extend(f"- discarded: {file_name}" for file_name in result.discarded_files)
    return "\n".join(lines)


def format_packet_write_result(result: ReviewPacketWriteResult) -> str:
    """Format an operational packet write result."""

    return "\n".join(
        [
            "Review specialist packet write",
            f"- review dir: {result.review_dir}",
            f"- packet: {result.packet_path}",
            f"- review items: {result.item_count}",
            f"- bytes written: {result.bytes_written}",
            "- vault writes: no",
            "- review queue writes: no",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jane review specialist preview and guarded packet apply.")
    parser.add_argument(
        "--review-dir",
        type=Path,
        default=review.REVIEW_DIR,
        help="Review queue directory. Defaults to the configured vault review directory.",
    )
    parser.add_argument(
        "--packet-path",
        type=Path,
        default=DEFAULT_REVIEW_PACKET_PATH,
        help="Operational review packet path. Defaults to SPROCKETS_COGS_SC_ROOT/output/review-packet.md.",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=agentic_loop.ARCHIVE_DIR,
        help="Review archive directory for confirmed packet apply. Defaults to SC archive/.",
    )
    parser.add_argument(
        "--audit-path",
        type=Path,
        default=DEFAULT_REVIEW_APPLY_AUDIT_PATH,
        help="JSONL audit path for confirmed packet apply. Defaults under SC output/.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm write effects after previewing an approved packet or direct action.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Alias for --confirm for direct action commands.",
    )
    parser.add_argument(
        "--reason",
        default="",
        help="Operator reason for direct reject action.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true", help="Preview review queue summary without writing.")
    mode.add_argument("--list", action="store_true", help="Preview review queue items without writing.")
    mode.add_argument("--packet-preview", action="store_true", help="Preview Obsidian review packet without writing.")
    mode.add_argument("--decision-template", action="store_true", help="Print an editable review decision template without writing.")
    mode.add_argument("--decision-import-preview", type=Path, metavar="PATH", help="Parse a filled decision template without applying it.")
    mode.add_argument("--packet-import-preview", type=Path, metavar="PATH", help="Parse packet frontmatter status after source checks without applying it.")
    mode.add_argument("--packet-apply-preview", type=Path, metavar="PATH", help="Preview guarded packet apply from packet frontmatter without writing.")
    mode.add_argument("--packet-apply", type=Path, metavar="PATH", help="Apply a source-checked approved packet only with --confirm.")
    mode.add_argument("--apply-preview", type=Path, metavar="PATH", help="Preview guarded decision effects without applying them.")
    mode.add_argument("--write-packet", action="store_true", help="Regenerate the operational review packet outside the vault. Writes only --packet-path.")
    mode.add_argument("--write-review-packet", action="store_true", help="Regenerate the importable Jane review packet outside the vault. Writes only --packet-path.")
    mode.add_argument("--show", metavar="TARGET", help="Preview one review item by exact filename or unique title/text match.")
    mode.add_argument("--approve", metavar="TARGET", help="Approve one review item by exact filename or unique title/text match. Requires --confirm/--yes.")
    mode.add_argument("--reject", metavar="TARGET", help="Reject one review item by exact filename or unique title/text match. Requires --confirm/--yes.")
    return parser


def specialist_from_args(args: argparse.Namespace) -> ReviewSpecialist:
    return ReviewSpecialist(
        ReviewSpecialistConfig(
            review_dir=args.review_dir,
            packet_path=args.packet_path,
            archive_dir=args.archive_dir,
            audit_path=args.audit_path,
        )
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    specialist = specialist_from_args(args)

    if args.inventory:
        print(format_review_inventory(specialist.inventory()))
    elif args.list:
        print(format_review_items(specialist.pending_items()))
    elif args.packet_preview:
        print(format_packet_preview(specialist.packet_preview()))
    elif args.decision_template:
        print(format_decision_template(specialist.decision_template()))
    elif args.decision_import_preview:
        print(format_decision_import_preview(specialist.decision_import_preview(args.decision_import_preview)))
    elif args.packet_import_preview:
        print(format_decision_import_preview(specialist.packet_decision_import_preview(args.packet_import_preview)))
    elif args.packet_apply_preview:
        print(format_decision_apply_preview(specialist.packet_apply_preview(args.packet_apply_preview)))
    elif args.packet_apply:
        if not args.confirm:
            parser.error("--packet-apply requires --confirm")
        print(format_packet_apply_result(specialist.apply_approved_packet(args.packet_apply, confirm=args.confirm)))
    elif args.apply_preview:
        print(format_decision_apply_preview(specialist.decision_apply_preview(args.apply_preview)))
    elif args.write_packet:
        print(format_packet_write_result(specialist.write_operational_packet()))
    elif args.write_review_packet:
        print(format_packet_write_result(specialist.write_review_packet()))
    elif args.show:
        print(format_action_preview(specialist.action_preview(args.show, "show", reason=args.reason)))
    elif args.approve:
        confirmed = args.confirm or args.yes
        if not confirmed:
            print(format_action_preview(specialist.action_preview(args.approve, "approve", reason=args.reason)))
        else:
            print(format_action_result(specialist.apply_action(args.approve, "approve", reason=args.reason, confirm=True)))
    elif args.reject:
        confirmed = args.confirm or args.yes
        if not confirmed:
            print(format_action_preview(specialist.action_preview(args.reject, "reject", reason=args.reason)))
        else:
            print(format_action_result(specialist.apply_action(args.reject, "reject", reason=args.reason, confirm=True)))


if __name__ == "__main__":
    main()

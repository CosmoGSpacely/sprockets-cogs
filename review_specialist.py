"""Review specialist facade for Phase 4 orchestration.

Stage 42A keeps this boundary read-only. It wraps the existing review queue
reporting and packet preview behavior without replacing `scripts/review` or
adding decision import/apply behavior.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import review


@dataclass(frozen=True)
class ReviewSpecialistConfig:
    """Filesystem roots owned by the Review specialist."""

    review_dir: Path = review.REVIEW_DIR


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


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _dict_str_int(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): count for key, count in value.items() if isinstance(count, int)}


VALID_REVIEW_DECISIONS = {"approve", "discard", "skip"}


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
        "> Preview/import contract only. This template does not approve, discard,",
        "> archive, or write anything by itself. Use decisions `approve`, `discard`,",
        "> or `skip`; leave blank for pending.",
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
                    issue="decision must be approve, discard, skip, or blank",
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Review specialist preview.")
    parser.add_argument(
        "--review-dir",
        type=Path,
        default=review.REVIEW_DIR,
        help="Review queue directory. Defaults to the configured vault review directory.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true", help="Preview review queue summary without writing.")
    mode.add_argument("--list", action="store_true", help="Preview review queue items without writing.")
    mode.add_argument("--packet-preview", action="store_true", help="Preview Obsidian review packet without writing.")
    mode.add_argument("--decision-template", action="store_true", help="Print an editable review decision template without writing.")
    mode.add_argument("--decision-import-preview", type=Path, metavar="PATH", help="Parse a filled decision template without applying it.")
    return parser


def specialist_from_args(args: argparse.Namespace) -> ReviewSpecialist:
    return ReviewSpecialist(ReviewSpecialistConfig(review_dir=args.review_dir))


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


if __name__ == "__main__":
    main()

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


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _dict_str_int(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): count for key, count in value.items() if isinstance(count, int)}


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


if __name__ == "__main__":
    main()

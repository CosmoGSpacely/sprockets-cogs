"""Preview-first helper for writing stage closeout evidence blocks.

This does not decide what happened in a stage. It gives Codex and humans a
repeatable way to capture the boring evidence that was otherwise living only in
terminal scrollback: timestamp, summary bullets, promoted/killed/scheduled
outcomes, commands run, and follow-up notes.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class StageCloseout:
    stage: str
    title: str
    summary: tuple[str, ...] = field(default_factory=tuple)
    promoted: tuple[str, ...] = field(default_factory=tuple)
    killed: tuple[str, ...] = field(default_factory=tuple)
    scheduled: tuple[str, ...] = field(default_factory=tuple)
    commands: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


def _section(title: str, rows: tuple[str, ...], *, empty: str = "- none") -> list[str]:
    lines = [f"### {title}", ""]
    if rows:
        lines.extend(f"- {row}" for row in rows)
    else:
        lines.append(empty)
    lines.append("")
    return lines


def render_closeout(closeout: StageCloseout) -> str:
    """Render a Markdown closeout block."""

    lines = [
        f"## Closeout Evidence - {closeout.timestamp}",
        "",
        f"Stage: {closeout.stage}",
        "",
        closeout.title,
        "",
    ]
    lines.extend(_section("Summary", closeout.summary))
    lines.extend(_section("Promoted", closeout.promoted))
    lines.extend(_section("Killed", closeout.killed))
    lines.extend(_section("Scheduled", closeout.scheduled))
    lines.extend(_section("Commands", closeout.commands))
    lines.extend(_section("Notes", closeout.notes))
    return "\n".join(lines).rstrip() + "\n"


def append_closeout(path: Path, block: str) -> None:
    """Append a closeout block to a stage file."""

    existing = path.read_text() if path.exists() else ""
    separator = "\n" if existing.endswith("\n") else "\n\n"
    path.write_text(existing + separator + block)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render or append a standardized stage closeout evidence block.",
    )
    parser.add_argument("--stage", required=True, help="stage number or label")
    parser.add_argument("--title", required=True, help="one-line closeout title")
    parser.add_argument("--summary", action="append", default=None, help="summary bullet; repeatable")
    parser.add_argument("--promoted", action="append", default=None, help="promoted outcome; repeatable")
    parser.add_argument("--killed", action="append", default=None, help="killed outcome; repeatable")
    parser.add_argument("--scheduled", action="append", default=None, help="scheduled outcome; repeatable")
    parser.add_argument("--command", action="append", default=None, help="command/evidence bullet; repeatable")
    parser.add_argument("--note", action="append", default=None, help="note bullet; repeatable")
    parser.add_argument("--stage-file", type=Path, help="stage GROK.md file to append to")
    parser.add_argument("--append", action="store_true", help="append to --stage-file instead of previewing")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    block = render_closeout(
        StageCloseout(
            stage=args.stage,
            title=args.title,
            summary=tuple(args.summary or ()),
            promoted=tuple(args.promoted or ()),
            killed=tuple(args.killed or ()),
            scheduled=tuple(args.scheduled or ()),
            commands=tuple(args.command or ()),
            notes=tuple(args.note or ()),
        )
    )
    if args.append:
        if not args.stage_file:
            parser.error("--append requires --stage-file")
        append_closeout(args.stage_file, block)
        print(f"appended closeout evidence to {args.stage_file}")
    else:
        print(block, end="")


if __name__ == "__main__":
    main()

"""Read-only intake archive report."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import frontmatter

import specialists.rosie.loop as agentic_loop


@dataclass(frozen=True)
class ArchivedInput:
    path: Path
    source: str
    session_id: str


@dataclass(frozen=True)
class ArchiveReport:
    archive_dir: Path
    input_dir: Path
    archived: tuple[ArchivedInput, ...]
    ignored_inputs: tuple[Path, ...]


def build_archive_report(
    archive_dir: Path = agentic_loop.ARCHIVE_DIR,
    input_dir: Path = agentic_loop.INPUT_DIR,
    *,
    limit: int = 10,
) -> ArchiveReport:
    archived_paths = sorted(
        archive_dir.glob("*.input") if archive_dir.exists() else (),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]
    archived = tuple(_archived_input(path) for path in archived_paths)
    ignored = tuple(
        sorted(
            (
                path
                for path in input_dir.iterdir()
                if path.is_file() and path.suffix != ".input"
            ),
            key=lambda path: path.name,
        )
        if input_dir.exists()
        else ()
    )
    return ArchiveReport(
        archive_dir=archive_dir,
        input_dir=input_dir,
        archived=archived,
        ignored_inputs=ignored,
    )


def _archived_input(path: Path) -> ArchivedInput:
    try:
        post = frontmatter.load(path)
    except Exception:
        return ArchivedInput(path=path, source="unparseable", session_id="")
    return ArchivedInput(
        path=path,
        source=str(post.get("source") or "unknown"),
        session_id=str(post.get("session_id") or ""),
    )


def format_archive_report(report: ArchiveReport) -> str:
    lines = [
        "Input archive report",
        "- writes: no",
        f"- archive_dir: {report.archive_dir}",
        f"- input_dir: {report.input_dir}",
        f"- recent archived .input files: {len(report.archived)}",
    ]
    for item in report.archived:
        suffix = f" source={item.source}"
        if item.session_id:
            suffix += f" session={item.session_id}"
        lines.append(f"  - {item.path.name}{suffix}")
    lines.append(f"- ignored non-.input files: {len(report.ignored_inputs)}")
    for path in report.ignored_inputs:
        lines.append(f"  - {path.name}: ignored because Rosie only processes .input files")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, default=agentic_loop.ARCHIVE_DIR)
    parser.add_argument("--input-dir", type=Path, default=agentic_loop.INPUT_DIR)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    print(format_archive_report(build_archive_report(args.archive_dir, args.input_dir, limit=args.limit)))


if __name__ == "__main__":
    main()

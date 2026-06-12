"""Generic source adapter proofs, acknowledgements, and status reporting."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import frontmatter

from input_adapter import InputEnvelope, write_input_file
from response_routing import (
    ResponseContext,
    ResponseEnvelope,
    ResponseType,
    format_response_preview,
    response_context_from_frontmatter,
)


@dataclass(frozen=True)
class AdapterStatus:
    input_dir: Path
    pending_inputs: int
    ignored_files: int
    rejected_files: int
    by_source: dict[str, int]
    oldest_pending: str


def write_source_input(
    *,
    source: str,
    content: str,
    input_dir: Path,
    session_id: str = "",
    source_id: str = "",
    modality: str = "text",
) -> Path:
    envelope = InputEnvelope(
        content=content,
        source=source,
        session_id=session_id,
        source_id=source_id,
        modality=modality,
    )
    return write_input_file(envelope, input_dir).path


def build_adapter_status(input_dir: Path, rejected_dir: Path | None = None) -> AdapterStatus:
    pending = sorted(input_dir.glob("*.input")) if input_dir.exists() else []
    ignored = [
        path
        for path in input_dir.iterdir()
        if input_dir.exists() and path.is_file() and path.suffix != ".input"
    ] if input_dir.exists() else []
    rejected = sorted(rejected_dir.glob("*")) if rejected_dir and rejected_dir.exists() else []
    sources: Counter[str] = Counter()
    for path in pending:
        try:
            post = frontmatter.load(path)
        except Exception:
            sources["unparseable"] += 1
            continue
        sources[str(post.get("source") or "unknown")] += 1
    oldest = min(pending, key=lambda path: path.stat().st_mtime).name if pending else ""
    return AdapterStatus(
        input_dir=input_dir,
        pending_inputs=len(pending),
        ignored_files=len(ignored),
        rejected_files=len(rejected),
        by_source=dict(sorted(sources.items())),
        oldest_pending=oldest,
    )


def format_adapter_status(status: AdapterStatus) -> str:
    lines = [
        "Adapter intake status",
        "- writes: no",
        f"- input_dir: {status.input_dir}",
        f"- pending .input files: {status.pending_inputs}",
        f"- ignored non-.input files: {status.ignored_files}",
        f"- rejected files: {status.rejected_files}",
    ]
    if status.oldest_pending:
        lines.append(f"- oldest pending input: {status.oldest_pending}")
    if status.by_source:
        lines.append("- by source:")
        for source, count in status.by_source.items():
            lines.append(f"  - {source}: {count}")
    return "\n".join(lines)


def acknowledgement_from_input_file(path: Path, text: str) -> ResponseEnvelope:
    post = frontmatter.load(path)
    context = response_context_from_frontmatter(post.metadata, fallback_session_id=path.stem)
    return ResponseEnvelope(
        context=context,
        response_type=ResponseType.ACKNOWLEDGEMENT,
        text=text,
    )


def acknowledgement_from_source(source: str, session_id: str, text: str) -> ResponseEnvelope:
    return ResponseEnvelope(
        context=ResponseContext(source=source, session_id=session_id),
        response_type=ResponseType.ACKNOWLEDGEMENT,
        text=text,
    )


def _source_write_parser(description: str, source: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("content", nargs="+")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--source-id", default="")
    parser.add_argument("--modality", default="text")
    parser.set_defaults(source=source)
    return parser


def discord_main(argv: Sequence[str] | None = None) -> None:
    parser = _source_write_parser("Write one Discord proof message as a .input file.", "discord")
    args = parser.parse_args(argv)
    try:
        path = write_source_input(
            source=args.source,
            content=" ".join(args.content),
            input_dir=args.input_dir,
            session_id=args.session_id,
            source_id=args.source_id,
            modality=args.modality,
        )
    except FileExistsError as exc:
        parser.error(str(exc))
    print("\n".join([
        "Discord adapter proof",
        "- writes: input",
        f"- path: {path}",
        f"- source: {args.source}",
    ]))


def open_webui_main(argv: Sequence[str] | None = None) -> None:
    parser = _source_write_parser("Write one Open WebUI proof message as a .input file.", "open-webui")
    args = parser.parse_args(argv)
    try:
        path = write_source_input(
            source=args.source,
            content=" ".join(args.content),
            input_dir=args.input_dir,
            session_id=args.session_id,
            source_id=args.source_id,
            modality=args.modality,
        )
    except FileExistsError as exc:
        parser.error(str(exc))
    print("\n".join([
        "Open WebUI pipe proof",
        "- writes: input",
        f"- path: {path}",
        "- disposition: proven through .input contract",
    ]))


def ack_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Preview a source acknowledgement.")
    parser.add_argument("text", nargs="+")
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--source")
    parser.add_argument("--session-id")
    args = parser.parse_args(argv)
    text = " ".join(args.text)
    if args.input_file:
        envelope = acknowledgement_from_input_file(args.input_file, text)
    else:
        if not args.source or not args.session_id:
            parser.error("use --input-file or both --source and --session-id")
        envelope = acknowledgement_from_source(args.source, args.session_id, text)
    print(format_response_preview(envelope))


def status_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Report adapter intake status.")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--rejected-dir", type=Path)
    args = parser.parse_args(argv)
    print(format_adapter_status(build_adapter_status(args.input_dir, args.rejected_dir)))

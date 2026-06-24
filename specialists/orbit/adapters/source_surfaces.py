"""Generic source adapter proofs, acknowledgements, and status reporting."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Sequence

import frontmatter

from specialists.orbit.adapters.input_adapter import (
    InputEnvelope,
    input_filename,
    stable_content_hash,
    unique_path,
    write_input_file,
)
from specialists.rudi.response_routing import (
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
    archived_by_source: dict[str, int]
    oldest_pending: str
    newest_archived_by_source: dict[str, str]
    newest_rejected: str


def write_source_input(
    *,
    source: str,
    content: str,
    input_dir: Path,
    session_id: str = "",
    source_id: str = "",
    modality: str = "text",
    unique: bool = True,
) -> Path:
    envelope = InputEnvelope(
        content=content,
        source=source,
        session_id=session_id,
        source_id=source_id,
        modality=modality,
    )
    return write_input_file(envelope, input_dir, unique=unique).path


def write_adapter_reject(
    *,
    source: str,
    reason: str,
    rejected_dir: Path,
    text: str = "",
    source_id: str = "",
) -> Path:
    """Write an explicit adapter-level reject artifact."""

    if not source.strip():
        raise ValueError("source cannot be empty")
    if not reason.strip():
        raise ValueError("reason cannot be empty")
    rejected_dir.mkdir(parents=True, exist_ok=True)
    identity = source_id.strip() or stable_content_hash(f"{source}\n{reason}\n{text}")
    envelope = InputEnvelope(content=text or reason, source=source, source_id=identity)
    stem = Path(input_filename(envelope)).stem
    path = unique_path(rejected_dir / f"{stem}.reject.md")
    post = frontmatter.Post(
        text.strip() + "\n" if text.strip() else "",
        source=source,
        source_id=source_id,
        reason=reason,
        writes="rejected",
    )
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


def _count_sources(paths: Sequence[Path]) -> tuple[dict[str, int], dict[str, str]]:
    sources: Counter[str] = Counter()
    newest: dict[str, Path] = {}
    for path in paths:
        try:
            post = frontmatter.load(path)
        except Exception:
            source = "unparseable"
        else:
            source = str(post.get("source") or "unknown")
        sources[source] += 1
        current = newest.get(source)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            newest[source] = path
    return (
        dict(sorted(sources.items())),
        {source: path.name for source, path in sorted(newest.items())},
    )


def build_adapter_status(
    input_dir: Path,
    rejected_dir: Path | None = None,
    archive_dir: Path | None = None,
) -> AdapterStatus:
    pending = sorted(input_dir.glob("*.input")) if input_dir.exists() else []
    ignored = (
        [
            path
            for path in input_dir.iterdir()
            if path.is_file() and path.suffix != ".input"
        ]
        if input_dir.exists()
        else []
    )
    rejected = sorted(rejected_dir.glob("*")) if rejected_dir and rejected_dir.exists() else []
    archived = sorted(archive_dir.glob("*.input")) if archive_dir and archive_dir.exists() else []
    sources, _ = _count_sources(pending)
    archived_sources, newest_archived = _count_sources(archived)
    oldest = min(pending, key=lambda path: path.stat().st_mtime).name if pending else ""
    newest_rejected = (
        max(rejected, key=lambda path: path.stat().st_mtime).name if rejected else ""
    )
    return AdapterStatus(
        input_dir=input_dir,
        pending_inputs=len(pending),
        ignored_files=len(ignored),
        rejected_files=len(rejected),
        by_source=sources,
        archived_by_source=archived_sources,
        oldest_pending=oldest,
        newest_archived_by_source=newest_archived,
        newest_rejected=newest_rejected,
    )


def adapter_status_payload(status: AdapterStatus) -> dict[str, object]:
    return {
        "input_dir": str(status.input_dir),
        "pending_inputs": status.pending_inputs,
        "ignored_files": status.ignored_files,
        "rejected_files": status.rejected_files,
        "by_source": status.by_source,
        "archived_by_source": status.archived_by_source,
        "oldest_pending": status.oldest_pending,
        "newest_archived_by_source": status.newest_archived_by_source,
        "newest_rejected": status.newest_rejected,
    }


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
    if status.archived_by_source:
        lines.append("- archived by source:")
        for source, count in status.archived_by_source.items():
            newest = status.newest_archived_by_source.get(source, "")
            suffix = f" newest={newest}" if newest else ""
            lines.append(f"  - {source}: {count}{suffix}")
    if status.newest_rejected:
        lines.append(f"- newest rejected: {status.newest_rejected}")
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


def _ingest_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--source", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--source-id", default="")
    parser.add_argument("--modality", default="text")
    return parser


def ingest_main(argv: Sequence[str] | None = None) -> None:
    parser = _ingest_parser("Write one source payload as a Rosie .input file.")
    args = parser.parse_args(argv)
    try:
        path = write_source_input(
            source=args.source,
            content=args.text,
            input_dir=args.input_dir,
            session_id=args.session_id,
            source_id=args.source_id,
            modality=args.modality,
        )
    except Exception as exc:
        parser.error(str(exc))
    print("\n".join([
        "Adapter ingest",
        "- writes: input",
        f"- path: {path}",
        f"- source: {args.source}",
    ]))


def reject_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write one adapter-level reject artifact.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--text", default="")
    parser.add_argument("--source-id", default="")
    parser.add_argument("--rejected-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        path = write_adapter_reject(
            source=args.source,
            reason=args.reason,
            rejected_dir=args.rejected_dir,
            text=args.text,
            source_id=args.source_id,
        )
    except Exception as exc:
        parser.error(str(exc))
    print("\n".join([
        "Adapter reject",
        "- writes: rejected",
        f"- path: {path}",
        f"- source: {args.source}",
        f"- reason: {args.reason}",
    ]))


def process_existing_adapter_inputs(
    *,
    input_dir: Path,
    processing_dir: Path,
    archive_dir: Path,
    output_dir: Path,
) -> int:
    """Process queued adapter inputs through the existing Rosie one-shot path."""

    from specialists.rosie import loop as rosie_loop

    env_keys = {
        "SPROCKETS_COGS_INPUT_DIR": str(input_dir),
        "SPROCKETS_COGS_PROCESSING_DIR": str(processing_dir),
        "SPROCKETS_COGS_ARCHIVE_DIR": str(archive_dir),
        "SPROCKETS_COGS_OUTPUT_DIR": str(output_dir),
    }
    old_env = {key: os.environ.get(key) for key in env_keys}
    old_paths = (
        rosie_loop.INPUT_DIR,
        rosie_loop.PROCESSING_DIR,
        rosie_loop.ARCHIVE_DIR,
        rosie_loop.OUTPUT_DIR,
    )
    try:
        for key, value in env_keys.items():
            os.environ[key] = value
        rosie_loop.INPUT_DIR = input_dir
        rosie_loop.PROCESSING_DIR = processing_dir
        rosie_loop.ARCHIVE_DIR = archive_dir
        rosie_loop.OUTPUT_DIR = output_dir
        rosie_loop.ensure_runtime_dirs()
        return rosie_loop.process_existing_inputs(input_dir)
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        (
            rosie_loop.INPUT_DIR,
            rosie_loop.PROCESSING_DIR,
            rosie_loop.ARCHIVE_DIR,
            rosie_loop.OUTPUT_DIR,
        ) = old_paths


def process_once_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Process existing adapter .input files once.")
    parser.add_argument("--input-dir", type=Path, default=Path("/home/cosmo/sc/input"))
    parser.add_argument("--processing-dir", type=Path, default=Path("/home/cosmo/sc/processing"))
    parser.add_argument("--archive-dir", type=Path, default=Path("/home/cosmo/sc/archive"))
    parser.add_argument("--output-dir", type=Path, default=Path("/home/cosmo/sc/output"))
    args = parser.parse_args(argv)
    try:
        count = process_existing_adapter_inputs(
            input_dir=args.input_dir,
            processing_dir=args.processing_dir,
            archive_dir=args.archive_dir,
            output_dir=args.output_dir,
        )
    except Exception as exc:
        parser.error(str(exc))
    print("\n".join([
        "Adapter process-once",
        "- writes: may process input",
        f"- processed inputs: {count}",
        f"- input_dir: {args.input_dir}",
        f"- archive_dir: {args.archive_dir}",
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
    parser.add_argument("--archive-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    status = build_adapter_status(args.input_dir, args.rejected_dir, args.archive_dir)
    if args.json:
        print(json.dumps(adapter_status_payload(status), indent=2, sort_keys=True))
    else:
        print(format_adapter_status(status))


def adapters_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Orbit adapter intake console.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Report adapter intake status.")
    status.add_argument("--input-dir", type=Path, default=Path("/home/cosmo/sc/input"))
    status.add_argument("--rejected-dir", type=Path, default=Path("/home/cosmo/sc/rejected"))
    status.add_argument("--archive-dir", type=Path, default=Path("/home/cosmo/sc/archive"))
    status.add_argument("--json", action="store_true")

    ingest = subparsers.add_parser("ingest", help="Write one source payload as .input.")
    ingest.add_argument("--source", required=True)
    ingest.add_argument("--text", required=True)
    ingest.add_argument("--input-dir", type=Path, default=Path("/home/cosmo/sc/input"))
    ingest.add_argument("--session-id", default="")
    ingest.add_argument("--source-id", default="")
    ingest.add_argument("--modality", default="text")

    reject = subparsers.add_parser("reject", help="Write one adapter reject artifact.")
    reject.add_argument("--source", required=True)
    reject.add_argument("--reason", required=True)
    reject.add_argument("--text", default="")
    reject.add_argument("--source-id", default="")
    reject.add_argument("--rejected-dir", type=Path, default=Path("/home/cosmo/sc/rejected"))

    process_once = subparsers.add_parser("process-once", help="Process queued inputs once.")
    process_once.add_argument("--input-dir", type=Path, default=Path("/home/cosmo/sc/input"))
    process_once.add_argument("--processing-dir", type=Path, default=Path("/home/cosmo/sc/processing"))
    process_once.add_argument("--archive-dir", type=Path, default=Path("/home/cosmo/sc/archive"))
    process_once.add_argument("--output-dir", type=Path, default=Path("/home/cosmo/sc/output"))

    args = parser.parse_args(argv)
    if args.command == "status":
        status_args = [
            "--input-dir", str(args.input_dir),
            "--rejected-dir", str(args.rejected_dir),
            "--archive-dir", str(args.archive_dir),
        ]
        if args.json:
            status_args.append("--json")
        status_main(status_args)
    elif args.command == "ingest":
        ingest_main([
            "--source", args.source,
            "--text", args.text,
            "--input-dir", str(args.input_dir),
            "--session-id", args.session_id,
            "--source-id", args.source_id,
            "--modality", args.modality,
        ])
    elif args.command == "reject":
        reject_main([
            "--source", args.source,
            "--reason", args.reason,
            "--text", args.text,
            "--source-id", args.source_id,
            "--rejected-dir", str(args.rejected_dir),
        ])
    elif args.command == "process-once":
        process_once_main([
            "--input-dir", str(args.input_dir),
            "--processing-dir", str(args.processing_dir),
            "--archive-dir", str(args.archive_dir),
            "--output-dir", str(args.output_dir),
        ])

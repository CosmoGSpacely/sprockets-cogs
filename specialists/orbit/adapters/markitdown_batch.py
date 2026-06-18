"""Batch helpers for MarkItDown-backed document `.input` files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Sequence

from specialists.orbit.adapters.input_adapter import input_filename, write_input_file
from specialists.orbit.adapters.markitdown_adapter import (
    DEFAULT_MAX_DOCUMENT_BYTES,
    DEFAULT_MAX_MARKDOWN_CHARS,
    TEXT_LIKE_SUFFIXES,
    convert_document,
    document_envelope,
    document_sha256,
)


MARKITDOWN_SUFFIXES = {
    ".csv",
    ".docx",
    ".html",
    ".htm",
    ".json",
    ".pdf",
    ".pptx",
    ".xlsx",
    ".xml",
}
DEFAULT_BATCH_LIMIT = 20


@dataclass(frozen=True)
class BatchDocumentItem:
    """One document candidate in a batch plan."""

    source_path: Path
    relative_path: str
    suffix: str
    bytes: int
    sha256: str
    status: str
    reason: str = ""
    filename: str = ""


@dataclass(frozen=True)
class BatchPlan:
    """Dry-run manifest for batch document ingestion."""

    root: Path
    items: tuple[BatchDocumentItem, ...]
    recursive: bool
    max_bytes: int
    max_markdown_chars: int
    markitdown_available: bool

    @property
    def ready_count(self) -> int:
        return sum(1 for item in self.items if item.status == "ready")

    @property
    def blocked_count(self) -> int:
        return sum(1 for item in self.items if item.status != "ready")


@dataclass(frozen=True)
class BatchApplyItem:
    """Write result for one batch plan item."""

    source_path: Path
    status: str
    reason: str = ""
    output_path: Path | None = None


@dataclass(frozen=True)
class BatchApplyResult:
    """Result of explicitly applying a batch plan."""

    plan: BatchPlan
    items: tuple[BatchApplyItem, ...]
    input_dir: Path
    limit: int

    @property
    def written_count(self) -> int:
        return sum(1 for item in self.items if item.status == "written")

    @property
    def skipped_count(self) -> int:
        return sum(1 for item in self.items if item.status.startswith("skipped"))

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.items if item.status == "error")


def markitdown_available() -> bool:
    """Return whether the optional MarkItDown dependency is importable."""

    try:
        import markitdown  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def discover_document_paths(root: Path, *, recursive: bool = False) -> tuple[Path, ...]:
    """Return deterministic document candidate paths under a file or directory."""

    if not root.exists():
        raise FileNotFoundError(f"batch root does not exist: {root}")
    if root.is_file():
        return (root,)
    if not root.is_dir():
        raise ValueError(f"batch root is not a file or directory: {root}")

    iterator = root.rglob("*") if recursive else root.iterdir()
    return tuple(sorted((path for path in iterator if path.is_file()), key=lambda path: str(path).lower()))


def _relative_path(root: Path, path: Path) -> str:
    if root.is_file():
        return path.name
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _candidate_status(path: Path, *, size: int, max_bytes: int, has_markitdown: bool) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if size > max_bytes:
        return "too_large", f"{size} bytes exceeds {max_bytes}"
    if suffix in TEXT_LIKE_SUFFIXES:
        return "ready", "text/Markdown conversion"
    if suffix in MARKITDOWN_SUFFIXES:
        if has_markitdown:
            return "ready", "MarkItDown conversion"
        return "requires_markitdown", "optional MarkItDown dependency is not installed"
    return "unsupported", f"unsupported suffix: {suffix or '(none)'}"


def build_batch_plan(
    root: Path,
    *,
    recursive: bool = False,
    max_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
    max_markdown_chars: int = DEFAULT_MAX_MARKDOWN_CHARS,
) -> BatchPlan:
    """Build a read-only batch manifest."""

    if max_bytes < 1:
        raise ValueError("max_bytes must be at least 1")
    if max_markdown_chars < 1:
        raise ValueError("max_markdown_chars must be at least 1")

    has_markitdown = markitdown_available()
    items: list[BatchDocumentItem] = []
    for path in discover_document_paths(root, recursive=recursive):
        size = path.stat().st_size
        status, reason = _candidate_status(
            path,
            size=size,
            max_bytes=max_bytes,
            has_markitdown=has_markitdown,
        )
        sha256 = document_sha256(path) if size <= max_bytes else ""
        filename = ""
        if status == "ready":
            try:
                conversion = convert_document(
                    path,
                    max_bytes=max_bytes,
                    max_markdown_chars=max_markdown_chars,
                )
            except Exception as exc:
                status = "conversion_error"
                reason = str(exc)
            else:
                filename = input_filename(document_envelope(conversion))
        items.append(
            BatchDocumentItem(
                source_path=path,
                relative_path=_relative_path(root, path),
                suffix=path.suffix.lower(),
                bytes=size,
                sha256=sha256,
                status=status,
                reason=reason,
                filename=filename,
            )
        )

    return BatchPlan(
        root=root,
        items=tuple(items),
        recursive=recursive,
        max_bytes=max_bytes,
        max_markdown_chars=max_markdown_chars,
        markitdown_available=has_markitdown,
    )


def apply_batch_plan(plan: BatchPlan, input_dir: Path, *, limit: int = DEFAULT_BATCH_LIMIT) -> BatchApplyResult:
    """Write ready batch items as `.input` files, skipping existing outputs."""

    if limit < 1:
        raise ValueError("limit must be at least 1")

    results: list[BatchApplyItem] = []
    ready_written_or_attempted = 0
    for item in plan.items:
        if item.status != "ready":
            results.append(
                BatchApplyItem(
                    source_path=item.source_path,
                    status="skipped_not_ready",
                    reason=item.reason,
                )
            )
            continue
        if ready_written_or_attempted >= limit:
            results.append(
                BatchApplyItem(
                    source_path=item.source_path,
                    status="skipped_limit",
                    reason=f"batch apply limit {limit} reached",
                )
            )
            continue

        ready_written_or_attempted += 1
        try:
            conversion = convert_document(
                item.source_path,
                max_bytes=plan.max_bytes,
                max_markdown_chars=plan.max_markdown_chars,
            )
            envelope = document_envelope(conversion)
            write_result = write_input_file(envelope, input_dir)
        except FileExistsError as exc:
            results.append(
                BatchApplyItem(
                    source_path=item.source_path,
                    status="skipped_existing",
                    reason=str(exc),
                )
            )
        except Exception as exc:
            results.append(
                BatchApplyItem(
                    source_path=item.source_path,
                    status="error",
                    reason=str(exc),
                )
            )
        else:
            results.append(
                BatchApplyItem(
                    source_path=item.source_path,
                    status="written",
                    output_path=write_result.path,
                )
            )

    return BatchApplyResult(
        plan=plan,
        items=tuple(results),
        input_dir=input_dir,
        limit=limit,
    )


def plan_to_json(plan: BatchPlan) -> str:
    """Return machine-readable batch plan JSON."""

    return json.dumps(
        {
            "root": str(plan.root),
            "recursive": plan.recursive,
            "markitdown_available": plan.markitdown_available,
            "max_bytes": plan.max_bytes,
            "max_markdown_chars": plan.max_markdown_chars,
            "ready_count": plan.ready_count,
            "blocked_count": plan.blocked_count,
            "items": [
                {
                    "path": str(item.source_path),
                    "relative_path": item.relative_path,
                    "suffix": item.suffix,
                    "bytes": item.bytes,
                    "sha256": item.sha256,
                    "status": item.status,
                    "reason": item.reason,
                    "filename": item.filename,
                }
                for item in plan.items
            ],
        },
        indent=2,
        sort_keys=True,
    )


def apply_result_to_json(result: BatchApplyResult) -> str:
    """Return machine-readable batch apply JSON."""

    return json.dumps(
        {
            "root": str(result.plan.root),
            "input_dir": str(result.input_dir),
            "limit": result.limit,
            "written_count": result.written_count,
            "skipped_count": result.skipped_count,
            "error_count": result.error_count,
            "items": [
                {
                    "path": str(item.source_path),
                    "status": item.status,
                    "reason": item.reason,
                    "output_path": str(item.output_path) if item.output_path else "",
                }
                for item in result.items
            ],
        },
        indent=2,
        sort_keys=True,
    )


def format_plan(plan: BatchPlan) -> str:
    """Return a human-readable dry-run batch plan."""

    lines = [
        "MarkItDown batch plan",
        "- writes: no",
        f"- root: {plan.root}",
        f"- recursive: {'yes' if plan.recursive else 'no'}",
        f"- MarkItDown installed: {'yes' if plan.markitdown_available else 'no'}",
        f"- candidates: {len(plan.items)}",
        f"- ready: {plan.ready_count}",
        f"- blocked: {plan.blocked_count}",
    ]
    for item in plan.items:
        detail = f" -> {item.filename}" if item.filename else f" ({item.reason})"
        lines.append(f"- {item.status}: {item.relative_path}{detail}")
    return "\n".join(lines)


def format_apply_result(result: BatchApplyResult) -> str:
    """Return a human-readable batch apply report."""

    lines = [
        "MarkItDown batch apply",
        "- writes: input",
        f"- root: {result.plan.root}",
        f"- input dir: {result.input_dir}",
        f"- limit: {result.limit}",
        f"- written: {result.written_count}",
        f"- skipped: {result.skipped_count}",
        f"- errors: {result.error_count}",
    ]
    for item in result.items:
        detail = f" -> {item.output_path}" if item.output_path else f" ({item.reason})"
        lines.append(f"- {item.status}: {item.source_path.name}{detail}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or apply a bounded batch of MarkItDown-backed document .input files.",
    )
    parser.add_argument("root", type=Path, help="file or directory to inventory")
    parser.add_argument("--recursive", action="store_true", help="scan directories recursively")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_DOCUMENT_BYTES)
    parser.add_argument("--max-markdown-chars", type=int, default=DEFAULT_MAX_MARKDOWN_CHARS)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--apply", action="store_true", help="write ready documents to --input-dir")
    parser.add_argument("--input-dir", type=Path, help="target input directory for --apply")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_BATCH_LIMIT,
        help="maximum ready documents to attempt during --apply",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        plan = build_batch_plan(
            args.root,
            recursive=args.recursive,
            max_bytes=args.max_bytes,
            max_markdown_chars=args.max_markdown_chars,
        )
    except Exception as exc:
        parser.error(str(exc))

    if args.apply:
        if args.input_dir is None:
            parser.error("--input-dir is required with --apply")
        try:
            result = apply_batch_plan(plan, args.input_dir, limit=args.limit)
        except Exception as exc:
            parser.error(str(exc))
        print(apply_result_to_json(result) if args.json else format_apply_result(result))
        return

    print(plan_to_json(plan) if args.json else format_plan(plan))


if __name__ == "__main__":
    main()

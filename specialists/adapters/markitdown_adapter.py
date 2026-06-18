"""Document adapter helpers for MarkItDown-backed `.input` files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Callable, Sequence

from specialists.adapters.input_adapter import (
    InputAttachment,
    InputEnvelope,
    input_filename,
    input_frontmatter,
    input_session_id,
    preview_input_file,
    render_input_file,
    write_input_file,
)


MARKITDOWN_SOURCE = "markitdown"
DOCUMENT_MODALITY = "document"
DEFAULT_MAX_DOCUMENT_BYTES = 2_000_000
DEFAULT_MAX_MARKDOWN_CHARS = 20_000
TEXT_LIKE_SUFFIXES = {".md", ".markdown", ".txt", ".text"}


@dataclass(frozen=True)
class DocumentConversion:
    """Converted document text plus audit metadata."""

    source_path: Path
    markdown: str
    converter: str
    original_bytes: int
    content_sha256: str
    truncated: bool = False
    review_recommended: bool = False
    review_reason: str = ""

    def __post_init__(self) -> None:
        if not self.markdown.strip():
            raise ValueError("converted document markdown cannot be empty")


def document_sha256(path: Path) -> str:
    """Return the SHA-256 digest of a document."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text_like(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _convert_with_markitdown(path: Path) -> str:
    try:
        from markitdown import MarkItDown
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "MarkItDown is not installed; use a text/Markdown file or install markitdown"
        ) from exc

    result = MarkItDown().convert(str(path))
    text = getattr(result, "text_content", "")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("MarkItDown returned empty text")
    return text


def convert_document(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
    max_markdown_chars: int = DEFAULT_MAX_MARKDOWN_CHARS,
    converter: Callable[[Path], str] | None = None,
) -> DocumentConversion:
    """Convert a single document to Markdown with conservative limits."""

    if max_bytes < 1:
        raise ValueError("max_bytes must be at least 1")
    if max_markdown_chars < 1:
        raise ValueError("max_markdown_chars must be at least 1")
    if not path.exists():
        raise FileNotFoundError(f"document does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"document is not a file: {path}")

    original_bytes = path.stat().st_size
    if original_bytes > max_bytes:
        raise ValueError(
            f"document is too large: {original_bytes} bytes exceeds {max_bytes}"
        )

    if converter is not None:
        markdown = converter(path)
        converter_name = getattr(converter, "__name__", "injected")
    elif path.suffix.lower() in TEXT_LIKE_SUFFIXES:
        markdown = _read_text_like(path)
        converter_name = "text"
    else:
        markdown = _convert_with_markitdown(path)
        converter_name = "markitdown"

    stripped = markdown.strip()
    truncated = len(stripped) > max_markdown_chars
    if truncated:
        stripped = stripped[:max_markdown_chars].rstrip()

    return DocumentConversion(
        source_path=path,
        markdown=stripped,
        converter=converter_name,
        original_bytes=original_bytes,
        content_sha256=document_sha256(path),
        truncated=truncated,
        review_recommended=truncated,
        review_reason="converted markdown exceeded limit and was truncated" if truncated else "",
    )


def document_envelope(conversion: DocumentConversion) -> InputEnvelope:
    """Wrap converted Markdown in the shared `.input` adapter contract."""

    media_type, _ = mimetypes.guess_type(conversion.source_path.name)
    metadata = {
        "document_name": conversion.source_path.name,
        "document_suffix": conversion.source_path.suffix.lower(),
        "document_size_bytes": str(conversion.original_bytes),
        "document_sha256": conversion.content_sha256,
        "converter": conversion.converter,
        "markdown_chars": str(len(conversion.markdown)),
        "truncated": "yes" if conversion.truncated else "no",
        "review_recommended": "yes" if conversion.review_recommended else "no",
    }
    if conversion.review_reason:
        metadata["review_reason"] = conversion.review_reason

    digest_prefix = conversion.content_sha256[:16]
    return InputEnvelope(
        content=conversion.markdown,
        source=MARKITDOWN_SOURCE,
        session_id=f"markitdown-{digest_prefix}",
        modality=DOCUMENT_MODALITY,
        source_id=f"document-{digest_prefix}",
        idempotency_key=f"markitdown:{conversion.content_sha256}",
        metadata=metadata,
        attachments=(
            InputAttachment(
                name=conversion.source_path.name,
                media_type=media_type or "",
                path=str(conversion.source_path),
                text_excerpt=conversion.markdown[:160],
            ),
        ),
    )


def format_document_preview(conversion: DocumentConversion, envelope: InputEnvelope) -> str:
    """Format a read-only document ingestion preview."""

    return "\n".join([
        "MarkItDown document preview",
        "- writes: no",
        f"- source path: {conversion.source_path}",
        f"- converter: {conversion.converter}",
        f"- bytes: {conversion.original_bytes}",
        f"- sha256: {conversion.content_sha256}",
        f"- markdown chars: {len(conversion.markdown)}",
        f"- truncated: {'yes' if conversion.truncated else 'no'}",
        f"- review recommended: {'yes' if conversion.review_recommended else 'no'}",
        f"- filename: {input_filename(envelope)}",
        f"- session_id: {input_session_id(envelope)}",
        "",
        preview_input_file(envelope),
    ])


def envelope_preview_to_json(
    conversion: DocumentConversion,
    envelope: InputEnvelope,
    *,
    writes: str = "none",
    path: Path | None = None,
) -> str:
    """Return machine-readable document adapter preview JSON."""

    return json.dumps(
        {
            "writes": writes,
            "path": str(path) if path is not None else "",
            "document": {
                "path": str(conversion.source_path),
                "name": conversion.source_path.name,
                "converter": conversion.converter,
                "bytes": conversion.original_bytes,
                "sha256": conversion.content_sha256,
                "markdown_chars": len(conversion.markdown),
                "truncated": conversion.truncated,
                "review_recommended": conversion.review_recommended,
                "review_reason": conversion.review_reason,
            },
            "filename": input_filename(envelope),
            "frontmatter": input_frontmatter(envelope),
            "content": envelope.content,
            "rendered": render_input_file(envelope),
        },
        indent=2,
        sort_keys=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or write a MarkItDown-backed document .input file.",
    )
    parser.add_argument(
        "document",
        type=Path,
        help="document path to convert; text/Markdown works without MarkItDown installed",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_DOCUMENT_BYTES,
        help="maximum document size in bytes before conversion",
    )
    parser.add_argument(
        "--max-markdown-chars",
        type=int,
        default=DEFAULT_MAX_MARKDOWN_CHARS,
        help="maximum converted Markdown characters to include in the .input",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable preview JSON",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the rendered .input file to --input-dir; refuses existing files",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="target input directory for --write; required when writing",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        conversion = convert_document(
            args.document,
            max_bytes=args.max_bytes,
            max_markdown_chars=args.max_markdown_chars,
        )
        envelope = document_envelope(conversion)
    except Exception as exc:
        parser.error(str(exc))

    if args.write:
        if args.input_dir is None:
            parser.error("--input-dir is required with --write")
        try:
            result = write_input_file(envelope, args.input_dir)
        except FileExistsError as exc:
            parser.error(str(exc))
        if args.json:
            print(envelope_preview_to_json(conversion, envelope, writes="input", path=result.path))
        else:
            print("\n".join([
                "MarkItDown document write",
                "- writes: input",
                f"- path: {result.path}",
                f"- source path: {conversion.source_path}",
                f"- converter: {conversion.converter}",
                f"- review recommended: {'yes' if conversion.review_recommended else 'no'}",
            ]))
        return

    if args.json:
        print(envelope_preview_to_json(conversion, envelope))
        return
    print(format_document_preview(conversion, envelope))


if __name__ == "__main__":
    main()

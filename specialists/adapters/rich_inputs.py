"""Rich input routing proof for images, scans, and document resources."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import mimetypes
from pathlib import Path
import shutil
from typing import Sequence

from input_adapter import InputAttachment, InputEnvelope, write_input_file
from slug_utils import slugify


RICH_INPUT_SOURCE = "rich-input"
RICH_RESOURCE_SOURCE = "rich-resource"
IMAGE_SUFFIXES = {".avif", ".bmp", ".gif", ".heic", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".text"}
DOCUMENT_SUFFIXES = {".csv", ".doc", ".docx", ".html", ".pdf", ".rtf", ".tsv", ".xls", ".xlsx"}


@dataclass(frozen=True)
class PreservedResource:
    original_path: Path
    preserved_path: Path
    content_sha256: str
    original_bytes: int
    media_type: str


@dataclass(frozen=True)
class RichInputRoute:
    kind: str
    route: str
    modality: str
    confidence: str
    review_reason: str
    extracted_text: str = ""


@dataclass(frozen=True)
class RichInputResult:
    preserved: PreservedResource
    route: RichInputRoute
    input_path: Path | None
    writes: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def media_type_for(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def preserve_resource(path: Path, resource_dir: Path) -> PreservedResource:
    if not path.exists():
        raise FileNotFoundError(f"rich input does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"rich input is not a file: {path}")

    digest = file_sha256(path)
    suffix = path.suffix.lower()
    stem = slugify(path.stem, max_length=64) or "resource"
    preserved_name = f"{digest[:12]}-{stem}{suffix}"
    resource_dir.mkdir(parents=True, exist_ok=True)
    preserved_path = resource_dir / preserved_name
    if not preserved_path.exists():
        shutil.copy2(path, preserved_path)
    return PreservedResource(
        original_path=path,
        preserved_path=preserved_path,
        content_sha256=digest,
        original_bytes=path.stat().st_size,
        media_type=media_type_for(path),
    )


def _read_optional_text(path: Path | None) -> str:
    if path is None:
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"OCR text file is empty: {path}")
    return text


def classify_rich_input(path: Path, *, ocr_text: str = "") -> RichInputRoute:
    suffix = path.suffix.lower()
    media_type = media_type_for(path)
    is_image = suffix in IMAGE_SUFFIXES or media_type.startswith("image/")
    is_text = suffix in TEXT_SUFFIXES or media_type.startswith("text/")
    is_document = suffix in DOCUMENT_SUFFIXES or "document" in media_type or media_type == "application/pdf"

    if ocr_text:
        return RichInputRoute(
            kind="scanned_text",
            route="extraction",
            modality="document",
            confidence="medium",
            review_reason="OCR text supplied; route text for Rosie while preserving original file.",
            extracted_text=ocr_text,
        )
    if is_text:
        return RichInputRoute(
            kind="text_document",
            route="extraction",
            modality="document",
            confidence="high",
            review_reason="Text-like file can route through ordinary extraction.",
            extracted_text=path.read_text(encoding="utf-8").strip(),
        )
    if is_image:
        return RichInputRoute(
            kind="image_resource",
            route="resource_review",
            modality="image",
            confidence="medium",
            review_reason="Image has no extracted text; preserve as resource and require review for graph links.",
        )
    if is_document:
        return RichInputRoute(
            kind="document_resource",
            route="resource_review",
            modality="document",
            confidence="low",
            review_reason="Document has no extracted text in this proof; preserve as resource and require review.",
        )
    return RichInputRoute(
        kind="unknown_resource",
        route="resource_review",
        modality="resource",
        confidence="low",
        review_reason="Unsupported rich input type; preserve file and require review.",
    )


def rich_input_envelope(preserved: PreservedResource, route: RichInputRoute) -> InputEnvelope:
    metadata = {
        "rich_input_kind": route.kind,
        "route": route.route,
        "confidence": route.confidence,
        "review_reason": route.review_reason,
        "original_name": preserved.original_path.name,
        "original_path": str(preserved.original_path),
        "preserved_path": str(preserved.preserved_path),
        "resource_sha256": preserved.content_sha256,
        "resource_bytes": str(preserved.original_bytes),
        "media_type": preserved.media_type,
        "write_authority": "input_only",
        "silent_obligations_allowed": "no",
    }
    attachment = InputAttachment(
        name=preserved.original_path.name,
        media_type=preserved.media_type,
        path=str(preserved.preserved_path),
        text_excerpt=route.extracted_text[:160],
    )
    if route.route == "extraction":
        return InputEnvelope(
            content=route.extracted_text,
            source=RICH_INPUT_SOURCE,
            session_id=f"rich-input-{preserved.content_sha256[:12]}",
            source_id=f"resource-{preserved.content_sha256[:16]}",
            idempotency_key=f"rich-input:{preserved.content_sha256}:{route.route}",
            modality=route.modality,
            metadata=metadata,
            attachments=(attachment,),
        )

    content = "\n".join([
        "Resource review candidate",
        f"Original file: {preserved.original_path.name}",
        f"Preserved file: {preserved.preserved_path}",
        f"Classification: {route.kind}",
        f"Review reason: {route.review_reason}",
        "",
        "Do not create a Cog, appointment, bridge edge, or obligation from this resource unless the user text explicitly asks for one.",
        "If useful, propose a Sprocket resource/reference linked to the preserved file.",
    ])
    return InputEnvelope(
        content=content,
        source=RICH_RESOURCE_SOURCE,
        session_id=f"rich-resource-{preserved.content_sha256[:12]}",
        source_id=f"resource-{preserved.content_sha256[:16]}",
        idempotency_key=f"rich-resource:{preserved.content_sha256}:{route.route}",
        modality=route.modality,
        metadata=metadata,
        attachments=(attachment,),
    )


def route_rich_input(
    path: Path,
    *,
    input_dir: Path,
    resource_dir: Path,
    ocr_text_path: Path | None = None,
    write: bool = True,
) -> RichInputResult:
    preserved = preserve_resource(path, resource_dir)
    route = classify_rich_input(path, ocr_text=_read_optional_text(ocr_text_path))
    envelope = rich_input_envelope(preserved, route)
    input_path = write_input_file(envelope, input_dir).path if write else None
    return RichInputResult(
        preserved=preserved,
        route=route,
        input_path=input_path,
        writes="resource,input" if write else "resource",
    )


def format_rich_input_result(result: RichInputResult) -> str:
    lines = [
        "Rich input routing proof",
        f"- writes: {result.writes}",
        f"- original path: {result.preserved.original_path}",
        f"- preserved path: {result.preserved.preserved_path}",
        f"- media type: {result.preserved.media_type}",
        f"- sha256: {result.preserved.content_sha256}",
        f"- route: {result.route.route}",
        f"- kind: {result.route.kind}",
        f"- modality: {result.route.modality}",
        f"- confidence: {result.route.confidence}",
        f"- review reason: {result.route.review_reason}",
        "- silent obligations allowed: no",
    ]
    if result.input_path is not None:
        lines.append(f"- input path: {result.input_path}")
    return "\n".join(lines)


def result_to_json(result: RichInputResult) -> str:
    return json.dumps(
        {
            "writes": result.writes,
            "input_path": str(result.input_path) if result.input_path else "",
            "resource": {
                "original_path": str(result.preserved.original_path),
                "preserved_path": str(result.preserved.preserved_path),
                "sha256": result.preserved.content_sha256,
                "bytes": result.preserved.original_bytes,
                "media_type": result.preserved.media_type,
            },
            "route": {
                "kind": result.route.kind,
                "route": result.route.route,
                "modality": result.route.modality,
                "confidence": result.route.confidence,
                "review_reason": result.route.review_reason,
                "extracted_text_chars": len(result.route.extracted_text),
            },
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Preserve and route one rich input file through the .input contract.",
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--resource-dir", type=Path, required=True)
    parser.add_argument("--ocr-text", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = route_rich_input(
            args.path,
            input_dir=args.input_dir,
            resource_dir=args.resource_dir,
            ocr_text_path=args.ocr_text,
        )
    except Exception as exc:
        parser.error(str(exc))
    print(result_to_json(result) if args.json else format_rich_input_result(result))


if __name__ == "__main__":
    main()

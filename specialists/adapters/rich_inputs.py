"""Rich input routing proof for images, scans, and document resources."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import time
from typing import Any, Callable, Mapping, Sequence

import ollama

from specialists.adapters.input_adapter import InputAttachment, InputEnvelope, write_input_file
from slug_utils import slugify


RICH_INPUT_SOURCE = "rich-input"
RICH_RESOURCE_SOURCE = "rich-resource"
IMAGE_SUFFIXES = {".avif", ".bmp", ".gif", ".heic", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".text"}
DOCUMENT_SUFFIXES = {".csv", ".doc", ".docx", ".html", ".pdf", ".rtf", ".tsv", ".xls", ".xlsx"}
DEFAULT_GEMMA_IMAGE_MODEL = os.environ.get(
    "SPROCKETS_COGS_IMAGE_MODEL",
    "gemma4:12b-32k-cosmo",
)
GEMMA_IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "source_kind": {
            "type": "string",
            "enum": ["object_photo", "scanned_text", "poster_artifact", "unknown"],
        },
        "resource_summary": {"type": "string"},
        "extracted_text": {"type": "string"},
        "suggested_route": {
            "type": "string",
            "enum": ["resource_sprocket", "text_extraction", "review"],
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "needs_review": {"type": "boolean"},
    },
    "required": [
        "source_kind",
        "resource_summary",
        "extracted_text",
        "suggested_route",
        "confidence",
        "needs_review",
    ],
}
GEMMA_IMAGE_PROMPT = """Inspect this input for Sprockets-Cogs rich-source routing.

Return compact JSON only. Rich sources are not allowed to create obligations,
appointments, scheduled Cogs, graph edges, or durable hierarchy directly.

Classify:
- object_photo: a meaningful object/resource photo with little or no text.
- scanned_text: handwriting, printed page, list, receipt, or notebook text.
- poster_artifact: visual/text artifact such as an advertisement, poster,
  poem, label, sign, or historical/reference material.
- unknown: insufficient or unsupported.

Route:
- text_extraction only if extracted_text is good enough to send to Rosie.
- resource_sprocket when it is clearly a resource/reference candidate.
- review when uncertain or when graph links require user confirmation.
"""


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
    resource_summary: str = ""
    model_source_kind: str = ""


@dataclass(frozen=True)
class RichInputResult:
    preserved: PreservedResource
    route: RichInputRoute
    input_path: Path | None
    writes: str


@dataclass(frozen=True)
class GemmaImageProbe:
    path: Path
    model: str
    source_kind: str
    resource_summary: str
    extracted_text: str
    suggested_route: str
    confidence: str
    needs_review: bool
    valid_json: bool
    latency_seconds: float
    media_type: str
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "model": self.model,
            "source_kind": self.source_kind,
            "resource_summary": self.resource_summary,
            "extracted_text": self.extracted_text,
            "suggested_route": self.suggested_route,
            "confidence": self.confidence,
            "needs_review": self.needs_review,
            "valid_json": self.valid_json,
            "latency_seconds": round(self.latency_seconds, 3),
            "media_type": self.media_type,
            "error": self.error,
        }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sniff_media_type(path: Path) -> str:
    """Return a content-sniffed media type for common stage input formats."""

    with path.open("rb") as handle:
        header = handle.read(16)
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    if header.startswith(b"%PDF"):
        return "application/pdf"
    return ""


def media_type_for(path: Path) -> str:
    sniffed = sniff_media_type(path)
    if sniffed:
        return sniffed
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


def _route_from_probe(probe: GemmaImageProbe) -> RichInputRoute | None:
    if not probe.valid_json:
        return None
    if probe.suggested_route == "text_extraction" and probe.extracted_text.strip():
        return RichInputRoute(
            kind="scanned_text",
            route="extraction",
            modality="document",
            confidence=probe.confidence,
            review_reason="Gemma image probe extracted text good enough for ordinary capture.",
            extracted_text=probe.extracted_text.strip(),
            resource_summary=probe.resource_summary,
            model_source_kind=probe.source_kind,
        )
    kind = "image_resource"
    if probe.source_kind == "poster_artifact":
        kind = "artifact_resource"
    elif probe.source_kind == "unknown":
        kind = "unknown_resource"
    reason = (
        "Gemma image probe identified a resource candidate; require review for graph links."
        if probe.suggested_route == "resource_sprocket"
        else "Gemma image probe requires review before graph interpretation."
    )
    return RichInputRoute(
        kind=kind,
        route="resource_review",
        modality="image",
        confidence=probe.confidence,
        review_reason=reason,
        extracted_text=probe.extracted_text.strip(),
        resource_summary=probe.resource_summary,
        model_source_kind=probe.source_kind,
    )


def classify_rich_input(
    path: Path,
    *,
    ocr_text: str = "",
    gemma_probe: GemmaImageProbe | None = None,
) -> RichInputRoute:
    if gemma_probe is not None:
        probed = _route_from_probe(gemma_probe)
        if probed is not None:
            return probed

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
    received_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "source_adapter": "orbit.rich_inputs",
        "rich_input_kind": route.kind,
        "route": route.route,
        "confidence": route.confidence,
        "review_reason": route.review_reason,
        "resource_summary": route.resource_summary,
        "model_source_kind": route.model_source_kind,
        "original_name": preserved.original_path.name,
        "original_path": str(preserved.original_path),
        "preserved_path": str(preserved.preserved_path),
        "resource_sha256": preserved.content_sha256,
        "resource_bytes": str(preserved.original_bytes),
        "media_type": preserved.media_type,
        "received_at": received_at,
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
        f"Summary: {route.resource_summary}" if route.resource_summary else "",
        f"Review reason: {route.review_reason}",
        "",
        "Do not create a Cog, appointment, bridge edge, or obligation from this resource unless the user text explicitly asks for one.",
        "If useful, propose a Sprocket resource/reference linked to the preserved file.",
    ]).replace("\n\n\n", "\n\n")
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
    gemma_probe: GemmaImageProbe | None = None,
    write: bool = True,
) -> RichInputResult:
    preserved = preserve_resource(path, resource_dir)
    route = classify_rich_input(
        path,
        ocr_text=_read_optional_text(ocr_text_path),
        gemma_probe=gemma_probe,
    )
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
                "resource_summary": result.route.resource_summary,
                "model_source_kind": result.route.model_source_kind,
                "extracted_text_chars": len(result.route.extracted_text),
            },
        },
        indent=2,
        sort_keys=True,
    )


def _message_content(response: Any) -> str:
    if isinstance(response, Mapping):
        message = response.get("message", {})
        if isinstance(message, Mapping):
            return str(message.get("content", ""))
        return ""
    message = getattr(response, "message", None)
    return str(getattr(message, "content", ""))


def run_gemma_image_probe(
    path: Path,
    *,
    model: str = DEFAULT_GEMMA_IMAGE_MODEL,
    chat_client: Callable[..., Any] | None = None,
) -> GemmaImageProbe:
    """Ask an Ollama-compatible vision model for safe rich-source routing JSON."""

    client = chat_client or ollama.chat
    media_type = media_type_for(path)
    start = time.monotonic()
    try:
        response = client(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": GEMMA_IMAGE_PROMPT,
                    "images": [str(path)],
                }
            ],
            format=GEMMA_IMAGE_SCHEMA,
            options={"temperature": 0.1},
            think=False,
        )
    except Exception as exc:
        return GemmaImageProbe(
            path=path,
            model=model,
            source_kind="unknown",
            resource_summary="",
            extracted_text="",
            suggested_route="review",
            confidence="low",
            needs_review=True,
            valid_json=False,
            latency_seconds=time.monotonic() - start,
            media_type=media_type,
            error=str(exc),
        )
    raw = _message_content(response)
    try:
        parsed = json.loads(raw)
        valid_json = isinstance(parsed, Mapping)
    except json.JSONDecodeError as exc:
        parsed = {}
        valid_json = False
        error = f"invalid JSON: {exc}: {raw[:160]}"
    else:
        error = ""
    return GemmaImageProbe(
        path=path,
        model=model,
        source_kind=str(parsed.get("source_kind") or "unknown"),
        resource_summary=str(parsed.get("resource_summary") or ""),
        extracted_text=str(parsed.get("extracted_text") or ""),
        suggested_route=str(parsed.get("suggested_route") or "review"),
        confidence=str(parsed.get("confidence") or "low"),
        needs_review=bool(parsed.get("needs_review", True)),
        valid_json=valid_json,
        latency_seconds=time.monotonic() - start,
        media_type=media_type,
        error=error,
    )


def format_gemma_image_probe(probe: GemmaImageProbe) -> str:
    lines = [
        "Gemma image capability probe",
        "- writes: no",
        f"- path: {probe.path}",
        f"- model: {probe.model}",
        f"- media type: {probe.media_type}",
        f"- valid JSON: {'yes' if probe.valid_json else 'no'}",
        f"- source kind: {probe.source_kind}",
        f"- suggested route: {probe.suggested_route}",
        f"- confidence: {probe.confidence}",
        f"- needs review: {'yes' if probe.needs_review else 'no'}",
        f"- latency seconds: {probe.latency_seconds:.3f}",
    ]
    if probe.resource_summary:
        lines.append(f"- summary: {probe.resource_summary}")
    if probe.extracted_text:
        lines.append(f"- extracted text chars: {len(probe.extracted_text)}")
    if probe.error:
        lines.append(f"- error: {probe.error}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Preserve and route one rich input file through the .input contract.",
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--resource-dir", type=Path, required=True)
    parser.add_argument("--ocr-text", type=Path)
    parser.add_argument("--gemma-image-probe", action="store_true")
    parser.add_argument("--gemma-model", default=DEFAULT_GEMMA_IMAGE_MODEL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    gemma_probe = None
    if args.gemma_image_probe:
        gemma_probe = run_gemma_image_probe(args.path, model=args.gemma_model)
    try:
        result = route_rich_input(
            args.path,
            input_dir=args.input_dir,
            resource_dir=args.resource_dir,
            ocr_text_path=args.ocr_text,
            gemma_probe=gemma_probe,
        )
    except Exception as exc:
        parser.error(str(exc))
    if args.json:
        payload = json.loads(result_to_json(result))
        if gemma_probe is not None:
            payload["gemma_image_probe"] = gemma_probe.to_dict()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if gemma_probe is not None:
        print(format_gemma_image_probe(gemma_probe))
        print("")
    print(format_rich_input_result(result))


if __name__ == "__main__":
    main()

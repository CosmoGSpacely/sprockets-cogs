"""Read-only preview for the extractor/classifier capture boundary."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Sequence

from classifier_context import build_default_context as build_context
from extractor_classifier import CAPTURE_MODEL, ExtractClassifier, ExtractClassifierConfig


@dataclass(frozen=True)
class CapturePreview:
    """Result of a read-only capture preview run."""

    content: str
    model: str
    raw_nodes: list[dict[str, Any]]
    classified_nodes: list[dict[str, Any]]
    classified: bool
    context_chars: int


def run_capture_preview(
    content: str,
    *,
    classify: bool = True,
    model: str | None = None,
    context: str | None = None,
    classifier: ExtractClassifier | None = None,
) -> CapturePreview:
    """Run extraction and optional classification without writing vault files."""

    selected_model = model or CAPTURE_MODEL
    capture = classifier or ExtractClassifier(
        ExtractClassifierConfig(model=selected_model)
    )
    raw_nodes = capture.extract_nodes(content)
    context_text = context if context is not None else build_context()
    classified_nodes: list[dict[str, Any]] = []
    if classify:
        classified_nodes = capture.classify_nodes(raw_nodes, context_text)

    return CapturePreview(
        content=content,
        model=selected_model,
        raw_nodes=raw_nodes,
        classified_nodes=classified_nodes,
        classified=classify,
        context_chars=len(context_text),
    )


def format_capture_preview(preview: CapturePreview) -> str:
    """Format capture preview output for quick terminal inspection."""

    lines = [
        "Capture preview",
        f"- model: {preview.model}",
        "- writes: none",
        f"- context chars: {preview.context_chars}",
        f"- raw items: {len(preview.raw_nodes)}",
        f"- classified nodes: {len(preview.classified_nodes)}"
        if preview.classified
        else "- classified nodes: skipped",
    ]
    if preview.raw_nodes:
        lines.append("")
        lines.append("Raw items:")
        for index, item in enumerate(preview.raw_nodes, start=1):
            raw = item.get("raw") or item.get("text") or item.get("item_text") or item
            lines.append(f"{index}. {raw}")
    if preview.classified:
        lines.append("")
        lines.append("Classified nodes:")
        if not preview.classified_nodes:
            lines.append("(none)")
        for index, node in enumerate(preview.classified_nodes, start=1):
            node_type = node.get("node_type", "unknown")
            text = node.get("item_text") or node.get("title") or "(untitled)"
            confidence = node.get("confidence", "unknown")
            lines.append(f"{index}. [{node_type}] {text} ({confidence})")
    return "\n".join(lines)


def capture_preview_to_json(preview: CapturePreview) -> str:
    """Return a stable JSON preview payload."""

    return json.dumps(
        {
            "content": preview.content,
            "model": preview.model,
            "writes": "none",
            "context_chars": preview.context_chars,
            "raw_nodes": preview.raw_nodes,
            "classified": preview.classified,
            "classified_nodes": preview.classified_nodes,
        },
        indent=2,
        sort_keys=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only preview of capture extraction/classification.",
    )
    parser.add_argument("content", nargs="+", help="input text to preview")
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="skip classification and show extracted raw items only",
    )
    parser.add_argument(
        "--model",
        help="override the extractor/classifier model for this preview",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    preview = run_capture_preview(
        " ".join(args.content),
        classify=not args.extract_only,
        model=args.model,
    )
    if args.json:
        print(capture_preview_to_json(preview))
    else:
        print(format_capture_preview(preview))


if __name__ == "__main__":
    main()

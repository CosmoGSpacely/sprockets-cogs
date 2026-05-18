"""Read-only preview CLI for adapter-produced `.input` files."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from input_adapter import (
    InputAttachment,
    InputEnvelope,
    input_filename,
    input_frontmatter,
    input_session_id,
    preview_input_file,
    render_input_file,
)


def parse_key_value_pairs(pairs: Sequence[str]) -> dict[str, str]:
    """Parse repeated KEY=VALUE metadata arguments."""

    parsed: dict[str, str] = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator or not key.strip():
            raise ValueError("metadata entries must use KEY=VALUE")
        parsed[key.strip()] = value
    return parsed


def parse_attachment_specs(specs: Sequence[str]) -> tuple[InputAttachment, ...]:
    """Parse attachment specs from comma-separated KEY=VALUE chunks."""

    attachments: list[InputAttachment] = []
    for spec in specs:
        fields = parse_key_value_pairs(
            part.strip()
            for part in spec.split(",")
            if part.strip()
        )
        try:
            name = fields.pop("name")
        except KeyError as exc:
            raise ValueError("attachment entries must include name=...") from exc
        attachments.append(
            InputAttachment(
                name=name,
                media_type=fields.pop("media_type", ""),
                path=fields.pop("path", ""),
                url=fields.pop("url", ""),
                text_excerpt=fields.pop("text_excerpt", ""),
            )
        )
        if fields:
            unknown = ", ".join(sorted(fields))
            raise ValueError(f"unknown attachment field(s): {unknown}")
    return tuple(attachments)


def build_envelope_from_args(args: argparse.Namespace) -> InputEnvelope:
    """Build an input envelope from parsed CLI args."""

    return InputEnvelope(
        content=" ".join(args.content),
        source=args.source,
        session_id=args.session_id,
        modality=args.modality,
        source_id=args.source_id,
        idempotency_key=args.idempotency_key,
        metadata=parse_key_value_pairs(args.metadata),
        attachments=parse_attachment_specs(args.attachment),
    )


def envelope_preview_to_json(envelope: InputEnvelope) -> str:
    """Return a stable JSON payload for preview automation."""

    return json.dumps(
        {
            "writes": "none",
            "filename": input_filename(envelope),
            "frontmatter": input_frontmatter(envelope),
            "content": envelope.content.strip(),
            "rendered": render_input_file(envelope),
        },
        indent=2,
        sort_keys=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only preview of a source adapter `.input` file.",
    )
    parser.add_argument("content", nargs="+", help="input text to wrap")
    parser.add_argument(
        "--source",
        required=True,
        help="adapter source label, such as cli, telegram, discord, markitdown, or obsidian",
    )
    parser.add_argument(
        "--session-id",
        default="",
        help="stable session id for Rosie; defaults to source plus content hash",
    )
    parser.add_argument(
        "--modality",
        default="text",
        help="input modality, such as text, document, image, audio, or mixed",
    )
    parser.add_argument(
        "--source-id",
        default="",
        help="source-specific message/document id used for deterministic filenames",
    )
    parser.add_argument(
        "--idempotency-key",
        default="",
        help="explicit idempotency key; preferred over source id for filenames",
    )
    parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="source metadata to include in frontmatter; repeatable",
    )
    parser.add_argument(
        "--attachment",
        action="append",
        default=[],
        metavar="KEY=VALUE,...",
        help="attachment metadata, e.g. name=file.pdf,path=/tmp/file.pdf,media_type=application/pdf",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable preview JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        envelope = build_envelope_from_args(args)
    except ValueError as exc:
        parser.error(str(exc))

    if args.json:
        print(envelope_preview_to_json(envelope))
    else:
        print(preview_input_file(envelope))


if __name__ == "__main__":
    main()

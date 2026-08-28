"""Render the exact messages sent to the model, without calling one.

Stage 138 needed instrumentation archaeology to answer "what actually reaches
the model" - the missing `Today:` anchor was invisible in code review and only
surfaced when a fixture produced a date in the past. This makes that question
one command.

Read-only, and makes no model call.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from specialists.rosie.extractor_classifier import (
    DEFAULT_CONTEXT_MAX_CHARS,
    build_classify_messages,
    build_extract_messages,
)
from specialists.uniblab.capture_fixtures import (
    DEFAULT_CONTEXT,
    FIXTURE_DIR,
    load_capture_fixtures,
)


CHARS_PER_TOKEN = 2.79
"""Measured on this project's real prompts in Stage 138 slice 2.

The customary ~4 is wrong here: these prompts are JSON, ALLCAPS labels, and
ISO dates. Used only for the estimate line; real counts come from the harness.
"""


def estimate_tokens(chars: int) -> int:
    return round(chars / CHARS_PER_TOKEN)


def _sample_raw_nodes(fixture) -> list[dict]:
    """Stand-in extraction output, so the classify prompt can be rendered.

    The classify call normally consumes real extract output. Dumping it without
    a model requires a plausible substitute; the fixture's own expected node
    types give one that matches the real shape.
    """

    if not fixture.expected_nodes:
        return [{"raw": fixture.content, "type_hint": "note"}]
    return [
        {"raw": fixture.content, "type_hint": "task"}
        for _ in fixture.expected_nodes[:3]
    ]


def render(
    fixture,
    *,
    context_max_chars: int = DEFAULT_CONTEXT_MAX_CHARS,
    use_examples: bool = True,
    raw_nodes: list[dict] | None = None,
) -> dict[str, Any]:
    """Build both message lists for one fixture."""

    nodes = raw_nodes if raw_nodes is not None else _sample_raw_nodes(fixture)
    return {
        "fixture_id": fixture.fixture_id,
        "now": fixture.now.isoformat(),
        "extract": build_extract_messages(fixture.content, fixture.now),
        "classify": build_classify_messages(
            nodes,
            fixture.context,
            fixture.now,
            use_examples=use_examples,
            context_max_chars=context_max_chars,
        ),
    }


def format_dump(rendered: dict[str, Any], *, full: bool = False) -> str:
    """Human-readable rendering, examples elided unless --full."""

    lines = [
        f"# prompt dump: {rendered['fixture_id']}",
        f"- now: {rendered['now']}",
        "- model calls: none (assembly only)",
    ]
    for call in ("extract", "classify"):
        messages = rendered[call]
        chars = sum(len(str(m.get("content", ""))) for m in messages)
        lines.append("")
        lines.append(
            f"## {call}: {len(messages)} messages, {chars} chars, "
            f"~{estimate_tokens(chars)} tokens"
        )
        for message in messages:
            role = message["role"]
            content = str(message.get("content", ""))
            is_example = message is not messages[0] and message is not messages[-1]
            if is_example and not full:
                lines.append(f"  [{role}] <few-shot example, {len(content)} chars>")
                continue
            lines.append(f"  [{role}]")
            lines.extend(f"    {line}" for line in content.splitlines())
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render assembled prompts for a fixture. Makes no model call.",
    )
    parser.add_argument("--fixture", action="append", dest="fixture_ids")
    parser.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    parser.add_argument(
        "--context-max-chars", type=int, default=DEFAULT_CONTEXT_MAX_CHARS
    )
    parser.add_argument("--no-examples", action="store_true")
    parser.add_argument(
        "--full", action="store_true", help="print few-shot examples in full"
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    fixtures = load_capture_fixtures(
        args.fixture_dir, only=tuple(args.fixture_ids or ())
    )
    if not fixtures:
        parser.error("no fixtures matched")
    rendered = [
        render(
            fixture,
            context_max_chars=args.context_max_chars,
            use_examples=not args.no_examples,
        )
        for fixture in fixtures
    ]
    if args.json:
        print(json.dumps(rendered, indent=2, sort_keys=True))
    else:
        print("\n\n".join(format_dump(item, full=args.full) for item in rendered))


if __name__ == "__main__":
    main()

"""Call architectures for the Stage 142 experiment.

Each architecture answers the same question - capture text in, classified nodes
out - with a different number of model calls and a different seam between them.
They are scored on the same fixtures by the same grader, so the only variable
is the shape.

Every architecture returns `(raw_nodes, classified_nodes)`. `raw_nodes` is the
intermediate representation the post-classify chain matches against, and it is
also the inspection point where Stage 141 findings 44, 55, and 61 were
diagnosed. An architecture that cannot produce one returns `[]`, and that is a
measured cost of the candidate rather than a gap to paper over.

## A confound that must be read with the results

Candidates 1, 2, and 5 reuse prompts that six stages of measurement have
already shaped. Candidates 3, 4, 6, and 7 need prompts that did not exist, so
their scores mix the architecture with the quality of prompts written in one
sitting. Finding 60 - prompt text is not compositional - says that mixing is
not small.

The merged prompts below are therefore written to carry the *same doctrine* as
the two-call pair, restating the rules rather than inventing new ones, and the
merged few-shot examples reuse the existing examples' content wherever the
shapes allow. That narrows the confound; it does not remove it. A new-prompt
candidate that wins decisively is signal. One that loses narrowly may be losing
on the prompt, and the honest response is a second prompt, not a verdict.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from specialists.rosie.prompts import (
    CLASSIFY_SCHEMA,
    CLASSIFY_SYSTEM,
    EXTRACT_EXAMPLES,
    EXTRACT_SCHEMA,
    EXTRACT_SYSTEM,
)
from specialists.rosie.extractor_classifier import (
    ModelOutputError,
    build_classify_messages,
    date_anchor,
    truncate_context,
)
from substrate.segmentation import segment_capture

log = logging.getLogger(__name__)


# ── Merged prompts (candidates 3, 4) ───────────────────────────────────────────

#: The two system prompts joined at the seam, with the hand-off text removed.
#: Not a concatenation: `EXTRACT_SYSTEM`'s "output them as JSON" framing and
#: `CLASSIFY_SYSTEM`'s "Given extracted items" framing contradict each other in
#: one call, and leaving both in would measure the contradiction.
_MERGED_PREAMBLE = """\
You are a capture engine. Given raw capture text, identify every discrete item
and output each one as a finished node in a single step.

Work in two stages internally, but output only the finished nodes.
"""

_MERGED_STAGE_ONE = """\

STAGE 1 - find the items.
"""

_MERGED_STAGE_TWO = """\

STAGE 2 - assign each item a node_type and fields.
"""


def _strip_output_format(text: str) -> str:
    """Drop a prompt's trailing 'Output format:' line.

    Each half declares its own output shape. In a merged prompt only the final
    shape is true, and leaving both in tells the model to emit two different
    envelopes.
    """

    lines = [
        line for line in text.splitlines()
        if not line.startswith("Output format:")
    ]
    return "\n".join(lines).rstrip() + "\n"


def _body_after_first_line(text: str) -> str:
    """Drop a prompt's role-declaration line, which the merged preamble owns."""

    return "\n".join(text.splitlines()[1:]).strip() + "\n"


MERGED_SYSTEM = (
    _MERGED_PREAMBLE
    + _MERGED_STAGE_ONE
    + _body_after_first_line(_strip_output_format(EXTRACT_SYSTEM))
    + _MERGED_STAGE_TWO
    + _body_after_first_line(_strip_output_format(CLASSIFY_SYSTEM))
    + '\nOutput format: {"nodes": [...]}\n'
)

#: Candidate 4's schema: the intermediate representation survives as two fields
#: per node instead of as a round trip. This is the whole point of the
#: candidate - it keeps `raw_nodes` inspectable without paying a second call.
STAGED_SCHEMA = {
    "type": "object",
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "raw": {"type": "string"},
                    "type_hint": {
                        "type": "string",
                        "enum": ["appointment", "task", "setting",
                                 "contact", "entity", "note"],
                    },
                    **CLASSIFY_SCHEMA["properties"]["nodes"]["items"]["properties"],
                },
                "required": ["raw", "type_hint", "node_type", "confidence",
                             "title", "item_text", "date"],
            },
        }
    },
    "required": ["nodes"],
}

MERGED_STAGED_SYSTEM = MERGED_SYSTEM.replace(
    'Output format: {"nodes": [...]}',
    'For every node also echo "raw" - the exact source text it came from - and\n'
    'its "type_hint". Echo the source text; do not rewrite it.\n\n'
    'Output format: {"nodes": [{"raw": "...", "type_hint": "...", "node_type": "...", ...}]}',
)

#: Merged few-shot examples. Content is lifted from the existing pairs so the
#: merged prompt teaches the same doctrine, not a fresh one.
MERGED_EXAMPLES = [
    {
        "role": "user",
        "content": (
            "Today: 2026-04-24 (Friday)\n\n"
            "Capture:\n\nI have a dentist appointment Thursday at 8am and need "
            "to pick up my prescription at CVS afterward. Frank's at 410-555-1212."
        ),
    },
    {
        "role": "assistant",
        "content": (
            '{"nodes": ['
            '{"node_type": "cogs/daily", "title": "DENTIST 8am", "item_text": "DENTIST 8am", "date": "2026-04-30", "confidence": "high"}, '
            '{"node_type": "cogs/daily", "title": "Pick up prescription at CVS", "item_text": "Pick up prescription at CVS", "date": "2026-04-30", "confidence": "high"}, '
            '{"node_type": "sprockets/contact", "title": "Frank", "item_text": "Frank, phone 410-555-1212", "date": "2026-04-24", "confidence": "high"}'
            "]}"
        ),
    },
    {
        "role": "user",
        "content": (
            "Today: 2026-04-22 (Wednesday)\n"
            "This week's workdays: Mon 2026-04-20  Tue 2026-04-21  Wed 2026-04-22  "
            "Thu 2026-04-23  Fri 2026-04-24\n\n"
            "Capture:\n\nWorking from home all week."
        ),
    },
    {
        "role": "assistant",
        "content": (
            '{"nodes": ['
            '{"node_type": "cogs/daily", "title": "WFH", "item_text": "WFH", "date": "2026-04-20", "confidence": "high"}, '
            '{"node_type": "cogs/daily", "title": "WFH", "item_text": "WFH", "date": "2026-04-21", "confidence": "high"}, '
            '{"node_type": "cogs/daily", "title": "WFH", "item_text": "WFH", "date": "2026-04-22", "confidence": "high"}, '
            '{"node_type": "cogs/daily", "title": "WFH", "item_text": "WFH", "date": "2026-04-23", "confidence": "high"}, '
            '{"node_type": "cogs/daily", "title": "WFH", "item_text": "WFH", "date": "2026-04-24", "confidence": "high"}'
            "]}"
        ),
    },
]

#: The staged variant needs its examples to show the echoed fields, or the
#: model has no demonstration of the behaviour the schema requires. Finding 49:
#: examples outrank prose.
MERGED_STAGED_EXAMPLES = [
    MERGED_EXAMPLES[0],
    {
        "role": "assistant",
        "content": (
            '{"nodes": ['
            '{"raw": "dentist appointment Thursday at 8am", "type_hint": "appointment", '
            '"node_type": "cogs/daily", "title": "DENTIST 8am", "item_text": "DENTIST 8am", "date": "2026-04-30", "confidence": "high"}, '
            '{"raw": "pick up prescription at CVS", "type_hint": "task", '
            '"node_type": "cogs/daily", "title": "Pick up prescription at CVS", "item_text": "Pick up prescription at CVS", "date": "2026-04-30", "confidence": "high"}, '
            '{"raw": "Frank, phone 410-555-1212", "type_hint": "contact", '
            '"node_type": "sprockets/contact", "title": "Frank", "item_text": "Frank, phone 410-555-1212", "date": "2026-04-24", "confidence": "high"}'
            "]}"
        ),
    },
    MERGED_EXAMPLES[2],
    {
        "role": "assistant",
        "content": (
            '{"nodes": ['
            + ", ".join(
                '{"raw": "working from home all week", "type_hint": "setting", '
                '"node_type": "cogs/daily", "title": "WFH", "item_text": "WFH", '
                f'"date": "2026-04-{day}", "confidence": "high"}}'
                for day in ("20", "21", "22", "23", "24")
            )
            + "]}"
        ),
    },
]

#: Candidate 2: extract preserves, never computes. Stage 141 slice 3d measured
#: most of this and reverted it standalone; here it is one arm of a larger
#: comparison rather than a change on its own.
PRESERVE_EXTRACT_SYSTEM = """\
You are an extraction engine. Given text, identify all discrete items and output them as JSON.

type_hint values:
  appointment — has a specific time (8am, 5:30p, noon)
  setting     — context keyword, no time (WFH, ONSITE, HOLIDAY)
  task        — actionable, no time anchor
  contact     — a person
  entity      — org, place, or thing mentioned only for reference
  note        — reference or idea, no action

A store or place name paired with a day or time is an errand, not an entity.
"WALMART Saturday" → {"raw": "WALMART Saturday", "type_hint": "task"}
Use entity only when nothing is being done at the place.

PRESERVE, NEVER COMPUTE. Copy the source text into the raw field exactly as
written. Keep every day, date, time, and repeat phrase verbatim.

Do not resolve dates. "Saturday" stays "Saturday", never a calendar date.
Do not expand repeats. "next 3 Saturdays" and "all next week" stay as written,
as ONE item. Something downstream does that arithmetic correctly and needs the
original phrase to do it.

Output format: {"items": [{"raw": "...", "type_hint": "..."}]}
"""

#: Candidate 7's second call: decisions, not nodes. The seam is by decision
#: type, and it is only cheap if the second call emits a small answer rather
#: than re-emitting everything it was given.
HIERARCHY_SYSTEM = """\
You are a hierarchy engine. Given classified nodes and known hierarchy parents
from context, decide which nodes belong to which parent.

Output one decision per node, in the same order, using its index.
parent_hint must be an exact area/goal/project title from the context, or ""
when the node has no parent. Never invent a parent name.

Output format: {"decisions": [{"index": 0, "parent_hint": ""}]}
"""

HIERARCHY_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "parent_hint": {"type": "string"},
                },
                "required": ["index", "parent_hint"],
            },
        }
    },
    "required": ["decisions"],
}


# ── Plumbing ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ArchitectureRun:
    raw_nodes: list[dict]
    classified_nodes: list[dict]
    notes: tuple[str, ...] = ()
    """What the architecture did that the score alone will not show - a
    segmenter decline, an escalation, a dropped inspection point."""


def _chat(classifier, call: str, messages: list[dict], schema: dict) -> Any:
    response = classifier.chat_client(
        model=classifier.config.model,
        messages=messages,
        format=schema,
        options=classifier.config.chat_options(),
        think=False,
    )
    classifier._record(call, messages, response)
    return response


def _parse(response: Any, key: str) -> list[dict]:
    """Read one model reply, raising rather than swallowing a parse failure.

    Matches the live path (finding 73). The harness records the exception per
    fixture, so a truncated generation shows as an error instead of scoring as
    a fixture that produced no nodes - which is how `segmented`'s runaway on
    `multi-day-setting-holiday` read as a clean 0 in slice 1.
    """

    raw = response.message.content
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("%s parse failed: %s | raw: %s", key, exc, raw)
        raise ModelOutputError(
            key, str(exc), getattr(response, "eval_count", None)
        ) from exc
    if isinstance(result, dict):
        return result.get(key, []) or []
    return result if isinstance(result, list) else []


def _capture_user_message(content: str, ref: datetime, context: str = "") -> str:
    parts = [date_anchor(ref)]
    if context:
        parts.append(truncate_context(context))
    parts.append(f"Capture:\n\n{content}")
    return "\n\n".join(parts)


def _split_staged(nodes: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separate candidate 4's echoed fields from the node fields.

    The echoed `raw`/`type_hint` become `raw_nodes` so the post-classify chain
    has its match target, and are stripped from the nodes so validation and
    grading see the same shape every other architecture produces.
    """

    raw_nodes: list[dict] = []
    classified: list[dict] = []
    for node in nodes:
        raw = str(node.get("raw") or "")
        if raw:
            raw_nodes.append(
                {"raw": raw, "type_hint": node.get("type_hint") or "task"}
            )
        classified.append(
            {k: v for k, v in node.items() if k not in ("raw", "type_hint")}
        )
    return raw_nodes, classified


# ── The candidates ─────────────────────────────────────────────────────────────


def two_call(classifier, content, ref, context, config) -> ArchitectureRun:
    """Candidate 1. Baseline: the shipped chain, untouched."""

    raw_nodes = classifier.extract_nodes(content, now=ref)
    classified = classifier.classify_nodes(
        raw_nodes, context, use_examples=config.use_examples, now=ref
    )
    return ArchitectureRun(raw_nodes, classified)


def preserve_extract(classifier, content, ref, context, config) -> ArchitectureRun:
    """Candidate 2. Same seam; extract computes nothing.

    Assembles its own extract messages rather than swapping the module global,
    so two architectures can never race on a patched prompt and a failure
    cannot leave the shipped prompt replaced.
    """

    messages = [
        {"role": "system", "content": PRESERVE_EXTRACT_SYSTEM},
        *(EXTRACT_EXAMPLES if config.use_examples else []),
        {"role": "user", "content": (
            f"{date_anchor(ref)}\n\nExtract all items from this text:\n\n{content}"
        )},
    ]
    response = _chat(classifier, "extract", messages, EXTRACT_SCHEMA)
    raw_nodes = _parse(response, "items")
    classified = classifier.classify_nodes(
        raw_nodes, context, use_examples=config.use_examples, now=ref
    )
    return ArchitectureRun(raw_nodes, classified)


def one_flat(classifier, content, ref, context, config) -> ArchitectureRun:
    """Candidate 3. One call, capture text to final nodes.

    Returns no `raw_nodes`. That is the candidate's real cost: the post-classify
    chain loses its match target and the inspection point disappears. Measured,
    not mitigated.
    """

    messages = [
        {"role": "system", "content": MERGED_SYSTEM},
        *(MERGED_EXAMPLES if config.use_examples else []),
        {"role": "user", "content": _capture_user_message(content, ref, context)},
    ]
    response = _chat(classifier, "merged", messages, CLASSIFY_SCHEMA)
    return ArchitectureRun(
        [], _parse(response, "nodes"),
        notes=("no raw_nodes: inspection point and date-match target lost",),
    )


def one_staged(classifier, content, ref, context, config) -> ArchitectureRun:
    """Candidate 4. One call, one prefill, one decode - schema carries both
    stages, so the intermediate representation survives as a field."""

    messages = [
        {"role": "system", "content": MERGED_STAGED_SYSTEM},
        *(MERGED_STAGED_EXAMPLES if config.use_examples else []),
        {"role": "user", "content": _capture_user_message(content, ref, context)},
    ]
    response = _chat(classifier, "merged-staged", messages, STAGED_SCHEMA)
    raw_nodes, classified = _split_staged(_parse(response, "nodes"))
    return ArchitectureRun(raw_nodes, classified)


def segmented(classifier, content, ref, context, config) -> ArchitectureRun:
    """Candidate 5. Code segments; the model only classifies.

    Falls back to the extract call when the splitter declines, so this is a
    hybrid. The fallback rate is part of the result: a candidate that declines
    on most real captures is a two-call architecture wearing a one-call name.
    """

    result = segment_capture(content)
    notes: list[str] = []
    if result.structured and result.segments:
        raw_nodes = result.to_raw_nodes(ref.strftime("%Y-%m-%d"))
        notes.append(f"segmented deterministically into {len(raw_nodes)}")
    else:
        raw_nodes = classifier.extract_nodes(content, now=ref)
        notes.append(f"fell back to extract: {result.declined_reason or 'no segments'}")
    classified = classifier.classify_nodes(
        raw_nodes, context, use_examples=config.use_examples, now=ref
    )
    return ArchitectureRun(raw_nodes, classified, notes=tuple(notes))


def conditional(classifier, content, ref, context, config) -> ArchitectureRun:
    """Candidate 6. One call by default; a second only for what the first got
    wrong. The retry path already does this as an exception; here it is the
    architecture."""

    first = one_staged(classifier, content, ref, context, config)
    escalate = [
        node for node in first.classified_nodes
        if node.get("confidence") == "low" or not node.get("node_type")
    ]
    if not escalate:
        return ArchitectureRun(
            first.raw_nodes, first.classified_nodes, notes=("no escalation",)
        )

    raw_for_escalation = [
        {"raw": str(node.get("item_text") or node.get("title") or ""),
         "type_hint": "task"}
        for node in escalate
    ]
    messages = build_classify_messages(
        raw_for_escalation, context, ref,
        error_context=(
            "These items were classified with low confidence. Re-decide their "
            "node_type and date, and raise confidence only if the text supports it."
        ),
        use_examples=config.use_examples,
        context_max_chars=config.context_max_chars,
    )
    response = _chat(classifier, "escalate", messages, CLASSIFY_SCHEMA)
    redone = _parse(response, "nodes")

    kept = [node for node in first.classified_nodes if node not in escalate]
    return ArchitectureRun(
        first.raw_nodes, kept + redone,
        notes=(f"escalated {len(escalate)} of {len(first.classified_nodes)}",),
    )


def two_seam_decision(classifier, content, ref, context, config) -> ArchitectureRun:
    """Candidate 7. Seam by decision type: structure and typing, then hierarchy.

    The second call emits decisions rather than nodes, which is the only way
    this is cheaper than candidate 1 - a call costs what it decodes.
    """

    first = one_staged(classifier, content, ref, context, config)
    nodes = first.classified_nodes
    if not nodes or not context:
        return ArchitectureRun(
            first.raw_nodes, nodes, notes=("hierarchy call skipped: no context",)
        )

    listing = json.dumps(
        [{"index": i, "node_type": n.get("node_type"), "title": n.get("title")}
         for i, n in enumerate(nodes)],
        indent=2,
    )
    messages = [
        {"role": "system", "content": HIERARCHY_SYSTEM},
        {"role": "user", "content": (
            f"{truncate_context(context, config.context_max_chars)}\n\n"
            f"Nodes:\n{listing}\n\nAssign parents."
        )},
    ]
    response = _chat(classifier, "hierarchy", messages, HIERARCHY_SCHEMA)
    for decision in _parse(response, "decisions"):
        index = decision.get("index")
        parent = str(decision.get("parent_hint") or "")
        if isinstance(index, int) and 0 <= index < len(nodes) and parent:
            nodes[index]["parent_hint"] = parent
    return ArchitectureRun(first.raw_nodes, nodes)


ARCHITECTURES: dict[str, Callable[..., ArchitectureRun]] = {
    "two-call": two_call,
    "preserve-extract": preserve_extract,
    "one-flat": one_flat,
    "one-staged": one_staged,
    "segmented": segmented,
    "conditional": conditional,
    "two-seam-decision": two_seam_decision,
}

DEFAULT_ARCHITECTURE = "two-call"

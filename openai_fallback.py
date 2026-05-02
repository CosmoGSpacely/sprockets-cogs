"""OpenAI fallback classification for review-first recovery."""

from __future__ import annotations

import json
import logging
import os

from prompts import CLASSIFY_SCHEMA, CLASSIFY_SYSTEM

log = logging.getLogger(__name__)

OPENAI_FALLBACK_MODEL = os.environ.get("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")


def openai_fallback_enabled() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _openai_classify_schema() -> dict:
    node_schema = dict(CLASSIFY_SCHEMA["properties"]["nodes"]["items"])
    node_schema["additionalProperties"] = False
    return {
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "items": node_schema,
            }
        },
        "required": ["nodes"],
        "additionalProperties": False,
    }


def _response_text(response) -> str:
    output_text = getattr(response, "output_text", "")
    if output_text:
        return output_text
    parts = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", "")
            if text:
                parts.append(text)
    return "".join(parts)


def classify_nodes_with_openai_fallback(
    raw_nodes: list[dict],
    context: str,
    reason: str,
) -> list[dict]:
    """
    Use OpenAI Structured Outputs to reclassify failed local-model output.
    Returned nodes are candidates only; callers should route them to review/.
    """
    if not raw_nodes:
        return []
    if not openai_fallback_enabled():
        log.info("OpenAI fallback skipped: OPENAI_API_KEY is not set")
        return []

    try:
        from openai import OpenAI
    except ImportError:
        log.warning("OpenAI fallback skipped: openai package is not installed")
        return []

    user_msg = (
        "The local model could not produce trusted structured output.\n"
        f"Reason: {reason}\n\n"
        f"Context:\n{context}\n\n"
        f"Extracted items:\n{json.dumps(raw_nodes, indent=2)}\n\n"
        "Classify each item. Return JSON only."
    )

    client = OpenAI()
    response = client.responses.create(
        model=OPENAI_FALLBACK_MODEL,
        input=[
            {"role": "system", "content": CLASSIFY_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "sprockets_cogs_classification",
                "schema": _openai_classify_schema(),
                "strict": True,
            }
        },
    )

    raw = _response_text(response)
    result = json.loads(raw)
    nodes = result.get("nodes", []) if isinstance(result, dict) else []
    log.info("OpenAI fallback classified %d node candidate(s)", len(nodes))
    return nodes

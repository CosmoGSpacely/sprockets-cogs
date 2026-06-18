"""Extractor/classifier facade for the Phase 4 capture role.

This module mirrors the current agentic loop prompt calls behind a narrow
interface. Stage 38A keeps it unwired from the live watcher until the boundary
is tested.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

import ollama

from specialists.rosie.prompts import (
    CLASSIFY_EXAMPLES,
    CLASSIFY_SCHEMA,
    CLASSIFY_SYSTEM,
    EXTRACT_EXAMPLES,
    EXTRACT_SCHEMA,
    EXTRACT_SYSTEM,
)


DEFAULT_CAPTURE_MODEL = "qwen3.5:9b-32k-cosmo"
CAPTURE_MODEL = os.environ.get(
    "SPROCKETS_COGS_EXTRACTOR_MODEL",
    os.environ.get("SPROCKETS_COGS_MODEL", DEFAULT_CAPTURE_MODEL),
)

log = logging.getLogger(__name__)


class ChatClient(Protocol):
    """Small protocol for Ollama-compatible chat clients."""

    def __call__(self, **kwargs: Any) -> Any:
        ...


@dataclass(frozen=True)
class ExtractClassifierConfig:
    """Runtime knobs for the capture extractor/classifier role."""

    model: str = CAPTURE_MODEL
    temperature: float = 0.1


def week_workdays(ref: datetime) -> str:
    """Return compact weekday anchors for date-sensitive extraction/classification."""

    monday = ref - timedelta(days=ref.weekday())
    return "  ".join(
        (monday + timedelta(days=i)).strftime("%a %Y-%m-%d") for i in range(5)
    )


def truncate_context(context: str, max_chars: int = 2000) -> str:
    """Keep classifier context bounded to the existing prompt budget."""

    if len(context) <= max_chars:
        return context
    return context[:max_chars] + "\n[... truncated]"


class ExtractClassifier:
    """Facade for the local model extraction/classification chain."""

    def __init__(
        self,
        config: ExtractClassifierConfig | None = None,
        chat_client: ChatClient | None = None,
    ) -> None:
        self.config = config or ExtractClassifierConfig()
        self.chat_client = chat_client or ollama.chat

    def extract_nodes(self, content: str, now: datetime | None = None) -> list[dict]:
        """Extract raw items from input text."""

        ref = now or datetime.now()
        extract_msg = (
            f"This week's workdays: {week_workdays(ref)}\n\n"
            f"Extract all items from this text:\n\n{content}"
        )
        messages = [
            {"role": "system", "content": EXTRACT_SYSTEM},
            *EXTRACT_EXAMPLES,
            {"role": "user", "content": extract_msg},
        ]
        response = self.chat_client(
            model=self.config.model,
            messages=messages,
            format=EXTRACT_SCHEMA,
            options={"temperature": self.config.temperature},
            think=False,
        )
        raw = response.message.content
        log.debug("extract_nodes raw: %s", raw)
        try:
            result = json.loads(raw)
            items = result.get("items", []) if isinstance(result, dict) else result
            log.info("Extracted %d item(s)", len(items))
            return items
        except json.JSONDecodeError as exc:
            log.error("extract_nodes JSON parse failed: %s | raw: %s", exc, raw)
            return []

    def classify_nodes(
        self,
        raw_nodes: list[dict],
        context: str,
        error_context: str = "",
        use_examples: bool = True,
        now: datetime | None = None,
    ) -> list[dict]:
        """Assign node_type, fields, and date to extracted items."""

        if not raw_nodes:
            return []
        today_dt = now or datetime.now()
        today = today_dt.strftime("%Y-%m-%d (%A)")
        user_msg = (
            f"Today: {today}\n"
            f"This week's workdays: {week_workdays(today_dt)}\n\n"
            f"{truncate_context(context)}\n\n"
            f"Extracted:\n{json.dumps(raw_nodes, indent=2)}\n\n"
        )
        if error_context:
            user_msg += f"Fix these issues from the previous attempt:\n{error_context}\n\n"
        user_msg += "Classify each item."

        examples = CLASSIFY_EXAMPLES if use_examples else []
        messages = [
            {"role": "system", "content": CLASSIFY_SYSTEM},
            *examples,
            {"role": "user", "content": user_msg},
        ]
        response = self.chat_client(
            model=self.config.model,
            messages=messages,
            format=CLASSIFY_SCHEMA,
            options={"temperature": self.config.temperature},
            think=False,
        )
        raw = response.message.content
        log.debug("classify_nodes raw: %s", raw)
        try:
            result = json.loads(raw)
            nodes = result.get("nodes", []) if isinstance(result, dict) else result
            log.info("Classified %d node(s)", len(nodes))
            return nodes
        except json.JSONDecodeError as exc:
            log.error("classify_nodes JSON parse failed: %s | raw: %s", exc, raw)
            return []

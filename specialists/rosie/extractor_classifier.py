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


DEFAULT_CAPTURE_MODEL = "gemma4:12b-16k-cosmo"
CAPTURE_MODEL = os.environ.get(
    "SPROCKETS_COGS_EXTRACTOR_MODEL",
    os.environ.get("SPROCKETS_COGS_MODEL", DEFAULT_CAPTURE_MODEL),
)

log = logging.getLogger(__name__)


class ChatClient(Protocol):
    """Small protocol for Ollama-compatible chat clients."""

    def __call__(self, **kwargs: Any) -> Any:
        ...


DEFAULT_CONTEXT_MAX_CHARS = 2000

_NS_PER_SECOND = 1_000_000_000


class ModelOutputError(RuntimeError):
    """The model's reply could not be read as the schema required.

    Raised instead of returning `[]`. Stage 142 finding 73: a generation
    truncated at `num_predict` produces invalid JSON, and both call sites used
    to log the parse failure and return an empty list. The capture was then
    consumed, wrote nothing, and reported success - indistinguishable from the
    correct answer on an input that genuinely contains no items.

    Truncation is not exotic. Marginal cost is ~34-49 completion tokens per
    node, so a photographed list of roughly 75 items reaches the 4,096 cap
    (finding 78), and that is an ordinary capture once image input is live.

    Raising leaves the input in `processing/` with a failure record, which is
    the behaviour a capture that could not be read deserves.
    """

    def __init__(self, call: str, detail: str, completion_tokens: int | None = None):
        self.call = call
        self.completion_tokens = completion_tokens
        suffix = (
            f" after {completion_tokens} completion tokens"
            f" (truncation likely if this is the num_predict cap)"
            if completion_tokens
            else ""
        )
        super().__init__(f"{call} output unreadable: {detail}{suffix}")


@dataclass(frozen=True)
class CallStats:
    """Measured cost of one model call.

    Token counts come from the model's own tokenizer via Ollama's
    `prompt_eval_count` / `eval_count`, not from a character estimate.
    """

    call: str
    model: str
    prompt_chars: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_seconds: float | None = None
    load_seconds: float | None = None
    prompt_eval_seconds: float | None = None
    eval_seconds: float | None = None

    @property
    def chars_per_token(self) -> float | None:
        """Measured ratio for this project's real prompts."""

        if not self.prompt_tokens:
            return None
        return self.prompt_chars / self.prompt_tokens


def _seconds(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return value / _NS_PER_SECOND


def _call_stats(call: str, model: str, messages: list[dict], response: Any) -> CallStats:
    """Build CallStats from a chat response, tolerating clients that omit fields."""

    return CallStats(
        call=call,
        model=model,
        prompt_chars=sum(len(str(message.get("content", ""))) for message in messages),
        prompt_tokens=getattr(response, "prompt_eval_count", None),
        completion_tokens=getattr(response, "eval_count", None),
        total_seconds=_seconds(getattr(response, "total_duration", None)),
        load_seconds=_seconds(getattr(response, "load_duration", None)),
        prompt_eval_seconds=_seconds(getattr(response, "prompt_eval_duration", None)),
        eval_seconds=_seconds(getattr(response, "eval_duration", None)),
    )


@dataclass(frozen=True)
class ExtractClassifierConfig:
    """Runtime knobs for the capture extractor/classifier role."""

    model: str = CAPTURE_MODEL
    temperature: float = 0.1
    context_max_chars: int = DEFAULT_CONTEXT_MAX_CHARS
    # Sampling knobs. None means "do not send it", so the model's own resolved
    # parameters apply and default behavior is unchanged. Request options
    # override Modelfile PARAMETER values, so anything set here wins.
    repeat_penalty: float | None = None
    presence_penalty: float | None = None
    top_k: int | None = None
    top_p: float | None = None

    def chat_options(self) -> dict[str, Any]:
        """Build the options dict for a chat call, omitting unset knobs."""

        options: dict[str, Any] = {"temperature": self.temperature}
        for name in ("repeat_penalty", "presence_penalty", "top_k", "top_p"):
            value = getattr(self, name)
            if value is not None:
                options[name] = value
        return options


def week_workdays(ref: datetime) -> str:
    """Return compact weekday anchors for date-sensitive extraction/classification."""

    monday = ref - timedelta(days=ref.weekday())
    return "  ".join(
        (monday + timedelta(days=i)).strftime("%a %Y-%m-%d") for i in range(5)
    )


TRUNCATION_MARKER = "[... truncated]"

#: Capture length above which a single classify call is no longer a safe shape.
#: Finding 78 measured ~34-49 completion tokens per node against a 4096 cap, so
#: the practical ceiling is ~75 nodes; this threshold is set well below that, at
#: roughly the size where a photographed list stops being a dictated note.
CAPTURE_BUDGET_CHARS = 4000


def capture_exceeds_budget(text: str) -> bool:
    """Whether a capture is too large for one unbatched pass.

    **The capture is never truncated.** Context is advisory vault state and
    degrades gracefully when trimmed; the capture is the user's own words, and
    silently cutting them is the finding 73 defect class - a total loss that
    scores as a clean result. An oversize capture is a batching case (D105) or
    a review case, never a truncated one.

    This predicate is the guard, not the handling. It exists so the condition
    is detectable and logged now rather than discovered in production; D105
    owns what to do about it.
    """

    return len(text) > CAPTURE_BUDGET_CHARS

#: Context lines that must survive bounding. The classify prompt has a hard
#: rule about this one - "Never invent a new area, goal, or project name for
#: parent_hint" - so it is the only part of the context the model is forbidden
#: to work around. It is also the last line of the block and the smallest.
PRIORITY_CONTEXT_PREFIXES = ("Known hierarchy parents:",)


def truncate_context(context: str, max_chars: int = DEFAULT_CONTEXT_MAX_CHARS) -> str:
    """Bound the classifier context, dropping the least load-bearing part first.

    Head-truncation was the Stage 142 slice 7 defect (finding 87): the
    hierarchy parent list sits at the end of the context, so every binding cap
    deleted the one section the prompt has a rule about while keeping twenty
    lines of recent nodes. Worse, it cut mid-word, and finding 88 measured that
    a visibly incomplete parent list suppresses `parent_hint` even when the
    needed name survives the cut.

    So: keep the priority lines whole, spend what is left on the rest, and drop
    whole lines rather than characters. A partial list is worse than a short
    one.
    """

    if len(context) <= max_chars:
        return context

    lines = context.splitlines()
    priority = [
        line for line in lines
        if line.startswith(PRIORITY_CONTEXT_PREFIXES)
    ]
    rest = [line for line in lines if line not in priority]

    priority_text = "\n".join(priority)
    if not priority or len(priority_text) + len(TRUNCATION_MARKER) + 1 > max_chars:
        # No priority section, or no room for it. Fall back to dropping whole
        # lines from the end - never a mid-word cut.
        return _fit_lines(lines, max_chars)

    budget = max_chars - len(priority_text) - len(TRUNCATION_MARKER) - 2
    kept: list[str] = []
    used = 0
    for line in rest:
        if used + len(line) + 1 > budget:
            break
        kept.append(line)
        used += len(line) + 1

    return "\n".join([*kept, TRUNCATION_MARKER, priority_text])


def _fit_lines(lines: list[str], max_chars: int) -> str:
    """Keep as many whole leading lines as fit, then mark the truncation."""

    kept: list[str] = []
    used = 0
    limit = max_chars - len(TRUNCATION_MARKER) - 1
    for line in lines:
        if used + len(line) + 1 > limit:
            break
        kept.append(line)
        used += len(line) + 1
    if not kept:
        # One line longer than the whole budget. Line granularity would drop
        # the entire context, so cut characters here rather than return
        # nothing - losing the tail beats losing everything.
        return lines[0][:limit] + "\n" + TRUNCATION_MARKER if lines else ""
    return "\n".join([*kept, TRUNCATION_MARKER])


def date_anchor(ref: datetime, *, include_workdays: bool = True) -> str:
    """Shared date block for both model calls.

    Both calls must state today's date and the week's workday anchors. They
    previously assembled this separately, and drifted: the extract call lost
    the `Today:` line while classify kept it, so the model resolved relative
    dates by guessing from the workday list (Stage 138 finding 12). Keeping one
    definition is what stops that recurring.

    `include_workdays=False` drops the calendar line. Stage 142 B5: under
    preserve-only extract the model is told never to compute a date, so the
    workday list is either dead weight or an invitation to compute anyway.
    Which one is a measurement (slice 6), not an argument.
    """

    today = f"Today: {ref.strftime('%Y-%m-%d (%A)')}"
    if not include_workdays:
        return today
    return f"{today}\nThis week's workdays: {week_workdays(ref)}"


def build_extract_messages(content: str, ref: datetime) -> list[dict]:
    """Assemble the exact message list for the extract call."""

    if capture_exceeds_budget(content):
        log.warning(
            "capture is %d chars, above the %d single-pass budget; "
            "sending unbatched (D105 owns batching)",
            len(content),
            CAPTURE_BUDGET_CHARS,
        )
    return [
        {"role": "system", "content": EXTRACT_SYSTEM},
        *EXTRACT_EXAMPLES,
        {
            "role": "user",
            "content": (
                f"{date_anchor(ref)}\n\n"
                f"Extract all items from this text:\n\n{content}"
            ),
        },
    ]


def build_classify_messages(
    raw_nodes: list[dict],
    context: str,
    ref: datetime,
    *,
    error_context: str = "",
    use_examples: bool = True,
    context_max_chars: int = DEFAULT_CONTEXT_MAX_CHARS,
    system: str | None = None,
    examples: list[dict] | None = None,
    include_workdays: bool = True,
) -> list[dict]:
    """Assemble the exact message list for the classify call.

    `system` and `examples` override the shipped prompt surface for one call.
    They exist so a harness arm can vary the prompt without swapping a module
    global, which two architectures running in one process would race on.
    """

    user_msg = (
        f"{date_anchor(ref, include_workdays=include_workdays)}\n\n"
        f"{truncate_context(context, context_max_chars)}\n\n"
        f"Extracted:\n{json.dumps(raw_nodes, indent=2)}\n\n"
    )
    if error_context:
        user_msg += f"Fix these issues from the previous attempt:\n{error_context}\n\n"
    user_msg += "Classify each item."

    return [
        {"role": "system", "content": system if system is not None else CLASSIFY_SYSTEM},
        *((examples if examples is not None else CLASSIFY_EXAMPLES) if use_examples else []),
        {"role": "user", "content": user_msg},
    ]


class ExtractClassifier:
    """Facade for the local model extraction/classification chain."""

    def __init__(
        self,
        config: ExtractClassifierConfig | None = None,
        chat_client: ChatClient | None = None,
    ) -> None:
        self.config = config or ExtractClassifierConfig()
        self.chat_client = chat_client or ollama.chat
        self.call_stats: list[CallStats] = []

    def _record(self, call: str, messages: list[dict], response: Any) -> None:
        """Record and log the measured cost of one model call."""

        stats = _call_stats(call, self.config.model, messages, response)
        self.call_stats.append(stats)
        log.info(
            "%s tokens: prompt=%s completion=%s chars=%d ratio=%s",
            call,
            stats.prompt_tokens,
            stats.completion_tokens,
            stats.prompt_chars,
            f"{stats.chars_per_token:.2f}" if stats.chars_per_token else "n/a",
        )

    def extract_nodes(self, content: str, now: datetime | None = None) -> list[dict]:
        """Extract raw items from input text."""

        ref = now or datetime.now()
        messages = build_extract_messages(content, ref)
        response = self.chat_client(
            model=self.config.model,
            messages=messages,
            format=EXTRACT_SCHEMA,
            options=self.config.chat_options(),
            think=False,
        )
        self._record("extract", messages, response)
        raw = response.message.content
        log.debug("extract_nodes raw: %s", raw)
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.error("extract_nodes JSON parse failed: %s | raw: %s", exc, raw)
            raise ModelOutputError(
                "extract", str(exc), getattr(response, "eval_count", None)
            ) from exc
        items = result.get("items", []) if isinstance(result, dict) else result
        log.info("Extracted %d item(s)", len(items))
        return items

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
        ref = now or datetime.now()
        messages = build_classify_messages(
            raw_nodes,
            context,
            ref,
            error_context=error_context,
            use_examples=use_examples,
            context_max_chars=self.config.context_max_chars,
        )
        response = self.chat_client(
            model=self.config.model,
            messages=messages,
            format=CLASSIFY_SCHEMA,
            options=self.config.chat_options(),
            think=False,
        )
        self._record("classify", messages, response)
        raw = response.message.content
        log.debug("classify_nodes raw: %s", raw)
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.error("classify_nodes JSON parse failed: %s | raw: %s", exc, raw)
            raise ModelOutputError(
                "classify", str(exc), getattr(response, "eval_count", None)
            ) from exc
        nodes = result.get("nodes", []) if isinstance(result, dict) else result
        log.info("Classified %d node(s)", len(nodes))
        return nodes

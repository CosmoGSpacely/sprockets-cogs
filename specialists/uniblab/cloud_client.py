"""Anthropic chat client shaped like the Ollama one, for Stage 145 only.

**Experiment-scoped.** This is an instrument, not a fallback, which is why it
lives in `uniblab` beside the harness rather than in `rudi`. D107 decides the
production fallback's shape and either promotes this code or replaces it;
either way this module retires with that decision rather than becoming another
module nothing imports.

Three translations are needed to make Anthropic answer the harness's questions:

1. **Schema becomes a forced tool call.** Anthropic has no
   `response_format: json_schema`. The equivalent is a tool whose
   `input_schema` is the schema, with `tool_choice` naming it, and the tool
   input read back as the answer.
2. **The system message moves out of the list.** Ollama takes a `system` role
   inside `messages`; Anthropic takes a top-level `system` parameter.
3. **The response is presented Ollama-shaped**, because `_call_stats` reads
   `prompt_eval_count`, `eval_count` and four `*_duration` fields off it.
   Token counts map from `usage`; **duration fields are deliberately absent** -
   cloud latency is network time and is not comparable to local prefill and
   decode, so a missing measurement is the honest answer rather than a
   misleading one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from specialists.rosie.extractor_classifier import ModelOutputError

ENV_FILE = Path.home() / ".config" / "sprockets-cogs" / "env"
API_KEY_NAME = "ANTHROPIC_API_KEY"

#: Matches the local `num_predict` cap so a truncation on one side is a
#: truncation on the other. Finding 73: a truncated generation must surface as
#: an error, never as a clean zero.
MAX_TOKENS = 4096

TOOL_NAME = "emit_result"


def load_api_key(env_file: Path = ENV_FILE) -> str:
    """Read the key from the service env file, falling back to the process env.

    The env file is checked first on purpose: the service reads that file, so a
    key exported only in a shell would let the harness succeed where the
    service would fail.
    """

    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == API_KEY_NAME:
                return value.strip().strip('"').strip("'")
    key = os.environ.get(API_KEY_NAME, "")
    if not key:
        raise RuntimeError(
            f"{API_KEY_NAME} not found in {env_file} or the environment"
        )
    return key


def split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Lift system-role messages into one system string.

    Ollama accepts a system role in the list; Anthropic takes it separately and
    requires the list to begin with a user turn.
    """

    system_parts = [
        str(m.get("content", "")) for m in messages if m.get("role") == "system"
    ]
    rest = [dict(m) for m in messages if m.get("role") != "system"]
    return "\n\n".join(system_parts), rest


class AnthropicChatClient:
    """Callable matching the `ChatClient` protocol used by `ExtractClassifier`."""

    def __init__(self, client: Any = None, api_key: str | None = None):
        if client is not None:
            self._client = client
        else:
            import anthropic

            self._client = anthropic.Anthropic(api_key=api_key or load_api_key())

    def __call__(
        self,
        *,
        model: str,
        messages: list[dict],
        format: dict | None = None,
        options: dict | None = None,
        think: bool = False,
        **_ignored: Any,
    ) -> SimpleNamespace:
        system, turns = split_system(messages)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "system": system,
            "messages": turns,
        }
        temperature = (options or {}).get("temperature")
        if temperature is not None:
            kwargs["temperature"] = temperature
        if format:
            kwargs["tools"] = [{
                "name": TOOL_NAME,
                "description": "Return the result in the required structure.",
                "input_schema": format,
            }]
            kwargs["tool_choice"] = {"type": "tool", "name": TOOL_NAME}

        response = self._client.messages.create(**kwargs)
        return self._to_ollama_shape(response, bool(format))

    @staticmethod
    def _to_ollama_shape(response: Any, expect_tool: bool) -> SimpleNamespace:
        usage = getattr(response, "usage", None)
        eval_count = getattr(usage, "output_tokens", None)

        if getattr(response, "stop_reason", None) == "max_tokens":
            raise ModelOutputError(
                "cloud", f"generation hit the {MAX_TOKENS} token cap", eval_count
            )

        content = ""
        if expect_tool:
            for block in getattr(response, "content", []) or []:
                if getattr(block, "type", None) == "tool_use":
                    content = json.dumps(getattr(block, "input", {}))
                    break
            else:
                raise ModelOutputError(
                    "cloud", "no tool_use block in the reply", eval_count
                )
        else:
            for block in getattr(response, "content", []) or []:
                if getattr(block, "type", None) == "text":
                    content = getattr(block, "text", "")
                    break

        return SimpleNamespace(
            message=SimpleNamespace(content=content),
            prompt_eval_count=getattr(usage, "input_tokens", None),
            eval_count=eval_count,
            # Durations deliberately omitted: see the module docstring.
        )


def is_cloud_model(model: str) -> bool:
    """Whether a harness `--model` value should be served by Anthropic."""

    return model.startswith("claude-")

"""Read-only Stage 24 probe for local model memory-tool readiness.

This module does not execute tools. It asks the local model to choose among a
small, explicit memory-tool vocabulary and reports whether the returned tool
call is parseable and allowed.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any

import ollama


DEFAULT_MODEL = "gemma4:12b-16k-cosmo"
MODEL = os.environ.get("SPROCKETS_COGS_MODEL", DEFAULT_MODEL)

ALLOWED_TOOL_NAMES = frozenset(
    {
        "search_memory",
        "get_memory_node",
        "summarize_recent_cogs",
        "no_memory_tool",
    }
)
REQUIRED_ARGUMENTS_BY_TOOL = {
    "search_memory": frozenset({"query", "reason"}),
    "get_memory_node": frozenset({"node_id", "reason"}),
    "summarize_recent_cogs": frozenset({"days", "reason"}),
    "no_memory_tool": frozenset({"reason"}),
}

MEMORY_TOOL_SYSTEM = """You are testing memory tool selection for Sprockets-Cogs.
Choose exactly one tool. Do not answer the user's request directly.
Use search_memory when the user asks for related project, task, contact, entity, note, or memory context.
Use get_memory_node only when the user provides a specific node id.
Use summarize_recent_cogs when the user asks about recent daily Cogs history.
Use no_memory_tool when no memory lookup is needed."""

MEMORY_TOOL_SPECS: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Search read-only Sprockets-Cogs memory for relevant nodes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Short memory search query derived from the user input.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Brief reason this memory search is useful.",
                    },
                },
                "required": ["query", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_memory_node",
            "description": "Fetch one read-only memory node by stable node id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "Stable Sprockets-Cogs node id, such as projects/example.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Brief reason this exact node is needed.",
                    },
                },
                "required": ["node_id", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_recent_cogs",
            "description": "Summarize read-only recent Cogs daily history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of recent days to inspect.",
                        "minimum": 1,
                        "maximum": 14,
                    },
                    "reason": {
                        "type": "string",
                        "description": "Brief reason recent daily history is useful.",
                    },
                },
                "required": ["days", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "no_memory_tool",
            "description": "Use when no memory lookup is needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief reason no memory tool is needed.",
                    },
                },
                "required": ["reason"],
            },
        },
    },
)

MEMORY_TOOL_CHOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {
            "type": "string",
            "enum": sorted(ALLOWED_TOOL_NAMES),
        },
        "arguments": {
            "type": "object",
        },
    },
    "required": ["tool", "arguments"],
}


@dataclass(frozen=True)
class MemoryToolChoice:
    """A parsed model-selected memory tool call."""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class MemoryToolProbeResult:
    """Outcome of one read-only memory-tool selection probe."""

    query: str
    model: str
    valid: bool
    tool_choice: MemoryToolChoice | None
    issue: str = ""


def _coerce_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_tool_call(tool_call: Any) -> MemoryToolChoice | None:
    function = getattr(tool_call, "function", None)
    if function is None and isinstance(tool_call, dict):
        function = tool_call.get("function")

    if isinstance(function, dict):
        name = function.get("name", "")
        arguments = function.get("arguments", {})
    else:
        name = getattr(function, "name", "")
        arguments = getattr(function, "arguments", {})

    if not name:
        return None
    return MemoryToolChoice(name=name, arguments=_coerce_arguments(arguments))


def parse_memory_tool_choices(response: Any) -> tuple[MemoryToolChoice, ...]:
    """Return parsed tool calls from an Ollama chat response."""
    message = getattr(response, "message", None)
    if message is None and isinstance(response, dict):
        message = response.get("message")

    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls is None and isinstance(message, dict):
        tool_calls = message.get("tool_calls")
    if not tool_calls:
        return ()

    choices = [_parse_tool_call(tool_call) for tool_call in tool_calls]
    return tuple(choice for choice in choices if choice is not None)


def validate_memory_tool_choices(
    query: str,
    model: str,
    choices: tuple[MemoryToolChoice, ...],
) -> MemoryToolProbeResult:
    """Validate that the model chose exactly one allowed memory tool."""
    if len(choices) != 1:
        return MemoryToolProbeResult(
            query=query,
            model=model,
            valid=False,
            tool_choice=None,
            issue=f"expected exactly 1 tool call, got {len(choices)}",
        )

    choice = choices[0]
    if choice.name not in ALLOWED_TOOL_NAMES:
        return MemoryToolProbeResult(
            query=query,
            model=model,
            valid=False,
            tool_choice=choice,
            issue=f"disallowed tool: {choice.name}",
        )

    required_arguments = REQUIRED_ARGUMENTS_BY_TOOL[choice.name]
    missing_arguments = sorted(
        argument for argument in required_arguments if argument not in choice.arguments
    )
    if missing_arguments:
        return MemoryToolProbeResult(
            query=query,
            model=model,
            valid=False,
            tool_choice=choice,
            issue=f"{choice.name} missing argument(s): {', '.join(missing_arguments)}",
        )

    return MemoryToolProbeResult(
        query=query,
        model=model,
        valid=True,
        tool_choice=choice,
    )


def probe_memory_tool_choice(query: str, model: str = MODEL) -> MemoryToolProbeResult:
    """Ask the local model to choose one read-only memory tool."""
    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": MEMORY_TOOL_SYSTEM},
                {"role": "user", "content": query},
            ],
            tools=list(MEMORY_TOOL_SPECS),
            options={"temperature": 0},
            think=False,
        )
    except Exception as exc:
        return MemoryToolProbeResult(
            query=query,
            model=model,
            valid=False,
            tool_choice=None,
            issue=f"native tool call failed: {exc}",
        )
    choices = parse_memory_tool_choices(response)
    return validate_memory_tool_choices(query, model, choices)


def probe_memory_tool_choice_json_contract(
    query: str,
    model: str = MODEL,
) -> MemoryToolProbeResult:
    """Ask the local model to choose one memory tool using structured JSON."""
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": MEMORY_TOOL_SYSTEM},
            {
                "role": "user",
                "content": (
                    "Return JSON with exactly these fields: tool, arguments.\n"
                    f"User input:\n{query}"
                ),
            },
        ],
        format=MEMORY_TOOL_CHOICE_SCHEMA,
        options={"temperature": 0},
        think=False,
    )
    raw = response.message.content
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return MemoryToolProbeResult(
            query=query,
            model=model,
            valid=False,
            tool_choice=None,
            issue=f"JSON contract parse failed: {exc}",
        )
    choice = MemoryToolChoice(
        name=str(parsed.get("tool", "")),
        arguments=_coerce_arguments(parsed.get("arguments", {})),
    )
    return validate_memory_tool_choices(query, model, (choice,))


def format_probe_result(result: MemoryToolProbeResult) -> str:
    """Format a probe result for terminal output."""
    lines = [
        "Stage 24 memory tool readiness probe",
        f"- model: {result.model}",
        f"- valid: {'yes' if result.valid else 'no'}",
    ]
    if result.tool_choice is not None:
        lines.append(f"- tool: {result.tool_choice.name}")
        if result.tool_choice.arguments:
            lines.append(f"- arguments: {json.dumps(result.tool_choice.arguments, sort_keys=True)}")
    if result.issue:
        lines.append(f"- issue: {result.issue}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe local model memory-tool selection without executing tools.",
    )
    parser.add_argument("query", help="User-style query to test.")
    parser.add_argument("--model", default=MODEL, help="Ollama model to probe.")
    parser.add_argument(
        "--mode",
        choices=("native", "json-contract"),
        default="native",
        help="Probe native Ollama tools or a structured JSON tool-choice contract.",
    )
    args = parser.parse_args()

    if args.mode == "json-contract":
        result = probe_memory_tool_choice_json_contract(args.query, model=args.model)
    else:
        result = probe_memory_tool_choice(args.query, model=args.model)
    print(format_probe_result(result))


if __name__ == "__main__":
    main()

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from memory_tool_probe import (
    MemoryToolChoice,
    format_probe_result,
    parse_memory_tool_choices,
    probe_memory_tool_choice,
    probe_memory_tool_choice_json_contract,
    validate_memory_tool_choices,
)


class MemoryToolProbeTests(TestCase):
    def test_parse_memory_tool_choices_accepts_object_response(self):
        response = SimpleNamespace(
            message=SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(
                        function=SimpleNamespace(
                            name="search_memory",
                            arguments={"query": "Phase 3", "reason": "project context"},
                        )
                    )
                ]
            )
        )

        choices = parse_memory_tool_choices(response)

        self.assertEqual(
            choices,
            (
                MemoryToolChoice(
                    name="search_memory",
                    arguments={"query": "Phase 3", "reason": "project context"},
                ),
            ),
        )

    def test_parse_memory_tool_choices_accepts_dict_response_and_json_arguments(self):
        response = {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "summarize_recent_cogs",
                            "arguments": '{"days": 3, "reason": "recent history"}',
                        }
                    }
                ]
            }
        }

        choices = parse_memory_tool_choices(response)

        self.assertEqual(choices[0].name, "summarize_recent_cogs")
        self.assertEqual(choices[0].arguments["days"], 3)

    def test_validate_memory_tool_choices_requires_exactly_one_tool(self):
        result = validate_memory_tool_choices("hello", "model", ())

        self.assertFalse(result.valid)
        self.assertEqual(result.issue, "expected exactly 1 tool call, got 0")

    def test_validate_memory_tool_choices_rejects_disallowed_tool(self):
        result = validate_memory_tool_choices(
            "hello",
            "model",
            (MemoryToolChoice(name="write_to_vault", arguments={}),),
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.issue, "disallowed tool: write_to_vault")

    def test_validate_memory_tool_choices_rejects_missing_required_arguments(self):
        result = validate_memory_tool_choices(
            "Find Phase 3",
            "model",
            (MemoryToolChoice(name="search_memory", arguments={"query": "Phase 3"}),),
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.issue, "search_memory missing argument(s): reason")

    def test_validate_memory_tool_choices_accepts_allowed_tool(self):
        result = validate_memory_tool_choices(
            "Find Phase 3 memory",
            "model",
            (
                MemoryToolChoice(
                    name="search_memory",
                    arguments={"query": "Phase 3 memory", "reason": "related project"},
                ),
            ),
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.tool_choice.name, "search_memory")

    @patch("memory_tool_probe.ollama.chat")
    def test_probe_memory_tool_choice_calls_ollama_with_read_only_tools(self, mock_chat):
        mock_chat.return_value = {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "no_memory_tool",
                            "arguments": {"reason": "no lookup needed"},
                        }
                    }
                ]
            }
        }

        result = probe_memory_tool_choice("Set a timer", model="test-model")

        self.assertTrue(result.valid)
        self.assertEqual(result.tool_choice.name, "no_memory_tool")
        kwargs = mock_chat.call_args.kwargs
        self.assertEqual(kwargs["model"], "test-model")
        self.assertEqual(kwargs["options"], {"temperature": 0})
        self.assertFalse(kwargs["think"])
        tool_names = {tool["function"]["name"] for tool in kwargs["tools"]}
        self.assertEqual(
            tool_names,
            {"search_memory", "get_memory_node", "summarize_recent_cogs", "no_memory_tool"},
        )

    @patch("memory_tool_probe.ollama.chat")
    def test_probe_memory_tool_choice_reports_native_tool_failure(self, mock_chat):
        mock_chat.side_effect = RuntimeError("model does not support tools")

        result = probe_memory_tool_choice("Find memory", model="test-model")

        self.assertFalse(result.valid)
        self.assertIn("native tool call failed", result.issue)
        self.assertIn("model does not support tools", result.issue)

    @patch("memory_tool_probe.ollama.chat")
    def test_probe_memory_tool_choice_json_contract_uses_structured_format(self, mock_chat):
        mock_chat.return_value.message.content = (
            '{"tool": "search_memory", '
            '"arguments": {"query": "Phase 3", "reason": "project context"}}'
        )

        result = probe_memory_tool_choice_json_contract("Find Phase 3", model="test-model")

        self.assertTrue(result.valid)
        self.assertEqual(result.tool_choice.name, "search_memory")
        kwargs = mock_chat.call_args.kwargs
        self.assertEqual(kwargs["model"], "test-model")
        self.assertIn("format", kwargs)
        self.assertNotIn("tools", kwargs)

    def test_format_probe_result_reports_tool_and_arguments(self):
        output = format_probe_result(
            validate_memory_tool_choices(
                "Find Phase 3",
                "model",
                (
                    MemoryToolChoice(
                        name="search_memory",
                        arguments={"query": "Phase 3", "reason": "project context"},
                    ),
                ),
            )
        )

        self.assertIn("Stage 24 memory tool readiness probe", output)
        self.assertIn("- valid: yes", output)
        self.assertIn("- tool: search_memory", output)
        self.assertIn('"query": "Phase 3"', output)

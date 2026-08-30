"""Stage 145: the Anthropic measurement client.

Every test uses a fake SDK client. The suite must never cost money, and a test
that needs the network is a test that gets skipped and then rots.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from specialists.rosie.extractor_classifier import ModelOutputError
from specialists.uniblab.cloud_client import (
    MAX_TOKENS,
    TOOL_NAME,
    AnthropicChatClient,
    is_cloud_model,
    load_api_key,
    split_system,
)

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array"}},
    "required": ["items"],
}


def _block(**kwargs):
    return SimpleNamespace(**kwargs)


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)


def _tool_response(payload, stop_reason="tool_use", output_tokens=42):
    return SimpleNamespace(
        content=[_block(type="tool_use", name=TOOL_NAME, input=payload)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=1234, output_tokens=output_tokens),
    )


class SplitSystemTests(unittest.TestCase):
    def test_system_is_lifted_out_and_turns_start_with_user(self):
        system, turns = split_system([
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "ok"},
        ])

        self.assertEqual(system, "be terse")
        self.assertEqual([m["role"] for m in turns], ["user", "assistant"])

    def test_multiple_system_messages_join(self):
        system, turns = split_system([
            {"role": "system", "content": "one"},
            {"role": "system", "content": "two"},
            {"role": "user", "content": "hi"},
        ])

        self.assertEqual(system, "one\n\ntwo")
        self.assertEqual(len(turns), 1)


class RequestShapeTests(unittest.TestCase):
    def test_schema_becomes_a_forced_tool_call(self):
        fake = FakeClient(_tool_response({"items": []}))
        client = AnthropicChatClient(client=fake)

        client(
            model="claude-haiku-4-5-20251001",
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "go"},
            ],
            format=SCHEMA,
            options={"temperature": 0.1},
        )

        sent = fake.messages.calls[0]
        self.assertEqual(sent["tool_choice"], {"type": "tool", "name": TOOL_NAME})
        self.assertEqual(sent["tools"][0]["input_schema"], SCHEMA)
        self.assertEqual(sent["system"], "sys")
        self.assertEqual(sent["max_tokens"], MAX_TOKENS)
        # anthropic 1.2.0 has no temperature parameter, so it must not be sent.
        # The cloud arms therefore run at the provider default - a recorded
        # confound against the local arms' 0.1.
        self.assertNotIn("temperature", sent)
        self.assertNotIn("system", [m["role"] for m in sent["messages"]])

    def test_no_schema_sends_no_tools(self):
        fake = FakeClient(SimpleNamespace(
            content=[_block(type="text", text="plain")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=5, output_tokens=2),
        ))

        result = AnthropicChatClient(client=fake)(
            model="claude-sonnet-5",
            messages=[{"role": "user", "content": "hi"}],
        )

        self.assertNotIn("tools", fake.messages.calls[0])
        self.assertEqual(result.message.content, "plain")


class ResponseShapeTests(unittest.TestCase):
    """`_call_stats` reads these attributes off the response, so the shape is
    part of the contract even though nothing declares it."""

    def test_tool_input_is_returned_as_json_text(self):
        payload = {"items": [{"raw": "Call Tom", "type_hint": "task"}]}
        client = AnthropicChatClient(client=FakeClient(_tool_response(payload)))

        result = client(model="claude-sonnet-5", messages=[], format=SCHEMA)

        self.assertEqual(json.loads(result.message.content), payload)

    def test_token_counts_map_and_durations_stay_absent(self):
        client = AnthropicChatClient(client=FakeClient(_tool_response({"items": []})))

        result = client(model="claude-sonnet-5", messages=[], format=SCHEMA)

        self.assertEqual(result.prompt_eval_count, 1234)
        self.assertEqual(result.eval_count, 42)
        # Cloud latency is network time; reporting it beside local prefill and
        # decode would invite a comparison that is not valid.
        for field in ("total_duration", "load_duration", "eval_duration"):
            self.assertFalse(hasattr(result, field), field)


class FailureTests(unittest.TestCase):
    def test_hitting_the_token_cap_raises_rather_than_scoring_zero(self):
        """Finding 73: a truncated generation that returns cleanly is a silent
        total loss. It must surface as an error on this path too."""

        response = _tool_response({"items": []}, stop_reason="max_tokens")
        client = AnthropicChatClient(client=FakeClient(response))

        with self.assertRaises(ModelOutputError):
            client(model="claude-sonnet-5", messages=[], format=SCHEMA)

    def test_a_text_reply_when_a_tool_was_required_raises(self):
        response = SimpleNamespace(
            content=[_block(type="text", text="I'd rather not")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )
        client = AnthropicChatClient(client=FakeClient(response))

        with self.assertRaises(ModelOutputError):
            client(model="claude-sonnet-5", messages=[], format=SCHEMA)


class KeyLoadingTests(unittest.TestCase):
    def test_env_file_is_read_and_quotes_stripped(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "env"
            path.write_text('# comment\nOTHER=x\nANTHROPIC_API_KEY="sk-ant-test"\n')

            self.assertEqual(load_api_key(path), "sk-ant-test")

    def test_missing_key_raises_rather_than_returning_empty(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "env"
            path.write_text("OTHER=x\n")
            import os

            os.environ.pop("ANTHROPIC_API_KEY", None)
            with self.assertRaises(RuntimeError):
                load_api_key(path)


class RoutingTests(unittest.TestCase):
    def test_claude_models_route_to_the_cloud_and_others_do_not(self):
        self.assertTrue(is_cloud_model("claude-sonnet-5"))
        self.assertTrue(is_cloud_model("claude-haiku-4-5-20251001"))
        self.assertFalse(is_cloud_model("gemma4:12b-16k-cosmo"))


if __name__ == "__main__":
    unittest.main()

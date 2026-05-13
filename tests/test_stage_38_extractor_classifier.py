import importlib
import json
import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import extractor_classifier as ec
import agentic_loop


def _response(payload):
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


class FakeChat:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return _response(self.payload)


class Stage38ExtractorClassifierTests(unittest.TestCase):
    def test_capture_model_defaults_to_project_model(self):
        original_env = os.environ.copy()
        try:
            os.environ.pop("SPROCKETS_COGS_EXTRACTOR_MODEL", None)
            os.environ.pop("SPROCKETS_COGS_MODEL", None)
            reloaded = importlib.reload(ec)

            self.assertEqual(reloaded.CAPTURE_MODEL, "qwen3.5:9b-32k-cosmo")
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(ec)

    def test_capture_model_prefers_role_specific_env(self):
        original_env = os.environ.copy()
        try:
            with patch.dict(
                os.environ,
                {
                    "SPROCKETS_COGS_MODEL": "general-model",
                    "SPROCKETS_COGS_EXTRACTOR_MODEL": "extractor-model",
                },
                clear=False,
            ):
                reloaded = importlib.reload(ec)

            self.assertEqual(reloaded.CAPTURE_MODEL, "extractor-model")
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(ec)

    def test_capture_model_falls_back_to_general_model_env(self):
        original_env = os.environ.copy()
        try:
            os.environ.pop("SPROCKETS_COGS_EXTRACTOR_MODEL", None)
            os.environ["SPROCKETS_COGS_MODEL"] = "general-model"
            reloaded = importlib.reload(ec)

            self.assertEqual(reloaded.CAPTURE_MODEL, "general-model")
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(ec)

    def test_extract_nodes_calls_ollama_shape_without_live_model(self):
        chat = FakeChat({"items": [{"raw": "Call Alex", "type_hint": "task"}]})
        classifier = ec.ExtractClassifier(
            ec.ExtractClassifierConfig(model="test-model", temperature=0.2),
            chat_client=chat,
        )

        items = classifier.extract_nodes(
            "Call Alex",
            now=datetime(2026, 5, 12, 9, 0),
        )

        self.assertEqual(items, [{"raw": "Call Alex", "type_hint": "task"}])
        self.assertEqual(len(chat.calls), 1)
        call = chat.calls[0]
        self.assertEqual(call["model"], "test-model")
        self.assertEqual(call["format"], ec.EXTRACT_SCHEMA)
        self.assertEqual(call["options"], {"temperature": 0.2})
        self.assertFalse(call["think"])
        self.assertIn("This week's workdays: Mon 2026-05-11", call["messages"][-1]["content"])

    def test_extract_nodes_returns_empty_on_invalid_json(self):
        chat = FakeChat({})
        chat.payload = None

        def bad_chat(**kwargs):
            return SimpleNamespace(message=SimpleNamespace(content="{not json"))

        classifier = ec.ExtractClassifier(chat_client=bad_chat)

        self.assertEqual(classifier.extract_nodes("bad"), [])

    def test_classify_nodes_calls_ollama_shape_without_live_model(self):
        chat = FakeChat({
            "nodes": [
                {
                    "node_type": "cogs/daily",
                    "item_text": "Call Alex",
                    "date": "2026-05-12",
                    "confidence": "high",
                }
            ]
        })
        classifier = ec.ExtractClassifier(
            ec.ExtractClassifierConfig(model="test-model"),
            chat_client=chat,
        )

        nodes = classifier.classify_nodes(
            [{"raw": "Call Alex", "type_hint": "task"}],
            "Already in today's note: (none)",
            now=datetime(2026, 5, 12, 9, 0),
        )

        self.assertEqual(nodes[0]["node_type"], "cogs/daily")
        call = chat.calls[0]
        self.assertEqual(call["model"], "test-model")
        self.assertEqual(call["format"], ec.CLASSIFY_SCHEMA)
        self.assertIn("Today: 2026-05-12 (Tuesday)", call["messages"][-1]["content"])
        self.assertIn("Classify each item.", call["messages"][-1]["content"])

    def test_classify_nodes_can_omit_examples_for_retry_shape(self):
        chat = FakeChat({"nodes": []})
        classifier = ec.ExtractClassifier(chat_client=chat)

        classifier.classify_nodes(
            [{"raw": "Call Alex"}],
            "context",
            error_context="fix date",
            use_examples=False,
            now=datetime(2026, 5, 12),
        )

        messages = chat.calls[0]["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(len(messages), 2)
        self.assertIn("Fix these issues", messages[-1]["content"])

    def test_classify_nodes_returns_empty_for_no_raw_nodes(self):
        classifier = ec.ExtractClassifier(chat_client=FakeChat({"nodes": []}))

        self.assertEqual(classifier.classify_nodes([], "context"), [])

    def test_truncate_context_marks_long_context(self):
        context = "x" * 2005

        truncated = ec.truncate_context(context, max_chars=10)

        self.assertEqual(truncated, "x" * 10 + "\n[... truncated]")

    def test_agentic_loop_extract_nodes_delegates_to_facade_with_existing_model(self):
        calls = []

        class FakeExtractorClassifier:
            def __init__(self, config):
                calls.append(("init", config.model))

            def extract_nodes(self, content):
                calls.append(("extract", content))
                return [{"raw": "Call Alex"}]

        with patch.object(agentic_loop, "MODEL", "loop-model"):
            with patch.object(agentic_loop, "ExtractClassifier", FakeExtractorClassifier):
                items = agentic_loop.extract_nodes("Call Alex")

        self.assertEqual(items, [{"raw": "Call Alex"}])
        self.assertEqual(calls, [("init", "loop-model"), ("extract", "Call Alex")])

    def test_agentic_loop_classify_nodes_delegates_to_facade_with_retry_shape(self):
        calls = []

        class FakeExtractorClassifier:
            def __init__(self, config):
                calls.append(("init", config.model))

            def classify_nodes(self, raw_nodes, context, error_context="", use_examples=True):
                calls.append((raw_nodes, context, error_context, use_examples))
                return [{"node_type": "cogs/daily"}]

        raw_nodes = [{"raw": "Call Alex"}]
        with patch.object(agentic_loop, "MODEL", "loop-model"):
            with patch.object(agentic_loop, "ExtractClassifier", FakeExtractorClassifier):
                nodes = agentic_loop.classify_nodes(
                    raw_nodes,
                    "context",
                    error_context="fix it",
                    use_examples=False,
                )

        self.assertEqual(nodes, [{"node_type": "cogs/daily"}])
        self.assertEqual(
            calls,
            [
                ("init", "loop-model"),
                (raw_nodes, "context", "fix it", False),
            ],
        )


if __name__ == "__main__":
    unittest.main()

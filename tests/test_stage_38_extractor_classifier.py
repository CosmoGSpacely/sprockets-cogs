import importlib
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import specialists.rosie.extractor_classifier as ec
import specialists.rosie.loop as agentic_loop
import specialists.rosie.capture_preview as capture_preview


def _response(payload):
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


class FakeChat:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return _response(self.payload)


class FakePreviewClassifier:
    def __init__(self):
        self.calls = []

    def extract_nodes(self, content):
        self.calls.append(("extract", content))
        return [{"raw": "Call Alex", "type_hint": "task"}]

    def classify_nodes(self, raw_nodes, context):
        self.calls.append(("classify", raw_nodes, context))
        return [
            {
                "node_type": "cogs/daily",
                "item_text": "Call Alex",
                "confidence": "high",
            }
        ]


class Stage38ExtractorClassifierTests(unittest.TestCase):
    def test_capture_model_defaults_to_project_model(self):
        original_env = os.environ.copy()
        try:
            os.environ.pop("SPROCKETS_COGS_EXTRACTOR_MODEL", None)
            os.environ.pop("SPROCKETS_COGS_MODEL", None)
            reloaded = importlib.reload(ec)

            self.assertEqual(reloaded.CAPTURE_MODEL, "gemma4:12b-16k-cosmo")
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

    def test_extract_nodes_raises_on_invalid_json(self):
        """Was `returns_empty_on_invalid_json`, asserting the defect.

        Stage 142 finding 73: returning `[]` for an unreadable reply made a
        truncated capture indistinguishable from one that genuinely contained
        no items, so the input was consumed, wrote nothing, and reported
        success. D104 changed it to raise, which leaves the file in
        `processing/` with a failure record.
        """

        def bad_chat(**kwargs):
            return SimpleNamespace(message=SimpleNamespace(content="{not json"))

        classifier = ec.ExtractClassifier(chat_client=bad_chat)

        with self.assertRaises(ec.ModelOutputError):
            classifier.extract_nodes("bad")

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
        """A single oversize line still yields content, not just the marker.

        Stage 142 slice 7 moved bounding to line granularity. One line longer
        than the entire budget is the case where that would drop everything,
        so it falls back to a character cut.
        """

        context = "x" * 2005

        truncated = ec.truncate_context(context, max_chars=100)

        self.assertTrue(truncated.startswith("x" * 80))
        self.assertTrue(truncated.endswith(ec.TRUNCATION_MARKER))
        self.assertLessEqual(len(truncated), 100)

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

    def test_capture_preview_runs_read_only_extract_and_classify(self):
        classifier = FakePreviewClassifier()

        preview = capture_preview.run_capture_preview(
            "Call Alex",
            model="preview-model",
            context="Existing context",
            classifier=classifier,
        )

        self.assertEqual(preview.model, "preview-model")
        self.assertEqual(preview.context_chars, len("Existing context"))
        self.assertEqual(preview.raw_nodes[0]["raw"], "Call Alex")
        self.assertEqual(preview.classified_nodes[0]["node_type"], "cogs/daily")
        self.assertEqual(
            classifier.calls,
            [
                ("extract", "Call Alex"),
                ("classify", [{"raw": "Call Alex", "type_hint": "task"}], "Existing context"),
            ],
        )

    def test_capture_preview_can_skip_classification(self):
        classifier = FakePreviewClassifier()

        preview = capture_preview.run_capture_preview(
            "Call Alex",
            classify=False,
            context="Existing context",
            classifier=classifier,
        )

        self.assertFalse(preview.classified)
        self.assertEqual(preview.classified_nodes, [])
        self.assertEqual(classifier.calls, [("extract", "Call Alex")])

    def test_format_capture_preview_reports_no_writes(self):
        preview = capture_preview.CapturePreview(
            content="Call Alex",
            model="preview-model",
            raw_nodes=[{"raw": "Call Alex"}],
            classified_nodes=[
                {
                    "node_type": "cogs/daily",
                    "item_text": "Call Alex",
                    "confidence": "high",
                }
            ],
            classified=True,
            context_chars=7,
        )

        output = capture_preview.format_capture_preview(preview)

        self.assertIn("Capture preview", output)
        self.assertIn("- writes: none", output)
        self.assertIn("1. Call Alex", output)
        self.assertIn("1. [cogs/daily] Call Alex (high)", output)

    def test_capture_preview_json_payload_is_machine_readable(self):
        preview = capture_preview.CapturePreview(
            content="Call Alex",
            model="preview-model",
            raw_nodes=[{"raw": "Call Alex"}],
            classified_nodes=[],
            classified=False,
            context_chars=0,
        )

        payload = json.loads(capture_preview.capture_preview_to_json(preview))

        self.assertEqual(payload["writes"], "none")
        self.assertEqual(payload["model"], "preview-model")
        self.assertFalse(payload["classified"])

    def test_capture_preview_main_prints_read_only_preview(self):
        classifier = FakePreviewClassifier()

        def fake_classifier(config):
            self.assertEqual(config.model, "preview-model")
            return classifier

        buf = io.StringIO()
        with patch.object(capture_preview, "ExtractClassifier", fake_classifier):
            with patch.object(capture_preview, "build_context", return_value="context"):
                with redirect_stdout(buf):
                    capture_preview.main(["--model", "preview-model", "Call", "Alex"])

        output = buf.getvalue()
        self.assertIn("Capture preview", output)
        self.assertIn("- writes: none", output)
        self.assertIn("classified nodes: 1", output)


class ContextBoundingTests(unittest.TestCase):
    """Stage 142 slice 7. The hierarchy parent list is the one context section
    the classify prompt forbids the model to work around, and it is last - so
    head-truncation deleted exactly it (finding 87)."""

    CONTEXT = (
        "Already in today's note:\n"
        + "".join(f"- Item number {i} (cogs/daily, 2026-06-12)\n" for i in range(20))
        + "Known hierarchy parents: General, Farm, Vehicle Maintenance, Home Network"
    )

    def test_parent_list_survives_a_binding_cap(self):
        bounded = ec.truncate_context(self.CONTEXT, max_chars=400)

        self.assertIn("Vehicle Maintenance", bounded)
        self.assertIn("Known hierarchy parents:", bounded)
        self.assertLessEqual(len(bounded), 400)

    def test_recent_notes_are_what_gets_dropped(self):
        bounded = ec.truncate_context(self.CONTEXT, max_chars=400)

        self.assertIn("Item number 0", bounded)
        self.assertNotIn("Item number 19", bounded)
        self.assertIn(ec.TRUNCATION_MARKER, bounded)

    def test_lines_are_dropped_whole(self):
        """Never a mid-word cut. Finding 88: a visibly partial parent list
        suppresses parent_hint even when the needed name survives."""

        bounded = ec.truncate_context(self.CONTEXT, max_chars=400)

        for line in bounded.splitlines():
            if line.startswith("- Item number"):
                self.assertTrue(line.endswith("2026-06-12)"), line)

    def test_unbounded_context_is_returned_unchanged(self):
        self.assertEqual(ec.truncate_context(self.CONTEXT, max_chars=5000), self.CONTEXT)

    def test_priority_line_too_large_falls_back_without_losing_everything(self):
        bounded = ec.truncate_context(self.CONTEXT, max_chars=120)

        self.assertIn("Already in today's note:", bounded)
        self.assertLessEqual(len(bounded), 120)


class CaptureBudgetTests(unittest.TestCase):
    """Stage 142 slice 7 / D10. The capture is bounded by detection, never by
    truncation - cutting the user's own words is a silent total loss."""

    def test_ordinary_capture_is_within_budget(self):
        self.assertFalse(ec.capture_exceeds_budget("Dentist Monday at 8am"))

    def test_photographed_list_sized_capture_is_flagged(self):
        self.assertTrue(ec.capture_exceeds_budget("x" * (ec.CAPTURE_BUDGET_CHARS + 1)))

    def test_oversize_capture_is_still_sent_whole(self):
        """The guard warns; it does not truncate and does not refuse."""

        content = "y" * (ec.CAPTURE_BUDGET_CHARS + 500)

        messages = ec.build_extract_messages(content, datetime(2026, 6, 12, 9, 0))

        self.assertIn(content, messages[-1]["content"])


if __name__ == "__main__":
    unittest.main()

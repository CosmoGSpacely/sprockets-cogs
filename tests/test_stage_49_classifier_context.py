import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import specialists.rosie.loop as agentic_loop
import specialists.rosie.capture_preview as capture_preview
import specialists.rosie.classifier_context as classifier_context
import specialists.rudi.production_retrieval as production_retrieval


class FakeCaptureClassifier:
    def __init__(self) -> None:
        self.calls = []

    def extract_nodes(self, content):
        self.calls.append(("extract", content))
        return [{"raw": content, "type_hint": "task"}]

    def classify_nodes(self, raw_nodes, context):
        self.calls.append(("classify", raw_nodes, context))
        return [{"node_type": "sprockets/task", "title": "Call Alex"}]


class Stage49ClassifierContextTests(unittest.TestCase):
    def test_base_context_includes_daily_items_entities_and_hierarchy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            today = datetime.now().strftime("%a %d %b %Y")
            (daily_dir / f"{today}.md").write_text(
                "- [ ] Call Alex\n"
                "Plain journal text should stay out.\n"
                "- [x] Finish review\n"
            )

            hot_entities = [
                {"node_type": "sprockets/contact", "title": "Alex Rivera"},
                {"node_type": "sprockets/entity", "title": "GlobalTech"},
            ]

            with patch.object(agentic_loop, "DAILY_DIR", daily_dir):
                with patch.object(
                    agentic_loop,
                    "get_entities_by_tier",
                    return_value=hot_entities,
                ):
                    with patch.object(
                        agentic_loop,
                        "_build_hierarchy_context",
                        return_value=[
                            "Project: Phase 3 - Memory Enhancement",
                        ],
                    ):
                        context = agentic_loop.build_context()

        self.assertIn("Already in today's note: Call Alex; Finish review", context)
        self.assertIn("Known contacts: Alex Rivera", context)
        self.assertIn("Known entities: GlobalTech", context)
        self.assertIn("Known hierarchy parent targets:", context)
        self.assertIn("Project: Phase 3 - Memory Enhancement", context)
        self.assertNotIn("Plain journal text", context)

    def test_context_for_input_returns_base_when_memory_context_is_empty(self) -> None:
        with patch.dict(
            os.environ,
            {production_retrieval.MEMORY_CONTEXT_ENV: "1"},
            clear=True,
        ):
            with patch.object(agentic_loop, "build_context", return_value="Base context"):
                with patch.object(agentic_loop, "retrieve_relevant_nodes", return_value=[]) as mock_retrieve:
                    context = agentic_loop.build_context_for_input("Find memory")

        self.assertEqual(context, "Base context")
        mock_retrieve.assert_called_once_with("Find memory")

    def test_capture_preview_uses_base_context_builder_when_not_injected(self) -> None:
        classifier = FakeCaptureClassifier()

        with patch.object(capture_preview, "build_context", return_value="Base context"):
            preview = capture_preview.run_capture_preview(
                "Call Alex",
                classifier=classifier,
            )

        self.assertEqual(preview.context_chars, len("Base context"))
        self.assertEqual(
            classifier.calls,
            [
                ("extract", "Call Alex"),
                ("classify", [{"raw": "Call Alex", "type_hint": "task"}], "Base context"),
            ],
        )

    def test_capture_preview_context_builder_uses_context_module_seam(self) -> None:
        self.assertIs(capture_preview.build_context, classifier_context.build_default_context)


if __name__ == "__main__":
    unittest.main()

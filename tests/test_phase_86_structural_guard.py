import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agentic_loop


class Phase86StructuralGuardTests(unittest.TestCase):
    def test_structural_guard_is_enabled_by_default_and_can_be_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(agentic_loop.structural_guard_enabled())

        with patch.dict(os.environ, {agentic_loop.STRUCTURAL_GUARD_ENV: "0"}, clear=True):
            self.assertFalse(agentic_loop.structural_guard_enabled())

    def test_structural_guard_builds_review_proposal_packet(self):
        raw_nodes = [{"raw": "Area: Farm. Goal: Fix tractor.", "type_hint": "task"}]
        classified = [
            {
                "node_type": "sprockets/task",
                "title": "Fix tractor",
                "confidence": "high",
            }
        ]
        written = []

        with patch.object(agentic_loop, "write_to_review", side_effect=lambda raw, reason: written.append((raw, reason))):
            remaining, routed = agentic_loop.route_structural_guard_to_review(
                "Area: Farm. Goal: Fix tractor.",
                raw_nodes,
                classified,
                "session-1",
            )

        self.assertTrue(routed)
        self.assertEqual(remaining, [])
        self.assertEqual(len(written), 1)
        proposal, reason = written[0]
        self.assertIn("structural_guard_packet_required", reason)
        self.assertEqual(proposal["kind"], "review_proposal")
        self.assertEqual(proposal["mutation_command"]["review_class"], "review_first")
        self.assertEqual(proposal["mutation_command"]["payload"]["guard"], "deterministic_packet_required")
        self.assertIn("intent", proposal["mutation_command"]["payload"])

    def test_process_input_routes_structural_language_to_review_without_writing_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            processing_dir = root / "processing"
            archive_dir = root / "archive"
            output_dir = root / "output"
            review_dir = root / "review"
            daily_dir = root / "daily"
            input_dir.mkdir()
            input_path = input_dir / "structural.input"
            input_path.write_text(
                "---\nsession_id: structural-test\n---\n\n"
                "Area: Farm. Goal: Fix tractor. Task: Remount front tires.\n"
            )

            raw_nodes = [
                {
                    "raw": "Area: Farm. Goal: Fix tractor. Task: Remount front tires.",
                    "type_hint": "task",
                }
            ]
            classified = [
                {
                    "node_type": "sprockets/task",
                    "title": "Remount front tires",
                    "confidence": "high",
                }
            ]

            with patch.object(agentic_loop, "INPUT_DIR", input_dir), \
                 patch.object(agentic_loop, "PROCESSING_DIR", processing_dir), \
                 patch.object(agentic_loop, "ARCHIVE_DIR", archive_dir), \
                 patch.object(agentic_loop, "OUTPUT_DIR", output_dir), \
                 patch.object(agentic_loop, "REVIEW_DIR", review_dir), \
                 patch.object(agentic_loop, "DAILY_DIR", daily_dir), \
                 patch.object(agentic_loop, "build_context_for_input", return_value=""), \
                 patch.object(agentic_loop, "extract_nodes", return_value=raw_nodes), \
                 patch.object(agentic_loop, "classify_nodes", return_value=classified), \
                 patch.object(agentic_loop, "write_node") as write_node:
                agentic_loop.ensure_runtime_dirs()
                agentic_loop.process_input(input_path)

            write_node.assert_not_called()
            self.assertTrue((archive_dir / "structural.input").exists())
            review_files = list(review_dir.glob("*.md"))
            self.assertEqual(len(review_files), 1)
            review_text = review_files[0].read_text()
            self.assertIn("structural_guard_packet_required", review_text)
            self.assertIn('"kind": "review_proposal"', review_text)
            self.assertIn('"operation": "create_sprocket_and_bridge"', review_text)
            self.assertIn('"direct_write_allowed": false', review_text)

            daily_files = list(daily_dir.glob("*.md"))
            self.assertEqual(len(daily_files), 1)
            self.assertIn("Processed 0 node(s)", daily_files[0].read_text())

    def test_structural_guard_allows_ordinary_capture(self):
        classified = [
            {
                "node_type": "cogs/daily",
                "item_text": "Call Tom",
                "date": "2026-06-10",
                "confidence": "high",
            }
        ]

        with patch.object(agentic_loop, "write_to_review") as write_to_review:
            remaining, routed = agentic_loop.route_structural_guard_to_review(
                "Call Tom",
                [{"raw": "Call Tom", "type_hint": "task"}],
                classified,
                "session-2",
            )

        self.assertFalse(routed)
        self.assertEqual(remaining, classified)
        write_to_review.assert_not_called()


if __name__ == "__main__":
    unittest.main()

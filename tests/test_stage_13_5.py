import json
import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agentic_loop
import entity_state
import review
from models import validate_node


class Stage135HardeningTests(unittest.TestCase):
    def test_agentic_loop_paths_can_be_configured_from_environment(self):
        original_env = os.environ.copy()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                os.environ["SPROCKETS_COGS_SC_ROOT"] = str(root / "sc")
                os.environ["SPROCKETS_COGS_VAULT_DIR"] = str(root / "vault")
                reloaded = importlib.reload(agentic_loop)

                self.assertEqual(reloaded.INPUT_DIR, root / "sc" / "input")
                self.assertEqual(reloaded.PROCESSING_DIR, root / "sc" / "processing")
                self.assertEqual(reloaded.ARCHIVE_DIR, root / "sc" / "archive")
                self.assertEqual(reloaded.OUTPUT_DIR, root / "sc" / "output")
                self.assertEqual(reloaded.VAULT_DIR, root / "vault")
                self.assertEqual(reloaded.DAILY_DIR, root / "vault" / "Cogs" / "daily")
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(agentic_loop)

    def test_entity_state_path_can_be_configured_from_environment(self):
        original_env = os.environ.copy()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                state_path = Path(tmp) / "state.json"
                os.environ["SPROCKETS_COGS_ENTITY_STATE_PATH"] = str(state_path)
                reloaded = importlib.reload(entity_state)

                self.assertEqual(reloaded.STATE_PATH, state_path)
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(entity_state)

    def test_process_existing_inputs_processes_sorted_input_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp)
            (input_dir / "b.input").write_text("b")
            (input_dir / "a.input").write_text("a")
            (input_dir / "ignore.txt").write_text("nope")

            processed = []

            def fake_process(path):
                processed.append(path.name)

            with patch.object(agentic_loop, "process_input", side_effect=fake_process):
                count = agentic_loop.process_existing_inputs(input_dir)

            self.assertEqual(count, 2)
            self.assertEqual(processed, ["a.input", "b.input"])

    def test_ensure_runtime_dirs_creates_operational_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {
                "INPUT_DIR": root / "input",
                "PROCESSING_DIR": root / "processing",
                "ARCHIVE_DIR": root / "archive",
                "OUTPUT_DIR": root / "output",
            }

            patches = [
                patch.object(agentic_loop, name, path)
                for name, path in paths.items()
            ]
            for active_patch in patches:
                active_patch.start()
            try:
                agentic_loop.ensure_runtime_dirs()
            finally:
                for active_patch in reversed(patches):
                    active_patch.stop()

            for path in paths.values():
                self.assertTrue(path.is_dir())

    def test_validate_output_separates_valid_low_confidence_and_invalid(self):
        raw_nodes = [
            {
                "node_type": "cogs/daily",
                "item_text": "DENTIST 8am",
                "date": "2026-05-02",
                "confidence": "high",
            },
            {
                "node_type": "sprockets/contact",
                "title": "Jordan Mack",
                "confidence": "low",
            },
            {
                "node_type": "unknown/type",
                "title": "Mystery",
                "confidence": "high",
            },
        ]

        valid, invalid = agentic_loop.validate_output(raw_nodes)

        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0].node_type, "cogs/daily")
        self.assertEqual(len(invalid), 2)
        self.assertEqual(invalid[0][2], "confidence: low")
        self.assertIn("Unknown node_type", invalid[1][2])

    def test_ensure_cogs_companions_adds_missing_daily_for_task(self):
        classified = [
            {
                "node_type": "sprockets/task",
                "title": "Send proposal to Jordan",
                "date": "2026-05-04",
                "status": "active",
                "confidence": "high",
            }
        ]

        result = agentic_loop.ensure_cogs_companions(classified)

        self.assertEqual(len(result), 2)
        companion = result[1]
        self.assertEqual(companion["node_type"], "cogs/daily")
        self.assertEqual(companion["item_text"], "Send proposal to Jordan")
        self.assertEqual(companion["date"], "2026-05-04")

    def test_find_duplicate_uses_fuzzy_slug_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "call-frank.md").write_text("---\n---\n")

            duplicate = agentic_loop._find_duplicate("Call Frank!", folder)

            self.assertIsNotNone(duplicate)
            self.assertEqual(duplicate.name, "call-frank.md")

    def test_write_to_review_writes_reason_and_raw_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            raw = {
                "node_type": "sprockets/task",
                "title": "Ambiguous task",
                "confidence": "low",
            }

            with patch.object(agentic_loop, "REVIEW_DIR", review_dir):
                agentic_loop.write_to_review(raw, "confidence: low")

            files = list(review_dir.glob("*.md"))
            self.assertEqual(len(files), 1)
            content = files[0].read_text()
            self.assertIn("**Reason:** confidence: low", content)
            self.assertIn(json.dumps(raw, indent=2), content)

    def test_list_pending_summarizes_review_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            raw = {
                "node_type": "sprockets/task",
                "title": "Ambiguous task",
                "item_text": "Ambiguous task",
                "date": "2026-05-02",
                "confidence": "low",
            }
            (review_dir / "pending.md").write_text(
                "---\nnode_type: review\nreviewed: false\n---\n\n"
                "**Reason:** confidence: low\n\n"
                f"```json\n{json.dumps(raw, indent=2)}\n```\n"
            )

            items = review.list_pending(review_dir)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["file"], "pending.md")
            self.assertEqual(items[0]["reason"], "confidence: low")
            self.assertEqual(items[0]["node_type"], "sprockets/task")
            self.assertEqual(items[0]["title"], "Ambiguous task")
            self.assertTrue(items[0]["parseable"])

    def test_list_pending_marks_unparseable_review_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            (review_dir / "broken.md").write_text(
                "---\nnode_type: review\nreviewed: false\n---\n\n"
                "**Reason:** retry failed\n\n"
                "```json\nnot json\n```\n"
            )

            items = review.list_pending(review_dir)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["file"], "broken.md")
            self.assertEqual(items[0]["reason"], "retry failed")
            self.assertFalse(items[0]["parseable"])

    def test_entity_state_tracks_hot_contact(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "entity_state.json"
            node = validate_node({
                "node_type": "sprockets/contact",
                "title": "Jordan Mack",
                "confidence": "high",
            })

            with patch.object(entity_state, "STATE_PATH", state_path):
                entity_state.upsert_entity(node)
                hot = entity_state.get_entities_by_tier("hot")

            self.assertEqual(len(hot), 1)
            self.assertEqual(hot[0]["title"], "Jordan Mack")
            self.assertEqual(hot[0]["node_type"], "sprockets/contact")


if __name__ == "__main__":
    unittest.main()

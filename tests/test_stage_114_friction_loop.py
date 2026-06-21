import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from specialists.jane import review
from specialists.rosie import loop
from specialists.uniblab import friction


class Stage114FrictionLoopTests(unittest.TestCase):
    def test_friction_records_group_repeated_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "friction.jsonl"
            friction.append_record(
                source="review-discard",
                pattern="discarded cogs/daily review item: confidence: low",
                evidence="/vault/review/one.md",
                log_path=log,
            )
            friction.append_record(
                source="review-discard",
                pattern="discarded cogs/daily review item: confidence: low",
                evidence="/vault/review/two.md",
                log_path=log,
            )

            records = friction.load_friction_records(log)
            summaries = friction.summarize_records(records)
            output = friction.format_friction_summary(records)

        self.assertEqual(len(records), 2)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].count, 2)
        self.assertIn("confidence: low", output)
        self.assertIn("/vault/review/one.md", output)

    def test_friction_candidate_writes_top_open_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "friction.jsonl"
            candidate_dir = root / "output"
            friction.append_record(
                source="processing-failure",
                pattern="input processing failed: ValueError",
                evidence="/home/cosmo/sc/processing/test.input",
                proposed_fix="test",
                log_path=log,
            )

            path = friction.write_top_candidate(
                friction.load_friction_records(log),
                candidate_dir=candidate_dir,
            )
            text = path.read_text(encoding="utf-8")

            self.assertTrue(path.exists())
            self.assertIn("type: friction-candidate", text)
            self.assertIn("input processing failed: ValueError", text)

    def test_jane_discard_records_friction(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "friction.jsonl"
            review_file = Path(tmp) / "candidate.md"

            record = review.record_review_discard(
                review_file=review_file,
                reason="confidence: low",
                node_type="cogs/daily",
                title="?",
                item_text="Call Tom",
                log_path=log,
            )
            records = friction.load_friction_records(log)

        self.assertEqual(record.source, "review-discard")
        self.assertEqual(records[0].evidence, str(review_file))
        self.assertIn("cogs/daily", records[0].pattern)

    def test_rosie_processing_failure_records_friction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            processing_dir = root / "processing"
            input_dir.mkdir()
            processing_dir.mkdir()
            input_file = input_dir / "bad.input"
            input_file.write_text("not frontmatter but fine", encoding="utf-8")
            log = root / "friction.jsonl"

            with (
                patch.object(loop, "PROCESSING_DIR", processing_dir),
                patch.object(loop, "build_context_for_input", side_effect=ValueError("boom")),
                patch("specialists.rosie.loop.record_processing_failure") as record_failure,
            ):
                loop.process_input(input_file)

            record_failure.assert_called_once()
            call = record_failure.call_args.kwargs

        self.assertEqual(call["input_file"], processing_dir / "bad.input")
        self.assertIsInstance(call["error"], ValueError)


if __name__ == "__main__":
    unittest.main()

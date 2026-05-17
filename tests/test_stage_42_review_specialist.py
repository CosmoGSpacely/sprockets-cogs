import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import review_specialist


class Stage42ReviewSpecialistTests(unittest.TestCase):
    def test_inventory_wraps_existing_review_report_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            _write_review_file(
                review_dir / "task.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/task",
                    "title": "Review specialist task",
                    "item_text": "Review specialist task",
                    "date": "2026-05-17",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )

            inventory = specialist.inventory()

            self.assertEqual(inventory.review_dir, review_dir)
            self.assertEqual(inventory.total, 1)
            self.assertEqual(inventory.parseable, 1)
            self.assertEqual(inventory.by_source["local low confidence"], 1)
            self.assertTrue((review_dir / "task.md").exists())

    def test_packet_preview_delegates_to_existing_packet_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            _write_review_file(
                review_dir / "pending.md",
                reason="openai_fallback_candidate: confidence: low",
                raw={
                    "node_type": "sprockets/note",
                    "title": "Review specialist packet",
                    "confidence": "high",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )

            packet = specialist.packet_preview()

            self.assertIn("# Sprockets-Cogs Review Packet", packet)
            self.assertIn("Review specialist packet", packet)
            self.assertNotIn(str(review_dir), packet)

    def test_format_review_inventory_marks_read_only(self):
        preview = review_specialist.ReviewInventoryPreview(
            review_dir=Path("/vault/review"),
            total=2,
            parseable=1,
            unparseable=1,
            by_source={"local low confidence": 1},
            by_node_type={"sprockets/task": 1},
            by_confidence={"low": 1},
            by_reason={"confidence: low": 1},
        )

        output = review_specialist.format_review_inventory(preview)

        self.assertIn("Review specialist inventory preview", output)
        self.assertIn("- total: 2", output)
        self.assertIn("- writes: no", output)

    def test_main_prints_inventory_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            buf = io.StringIO()

            with redirect_stdout(buf):
                review_specialist.main(["--review-dir", str(review_dir), "--inventory"])

            output = buf.getvalue()
            self.assertIn("Review specialist inventory preview", output)
            self.assertIn("- total: 0", output)
            self.assertIn("- writes: no", output)

    def test_main_prints_packet_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            buf = io.StringIO()

            with redirect_stdout(buf):
                review_specialist.main(["--review-dir", str(review_dir), "--packet-preview"])

            output = buf.getvalue()
            self.assertIn("Review specialist packet preview", output)
            self.assertIn("# Sprockets-Cogs Review Packet", output)
            self.assertIn("- writes: no", output)

    def test_decision_template_lists_pending_files_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            _write_review_file(
                review_dir / "pending.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/task",
                    "title": "Decision template task",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )

            template = specialist.decision_template()

            self.assertIn("# Sprockets-Cogs Review Decision Template", template)
            self.assertIn("| File | Decision | Notes |", template)
            self.assertIn("| pending.md |  |  |", template)
            self.assertTrue((review_dir / "pending.md").exists())

    def test_decision_import_preview_validates_against_current_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            review_dir.mkdir()
            _write_review_file(
                review_dir / "approve-me.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/task",
                    "title": "Approve me",
                    "confidence": "low",
                },
            )
            packet = root / "decisions.md"
            packet.write_text(
                "# Decisions\n\n"
                "| File | Decision | Notes |\n"
                "|---|---|---|\n"
                "| approve-me.md | approve | looks right |\n"
                "| missing.md | discard | stale row |\n"
                "| approve-me.md | nope | bad decision |\n"
                "| approve-me.md |  | not ready |\n"
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )

            preview = specialist.decision_import_preview(packet)

            self.assertEqual(preview.actionable_count, 1)
            self.assertEqual(preview.pending_count, 1)
            self.assertEqual(preview.invalid_count, 2)
            self.assertTrue((review_dir / "approve-me.md").exists())

    def test_main_prints_decision_import_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            review_dir.mkdir()
            _write_review_file(
                review_dir / "pending.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/task",
                    "title": "Pending",
                    "confidence": "low",
                },
            )
            packet = root / "decisions.md"
            packet.write_text(
                "| File | Decision | Notes |\n"
                "|---|---|---|\n"
                "| pending.md | skip | keep it |\n"
            )
            buf = io.StringIO()

            with redirect_stdout(buf):
                review_specialist.main(
                    [
                        "--review-dir",
                        str(review_dir),
                        "--decision-import-preview",
                        str(packet),
                    ]
                )

            output = buf.getvalue()
            self.assertIn("Review specialist decision import preview", output)
            self.assertIn("- actionable: 1", output)
            self.assertIn("- writes: no", output)


def _write_review_file(path: Path, reason: str, raw: dict) -> None:
    path.write_text(
        "---\nnode_type: review\nreviewed: false\n---\n\n"
        f"**Reason:** {reason}\n\n"
        f"```json\n{json.dumps(raw, indent=2)}\n```\n"
    )

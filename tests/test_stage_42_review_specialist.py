import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import frontmatter
import specialists.jane.specialist as review_specialist
from substrate.cog_appearance_registry import CogAppearance


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

    def test_packet_preview_marks_possible_duplicate_alternatives(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            _write_review_file(
                review_dir / "task.md",
                reason="openai_fallback_candidate: confidence: low",
                raw={
                    "node_type": "sprockets/task",
                    "title": "Relocate turtle",
                    "confidence": "low",
                },
            )
            _write_review_file(
                review_dir / "daily.md",
                reason="openai_fallback_candidate: confidence: low",
                raw={
                    "node_type": "cogs/daily",
                    "item_text": "Relocate turtle",
                    "date": "2026-05-24",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )

            packet = specialist.packet_preview()

            self.assertIn("possible duplicate group 1", packet)
            self.assertIn("daily.md, task.md", packet)

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

    def test_packet_decision_import_preview_source_checks_frontmatter_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            review_dir.mkdir()
            _write_review_file(
                review_dir / "pending.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/task",
                    "title": "Packet status",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )
            packet = root / "packet.md"
            packet.write_text(_packet_with_decision(specialist, "pending.md", "approve"))

            preview = specialist.packet_decision_import_preview(packet)

            self.assertEqual(preview.actionable_count, 1)
            self.assertEqual(preview.invalid_count, 0)
            self.assertEqual(preview.rows[0].file, "pending.md")
            self.assertEqual(preview.rows[0].decision, "approve")
            self.assertTrue((review_dir / "pending.md").exists())

    def test_packet_decision_import_preview_rejects_stale_queue_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            review_dir.mkdir()
            pending = review_dir / "pending.md"
            _write_review_file(
                pending,
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/task",
                    "title": "Packet fingerprint",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )
            packet = root / "packet.md"
            packet.write_text(specialist.packet_preview().replace("status: pending", "status: rejected"))
            pending.write_text(pending.read_text() + "\nchanged after packet\n")

            preview = specialist.packet_decision_import_preview(packet)

            self.assertEqual(preview.actionable_count, 0)
            self.assertEqual(preview.invalid_count, 1)
            self.assertIn("fingerprint", preview.rows[0].issue)

    def test_main_prints_packet_decision_import_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            review_dir.mkdir()
            _write_review_file(
                review_dir / "pending.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/task",
                    "title": "Packet CLI",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )
            packet = root / "packet.md"
            packet.write_text(_packet_with_decision(specialist, "pending.md", "skip"))
            buf = io.StringIO()

            with redirect_stdout(buf):
                review_specialist.main(
                    [
                        "--review-dir",
                        str(review_dir),
                        "--packet-import-preview",
                        str(packet),
                    ]
                )

            output = buf.getvalue()
            self.assertIn("Review specialist decision import preview", output)
            self.assertIn("- actionable: 1", output)
            self.assertIn("- pending.md: skip (ok)", output)
            self.assertIn("- writes: no", output)

    def test_operational_packet_combines_queue_preview_and_decision_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            _write_review_file(
                review_dir / "pending.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/task",
                    "title": "Write packet",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )

            packet = specialist.operational_packet_markdown()

            self.assertIn("# Sprockets-Cogs Review Operations Packet", packet)
            self.assertIn("## Queue Preview", packet)
            self.assertIn("# Sprockets-Cogs Review Packet", packet)
            self.assertIn("## Decision Template", packet)
            self.assertIn("| pending.md |  |  |", packet)

    def test_write_operational_packet_is_idempotent_and_outside_review_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            output_path = root / "output" / "review-packet.md"
            review_dir.mkdir()
            _write_review_file(
                review_dir / "pending.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/task",
                    "title": "Packet write",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(
                    review_dir=review_dir,
                    packet_path=output_path,
                )
            )

            first = specialist.write_operational_packet()
            second = specialist.write_operational_packet()

            self.assertEqual(first.packet_path, output_path)
            self.assertEqual(first.bytes_written, second.bytes_written)
            self.assertTrue(output_path.exists())
            self.assertTrue((review_dir / "pending.md").exists())
            self.assertIn("# Sprockets-Cogs Review Operations Packet", output_path.read_text())

    def test_main_writes_operational_packet_to_configured_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            packet_path = root / "output" / "review-packet.md"
            review_dir.mkdir()
            buf = io.StringIO()

            with redirect_stdout(buf):
                review_specialist.main(
                    [
                        "--review-dir",
                        str(review_dir),
                        "--packet-path",
                        str(packet_path),
                        "--write-packet",
                    ]
                )

            output = buf.getvalue()
            self.assertIn("Review specialist packet write", output)
            self.assertIn("- vault writes: no", output)
            self.assertTrue(packet_path.exists())

    def test_write_review_packet_creates_importable_frontmatter_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            packet_path = root / "output" / "review-packet.md"
            review_dir.mkdir()
            _write_review_file(
                review_dir / "pending.md",
                reason="confidence: low",
                raw={
                    "node_type": "cogs/daily",
                    "item_text": "Importable review packet",
                    "date": "2026-05-23",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(
                    review_dir=review_dir,
                    packet_path=packet_path,
                )
            )

            result = specialist.write_review_packet()
            preview = specialist.packet_decision_import_preview(packet_path)

            self.assertEqual(result.packet_path, packet_path)
            self.assertTrue(packet_path.read_text().startswith("---\ntype: review-packet\n"))
            self.assertIn("packet_schema: jane-vault-action-v1", packet_path.read_text())
            self.assertIn("## Vault Decision Surface", packet_path.read_text())
            self.assertIn("| pending.md |  |  |", packet_path.read_text())
            self.assertEqual(preview.invalid_count, 0)
            self.assertEqual(preview.pending_count, 1)
            self.assertNotIn("# Sprockets-Cogs Review Operations Packet", packet_path.read_text())

    def test_packet_decisions_accept_reject_and_edit_vault_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            review_dir.mkdir()
            _write_review_file(
                review_dir / "reject.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/note",
                    "title": "Reject from packet",
                    "confidence": "low",
                },
            )
            _write_review_file(
                review_dir / "edit.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/note",
                    "title": "Edit from packet",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )
            packet = root / "packet.md"
            packet.write_text(_packet_with_decisions(specialist, {"reject.md": "reject", "edit.md": "edit"}))

            preview = specialist.packet_apply_preview(packet)

            self.assertEqual(preview.discard_count, 1)
            self.assertEqual(preview.edit_count, 1)
            self.assertEqual(preview.skip_count, 0)
            self.assertIn("reject.md", {action.file for action in preview.actions})
            self.assertIn("edit.md", {action.file for action in preview.actions})

    def test_main_writes_importable_review_packet_to_configured_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            packet_path = root / "output" / "review-packet.md"
            review_dir.mkdir()
            buf = io.StringIO()

            with redirect_stdout(buf):
                review_specialist.main(
                    [
                        "--review-dir",
                        str(review_dir),
                        "--packet-path",
                        str(packet_path),
                        "--write-review-packet",
                    ]
                )

            output = buf.getvalue()
            self.assertIn("Review specialist packet write", output)
            self.assertTrue(packet_path.exists())
            self.assertTrue(packet_path.read_text().startswith("---\ntype: review-packet\n"))

    def test_decision_apply_preview_groups_guarded_effects_without_writing(self):
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
            _write_review_file(
                review_dir / "discard-me.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/note",
                    "title": "Discard me",
                    "confidence": "low",
                },
            )
            packet = root / "decisions.md"
            packet.write_text(
                "| File | Decision | Notes |\n"
                "|---|---|---|\n"
                "| approve-me.md | approve | good |\n"
                "| discard-me.md | discard | no |\n"
                "| missing.md | approve | stale |\n"
                "| approve-me.md | skip | duplicate |\n"
                "| discard-me.md |  | later |\n"
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )

            preview = specialist.decision_apply_preview(packet)

            self.assertEqual(preview.approve_count, 1)
            self.assertEqual(preview.discard_count, 1)
            self.assertEqual(preview.edit_count, 0)
            self.assertEqual(preview.skip_count, 0)
            self.assertEqual(preview.pending_count, 0)
            self.assertEqual(preview.rejected_count, 3)
            self.assertTrue((review_dir / "approve-me.md").exists())
            self.assertTrue((review_dir / "discard-me.md").exists())

    def test_decision_apply_preview_rejects_unparseable_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            review_dir.mkdir()
            (review_dir / "bad.md").write_text(
                "---\nnode_type: review\nreviewed: false\n---\n\n"
                "**Reason:** confidence: low\n\n"
                "No JSON here.\n"
            )
            packet = root / "decisions.md"
            packet.write_text(
                "| File | Decision | Notes |\n"
                "|---|---|---|\n"
                "| bad.md | approve | impossible |\n"
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )

            preview = specialist.decision_apply_preview(packet)

            self.assertEqual(preview.approve_count, 0)
            self.assertEqual(preview.rejected_count, 1)
            self.assertIn("unparseable", preview.actions[0].issue)

    def test_main_prints_guarded_apply_preview(self):
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
                "| pending.md | approve | yes |\n"
            )
            buf = io.StringIO()

            with redirect_stdout(buf):
                review_specialist.main(
                    [
                        "--review-dir",
                        str(review_dir),
                        "--apply-preview",
                        str(packet),
                    ]
                )

            output = buf.getvalue()
            self.assertIn("Review specialist guarded apply preview", output)
            self.assertIn("- would approve: 1", output)
            self.assertIn("- vault writes: no", output)

    def test_packet_apply_requires_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            review_dir.mkdir()
            _write_review_file(
                review_dir / "pending.md",
                reason="confidence: low",
                raw={
                    "node_type": "cogs/daily",
                    "item_text": "Confirm Jane packet apply",
                    "date": "2026-05-22",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )
            packet = root / "packet.md"
            packet.write_text(_packet_with_decision(specialist, "pending.md", "approve"))

            with self.assertRaisesRegex(ValueError, "explicit confirmation"):
                specialist.apply_approved_packet(packet)

            self.assertTrue((review_dir / "pending.md").exists())

    def test_packet_apply_approved_packet_archives_reviews_and_writes_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            archive_dir = root / "archive"
            audit_path = root / "output" / "review-apply-audit.jsonl"
            review_dir.mkdir()
            _write_review_file(
                review_dir / "approved.md",
                reason="confidence: low",
                raw={
                    "node_type": "cogs/daily",
                    "item_text": "Approved from Jane packet",
                    "date": "2026-05-22",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(
                    review_dir=review_dir,
                    archive_dir=archive_dir,
                    audit_path=audit_path,
                )
            )
            packet = root / "packet.md"
            packet.write_text(_packet_with_decision(specialist, "approved.md", "approve"))

            with patch.object(review_specialist.review, "write_node") as write_node:
                result = specialist.apply_approved_packet(packet, confirm=True)

            self.assertEqual(result.approved_files, ("approved.md",))
            write_node.assert_called_once()
            self.assertEqual(write_node.call_args.args[0].confidence.value, "high")
            self.assertFalse((review_dir / "approved.md").exists())
            self.assertTrue((archive_dir / "approved.md").exists())
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(audit["decision"], "approved")
            self.assertEqual(audit["approved_files"], ["approved.md"])
            self.assertEqual(frontmatter.load(str(packet)).get("status"), "applied")

            with self.assertRaisesRegex(ValueError, "approved"):
                specialist.apply_approved_packet(packet, confirm=True)

    def test_packet_apply_handles_per_item_approve_discard_and_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            archive_dir = root / "archive"
            audit_path = root / "output" / "review-apply-audit.jsonl"
            review_dir.mkdir()
            _write_review_file(
                review_dir / "approve.md",
                reason="confidence: low",
                raw={
                    "node_type": "cogs/daily",
                    "item_text": "Approve from packet table",
                    "date": "2026-05-22",
                    "confidence": "low",
                },
            )
            _write_review_file(
                review_dir / "discard.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/note",
                    "title": "Discard from packet table",
                    "confidence": "low",
                },
            )
            _write_review_file(
                review_dir / "skip.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/note",
                    "title": "Skip from packet table",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(
                    review_dir=review_dir,
                    archive_dir=archive_dir,
                    audit_path=audit_path,
                )
            )
            packet = root / "packet.md"
            packet.write_text(
                _packet_with_decisions(
                    specialist,
                    {
                        "approve.md": "approve",
                        "discard.md": "discard",
                        "skip.md": "skip",
                    },
                )
            )

            preview = specialist.packet_apply_preview(packet)
            with patch.object(review_specialist.review, "write_node") as write_node:
                result = specialist.apply_approved_packet(packet, confirm=True)

            self.assertEqual(preview.approve_count, 1)
            self.assertEqual(preview.discard_count, 1)
            self.assertEqual(preview.skip_count, 1)
            self.assertEqual(result.approved_files, ("approve.md",))
            self.assertEqual(result.discarded_files, ("discard.md",))
            write_node.assert_called_once()
            self.assertFalse((review_dir / "approve.md").exists())
            self.assertFalse((review_dir / "discard.md").exists())
            self.assertTrue((review_dir / "skip.md").exists())
            self.assertTrue((archive_dir / "approve.md").exists())
            self.assertTrue((archive_dir / "discard.md").exists())
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(audit["approved_files"], ["approve.md"])
            self.assertEqual(audit["discarded_files"], ["discard.md"])

    def test_packet_apply_preview_rejects_existing_sprockets_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            task_dir = root / "tasks"
            archive_dir = root / "archive"
            review_dir.mkdir()
            task_dir.mkdir()
            (task_dir / "duplicate-task.md").write_text("already here")
            _write_review_file(
                review_dir / "task.md",
                reason="confidence: low",
                raw={
                    "node_type": "sprockets/task",
                    "title": "Duplicate task",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir, archive_dir=archive_dir)
            )
            packet = root / "packet.md"
            packet.write_text(_packet_with_decision(specialist, "task.md", "approve"))

            with patch.dict(review_specialist.agentic_loop.SPROCKETS_FOLDERS, {"sprockets/task": task_dir}, clear=True):
                preview = specialist.packet_apply_preview(packet)

            self.assertEqual(preview.approve_count, 0)
            self.assertEqual(preview.rejected_count, 1)
            self.assertIn("collide", preview.actions[0].issue)
            self.assertTrue((review_dir / "task.md").exists())

    def test_main_prints_confirmed_packet_apply_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            review_dir.mkdir()
            _write_review_file(
                review_dir / "approved.md",
                reason="confidence: low",
                raw={
                    "node_type": "cogs/daily",
                    "item_text": "CLI Jane apply",
                    "date": "2026-05-22",
                    "confidence": "low",
                },
            )
            packet = root / "packet.md"
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )
            packet.write_text(_packet_with_decision(specialist, "approved.md", "approve"))
            buf = io.StringIO()

            with patch.object(review_specialist.review, "write_node"), redirect_stdout(buf):
                review_specialist.main(
                    [
                        "--review-dir",
                        str(review_dir),
                        "--archive-dir",
                        str(root / "archive"),
                        "--audit-path",
                        str(root / "audit.jsonl"),
                        "--packet-apply",
                        str(packet),
                        "--confirm",
                    ]
                )

            output = buf.getvalue()
            self.assertIn("Review specialist approved packet apply", output)
            self.assertIn("- packet status: applied", output)
            self.assertIn("- vault writes: yes", output)

    def test_appearance_conflict_packet_references_registry_and_known_surfaces(self):
        appearances = [
            CogAppearance(
                cog_id="cog-july-3-walmart",
                surface="day",
                period="2026-07-03",
                path="Cogs/2026/07/27/2026-07-03 Fri.md",
            ),
            CogAppearance(
                cog_id="cog-july-3-walmart",
                surface="5wow",
                period="2026-06",
                path="Cogs/2026/2026-06.md",
            ),
        ]

        packet = review_specialist.review.appearance_conflict_packet_markdown(
            cog_id="cog-july-3-walmart",
            source_action="User checked the June 5WOW appearance as done.",
            proposed_state="done",
            appearances=appearances,
        )

        self.assertIn("type: appearance-conflict-review", packet)
        self.assertIn("registry_path: .graph/cog-appearances.json", packet)
        self.assertIn("Jane asks one compact question", packet)
        self.assertIn("| day | 2026-07-03 | Cogs/2026/07/27/2026-07-03 Fri.md | [ ] | open |", packet)
        self.assertIn("| 5wow | 2026-06 | Cogs/2026/2026-06.md | [ ] | open |", packet)
        self.assertIn("| cog-july-3-walmart |  |  |", packet)


def _write_review_file(path: Path, reason: str, raw: dict) -> None:
    path.write_text(
        "---\nnode_type: review\nreviewed: false\n---\n\n"
        f"**Reason:** {reason}\n\n"
        f"```json\n{json.dumps(raw, indent=2)}\n```\n"
    )


def _packet_with_decision(
    specialist: review_specialist.ReviewSpecialist,
    file_name: str,
    decision: str,
) -> str:
    return _packet_with_decisions(specialist, {file_name: decision})


def _packet_with_decisions(
    specialist: review_specialist.ReviewSpecialist,
    decisions: dict[str, str],
) -> str:
    packet = specialist.packet_preview().replace("status: pending", "status: approved")
    for file_name, decision in decisions.items():
        packet = packet.replace(f"| {file_name} |  |", f"| {file_name} | {decision} |")
    return packet

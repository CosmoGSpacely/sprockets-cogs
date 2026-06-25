import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import specialists.rosie.loop as agentic_loop
from specialists.astro import vault
from specialists.cogs.corrections import (
    apply_correction_command,
    parse_correction_command,
)
from specialists.cogs.time_context import apply_bounded_recurrence_context


class Stage132InputCorrectionTimeTests(unittest.TestCase):
    def test_parse_fullbloom_not_full_loom_as_text_replacement(self):
        correction = parse_correction_command("FullBloom not full loom", "2026-06-24")

        self.assertIsNotNone(correction)
        self.assertEqual(correction.kind, "replace_text")
        self.assertEqual(correction.old_text, "full loom")
        self.assertEqual(correction.new_text, "FullBloom")

    def test_replace_text_correction_updates_multiple_open_cogs(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp) / "Cogs"
            for date_iso in ("2026-06-24", "2026-06-25"):
                path = vault.ensure_daily_note(date_iso, daily_dir)
                path.write_text(path.read_text() + "- [ ] Full loom\n", encoding="utf-8")
            carried = vault.ensure_daily_note("2026-06-23", daily_dir)
            carried.write_text(carried.read_text() + "- [>] Full loom\n", encoding="utf-8")

            correction = parse_correction_command("FullBloom not full loom", "2026-06-24")
            result = apply_correction_command(correction, daily_dir)

            self.assertEqual(result.status, "corrected")
            for date_iso in ("2026-06-23", "2026-06-24", "2026-06-25"):
                text = vault.daily_note_path(date_iso, daily_dir).read_text(encoding="utf-8")
                self.assertIn("FullBloom", text)
                self.assertIn("correction: replaced 'full loom'", text)
                self.assertNotIn("Full loom", text)
            carried_text = vault.daily_note_path("2026-06-23", daily_dir).read_text(encoding="utf-8")
            self.assertIn("- [>] FullBloom", carried_text)

    def test_parse_remove_vacation_move_date_range(self):
        correction = parse_correction_command(
            "Remove vacation August 4-11, it's September 4-11",
            "2026-06-24",
        )

        self.assertIsNotNone(correction)
        self.assertEqual(correction.kind, "move_date_range")
        self.assertEqual(correction.label, "vacation")
        self.assertEqual(correction.old_start, "2026-08-04")
        self.assertEqual(correction.old_end, "2026-08-11")
        self.assertEqual(correction.new_start, "2026-09-04")
        self.assertEqual(correction.new_end, "2026-09-11")

    def test_move_date_range_marks_old_and_adds_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp) / "Cogs"
            for day in range(4, 12):
                date_iso = f"2026-08-{day:02d}"
                path = vault.ensure_daily_note(date_iso, daily_dir)
                path.write_text(path.read_text() + "- [ ] VACATION\n", encoding="utf-8")

            correction = parse_correction_command(
                "Remove vacation August 4-11, it's September 4-11",
                "2026-06-24",
            )
            result = apply_correction_command(correction, daily_dir)

            self.assertEqual(result.status, "corrected")
            august = vault.daily_note_path("2026-08-04", daily_dir).read_text(encoding="utf-8")
            september = vault.daily_note_path("2026-09-04", daily_dir).read_text(encoding="utf-8")
            self.assertIn("- [-] VACATION", august)
            self.assertIn("correction: moved to 2026-09-04..2026-09-11", august)
            self.assertIn("- [ ] VACATION", september)

    def test_bounded_recurrence_expands_time_first_real_input(self):
        raw_nodes = [{"raw": "Yoga is 10am the next six Saturdays", "type_hint": "appointment"}]
        classified = [
            {
                "node_type": "cogs/daily",
                "title": "YOGA",
                "item_text": "YOGA",
                "date": "2026-06-24",
                "confidence": "high",
            }
        ]

        result, decisions = apply_bounded_recurrence_context(raw_nodes, classified, "2026-06-24")

        self.assertEqual(len(result), 6)
        self.assertEqual([node["date"] for node in result][0], "2026-06-27")
        self.assertEqual([node["date"] for node in result][-1], "2026-08-01")
        self.assertEqual({node["item_text"] for node in result}, {"10a YOGA"})
        self.assertEqual(len(decisions), 1)

    def test_process_input_uses_source_timestamp_for_tomorrow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            processing_dir = root / "processing"
            archive_dir = root / "archive"
            output_dir = root / "output"
            daily_dir = root / "vault" / "Cogs"
            review_dir = root / "vault" / "review"
            for path in [input_dir, processing_dir, archive_dir, output_dir, daily_dir, review_dir]:
                path.mkdir(parents=True)
            input_path = input_dir / "telegram-bocce.input"
            input_path.write_text(
                "---\n"
                "session_id: stage132\n"
                "source: telegram\n"
                "metadata:\n"
                "  source_timestamp: '2026-06-24T23:09:00-04:00'\n"
                "---\n\n"
                "Bocce 6:30p tomorrow\n",
                encoding="utf-8",
            )
            raw_nodes = [{"raw": "Bocce 6:30p tomorrow", "type_hint": "appointment"}]
            classified = [
                {
                    "node_type": "cogs/daily",
                    "title": "BOCCE 6:30p",
                    "item_text": "BOCCE 6:30p",
                    "date": "2026-06-23",
                    "confidence": "high",
                }
            ]

            with patch.object(agentic_loop, "INPUT_DIR", input_dir), \
                 patch.object(agentic_loop, "PROCESSING_DIR", processing_dir), \
                 patch.object(agentic_loop, "ARCHIVE_DIR", archive_dir), \
                 patch.object(agentic_loop, "OUTPUT_DIR", output_dir), \
                 patch.object(agentic_loop, "DAILY_DIR", daily_dir), \
                 patch.object(agentic_loop, "REVIEW_DIR", review_dir), \
                 patch.object(agentic_loop, "build_context_for_input", return_value=""), \
                 patch.object(agentic_loop, "extract_nodes", return_value=raw_nodes), \
                 patch.object(agentic_loop, "classify_nodes", return_value=classified), \
                 patch.object(agentic_loop, "memory_parent_trace") as memory_trace, \
                 patch.object(agentic_loop, "write_memory_parent_trace"), \
                 patch.object(agentic_loop, "send_processed_ack"):
                memory_trace.return_value.parent_title = ""
                memory_trace.return_value.selected = False
                memory_trace.return_value.retrieved_count = 0
                memory_trace.return_value.reason = "disabled"
                agentic_loop.process_input(input_path)

            right_note = vault.daily_note_path("2026-06-25", daily_dir)
            self.assertTrue(right_note.exists())
            self.assertIn("6:30p BOCCE", right_note.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

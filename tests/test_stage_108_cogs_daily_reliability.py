from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import specialists.rosie.loop as agentic_loop
import specialists.cogs.carry as carry
import specialists.astro.vault as vault
from specialists.cogs.ordering import ordering_needs_review, sort_cogs_items
from specialists.cogs.time_context import (
    apply_bounded_recurrence_context,
    expand_bounded_recurrence,
)


class Stage108CogsDailyReliabilityTests(TestCase):
    def test_expands_next_count_weekday_recurrence(self):
        occurrences = expand_bounded_recurrence(
            "YOGA next 8 Saturdays at 10am",
            "2026-06-17",
        )

        self.assertEqual(len(occurrences), 8)
        self.assertEqual(occurrences[0].date, "2026-06-20")
        self.assertEqual(occurrences[-1].date, "2026-08-08")
        self.assertEqual({item.item_text for item in occurrences}, {"10a YOGA"})

    def test_expands_multi_weekday_recurrence(self):
        occurrences = expand_bounded_recurrence(
            "class Mondays and Wednesdays for 2 weeks at 6p",
            "2026-06-17",
        )

        self.assertEqual(
            [(item.date, item.item_text) for item in occurrences],
            [
                ("2026-06-17", "6p CLASS"),
                ("2026-06-22", "6p CLASS"),
                ("2026-06-24", "6p CLASS"),
            ],
        )

    def test_apply_bounded_recurrence_context_creates_dated_nodes(self):
        raw_nodes = [{"raw": "YOGA next 2 Saturdays at 10am"}]
        classified = [
            {
                "node_type": "cogs/daily",
                "item_text": "YOGA next 2 Saturdays at 10am",
                "date": "2026-06-17",
                "confidence": "high",
            }
        ]

        result, decisions = apply_bounded_recurrence_context(raw_nodes, classified, "2026-06-17")

        self.assertEqual([node["date"] for node in result], ["2026-06-20", "2026-06-27"])
        self.assertEqual([node["item_text"] for node in result], ["10a YOGA", "10a YOGA"])
        self.assertTrue(all(node["_bounded_recurrence"] for node in result))
        self.assertEqual(decisions[0].occurrence_count, 2)

    def test_process_input_writes_bounded_recurrence_without_review(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            processing_dir = root / "processing"
            archive_dir = root / "archive"
            output_dir = root / "output"
            daily_dir = root / "vault" / "Cogs" / "daily"
            review_dir = root / "vault" / "review"
            for path in [input_dir, processing_dir, archive_dir, output_dir, daily_dir, review_dir]:
                path.mkdir(parents=True)
            input_path = input_dir / "bounded-yoga.input"
            input_path.write_text(
                "---\nsession_id: stage108\nsource: telegram\n---\n\n"
                "YOGA next 2 Saturdays at 10am\n",
                encoding="utf-8",
            )
            raw_nodes = [{"raw": "YOGA next 2 Saturdays at 10am", "type_hint": "appointment"}]
            classified = [
                {
                    "node_type": "cogs/daily",
                    "title": "YOGA next 2 Saturdays at 10am",
                    "item_text": "YOGA next 2 Saturdays at 10am",
                    "date": "2026-06-17",
                    "confidence": "high",
                }
            ]

            class FakeDateTime:
                @classmethod
                def now(cls):
                    return cls()

                def strftime(self, fmt):
                    if fmt == "%Y-%m-%d":
                        return "2026-06-17"
                    if fmt == "%H:%M":
                        return "09:00"
                    if fmt == "%Y%m%d_%H%M%S_%f":
                        return "20260617_090000_000000"
                    return "2026-06-17"

            with patch.object(agentic_loop, "INPUT_DIR", input_dir), \
                 patch.object(agentic_loop, "PROCESSING_DIR", processing_dir), \
                 patch.object(agentic_loop, "ARCHIVE_DIR", archive_dir), \
                 patch.object(agentic_loop, "OUTPUT_DIR", output_dir), \
                 patch.object(agentic_loop, "DAILY_DIR", daily_dir), \
                 patch.object(agentic_loop, "REVIEW_DIR", review_dir), \
                 patch.object(agentic_loop, "datetime", FakeDateTime), \
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

            first_note = daily_dir / "2026-06-20 Sat.md"
            second_note = daily_dir / "2026-06-27 Sat.md"
            self.assertIn("10a YOGA", first_note.read_text(encoding="utf-8"))
            self.assertIn("10a YOGA", second_note.read_text(encoding="utf-8"))
            self.assertEqual(list(review_dir.glob("*.md")), [])

    def test_apply_plan_document_preserves_multiline_details(self):
        with TemporaryDirectory() as tmp:
            daily_dir = Path(tmp) / "daily"
            daily_dir.mkdir()
            note = vault.ensure_daily_note("2026-06-17", daily_dir)
            note.write_text(
                note.read_text()
                + "- [ ] TRAVEL TO MKE\n"
                  "  reservation: ABC123\n"
                  "  hotel: Pfister\n"
            )
            candidates = carry.scan_daily_notes(daily_dir, through_date="2026-06-17")
            plan = carry.build_plan_document(candidates, "2026-06-18")

            carry.apply_plan_document(plan)

            target = daily_dir / "2026-06-18 Thu.md"
            target_text = target.read_text(encoding="utf-8")
            self.assertIn("- [ ] TRAVEL TO MKE\n  reservation: ABC123\n  hotel: Pfister\n", target_text)
            self.assertIn("- [>] TRAVEL TO MKE", note.read_text(encoding="utf-8"))

    def test_correct_cog_locator_moves_one_clear_target(self):
        with TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            wrong_note = vault.ensure_daily_note("2026-06-18", daily_dir)
            wrong_note.write_text(wrong_note.read_text() + "- [ ] SHAKESPEARE\n")

            result = vault.correct_cog_locator("SHAKESPEARE", "2026-06-26", daily_dir)

            self.assertEqual(result.status, "corrected")
            self.assertIn("- [>] SHAKESPEARE", wrong_note.read_text(encoding="utf-8"))
            self.assertIn("correction: moved to 2026-06-26", wrong_note.read_text(encoding="utf-8"))
            target = daily_dir / "2026-06-26 Fri.md"
            self.assertIn("- [ ] SHAKESPEARE", target.read_text(encoding="utf-8"))

    def test_correct_cog_locator_routes_ambiguous_match_to_review_status(self):
        with TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            first = vault.ensure_daily_note("2026-06-18", daily_dir)
            second = vault.ensure_daily_note("2026-06-19", daily_dir)
            first.write_text(first.read_text() + "- [ ] SHAKESPEARE\n")
            second.write_text(second.read_text() + "- [ ] SHAKESPEARE tickets\n")

            result = vault.correct_cog_locator("SHAKESPEARE", "2026-06-26", daily_dir)

            self.assertEqual(result.status, "review")
            self.assertIn("2 open Cogs matched", result.message)

    def test_planner_order_uses_explicit_times_and_dayparts_without_review_noise(self):
        ordered = sort_cogs_items([
            "dinner with Mom",
            "lunch with Tom",
            "8a DENTIST",
            "call pharmacy",
        ])

        self.assertEqual(
            ordered,
            ["8a DENTIST", "lunch with Tom", "call pharmacy", "dinner with Mom"],
        )
        self.assertFalse(ordering_needs_review("dinner with Mom"))
        self.assertTrue(ordering_needs_review("take medication before surgery"))

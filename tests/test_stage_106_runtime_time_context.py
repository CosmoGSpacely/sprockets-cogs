from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import specialists.rosie.loop as agentic_loop
from specialists.cogs.format import apply_cogs_item_format, normalize_cogs_time_text
from specialists.cogs.time_context import (
    apply_runtime_date_context,
    resolve_relative_cogs_horizon,
    resolve_relative_date,
)


class Stage106RuntimeTimeContextTests(TestCase):
    def test_normalize_cogs_time_tokens_and_spans(self):
        self.assertEqual(normalize_cogs_time_text("DENTIST 10am"), "DENTIST 10a")
        self.assertEqual(normalize_cogs_time_text("YOGA 3:30pm"), "YOGA 3:30p")
        self.assertEqual(normalize_cogs_time_text("CRAFT FAIR 8am to 2pm"), "CRAFT FAIR 8a-2p")

    def test_apply_cogs_item_format_restores_span_from_raw_text(self):
        raw_nodes = [{"raw": "Craft fair 8am to 2pm tomorrow", "type_hint": "appointment"}]
        classified = [
            {
                "node_type": "cogs/daily",
                "title": "CRAFT FAIR 8am",
                "item_text": "CRAFT FAIR 8am",
                "date": "2026-06-13",
                "confidence": "high",
            }
        ]

        result, decisions = apply_cogs_item_format(raw_nodes, classified)

        self.assertEqual(result[0]["item_text"], "8a-2p CRAFT FAIR")
        self.assertEqual(result[0]["title"], "8a-2p CRAFT FAIR")
        self.assertEqual(len(decisions), 1)

    def test_resolve_tomorrow_from_processing_date(self):
        self.assertEqual(
            resolve_relative_date("Craft fair 8am to 2pm tomorrow", "2026-06-12"),
            ("2026-06-13", "tomorrow"),
        )

    def test_resolve_weekend_week_and_month_carry_semantics(self):
        self.assertEqual(
            resolve_relative_cogs_horizon("Craft fair this weekend", "2026-06-12"),
            ("2026-06-13", "this weekend", "day"),
        )
        self.assertEqual(
            resolve_relative_cogs_horizon("Call Tom next week", "2026-06-12"),
            ("2026-06-12", "next week", "week"),
        )
        self.assertEqual(
            resolve_relative_cogs_horizon("Craft fair 8am next month", "2026-06-12"),
            ("2026-07-01", "next month", "month"),
        )
        self.assertEqual(
            resolve_relative_cogs_horizon("Craft fair 8am tomorrow", "2026-06-12"),
            ("2026-06-13", "tomorrow", "day"),
        )

    def test_apply_runtime_context_overrides_stale_model_date(self):
        raw_nodes = [{"raw": "Craft fair 8am to 2pm tomorrow", "type_hint": "appointment"}]
        classified = [
            {
                "node_type": "cogs/daily",
                "title": "CRAFT FAIR 8am",
                "item_text": "CRAFT FAIR 8am",
                "date": "2026-06-09",
                "confidence": "high",
            }
        ]

        result, decisions = apply_runtime_date_context(raw_nodes, classified, "2026-06-12")

        self.assertEqual(result[0]["date"], "2026-06-13")
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].original_date, "2026-06-09")
        self.assertEqual(decisions[0].resolved_date, "2026-06-13")

    def test_process_input_writes_tomorrow_to_runtime_relative_day(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            processing_dir = root / "processing"
            archive_dir = root / "archive"
            output_dir = root / "output"
            daily_dir = root / "vault" / "Cogs" / "daily"
            for path in [input_dir, processing_dir, archive_dir, output_dir, daily_dir]:
                path.mkdir(parents=True)
            input_path = input_dir / "telegram-craft.input"
            input_path.write_text(
                "---\nsession_id: stage106\nsource: telegram\n---\n\n"
                "Craft fair 8am to 2pm tomorrow\n",
                encoding="utf-8",
            )
            raw_nodes = [{"raw": "Craft fair 8am to 2pm tomorrow", "type_hint": "appointment"}]
            classified = [
                {
                    "node_type": "cogs/daily",
                    "title": "CRAFT FAIR 8am",
                    "item_text": "CRAFT FAIR 8am",
                    "date": "2026-06-09",
                    "confidence": "high",
                }
            ]

            class FakeDateTime:
                @classmethod
                def now(cls):
                    return cls()

                def strftime(self, fmt):
                    if fmt == "%Y-%m-%d":
                        return "2026-06-12"
                    if fmt == "%H:%M":
                        return "09:00"
                    if fmt == "%Y%m%d_%H%M%S_%f":
                        return "20260612_090000_000000"
                    return "2026-06-12"

            with patch.object(agentic_loop, "INPUT_DIR", input_dir), \
                 patch.object(agentic_loop, "PROCESSING_DIR", processing_dir), \
                 patch.object(agentic_loop, "ARCHIVE_DIR", archive_dir), \
                 patch.object(agentic_loop, "OUTPUT_DIR", output_dir), \
                 patch.object(agentic_loop, "DAILY_DIR", daily_dir), \
                 patch.object(agentic_loop, "REVIEW_DIR", root / "review"), \
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

            wrong_note = daily_dir / "2026-06-09 Tue.md"
            right_note = daily_dir / "2026-06-13 Sat.md"
            self.assertFalse(wrong_note.exists())
            self.assertTrue(right_note.exists())
            self.assertIn("8a-2p CRAFT FAIR", right_note.read_text(encoding="utf-8"))
            self.assertTrue((archive_dir / "telegram-craft.input").exists())

    def test_process_input_writes_next_month_to_monthly_carry(self):
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
            input_path = input_dir / "telegram-craft-month.input"
            input_path.write_text(
                "---\nsession_id: stage106\nsource: telegram\n---\n\n"
                "Craft fair 8am next month\n",
                encoding="utf-8",
            )
            raw_nodes = [{"raw": "Craft fair 8am next month", "type_hint": "appointment"}]
            classified = [
                {
                    "node_type": "cogs/daily",
                    "title": "CRAFT FAIR 8am",
                    "item_text": "CRAFT FAIR 8am",
                    "date": "2026-06-12",
                    "confidence": "high",
                }
            ]

            class FakeDateTime:
                @classmethod
                def now(cls):
                    return cls()

                def strftime(self, fmt):
                    if fmt == "%Y-%m-%d":
                        return "2026-06-12"
                    if fmt == "%H:%M":
                        return "09:00"
                    if fmt == "%Y%m%d_%H%M%S_%f":
                        return "20260612_090000_000000"
                    return "2026-06-12"

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

            monthly_note = root / "vault" / "Cogs" / "2026" / "2026-07.md"
            self.assertTrue(monthly_note.exists())
            monthly_text = monthly_note.read_text(encoding="utf-8")
            self.assertIn("## CARRY\n\n- [ ] 8a CRAFT FAIR\n\n## Dates", monthly_text)
            self.assertEqual(list(review_dir.glob("*.md")), [])
            self.assertTrue((archive_dir / "telegram-craft-month.input").exists())

    def test_process_input_writes_next_week_to_current_week_carry(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            processing_dir = root / "processing"
            archive_dir = root / "archive"
            output_dir = root / "output"
            daily_dir = root / "vault" / "Cogs" / "daily"
            for path in [input_dir, processing_dir, archive_dir, output_dir, daily_dir]:
                path.mkdir(parents=True)
            input_path = input_dir / "telegram-call-next-week.input"
            input_path.write_text(
                "---\nsession_id: stage106\nsource: telegram\n---\n\n"
                "Call Tom next week\n",
                encoding="utf-8",
            )
            raw_nodes = [{"raw": "Call Tom next week", "type_hint": "task"}]
            classified = [
                {
                    "node_type": "cogs/daily",
                    "title": "Call Tom",
                    "item_text": "Call Tom",
                    "date": "2026-06-19",
                    "confidence": "high",
                }
            ]

            class FakeDateTime:
                @classmethod
                def now(cls):
                    return cls()

                def strftime(self, fmt):
                    if fmt == "%Y-%m-%d":
                        return "2026-06-12"
                    if fmt == "%H:%M":
                        return "09:00"
                    if fmt == "%Y%m%d_%H%M%S_%f":
                        return "20260612_090000_000000"
                    return "2026-06-12"

            with patch.object(agentic_loop, "INPUT_DIR", input_dir), \
                 patch.object(agentic_loop, "PROCESSING_DIR", processing_dir), \
                 patch.object(agentic_loop, "ARCHIVE_DIR", archive_dir), \
                 patch.object(agentic_loop, "OUTPUT_DIR", output_dir), \
                 patch.object(agentic_loop, "DAILY_DIR", daily_dir), \
                 patch.object(agentic_loop, "REVIEW_DIR", root / "vault" / "review"), \
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

            weekly_note = root / "vault" / "Cogs" / "2026" / "06" / "2026-W24.md"
            self.assertTrue(weekly_note.exists())
            self.assertIn("## CARRY\n\n- [ ] Call Tom\n\n## This Week", weekly_note.read_text(encoding="utf-8"))
            self.assertTrue((archive_dir / "telegram-call-next-week.input").exists())

    def test_ordinary_cogs_capture_does_not_call_memory_parent_retrieval(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            processing_dir = root / "processing"
            archive_dir = root / "archive"
            output_dir = root / "output"
            daily_dir = root / "vault" / "Cogs" / "daily"
            for path in [input_dir, processing_dir, archive_dir, output_dir, daily_dir]:
                path.mkdir(parents=True)
            input_path = input_dir / "ordinary-cogs.input"
            input_path.write_text(
                "---\nsession_id: stage106\nsource: telegram\n---\n\n"
                "Buy sealant tomorrow\n",
                encoding="utf-8",
            )
            raw_nodes = [{"raw": "Buy sealant tomorrow", "type_hint": "task"}]
            classified = [
                {
                    "node_type": "cogs/daily",
                    "title": "Buy sealant",
                    "item_text": "Buy sealant",
                    "date": "2026-06-18",
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
                 patch.object(agentic_loop, "REVIEW_DIR", root / "vault" / "review"), \
                 patch.object(agentic_loop, "datetime", FakeDateTime), \
                 patch.object(agentic_loop, "build_context_for_input", return_value=""), \
                 patch.object(agentic_loop, "extract_nodes", return_value=raw_nodes), \
                 patch.object(agentic_loop, "classify_nodes", return_value=classified), \
                 patch.object(agentic_loop, "memory_parent_trace", side_effect=AssertionError("memory called")), \
                 patch.object(agentic_loop, "write_memory_parent_trace"), \
                 patch.object(agentic_loop, "send_processed_ack"):
                agentic_loop.process_input(input_path)

            note = daily_dir / "2026-06-18 Thu.md"
            self.assertTrue(note.exists())
            self.assertIn("Buy sealant", note.read_text(encoding="utf-8"))

    def test_event_attached_entity_routes_to_review_without_blocking_cogs(self):
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
            input_path = input_dir / "dentist-address.input"
            input_path.write_text(
                "---\nsession_id: stage106\nsource: telegram\n---\n\n"
                "Dentist 8am at 123 Main St tomorrow\n",
                encoding="utf-8",
            )
            raw_nodes = [{"raw": "Dentist 8am at 123 Main St tomorrow", "type_hint": "appointment"}]
            classified = [
                {
                    "node_type": "cogs/daily",
                    "title": "DENTIST 8am",
                    "item_text": "DENTIST 8am",
                    "date": "2026-06-18",
                    "confidence": "high",
                },
                {
                    "node_type": "sprockets/entity",
                    "title": "123 Main St",
                    "confidence": "high",
                },
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
                 patch.object(agentic_loop, "memory_parent_trace", side_effect=AssertionError("memory called")), \
                 patch.object(agentic_loop, "write_memory_parent_trace"), \
                 patch.object(agentic_loop, "send_processed_ack"):
                agentic_loop.process_input(input_path)

            note = daily_dir / "2026-06-18 Thu.md"
            self.assertTrue(note.exists())
            self.assertIn("8a DENTIST", note.read_text(encoding="utf-8"))
            self.assertFalse((root / "vault" / "Sprockets" / "entities" / "123-main-st.md").exists())
            review_text = "\n".join(path.read_text(encoding="utf-8") for path in review_dir.glob("*.md"))
            self.assertIn("ordinary_entity_authority_guard", review_text)
            self.assertIn("123 Main St", review_text)

    def test_recurring_cogs_language_routes_to_review_without_writing_event(self):
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
            input_path = input_dir / "recurring-yoga.input"
            input_path.write_text(
                "---\nsession_id: stage106\nsource: telegram\n---\n\n"
                "Yoga every Tuesday 5:30pm\n",
                encoding="utf-8",
            )
            raw_nodes = [{"raw": "Yoga every Tuesday 5:30pm", "type_hint": "appointment"}]
            classified = [
                {
                    "node_type": "cogs/daily",
                    "title": "YOGA every Tuesday 5:30pm",
                    "item_text": "YOGA every Tuesday 5:30pm",
                    "date": "2026-06-23",
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
                 patch.object(agentic_loop, "memory_parent_trace", side_effect=AssertionError("memory called")), \
                 patch.object(agentic_loop, "write_memory_parent_trace"), \
                 patch.object(agentic_loop, "send_processed_ack"):
                agentic_loop.process_input(input_path)

            guessed_note = daily_dir / "2026-06-23 Tue.md"
            self.assertFalse(guessed_note.exists())
            today_note = daily_dir / "2026-06-17 Wed.md"
            self.assertTrue(today_note.exists())
            self.assertNotIn("YOGA", today_note.read_text(encoding="utf-8"))
            review_text = "\n".join(path.read_text(encoding="utf-8") for path in review_dir.glob("*.md"))
            self.assertIn("recurrence_guard", review_text)
            self.assertIn("every Tuesday", review_text)

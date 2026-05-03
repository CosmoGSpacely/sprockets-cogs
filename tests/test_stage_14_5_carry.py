import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import carry
import vault


class Stage145CarryPrimitiveTests(unittest.TestCase):
    def test_ensure_daily_note_creates_expected_cogs_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)

            path = vault.ensure_daily_note("2026-05-04", daily_dir)

            self.assertEqual(path.name, "Mon 04 May 2026.md")
            text = path.read_text()
            self.assertIn("node_type: cogs/daily", text)
            self.assertIn("date: 2026-05-04", text)
            self.assertIn("# Mon 04 May 2026", text)

    def test_append_cogs_item_text_skips_existing_item_across_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            path = vault.ensure_daily_note("2026-05-04", daily_dir)
            path.write_text(path.read_text() + "- [>] Call Jordan\n")

            appended = vault.append_cogs_item_text("2026-05-04", "Call Jordan", daily_dir)

            self.assertFalse(appended)
            self.assertEqual(path.read_text().count("Call Jordan"), 1)

    def test_parse_cogs_blocks_keeps_child_lines_with_parent(self):
        content = (
            "---\n---\n\n"
            "# Mon 04 May 2026\n\n"
            "- [ ] WALMART\n"
            "  - [ ] return battery\n"
            "  - [ ] buy vitamins\n"
            "- [x] Done thing\n"
            "- [ ] Call Jordan\n"
            "plain note\n"
        )

        blocks = vault.parse_cogs_blocks(content)

        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].item_text, "WALMART")
        self.assertEqual(blocks[0].lines, (
            "- [ ] WALMART",
            "  - [ ] return battery",
            "  - [ ] buy vitamins",
        ))
        self.assertEqual(blocks[1].item_text, "Call Jordan")

    def test_parse_cogs_blocks_can_include_carried_and_cancelled_states(self):
        content = "- [>] Carried\n- [-] Cancelled\n- [ ] Open\n"

        blocks = vault.parse_cogs_blocks(content, states={" ", ">", "-"})

        self.assertEqual([block.state for block in blocks], [">", "-", " "])

    def test_mark_block_state_changes_only_parent_marker(self):
        content = "- [ ] WALMART\n  - [ ] return battery\n"
        block = vault.parse_cogs_blocks(content)[0]

        marked = vault.mark_block_state(content, block, ">")

        self.assertEqual(marked, "- [>] WALMART\n  - [ ] return battery\n")

    def test_mark_block_state_rejects_unknown_state(self):
        block = vault.parse_cogs_blocks("- [ ] Call Jordan\n")[0]

        with self.assertRaises(ValueError):
            vault.mark_block_state("- [ ] Call Jordan\n", block, "?")

    def test_scan_daily_notes_lists_open_blocks_through_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            old_note = vault.ensure_daily_note("2026-05-01", daily_dir)
            old_note.write_text(
                old_note.read_text()
                + "- [ ] WALMART\n"
                  "  - [ ] return battery\n"
                  "- [x] Done\n"
            )
            future_note = vault.ensure_daily_note("2026-05-06", daily_dir)
            future_note.write_text(future_note.read_text() + "- [ ] Future thing\n")

            candidates = carry.scan_daily_notes(daily_dir, through_date="2026-05-03")

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].date, "2026-05-01")
            self.assertEqual(candidates[0].block.item_text, "WALMART")
            self.assertEqual(candidates[0].block.lines, (
                "- [ ] WALMART",
                "  - [ ] return battery",
            ))

    def test_print_candidates_summarizes_file_line_and_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            note = vault.ensure_daily_note("2026-05-01", daily_dir)
            note.write_text(note.read_text() + "- [ ] Call Jordan\n")
            candidate = carry.scan_daily_notes(daily_dir, through_date="2026-05-03")[0]
            stream = StringIO()

            with redirect_stdout(stream):
                carry.print_candidates([candidate])

            output = stream.getvalue()
            self.assertIn("1 open Cogs carry candidate", output)
            self.assertIn("2026-05-01", output)
            self.assertIn("- [ ] Call Jordan", output)

    def test_print_candidates_handles_empty_scan(self):
        stream = StringIO()

        with redirect_stdout(stream):
            carry.print_candidates([])

        self.assertIn("No open Cogs carry candidates found.", stream.getvalue())

    def test_build_default_plan_carries_every_candidate_to_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            note = vault.ensure_daily_note("2026-05-01", daily_dir)
            note.write_text(note.read_text() + "- [ ] Call Jordan\n")
            candidates = carry.scan_daily_notes(daily_dir, through_date="2026-05-03")

            decisions = carry.build_default_plan(candidates, "2026-05-04")

            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0].action, "carry")
            self.assertEqual(decisions[0].destination_date, "2026-05-04")

    def test_preview_plan_is_readable_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            note = vault.ensure_daily_note("2026-05-01", daily_dir)
            original = note.read_text() + "- [ ] Call Jordan\n"
            note.write_text(original)
            candidates = carry.scan_daily_notes(daily_dir, through_date="2026-05-03")
            decisions = carry.build_default_plan(candidates, "2026-05-04")

            preview = carry.preview_plan(decisions)

            self.assertIn("1 carry decision", preview)
            self.assertIn("carry", preview)
            self.assertIn("-> 2026-05-04", preview)
            self.assertIn("Call Jordan", preview)
            self.assertEqual(note.read_text(), original)

    def test_validate_decision_rejects_bad_carry_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            note = vault.ensure_daily_note("2026-05-01", daily_dir)
            note.write_text(note.read_text() + "- [ ] Call Jordan\n")
            candidate = carry.scan_daily_notes(daily_dir, through_date="2026-05-03")[0]

            with self.assertRaises(ValueError):
                carry.validate_decision(carry.CarryDecision(candidate, "invent"))
            with self.assertRaises(ValueError):
                carry.validate_decision(carry.CarryDecision(candidate, "carry"))
            with self.assertRaises(ValueError):
                carry.validate_decision(carry.CarryDecision(candidate, "skip", "2026-05-04"))

    def test_build_plan_document_creates_editable_json_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            note = vault.ensure_daily_note("2026-05-01", daily_dir)
            note.write_text(note.read_text() + "- [ ] Call Jordan\n")
            candidates = carry.scan_daily_notes(daily_dir, through_date="2026-05-03")

            plan = carry.build_plan_document(candidates, "2026-05-04")

            self.assertEqual(plan["kind"], "sprockets-cogs/carry-plan")
            self.assertEqual(plan["version"], 1)
            self.assertEqual(len(plan["items"]), 1)
            self.assertEqual(plan["items"][0]["action"], "carry")
            self.assertEqual(plan["items"][0]["destination_date"], "2026-05-04")
            self.assertEqual(plan["items"][0]["item_text"], "Call Jordan")
            self.assertEqual(carry.validate_plan_document(plan), [])

    def test_plan_document_round_trips_to_disk_without_vault_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp) / "daily"
            daily_dir.mkdir()
            note = vault.ensure_daily_note("2026-05-01", daily_dir)
            original = note.read_text() + "- [ ] Call Jordan\n"
            note.write_text(original)
            candidates = carry.scan_daily_notes(daily_dir, through_date="2026-05-03")
            plan = carry.build_plan_document(candidates, "2026-05-04")
            plan_path = Path(tmp) / "carry-plan.json"

            carry.write_plan_document(plan, plan_path)
            loaded = carry.load_plan_document(plan_path)

            self.assertEqual(loaded, plan)
            self.assertEqual(note.read_text(), original)

    def test_validate_plan_document_rejects_bad_actions_and_dates(self):
        plan = {
            "kind": "sprockets-cogs/carry-plan",
            "version": 1,
            "items": [
                {
                    "id": "one",
                    "action": "carry",
                    "destination_date": "",
                    "source": {"date": "2026-05-01", "path": "/tmp/a.md", "line": 1},
                    "item_text": "Call Jordan",
                    "lines": ["- [ ] Call Jordan"],
                },
                {
                    "id": "two",
                    "action": "skip",
                    "destination_date": "2026-05-04",
                    "source": {"date": "2026-05-01", "path": "/tmp/a.md", "line": 2},
                    "item_text": "Skip me",
                    "lines": ["- [ ] Skip me"],
                },
            ],
        }

        issues = carry.validate_plan_document(plan)

        self.assertIn("items[1].destination_date is required for carry", issues)
        self.assertIn("items[2].destination_date must be empty for skip", issues)

    def test_preview_plan_document_lists_editable_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            note = vault.ensure_daily_note("2026-05-01", daily_dir)
            note.write_text(note.read_text() + "- [ ] Call Jordan\n- [ ] Archive receipt\n")
            candidates = carry.scan_daily_notes(daily_dir, through_date="2026-05-03")
            plan = carry.build_plan_document(candidates, "2026-05-04")
            plan["items"][1]["action"] = "drop"
            plan["items"][1]["destination_date"] = ""

            preview = carry.preview_plan_document(plan)

            self.assertIn("2 carry plan item", preview)
            self.assertIn("carry", preview)
            self.assertIn("-> 2026-05-04", preview)
            self.assertIn("drop", preview)
            self.assertIn("Archive receipt", preview)


if __name__ == "__main__":
    unittest.main()

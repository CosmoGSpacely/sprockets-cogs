import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import specialists.astro.vault as vault
import specialists.cogs.carry as carry


class Stage129CarryIntelligenceTests(unittest.TestCase):
    def test_carry_status_reports_open_and_marked_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            old = vault.ensure_daily_note("2026-06-20", daily_dir)
            old.write_text(old.read_text() + "- [ ] Call Alex\n- [>] WALMART\n")

            status = carry.build_carry_status(daily_dir, through_date="2026-06-24")
            output = carry.format_carry_status(status)

        self.assertEqual(status.open_candidates, 1)
        self.assertEqual(status.marked_candidates, 1)
        self.assertEqual(status.oldest_open_date, "2026-06-20")
        self.assertIn("Cogs carry status", output)
        self.assertIn("open candidates: 1", output)

    def test_smart_plan_adds_rule_reasons_and_skips_ambiguous_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            old = vault.ensure_daily_note("2026-06-20", daily_dir)
            old.write_text(
                old.read_text()
                + "- [ ] Call Alex\n"
                  "- [ ] Maybe call plumber?\n"
            )
            candidates = carry.scan_daily_notes(daily_dir, through_date="2026-06-24")

            plan = carry.build_smart_plan_document(
                candidates,
                "2026-06-25",
                reference_date="2026-06-24",
            )
            preview = carry.preview_plan_document(plan)

        self.assertEqual([item["action"] for item in plan["items"]], ["carry", "skip"])
        self.assertEqual(plan["items"][0]["rule"], "carry_default")
        self.assertEqual(plan["items"][1]["rule"], "ambiguous_item")
        self.assertIn("carry_default", preview)
        self.assertIn("ambiguous carry wording", preview)

    def test_smart_plan_schedules_explicit_future_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            old = vault.ensure_daily_note("2026-06-20", daily_dir)
            old.write_text(old.read_text() + "- [ ] Pay insurance 2026-07-01\n")
            candidates = carry.scan_daily_notes(daily_dir, through_date="2026-06-24")

            plan = carry.build_smart_plan_document(
                candidates,
                "2026-06-25",
                reference_date="2026-06-24",
            )

        self.assertEqual(plan["items"][0]["action"], "schedule")
        self.assertEqual(plan["items"][0]["destination_date"], "2026-07-01")
        self.assertEqual(plan["items"][0]["rule"], "explicit_future_date")

    def test_smart_plan_uses_resolved_recurrence_destination_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            old = vault.ensure_daily_note("2026-06-20", daily_dir)
            old.write_text(old.read_text() + "- [ ] YOGA next 2 Saturdays at 10a\n")
            candidates = carry.scan_daily_notes(daily_dir, through_date="2026-06-24")

            plan = carry.build_smart_plan_document(
                candidates,
                "2026-06-25",
                reference_date="2026-06-24",
            )
            preview = carry.preview_apply_plan_document(plan)

        self.assertEqual(plan["items"][0]["action"], "schedule")
        self.assertEqual(plan["items"][0]["destination_date"], "2026-06-27")
        self.assertEqual(plan["items"][0]["item_text"], "10a YOGA")
        self.assertEqual(plan["items"][0]["destination_lines"], ["- [ ] 10a YOGA"])
        self.assertEqual(len(plan["items"][0]["recurrence_preview"]), 2)
        self.assertIn("schedule [ ] on 2026-06-27: 10a YOGA", preview)

    def test_sc_shaped_carry_commands_map_to_existing_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp) / "Cogs"
            plan_path = Path(tmp) / "carry-plan.json"
            old = vault.ensure_daily_note("2026-06-20", daily_dir)
            old.write_text(old.read_text() + "- [ ] Call Alex\n")
            stdout = StringIO()

            with redirect_stdout(stdout):
                carry.main([
                    "status",
                    "--daily-dir",
                    str(daily_dir),
                    "--through",
                    "2026-06-24",
                ])
                carry.main([
                    "plan",
                    "--smart",
                    "--daily-dir",
                    str(daily_dir),
                    "--through",
                    "2026-06-24",
                    "--to",
                    "2026-06-25",
                    "--reference-date",
                    "2026-06-24",
                    "--out",
                    str(plan_path),
                ])
                carry.main(["preview-plan", str(plan_path)])

            output = stdout.getvalue()
            self.assertTrue(plan_path.exists())

        self.assertIn("Cogs carry status", output)
        self.assertIn("Wrote smart carry plan", output)
        self.assertIn("carry_default", output)

    def test_obligation_projection_packet_is_review_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Sprockets" / "tasks" / "renew-passport.md"
            source.parent.mkdir(parents=True)
            source.write_text("# Renew Passport\n", encoding="utf-8")
            out = root / "review" / "projection.md"

            carry.write_obligation_projection_packet(
                source_path=source,
                destination_date="2026-07-01",
                item_text="Renew passport",
                reason="deadline needs a Cogs horizon item",
                out_path=out,
            )
            text = out.read_text(encoding="utf-8")

        self.assertIn("packet_type: sprockets-cogs/obligation-projection", text)
        self.assertIn("Proposed Cogs date: `2026-07-01`", text)
        self.assertIn('"operation": "create_cog"', text)

    def test_apply_smart_plan_uses_cogs_root_for_future_nested_destinations(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"
            old = vault.ensure_daily_note("2026-06-20", cogs_dir)
            old.write_text(old.read_text() + "- [ ] Pay insurance 2026-07-01\n")
            candidates = carry.scan_daily_notes(cogs_dir, through_date="2026-06-24")
            plan = carry.build_smart_plan_document(
                candidates,
                "2026-06-25",
                reference_date="2026-06-24",
            )

            results = carry.apply_plan_document(plan)

            july = vault.daily_note_path("2026-07-01", cogs_dir)
            misplaced = old.parent / "2026-07-01 Wed.md"

            self.assertIn("carried", results[0])
            self.assertTrue(july.exists())
            self.assertIn("- [ ] Pay insurance 2026-07-01", july.read_text(encoding="utf-8"))
            self.assertFalse(misplaced.exists())


if __name__ == "__main__":
    unittest.main()

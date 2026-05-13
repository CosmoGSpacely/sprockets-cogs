import tempfile
import unittest
from pathlib import Path

import cogs_specialist
import vault


class Stage39CogsSpecialistTests(unittest.TestCase):
    def test_inventory_delegates_to_existing_planning_inventory_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            specialist = cogs_specialist.CogsSpecialist(
                cogs_specialist.CogsSpecialistConfig(
                    cogs_dir=cogs_dir,
                    daily_dir=cogs_dir / "daily",
                )
            )

            inventory = specialist.inventory("2026-05-13")

            self.assertEqual(inventory.cogs_dir, cogs_dir)
            self.assertFalse(inventory.current_weekly_exists)
            self.assertFalse((cogs_dir / "weekly").exists())

    def test_carry_preview_builds_editable_plan_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            daily_dir = cogs_dir / "daily"
            note = vault.ensure_daily_note("2026-05-11", daily_dir)
            note.write_text(note.read_text() + "- [ ] Carry this forward\n")
            specialist = cogs_specialist.CogsSpecialist(
                cogs_specialist.CogsSpecialistConfig(
                    cogs_dir=cogs_dir,
                    daily_dir=daily_dir,
                )
            )

            preview = specialist.carry_preview(
                through_date="2026-05-12",
                destination_date="2026-05-13",
            )

            self.assertEqual(preview.candidate_count, 1)
            self.assertEqual(preview.plan["items"][0]["item_text"], "Carry this forward")
            self.assertIn("would be applied", preview.preview)
            self.assertIn("- [ ] Carry this forward", note.read_text())
            self.assertFalse(vault.daily_note_path("2026-05-13", daily_dir).exists())

    def test_nightly_preview_reports_existing_nightly_plan_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            daily_dir = cogs_dir / "daily"
            note = vault.ensure_daily_note("2026-05-11", daily_dir)
            note.write_text(note.read_text() + "- [ ] Carry tonight\n")
            specialist = cogs_specialist.CogsSpecialist(
                cogs_specialist.CogsSpecialistConfig(
                    cogs_dir=cogs_dir,
                    daily_dir=daily_dir,
                )
            )

            preview = specialist.nightly_preview(
                through_date="2026-05-12",
                destination_date="2026-05-13",
            )

            self.assertIn("Nightly carry report", preview.report)
            self.assertIn("- open candidates: 1", preview.report)
            self.assertIn("- writes: no", preview.report)
            self.assertIn("- [ ] Carry tonight", note.read_text())
            self.assertFalse(vault.daily_note_path("2026-05-13", daily_dir).exists())

    def test_planning_preview_reports_create_plan_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            specialist = cogs_specialist.CogsSpecialist(
                cogs_specialist.CogsSpecialistConfig(
                    cogs_dir=cogs_dir,
                    daily_dir=cogs_dir / "daily",
                )
            )

            preview = specialist.planning_preview("2026-05-13")

            self.assertEqual([item.kind for item in preview.create_plan], ["weekly", "monthly", "annual"])
            self.assertIn("Planning-note create preview", preview.report)
            self.assertIn("No files written.", preview.report)
            self.assertFalse((cogs_dir / "weekly" / "2026-W20.md").exists())

    def test_format_cogs_specialist_preview_marks_read_only_posture(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            specialist = cogs_specialist.CogsSpecialist(
                cogs_specialist.CogsSpecialistConfig(
                    cogs_dir=cogs_dir,
                    daily_dir=cogs_dir / "daily",
                )
            )
            preview = specialist.planning_preview("2026-05-13")

            output = cogs_specialist.format_cogs_specialist_preview(preview)

            self.assertIn("Cogs specialist planning preview", output)
            self.assertIn("- writes: no", output)
            self.assertIn("- planned items: 3", output)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

import cogs_naming
import cogs_planning
import vault


class Stage26CogsNamingTests(unittest.TestCase):
    def test_daily_filename_supports_legacy_and_iso_first_styles(self):
        self.assertEqual(cogs_naming.daily_filename("2026-05-11"), "Mon 11 May 2026.md")
        self.assertEqual(cogs_naming.daily_filename("2026-05-11", "iso-weekday"), "2026-05-11 Mon.md")
        self.assertEqual(cogs_naming.daily_filename("2026-05-11", "iso"), "2026-05-11.md")

    def test_planned_note_filenames_use_iso_first_periodic_names(self):
        names = cogs_naming.planned_note_filenames("2026-05-11")

        self.assertEqual(names["daily"], "2026-05-11 Mon.md")
        self.assertEqual(names["weekly"], "2026-W20.md")
        self.assertEqual(names["monthly"], "2026-05.md")
        self.assertEqual(names["annual"], "2026.md")
        self.assertEqual(names["five_wow_anchor"], "2026-05")

    def test_resolve_existing_daily_path_accepts_iso_first_or_legacy_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            iso_path = daily_dir / "2026-05-11 Mon.md"
            legacy_path = daily_dir / "Mon 11 May 2026.md"
            iso_path.write_text("---\ndate: 2026-05-11\n---\n")
            legacy_path.write_text("---\ndate: 2026-05-11\n---\n")

            resolved = cogs_naming.resolve_existing_daily_path("2026-05-11", daily_dir)

            self.assertEqual(resolved, iso_path)

    def test_vault_daily_note_path_uses_existing_iso_first_file_before_legacy_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            iso_path = daily_dir / "2026-05-11 Mon.md"
            iso_path.write_text("---\nnode_type: cogs/daily\ndate: 2026-05-11\n---\n\n")

            path = vault.ensure_daily_note("2026-05-11", daily_dir)

            self.assertEqual(path, iso_path)
            self.assertFalse((daily_dir / "Mon 11 May 2026.md").exists())

    def test_build_daily_rename_plan_is_read_only_and_detects_safe_renames(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            legacy = vault.ensure_daily_note("2026-05-11", daily_dir)

            plan = cogs_naming.build_daily_rename_plan(daily_dir)

            self.assertEqual(len(plan), 1)
            self.assertEqual(plan[0].date_iso, "2026-05-11")
            self.assertEqual(plan[0].source_path, legacy)
            self.assertEqual(plan[0].target_path.name, "2026-05-11 Mon.md")
            self.assertEqual(plan[0].status, "rename")
            self.assertTrue(legacy.exists())
            self.assertFalse(plan[0].target_path.exists())

    def test_build_daily_rename_plan_detects_collisions_and_invalid_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            vault.ensure_daily_note("2026-05-11", daily_dir)
            (daily_dir / "2026-05-11 Mon.md").write_text("---\ndate: 2026-05-11\n---\n")
            (daily_dir / "loose.md").write_text("no date here\n")

            plan = cogs_naming.build_daily_rename_plan(daily_dir)
            by_name = {item.source_path.name: item for item in plan}

            self.assertEqual(by_name["Mon 11 May 2026.md"].status, "collision")
            self.assertEqual(by_name["2026-05-11 Mon.md"].status, "already-current")
            self.assertEqual(by_name["loose.md"].status, "invalid")

    def test_planning_preview_formats_5wow_as_monthly_anchor(self):
        output = cogs_planning.format_planning_names("2026-05-11")

        self.assertIn("- daily: 2026-05-11 Mon.md", output)
        self.assertIn("- weekly: 2026-W20.md", output)
        self.assertIn("- monthly: 2026-05.md", output)
        self.assertIn("- 5WOW: monthly section anchor 2026-05", output)

    def test_daily_rename_plan_preview_is_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            vault.ensure_daily_note("2026-05-11", daily_dir)

            output = cogs_planning.format_daily_rename_plan(daily_dir)

            self.assertIn("Summary: rename: 1", output)
            self.assertIn("rename Mon 11 May 2026.md -> 2026-05-11 Mon.md", output)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

import specialists.cogs.naming as cogs_naming
import specialists.cogs.planning as cogs_planning
import specialists.astro.vault as vault


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
        self.assertEqual(names["5wow"], "2026-05-5WOW.md")
        self.assertEqual(names["12mf"], "2026-01-12MF.md")
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
            legacy = _write_legacy_daily_note(daily_dir, "2026-05-11")

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
            _write_legacy_daily_note(daily_dir, "2026-05-11")
            (daily_dir / "2026-05-11 Mon.md").write_text("---\ndate: 2026-05-11\n---\n")
            (daily_dir / "loose.md").write_text("no date here\n")

            plan = cogs_naming.build_daily_rename_plan(daily_dir)
            by_name = {item.source_path.name: item for item in plan}

            self.assertEqual(by_name["Mon 11 May 2026.md"].status, "collision")
            self.assertEqual(by_name["2026-05-11 Mon.md"].status, "already-current")
            self.assertEqual(by_name["loose.md"].status, "invalid")

    def test_planning_preview_formats_window_files_as_separate_surfaces(self):
        output = cogs_planning.format_planning_names("2026-05-11")

        self.assertIn("- daily: 2026-05-11 Mon.md", output)
        self.assertIn("- weekly: 2026-W20.md", output)
        self.assertIn("- monthly: 2026-05.md", output)
        self.assertIn("- 5WOW: 2026-05-5WOW.md", output)
        self.assertIn("- 12MF: 2026-01-12MF.md", output)

    def test_daily_rename_plan_preview_is_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            _write_legacy_daily_note(daily_dir, "2026-05-11")

            output = cogs_planning.format_daily_rename_plan(daily_dir)

            self.assertIn("Summary: rename: 1", output)
            self.assertIn("rename Mon 11 May 2026.md -> 2026-05-11 Mon.md", output)

    def test_inventory_counts_planning_notes_and_reports_current_periods(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            daily_dir = cogs_dir / "daily"
            weekly_dir = cogs_dir / "2026" / "05"
            monthly_dir = cogs_dir / "2026"
            annual_dir = cogs_dir
            weekly_dir.mkdir(parents=True)
            monthly_dir.mkdir(parents=True, exist_ok=True)
            annual_dir.mkdir(parents=True, exist_ok=True)
            _write_legacy_daily_note(daily_dir, "2026-05-11")
            (weekly_dir / "2026-W20.md").write_text("# Week\n")
            (monthly_dir / "2026-05.md").write_text("# Month\n")
            (annual_dir / "2026.md").write_text("# Year\n")

            inventory = cogs_planning.build_inventory(cogs_dir, "2026-05-11")

            self.assertEqual(inventory.daily_count, 1)
            self.assertEqual(inventory.daily_legacy_count, 1)
            self.assertEqual(inventory.weekly_count, 1)
            self.assertTrue(inventory.current_weekly_exists)
            self.assertTrue(inventory.current_monthly_exists)
            self.assertTrue(inventory.current_annual_exists)
            self.assertEqual(inventory.current_5wow_anchor, "2026-05")

    def test_vault_daily_note_path_prefers_iso_first_for_new_daily_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)

            path = vault.ensure_daily_note("2026-05-11", daily_dir)

            self.assertEqual(path.name, "2026-05-11 Mon.md")
            self.assertFalse((daily_dir / "Mon 11 May 2026.md").exists())

    def test_vault_daily_note_path_uses_nested_cogs_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"

            path = vault.ensure_daily_note("2026-05-11", cogs_dir)

            self.assertEqual(path, cogs_dir / "2026" / "05" / "20" / "2026-05-11 Mon.md")
            self.assertTrue(path.exists())

    def test_cogs_directory_migration_plan_moves_flat_periodic_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"
            daily = _write_legacy_daily_note(cogs_dir / "daily", "2026-05-11")
            weekly = cogs_dir / "weekly" / "2026-W20.md"
            monthly = cogs_dir / "monthly" / "2026-05.md"
            annual = cogs_dir / "annual" / "2026.md"
            for path, text in [
                (weekly, "---\nnode_type: cogs/weekly\nweek: 2026-W20\n---\n"),
                (monthly, "---\nnode_type: cogs/monthly\nmonth: 2026-05\n---\n"),
                (annual, "---\nnode_type: cogs/annual\nyear: 2026\n---\n"),
            ]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)

            plan = cogs_naming.build_cogs_directory_migration_plan(cogs_dir)
            by_kind = {item.kind: item for item in plan}

            self.assertEqual(by_kind["daily"].source_path, daily)
            self.assertEqual(by_kind["daily"].target_path, cogs_dir / "2026" / "05" / "20" / "2026-05-11 Mon.md")
            self.assertEqual(by_kind["weekly"].target_path, cogs_dir / "2026" / "05" / "2026-W20.md")
            self.assertEqual(by_kind["monthly"].target_path, cogs_dir / "2026" / "2026-05.md")
            self.assertEqual(by_kind["annual"].target_path, cogs_dir / "2026.md")
            self.assertEqual({item.status for item in plan}, {"move"})

    def test_cogs_directory_migration_apply_moves_flat_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"
            legacy = _write_legacy_daily_note(cogs_dir / "daily", "2026-05-11")

            output = cogs_planning.apply_cogs_directory_migration(cogs_dir)
            target = cogs_dir / "2026" / "05" / "20" / "2026-05-11 Mon.md"

            self.assertIn("Summary: moved: 1", output)
            self.assertFalse(legacy.exists())
            self.assertTrue(target.exists())

    def test_cogs_directory_migration_plan_blocks_duplicate_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"
            first = cogs_dir / "daily" / "First.md"
            second = cogs_dir / "daily" / "Second.md"
            for path in (first, second):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("---\nnode_type: cogs/daily\ndate: 2026-05-11\n---\n")

            plan = cogs_naming.build_cogs_directory_migration_plan(cogs_dir)

            self.assertEqual({item.status for item in plan}, {"collision"})
            self.assertTrue(all("multiple source files" in item.reason for item in plan))

    def test_daily_rename_apply_renames_reviewed_legacy_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            legacy = _write_legacy_daily_note(daily_dir, "2026-05-11")

            output = cogs_planning.apply_daily_renames(daily_dir)

            target = daily_dir / "2026-05-11 Mon.md"
            self.assertIn("Summary: renamed: 1", output)
            self.assertIn("renamed Mon 11 May 2026.md -> 2026-05-11 Mon.md", output)
            self.assertFalse(legacy.exists())
            self.assertTrue(target.exists())

    def test_daily_rename_apply_refuses_blocked_plan_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            legacy = _write_legacy_daily_note(daily_dir, "2026-05-11")
            (daily_dir / "loose.md").write_text("no date here\n")

            with self.assertRaisesRegex(ValueError, "blocked items"):
                cogs_naming.apply_daily_rename_plan(daily_dir)

            self.assertTrue(legacy.exists())
            self.assertFalse((daily_dir / "2026-05-11 Mon.md").exists())

    def test_inventory_preview_reports_missing_current_planning_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)

            output = cogs_planning.format_inventory(cogs_dir, "2026-05-11")

            self.assertIn("Daily notes: 0 total", output)
            self.assertIn("- weekly 2026-W20.md: missing", output)
            self.assertIn("- monthly 2026-05.md: missing", output)
            self.assertIn("- annual 2026.md: missing", output)
            self.assertIn("- 5WOW monthly anchor: 2026-05", output)

    def test_five_wow_grid_is_month_shaped_weekday_view(self):
        grid = cogs_planning.five_wow_grid("2026-05")

        self.assertEqual(len(grid), 5)
        self.assertEqual(grid[0], ["04-27", "04-28", "04-29", "04-30", "05-01"])
        self.assertEqual(grid[4], ["05-25", "05-26", "05-27", "05-28", "05-29"])

    def test_calendar_grid_is_seven_day_month_view(self):
        grid = cogs_planning.calendar_grid("2026-05")

        self.assertEqual(grid[0], ["", "", "", "", "01", "02", "03"])
        self.assertEqual(grid[1], ["04", "05", "06", "07", "08", "09", "10"])
        self.assertEqual(grid[4], ["25", "26", "27", "28", "29", "30", "31"])

    def test_five_wow_rows_are_vertical_weekday_view(self):
        rows = cogs_planning.five_wow_rows("2026-05")

        self.assertEqual(rows[0], (1, "Mon", "2026-04-27"))
        self.assertEqual(rows[4], (1, "Fri", "2026-05-01"))
        self.assertEqual(rows[-1], (5, "Fri", "2026-05-29"))

    def test_five_wow_rows_include_following_month_boundary_days(self):
        rows = cogs_planning.five_wow_rows("2026-06")

        self.assertEqual(rows[0], (1, "Mon", "2026-06-01"))
        self.assertEqual(rows[-1], (5, "Fri", "2026-07-03"))

    def test_month_preview_includes_month_note_and_5wow_table(self):
        output = cogs_planning.format_month_preview("2026-05")

        self.assertIn("Cogs month preview for 2026-05", output)
        self.assertIn("- monthly note: 2026-05.md", output)
        self.assertIn("- annual note: 2026.md", output)
        self.assertIn("- first ISO week: 2026-W18.md", output)
        self.assertIn("- calendar section: monthly Mon-Sun grid", output)
        self.assertIn("- 5WOW file: vertical weekday planning view", output)
        self.assertIn("- 12MF file: twelve-month forward look", output)
        self.assertIn("| M | T | W | Th | F | S | Su |", output)
        self.assertIn(
            "| 27<br><br> | 28<br><br> | 29<br><br> | 30<br><br> | "
            "01<br><br> | 02<br><br> | 03<br><br> |",
            output,
        )
        self.assertIn("| Date | Setting | Cogs | Date |", output)
        self.assertIn("| 27 Mon |  |  | 27 |", output)
        self.assertIn("| 01 Fri |  |  | 01 |", output)

    def test_daily_template_preview_is_flat_day_order_surface(self):
        output = cogs_planning.render_daily_note_template("2026-05-13")

        self.assertIn("node_type: cogs/daily", output)
        self.assertIn("date: 2026-05-13", output)
        self.assertIn("# Wed 13 May 2026", output)
        self.assertIn("likely day order", output)
        self.assertNotIn("## Appointments", output)
        self.assertNotIn("## Today", output)
        self.assertNotIn("## Carry", output)

    def test_weekly_template_preview_uses_iso_week_and_date_rails(self):
        output = cogs_planning.render_weekly_note_template("2026-05-13")

        self.assertIn("node_type: cogs/weekly", output)
        self.assertIn("week: 2026-W20", output)
        self.assertNotIn("cssclasses:", output)
        self.assertIn("# Week 20 - May 2026", output)
        self.assertIn("## CARRY", output)
        self.assertNotIn("## 5WOW", output)
        self.assertNotIn("## This Week", output)
        self.assertIn("| Date | Setting | Cogs | Date |", output)
        self.assertIn("| 11 Mon |  | <br><br><br> | 11 |", output)
        self.assertIn("| 17 Sun |  | <br><br><br> | 17 |", output)
        self.assertNotIn("[[", output)

    def test_monthly_template_preview_is_month_surface_only(self):
        output = cogs_planning.render_monthly_note_template("2026-05")

        self.assertIn("node_type: cogs/monthly", output)
        self.assertIn("month: 2026-05", output)
        self.assertNotIn("cssclasses:", output)
        self.assertNotIn("## Calendar", output)
        self.assertIn("| M | T | W | Th | F | S | Su |", output)
        self.assertIn(
            "| 27<br><br> | 28<br><br> | 29<br><br> | 30<br><br> | "
            "01<br><br> | 02<br><br> | 03<br><br> |",
            output,
        )
        self.assertNotIn("Apr 27", output)
        self.assertIn("## CARRY", output)
        self.assertIn("## KEY", output)
        self.assertNotIn("## 5WOW", output)
        self.assertNotIn("## 12-Month Forward Look", output)
        self.assertNotIn("### Fri 2026-05-01", output)
        self.assertIn("- `~~` setting span", output)

    def test_5wow_template_is_separate_window_surface(self):
        output = cogs_planning.render_five_wow_note_template("2026-06")

        self.assertIn("node_type: cogs/5wow", output)
        self.assertIn("month: 2026-06", output)
        self.assertNotIn("cssclasses:", output)
        self.assertNotIn("# 2026-06 5WOW", output)
        self.assertNotIn("Window surface:", output)
        self.assertIn("| Date | Setting | Cogs | Date |", output)
        self.assertIn("| 01 Mon |  |  | 01 |", output)
        self.assertIn("| 03 Fri |  |  | 03 |", output)

    def test_5wow_august_starts_in_august_and_includes_august_31_week(self):
        output = cogs_planning.render_five_wow_note_template("2026-08")
        rows = cogs_planning.five_wow_rows("2026-08")

        self.assertEqual(rows[0], (1, "Mon", "2026-08-03"))
        self.assertEqual(rows[-5], (5, "Mon", "2026-08-31"))
        self.assertEqual(rows[-1], (5, "Fri", "2026-09-04"))
        self.assertIn("| 31 Mon |  |  | 31 |", output)
        self.assertNotIn("[[", output)

    def test_12mf_template_is_separate_window_surface(self):
        output = cogs_planning.render_12mf_note_template("2026-06")

        self.assertIn("node_type: cogs/12mf", output)
        self.assertIn("year: 2026", output)
        self.assertIn("# 2026 12MF", output)
        self.assertIn("| + | Month | Cogs | Notes |", output)
        self.assertIn("| 1 | 2026-01 |  |  |", output)
        self.assertIn("| 12 | 2026-12 |  |  |", output)

    def test_forward_12_month_rows_cross_year_boundary(self):
        rows = cogs_planning.forward_12_month_rows("2026-06")

        self.assertEqual(rows[0], (1, "2026-01"))
        self.assertEqual(rows[-1], (12, "2026-12"))

    def test_annual_template_preview_includes_month_sections(self):
        output = cogs_planning.render_annual_note_template(2026)

        self.assertIn("node_type: cogs/annual", output)
        self.assertIn("year: 2026", output)
        self.assertIn("# 2026", output)
        self.assertIn("### 2026-01", output)
        self.assertIn("### 2026-12", output)

    def test_template_preview_dispatches_by_template_kind(self):
        self.assertIn("# Wed 13 May 2026", cogs_planning.format_template_preview("daily", "2026-05-13"))
        self.assertIn("# Week 20 - May 2026", cogs_planning.format_template_preview("weekly", "2026-05-13"))
        self.assertIn("# 2026-05", cogs_planning.format_template_preview("monthly", "2026-05"))
        self.assertIn("| 27 Mon |  |  | 27 |", cogs_planning.format_template_preview("5wow", "2026-05"))
        self.assertIn("# 2026 12MF", cogs_planning.format_template_preview("12mf", "2026-05"))
        self.assertIn("# 2026", cogs_planning.format_template_preview("annual", "2026"))

    def test_create_plan_for_date_previews_week_month_and_year_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)

            plan = cogs_planning.build_create_plan(cogs_dir, "2026-05-13")

            self.assertEqual([item.kind for item in plan], ["daily", "weekly", "monthly", "5wow", "12mf", "annual"])
            self.assertEqual([item.status for item in plan], ["create", "create", "create", "create", "create", "create"])
            self.assertEqual(plan[0].path, cogs_dir / "2026" / "05" / "20" / "2026-05-13 Wed.md")
            self.assertEqual(plan[1].path, cogs_dir / "2026" / "05" / "2026-W20.md")
            self.assertEqual(plan[2].path, cogs_dir / "2026" / "2026-05.md")
            self.assertEqual(plan[3].path, cogs_dir / "2026" / "2026-05-5WOW.md")
            self.assertEqual(plan[4].path, cogs_dir / "2026" / "2026-01-12MF.md")
            self.assertEqual(plan[5].path, cogs_dir / "2026.md")
            self.assertFalse(plan[0].path.exists())
            self.assertIn("node_type: cogs/daily", plan[0].template)

    def test_create_plan_for_month_previews_month_and_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)

            plan = cogs_planning.build_create_plan(cogs_dir, "2026-05")

            self.assertEqual([item.kind for item in plan], ["monthly", "5wow", "12mf", "annual"])
            self.assertEqual(plan[0].path, cogs_dir / "2026" / "2026-05.md")
            self.assertEqual(plan[1].path, cogs_dir / "2026" / "2026-05-5WOW.md")
            self.assertEqual(plan[2].path, cogs_dir / "2026" / "2026-01-12MF.md")
            self.assertEqual(plan[3].path, cogs_dir / "2026.md")

    def test_create_plan_marks_existing_targets_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            monthly = cogs_dir / "2026" / "2026-05.md"
            monthly.parent.mkdir(parents=True)
            monthly.write_text("existing\n")

            plan = cogs_planning.build_create_plan(cogs_dir, "2026-05")

            self.assertEqual(plan[0].status, "exists")
            self.assertEqual(plan[0].reason, "target already exists")
            self.assertEqual(monthly.read_text(), "existing\n")

    def test_create_plan_preview_reports_summary_and_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)

            output = cogs_planning.format_create_plan(cogs_dir, "2026-05-13")

            self.assertIn("Planning-note create preview for 2026-05-13", output)
            self.assertIn("Summary: create: 6", output)
            self.assertIn("create daily", output)
            self.assertIn("create weekly", output)
            self.assertIn("create monthly", output)
            self.assertIn("create 5wow", output)
            self.assertIn("create 12mf", output)
            self.assertIn("create annual", output)
            self.assertIn("No files written.", output)

    def test_filter_create_plan_can_limit_to_monthly(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            plan = cogs_planning.build_create_plan(cogs_dir, "2026-05-13")

            filtered = cogs_planning.filter_create_plan(plan, "monthly")

            self.assertEqual([item.kind for item in filtered], ["monthly"])

    def test_filter_create_plan_can_limit_to_daily(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            plan = cogs_planning.build_create_plan(cogs_dir, "2026-05-13")

            filtered = cogs_planning.filter_create_plan(plan, "daily")

            self.assertEqual([item.kind for item in filtered], ["daily"])

    def test_create_planning_notes_writes_missing_monthly_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)

            results = cogs_planning.create_planning_notes(cogs_dir, "2026-05", "monthly")

            monthly = cogs_dir / "2026" / "2026-05.md"
            self.assertEqual(results, [f"created monthly: {monthly}"])
            self.assertTrue(monthly.exists())
            self.assertNotIn("## 5WOW", monthly.read_text())
            self.assertFalse((cogs_dir / "2026.md").exists())

    def test_create_planning_notes_refuses_to_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            monthly = cogs_dir / "2026" / "2026-05.md"
            monthly.parent.mkdir(parents=True)
            monthly.write_text("manual\n")

            results = cogs_planning.create_planning_notes(cogs_dir, "2026-05", "monthly")

            self.assertEqual(results, [f"exists monthly: {monthly}"])
            self.assertEqual(monthly.read_text(), "manual\n")

    def test_ensure_current_planning_notes_creates_current_week_month_and_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)

            results = cogs_planning.ensure_current_planning_notes(cogs_dir, "2026-05-13")

            weekly = cogs_dir / "2026" / "05" / "2026-W20.md"
            monthly = cogs_dir / "2026" / "2026-05.md"
            five_wow = cogs_dir / "2026" / "2026-05-5WOW.md"
            twelve_mf = cogs_dir / "2026" / "2026-01-12MF.md"
            annual = cogs_dir / "2026.md"
            self.assertEqual(
                results,
                [
                    f"created weekly: {weekly}",
                    f"created monthly: {monthly}",
                    f"created 5wow: {five_wow}",
                    f"created 12mf: {twelve_mf}",
                    f"created annual: {annual}",
                ],
            )
            self.assertTrue(weekly.exists())
            self.assertTrue(monthly.exists())
            self.assertTrue(five_wow.exists())
            self.assertTrue(twelve_mf.exists())
            self.assertTrue(annual.exists())
            self.assertFalse((cogs_dir / "2026" / "05" / "20" / "2026-05-13 Wed.md").exists())

    def test_ensure_planning_horizon_creates_future_landing_surfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)

            results = cogs_planning.ensure_planning_horizon(cogs_dir, "2026-06-22")

            self.assertTrue((cogs_dir / "2026" / "06" / "26" / "2026-06-22 Mon.md").exists())
            self.assertTrue((cogs_dir / "2026" / "07" / "29" / "2026-07-13 Mon.md").exists())
            self.assertTrue((cogs_dir / "2026" / "06" / "2026-W26.md").exists())
            self.assertTrue((cogs_dir / "2026" / "09" / "2026-W38.md").exists())
            self.assertTrue((cogs_dir / "2026" / "2026-08.md").exists())
            self.assertTrue((cogs_dir / "2026" / "2026-08-5WOW.md").exists())
            self.assertTrue((cogs_dir / "2026" / "2026-01-12MF.md").exists())
            self.assertTrue((cogs_dir / "2027" / "2027-01-12MF.md").exists())
            self.assertTrue((cogs_dir / "2027.md").exists())
            self.assertIn("created daily:", "\n".join(results))
            self.assertIn("created annual:", "\n".join(results))

    def test_ensure_current_planning_notes_preserves_existing_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            monthly = cogs_dir / "2026" / "2026-05.md"
            monthly.parent.mkdir(parents=True)
            monthly.write_text("manual\n")

            results = cogs_planning.ensure_current_planning_notes(cogs_dir, "2026-05-13")

            self.assertIn(f"exists monthly: {monthly}", results)
            self.assertEqual(monthly.read_text(), "manual\n")

    def test_refresh_empty_planning_surfaces_rewrites_old_empty_surfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            monthly = cogs_dir / "2026" / "2026-06.md"
            five_wow = cogs_dir / "2026" / "2026-06-5WOW.md"
            weekly = cogs_dir / "2026" / "06" / "2026-W26.md"
            for path in (monthly, five_wow, weekly):
                path.parent.mkdir(parents=True, exist_ok=True)
            monthly.write_text(
                "---\nnode_type: cogs/monthly\nmonth: 2026-06\ntags: [cogs/monthly]\n---\n\n"
                "# 2026-06\n\n## Calendar\n\n## 5WOW\n\n"
                "| Week | Day | Date | Setting | Notes |\n|---|---|---|---|---|\n"
                "| 1 | Mon | 2026-06-01 |  |  |\n\n## Carry In\n\n## Dates\n"
            )
            five_wow.write_text(
                "---\nnode_type: cogs/5wow\nmonth: 2026-06\ntags: [cogs/5wow]\n---\n\n"
                "# 2026-06 5WOW\n\n"
                "| Week | Day | Date | Cogs | Notes |\n|---|---|---|---|---|\n"
                "| 1 | Mon | 2026-06-01 |  |  |\n"
            )
            weekly.write_text(
                "---\nnode_type: cogs/weekly\nweek: 2026-W26\ntags: [cogs/weekly]\n---\n\n"
                "# 2026-W26\n\n## Carry In\n\n## Weekdays\n\n### Mon 2026-06-22\n"
            )

            results = cogs_planning.refresh_empty_planning_surfaces(cogs_dir, "2026-06-25")

            self.assertIn(f"refreshed monthly: {monthly}", results)
            self.assertIn(f"refreshed 5wow: {five_wow}", results)
            self.assertIn(f"refreshed weekly: {weekly}", results)
            self.assertIn("## CARRY", monthly.read_text())
            self.assertIn("| Date | Setting | Cogs | Date |", five_wow.read_text())
            self.assertIn("| Date | Setting | Cogs | Date |", weekly.read_text())

    def test_refresh_empty_planning_surfaces_preserves_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            five_wow = cogs_dir / "2026" / "2026-06-5WOW.md"
            five_wow.parent.mkdir(parents=True, exist_ok=True)
            five_wow.write_text(
                "---\nnode_type: cogs/5wow\nmonth: 2026-06\ntags: [cogs/5wow]\n---\n\n"
                "# 2026-06 5WOW\n\n"
                "| Week | Day | Date | Cogs | Notes |\n|---|---|---|---|---|\n"
                "| 1 | Mon | 2026-06-01 | - [ ] real item |  |\n"
            )

            results = cogs_planning.refresh_empty_planning_surfaces(cogs_dir, "2026-06-25")

            self.assertIn(f"preserve 5wow: {five_wow}", results)
            self.assertIn("real item", five_wow.read_text())

    def test_refresh_empty_planning_surfaces_repairs_buggy_5wow_rails(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            five_wow = cogs_dir / "2026" / "2026-08-5WOW.md"
            five_wow.parent.mkdir(parents=True, exist_ok=True)
            five_wow.write_text(
                "---\nnode_type: cogs/5wow\nmonth: 2026-08\ntags: [cogs/5wow]\n---\n\n"
                "# 2026-08 5WOW\n\n"
                "| Date | Setting | Cogs | Date |\n|---|---|---|---|\n"
                "| [[2026-07-27 Mon|27 Mon]] |  |  | [[2026-07-27 Mon|27]] |\n"
            )

            results = cogs_planning.refresh_empty_planning_surfaces(cogs_dir, "2026-06-25")

            self.assertIn(f"refreshed 5wow: {five_wow}", results)
            repaired = five_wow.read_text()
            self.assertIn("| 03 Mon |  |  | 03 |", repaired)
            self.assertIn("| 31 Mon |  |  | 31 |", repaired)
            self.assertNotIn("[[", repaired)
            self.assertNotIn("# 2026-08 5WOW", repaired)

    def test_refresh_empty_planning_surfaces_updates_empty_calendar_month(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            monthly = cogs_dir / "2026" / "2026-08.md"
            monthly.parent.mkdir(parents=True, exist_ok=True)
            monthly.write_text(
                "---\nnode_type: cogs/monthly\nmonth: 2026-08\ntags: [cogs/monthly]\n---\n\n"
                "# 2026-08\n\n"
                "| M | T | W | Th | F | S | Su |\n|---|---|---|---|---|---|---|\n"
                "| Jul 27<br> | Jul 28<br> | Jul 29<br> | Jul 30<br> | Jul 31<br> | 01<br> | 02<br> |\n\n"
                "## CARRY\n\n## KEY\n\n- `~~` setting span\n"
            )

            results = cogs_planning.refresh_empty_planning_surfaces(cogs_dir, "2026-06-25")

            self.assertIn(f"refreshed monthly: {monthly}", results)
            refreshed = monthly.read_text()
            self.assertNotIn("cssclasses:", refreshed)
            self.assertIn(
                "| 27<br><br> | 28<br><br> | 29<br><br> | 30<br><br> | "
                "31<br><br> | 01<br><br> | 02<br><br> |",
                refreshed,
            )
            self.assertNotIn("Jul 27", refreshed)

    def test_refresh_empty_planning_surfaces_removes_empty_obsolete_rolling_12mf(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp)
            obsolete = cogs_dir / "2026" / "2026-06-12MF.md"
            annual = cogs_dir / "2026" / "2026-01-12MF.md"
            obsolete.parent.mkdir(parents=True, exist_ok=True)
            obsolete.write_text(
                "---\nnode_type: cogs/12mf\nmonth: 2026-06\ntags: [cogs/12mf]\n---\n\n"
                "# 2026-06 12MF\n\n"
                "| + | Month | Cogs | Notes |\n|---|---|---|---|\n"
                "| 1 | 2026-06 |  |  |\n"
            )
            annual.write_text(cogs_planning.render_12mf_note_template("2026-01"))

            results = cogs_planning.refresh_empty_planning_surfaces(cogs_dir, "2026-06-25")

            self.assertIn(f"removed obsolete 12mf: {obsolete}", results)
            self.assertFalse(obsolete.exists())
            self.assertTrue(annual.exists())


def _write_legacy_daily_note(daily_dir: Path, date_iso: str) -> Path:
    path = cogs_naming.daily_path(date_iso, daily_dir, "legacy")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nnode_type: cogs/daily\ndate: {date_iso}\ntags: [cogs/daily]\n---\n\n"
        f"# {cogs_naming.daily_heading(date_iso)}\n\n"
    )
    return path


if __name__ == "__main__":
    unittest.main()

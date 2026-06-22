from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import specialists.astro.obsidian_views as obsidian_views


class Stage58ObsidianViewsTests(unittest.TestCase):
    def test_view_note_set_has_expected_additive_paths(self):
        notes = obsidian_views.stage_58_view_notes()

        self.assertEqual(
            [str(note.relative_path) for note in notes],
            [
                "HOME.md",
                "Sprockets/areas-index.md",
                "Sprockets/goals-index.md",
                "Sprockets/tasks-index.md",
                "Sprockets/projects-index.md",
                "Sprockets/contacts-index.md",
                "Sprockets/hierarchy-view.md",
                "Cogs/cogs-navigation.md",
                "REVIEW.md",
            ],
        )

    def test_stage_59_navigation_refresh_scope_is_home_and_cogs_navigation_only(self):
        notes = obsidian_views.stage_59_navigation_notes()

        self.assertEqual(
            [str(note.relative_path) for note in notes],
            [
                "HOME.md",
                "Sprockets/areas-index.md",
                "Sprockets/goals-index.md",
                "Sprockets/tasks-index.md",
                "Sprockets/projects-index.md",
                "Cogs/cogs-navigation.md",
            ],
        )

    def test_preview_shows_target_paths_and_generated_markdown(self):
        notes = obsidian_views.stage_58_view_notes()
        preview = obsidian_views.format_view_preview(notes, vault_dir=Path("/vault"))

        self.assertIn("Obsidian view-note preview", preview)
        self.assertIn("- writes: no", preview)
        self.assertIn("=== /vault/HOME.md ===", preview)
        self.assertIn('FROM "Sprockets/tasks"', preview)
        self.assertIn('SORT date DESC', preview)
        self.assertIn('FROM "review"', preview)

    def test_home_note_is_stable_navigation_without_templater_tokens(self):
        home = _note_markdown("HOME.md")

        self.assertIn("[[Cogs/cogs-navigation|Cogs navigation]]", home)
        self.assertIn("[[Sprockets/areas-index|Areas]]", home)
        self.assertIn("[[Sprockets/goals-index|Goals]]", home)
        self.assertIn("[[Sprockets/hierarchy-view|Hierarchy]]", home)
        self.assertIn("[[REVIEW|Jane review]]", home)
        self.assertIn("## Germane Today", home)
        self.assertIn("Unsafe signals", home)
        self.assertIn("user_pin = true", home)
        self.assertNotIn("tp.date.now", home)

    def test_index_notes_use_live_stage_58_field_posture(self):
        areas_index = _note_markdown("Sprockets/areas-index.md")
        goals_index = _note_markdown("Sprockets/goals-index.md")
        task_index = _note_markdown("Sprockets/tasks-index.md")
        projects_index = _note_markdown("Sprockets/projects-index.md")
        contacts_index = _note_markdown("Sprockets/contacts-index.md")

        self.assertIn('node_type = "sprockets/area"', areas_index)
        self.assertIn('node_type = "sprockets/goal"', goals_index)
        self.assertIn("View surface only", areas_index)
        self.assertIn('node_type = "sprockets/task"', task_index)
        self.assertIn('status != "complete"', task_index)
        self.assertIn("parent AS Parent", task_index)
        self.assertNotIn("area AS Area", task_index)
        self.assertIn('node_type = "sprockets/project"', projects_index)
        self.assertNotIn("status = \"active\"", projects_index)
        self.assertIn('node_type = "sprockets/contact"', contacts_index)
        self.assertIn("SORT title ASC", contacts_index)

    def test_review_landing_stays_outside_queue_and_surfaces_pending_review_notes(self):
        review_landing = _note_markdown("REVIEW.md")

        self.assertIn("# Jane Review", review_landing)
        self.assertIn('FROM "review"', review_landing)
        self.assertIn('node_type = "review" AND reviewed = false', review_landing)
        self.assertNotIn("scripts/review` for approve", review_landing)

    def test_hierarchy_and_cogs_notes_keep_safe_first_shape(self):
        hierarchy = _note_markdown("Sprockets/hierarchy-view.md")
        cogs_navigation = _note_markdown("Cogs/cogs-navigation.md")

        self.assertIn("flat and parent-aware", hierarchy)
        self.assertIn("parent AS Parent", hierarchy)
        self.assertNotIn("dataviewjs", hierarchy)
        self.assertIn('node_type = "cogs/daily" AND date', cogs_navigation)
        self.assertIn("SORT date DESC", cogs_navigation)
        self.assertIn('node_type = "cogs/weekly"', cogs_navigation)
        self.assertIn("## Current Planning", cogs_navigation)
        self.assertIn("### Today", cogs_navigation)
        self.assertIn('date = date(today)', cogs_navigation)
        self.assertIn("### This Week", cogs_navigation)
        self.assertIn('week = dateformat(date(today), "kkkk-\'W\'WW")', cogs_navigation)
        self.assertIn("### This Month and 5WOW", cogs_navigation)
        self.assertIn('link(file.path + "#5WOW", "Open 5WOW")', cogs_navigation)
        self.assertIn('month = dateformat(date(today), "yyyy-MM")', cogs_navigation)
        self.assertIn("### Far Horizon", cogs_navigation)
        self.assertIn('string(year) = dateformat(date(today), "yyyy")', cogs_navigation)

    def test_cli_is_read_only_for_target_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            stdout = StringIO()

            with redirect_stdout(stdout):
                obsidian_views.main(["--vault-dir", str(vault)])

            self.assertIn(str(vault / "HOME.md"), stdout.getvalue())
            self.assertFalse(vault.exists())

    def test_create_view_notes_writes_missing_notes_and_preserves_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            home = vault / "HOME.md"
            home.parent.mkdir(parents=True)
            home.write_text("manual home\n", encoding="utf-8")

            results = obsidian_views.create_view_notes(
                obsidian_views.stage_58_view_notes(),
                vault_dir=vault,
            )

            self.assertEqual(results[0].status, "exists")
            self.assertEqual(home.read_text(encoding="utf-8"), "manual home\n")
            self.assertEqual(results[1].status, "created")
            self.assertTrue((vault / "Sprockets/areas-index.md").exists())
            self.assertTrue((vault / "Sprockets/goals-index.md").exists())
            self.assertTrue((vault / "Sprockets/tasks-index.md").exists())
            self.assertTrue((vault / "Cogs/cogs-navigation.md").exists())

    def test_create_cli_reports_created_then_existing_for_idempotent_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            first_stdout = StringIO()
            second_stdout = StringIO()

            with redirect_stdout(first_stdout):
                obsidian_views.main(["--vault-dir", str(vault), "--create"])
            with redirect_stdout(second_stdout):
                obsidian_views.main(["--vault-dir", str(vault), "--create"])

            self.assertIn("- writes: vault", first_stdout.getvalue())
            self.assertIn("- summary: created: 9", first_stdout.getvalue())
            self.assertIn("- summary: exists: 9", second_stdout.getvalue())

    def test_refresh_navigation_notes_replaces_reviewed_navigation_notes_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            home = vault / "HOME.md"
            tasks = vault / "Sprockets" / "tasks-index.md"
            home.parent.mkdir(parents=True)
            tasks.parent.mkdir(parents=True)
            home.write_text("old home\n", encoding="utf-8")
            tasks.write_text("manual tasks\n", encoding="utf-8")

            results = obsidian_views.refresh_navigation_notes(
                obsidian_views.stage_59_navigation_notes(),
                vault_dir=vault,
            )

            self.assertEqual([result.status for result in results], ["updated", "created", "created", "updated", "created", "created"])
            self.assertIn("# Sprockets-Cogs Home", home.read_text(encoding="utf-8"))
            self.assertTrue((vault / "Sprockets" / "areas-index.md").exists())
            self.assertTrue((vault / "Sprockets" / "goals-index.md").exists())
            self.assertTrue((vault / "Cogs" / "cogs-navigation.md").exists())
            self.assertIn("# Open Sprockets Tasks", tasks.read_text(encoding="utf-8"))

    def test_refresh_navigation_cli_reports_reviewed_write_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            stdout = StringIO()

            with redirect_stdout(stdout):
                obsidian_views.main(["--vault-dir", str(vault), "--refresh-navigation"])

            self.assertIn("- notes: 6", stdout.getvalue())
            self.assertIn("- summary: created: 6", stdout.getvalue())
            self.assertTrue((vault / "HOME.md").exists())
            self.assertTrue((vault / "Sprockets" / "tasks-index.md").exists())
            self.assertFalse((vault / "REVIEW.md").exists())


def _note_markdown(relative_path: str) -> str:
    return {
        str(note.relative_path): note.markdown
        for note in obsidian_views.stage_58_view_notes()
    }[relative_path]


if __name__ == "__main__":
    unittest.main()

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import obsidian_views


class Stage58ObsidianViewsTests(unittest.TestCase):
    def test_view_note_set_has_expected_additive_paths(self):
        notes = obsidian_views.stage_58_view_notes()

        self.assertEqual(
            [str(note.relative_path) for note in notes],
            [
                "HOME.md",
                "Sprockets/tasks-index.md",
                "Sprockets/projects-index.md",
                "Sprockets/contacts-index.md",
                "Sprockets/hierarchy-view.md",
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
        self.assertIn("Jane review surfacing arrives in Stage 60.", preview)

    def test_home_note_is_stable_navigation_without_templater_tokens(self):
        home = _note_markdown("HOME.md")

        self.assertIn("[[Cogs/cogs-navigation|Cogs navigation]]", home)
        self.assertIn("[[Cogs/daily|Daily notes]]", home)
        self.assertIn("[[Sprockets/hierarchy-view|Hierarchy]]", home)
        self.assertNotIn("tp.date.now", home)

    def test_index_notes_use_live_stage_58_field_posture(self):
        task_index = _note_markdown("Sprockets/tasks-index.md")
        projects_index = _note_markdown("Sprockets/projects-index.md")
        contacts_index = _note_markdown("Sprockets/contacts-index.md")

        self.assertIn('node_type = "sprockets/task"', task_index)
        self.assertIn('status != "complete"', task_index)
        self.assertIn("parent AS Parent", task_index)
        self.assertNotIn("area AS Area", task_index)
        self.assertIn('node_type = "sprockets/project"', projects_index)
        self.assertNotIn("status = \"active\"", projects_index)
        self.assertIn('node_type = "sprockets/contact"', contacts_index)
        self.assertIn("SORT title ASC", contacts_index)

    def test_hierarchy_and_cogs_notes_keep_safe_first_shape(self):
        hierarchy = _note_markdown("Sprockets/hierarchy-view.md")
        cogs_navigation = _note_markdown("Cogs/cogs-navigation.md")

        self.assertIn("flat and parent-aware", hierarchy)
        self.assertIn("parent AS Parent", hierarchy)
        self.assertNotIn("dataviewjs", hierarchy)
        self.assertIn('node_type = "cogs/daily" AND date', cogs_navigation)
        self.assertIn("SORT date DESC", cogs_navigation)
        self.assertIn('node_type = "cogs/weekly"', cogs_navigation)

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
            self.assertIn("- summary: created: 6", first_stdout.getvalue())
            self.assertIn("- summary: exists: 6", second_stdout.getvalue())


def _note_markdown(relative_path: str) -> str:
    return {
        str(note.relative_path): note.markdown
        for note in obsidian_views.stage_58_view_notes()
    }[relative_path]


if __name__ == "__main__":
    unittest.main()

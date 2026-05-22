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

    def test_cli_is_read_only_for_target_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            stdout = StringIO()

            with redirect_stdout(stdout):
                obsidian_views.main(["--vault-dir", str(vault)])

            self.assertIn(str(vault / "HOME.md"), stdout.getvalue())
            self.assertFalse(vault.exists())


if __name__ == "__main__":
    unittest.main()

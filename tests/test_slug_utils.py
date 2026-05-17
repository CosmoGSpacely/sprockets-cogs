import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import agentic_loop
import entity_state
import sprockets_specialist
from models import SprocketsContact, SprocketsTask
from slug_utils import slugify


class SlugUtilsTests(unittest.TestCase):
    def test_slugify_normalizes_punctuation_whitespace_and_case(self):
        self.assertEqual(slugify("  Hello, Sprockets & Cogs!  "), "hello-sprockets-cogs")

    def test_slugify_truncates_to_canonical_sixty_characters(self):
        title = "This is a very long hierarchy proposal title that should be truncated consistently"

        self.assertEqual(slugify(title), "this-is-a-very-long-hierarchy-proposal-title-that-should-be")
        self.assertLessEqual(len(slugify(title)), 60)

    def test_live_writer_and_sprockets_preview_use_same_long_title_slug(self):
        title = "This is a very long hierarchy proposal title that should be truncated consistently"
        expected_slug = slugify(title)

        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            goal_path = vault / "Sprockets" / "goals" / "build-sprockets-cogs.md"
            goal_path.parent.mkdir(parents=True)
            goal_path.write_text(
                "---\n"
                "node_type: sprockets/goal\n"
                "uuid: goal-1\n"
                "title: Build Sprockets-Cogs\n"
                "---\n\n"
                "# Build Sprockets-Cogs\n"
            )
            specialist = sprockets_specialist.SprocketsSpecialist(
                sprockets_specialist.SprocketsSpecialistConfig(vault_dir=vault)
            )

            preview = specialist.hierarchy_proposal_preview(
                "project",
                title,
                "Build Sprockets-Cogs",
            )

            self.assertEqual(preview.slug, expected_slug)

            task_folder = vault / "Sprockets" / "tasks"
            task = SprocketsTask(node_type="sprockets/task", title=title, confidence="high")
            agentic_loop._write_sprockets_node(task, task_folder)

            self.assertTrue((task_folder / f"{expected_slug}.md").exists())

    def test_entity_state_uses_canonical_slug_key_for_long_titles(self):
        title = "This is a very long hierarchy proposal title that should be truncated consistently"
        expected_slug = slugify(title)

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "entity_state.json"
            contact = SprocketsContact(node_type="sprockets/contact", title=title, confidence="high")

            with patch.object(entity_state, "STATE_PATH", state_path):
                entity_state.upsert_entity(contact)
                state = entity_state.load_state()

            self.assertIn(expected_slug, state)
            self.assertEqual(state[expected_slug]["title"], title)

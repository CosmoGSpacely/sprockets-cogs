import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import sprockets_specialist


def write_node(vault: Path, folder: str, slug: str, metadata: str = "") -> Path:
    path = vault / "Sprockets" / folder / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{metadata}---\n\n# {slug}\n")
    return path


class Stage40SprocketsSpecialistTests(unittest.TestCase):
    def test_inventory_delegates_to_existing_hierarchy_inspection_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "areas",
                "learn-agentic-ai",
                "node_type: sprockets/area\n"
                "uuid: area-1\n"
                "title: Learn Agentic AI\n",
            )
            write_node(
                vault,
                "goals",
                "build-sprockets-cogs",
                "node_type: sprockets/goal\n"
                "uuid: goal-1\n"
                "title: Build Sprockets-Cogs\n"
                "parent: [[learn-agentic-ai]]\n",
            )
            specialist = sprockets_specialist.SprocketsSpecialist(
                sprockets_specialist.SprocketsSpecialistConfig(vault_dir=vault)
            )

            preview = specialist.inventory()

            self.assertEqual(preview.vault_dir, vault)
            self.assertEqual(len(preview.nodes), 2)
            self.assertEqual(preview.nodes[0].slug, "learn-agentic-ai")
            self.assertEqual(preview.nodes[1].parent_slug, "learn-agentic-ai")
            self.assertEqual(preview.issues, ())
            self.assertIn("Hierarchy counts:", preview.report)

    def test_parent_match_preview_matches_hierarchy_titles_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "projects",
                "phase-3-memory-enhancement",
                "node_type: sprockets/project\n"
                "uuid: project-1\n"
                "title: Phase 3 - Memory Enhancement\n",
            )
            write_node(
                vault,
                "contacts",
                "phase-3-contact",
                "node_type: sprockets/contact\n"
                "uuid: contact-1\n"
                "title: Phase 3 Contact\n",
            )
            specialist = sprockets_specialist.SprocketsSpecialist(
                sprockets_specialist.SprocketsSpecialistConfig(vault_dir=vault)
            )

            preview = specialist.parent_match_preview("Phase 3 - Memory")

            self.assertTrue(preview.matched)
            self.assertFalse(preview.ambiguous)
            self.assertEqual(preview.slug, "phase-3-memory-enhancement")
            self.assertEqual(preview.uuid, "project-1")

    def test_parent_match_preview_reports_ambiguity_without_guessing(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "projects",
                "phase-2-hardening",
                "node_type: sprockets/project\n"
                "uuid: project-1\n"
                "title: Phase 2 - Hardening\n",
            )
            write_node(
                vault,
                "projects",
                "phase-2-handoff",
                "node_type: sprockets/project\n"
                "uuid: project-2\n"
                "title: Phase 2 - Handoff\n",
            )
            specialist = sprockets_specialist.SprocketsSpecialist(
                sprockets_specialist.SprocketsSpecialistConfig(vault_dir=vault)
            )

            preview = specialist.parent_match_preview("Phase 2")

            self.assertFalse(preview.matched)
            self.assertTrue(preview.ambiguous)
            self.assertCountEqual(
                [title for _, title, _ in preview.matches],
                ["Phase 2 - Hardening", "Phase 2 - Handoff"],
            )

    def test_hierarchy_context_preview_formats_parent_context_without_note_bodies(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "goals",
                "build-sprockets-cogs",
                "node_type: sprockets/goal\n"
                "uuid: goal-1\n"
                "title: Build Sprockets-Cogs\n",
            )
            write_node(
                vault,
                "projects",
                "phase-4-multi-agent",
                "node_type: sprockets/project\n"
                "uuid: project-1\n"
                "title: Phase 4 - Multi-Agent Architecture\n"
                "parent: [[build-sprockets-cogs]]\n",
            )
            specialist = sprockets_specialist.SprocketsSpecialist(
                sprockets_specialist.SprocketsSpecialistConfig(vault_dir=vault)
            )

            context = specialist.hierarchy_context_preview()

            self.assertIn("Goal: Build Sprockets-Cogs", context)
            self.assertIn(
                "Project: Phase 4 - Multi-Agent Architecture (under Build Sprockets-Cogs)",
                context,
            )

    def test_hierarchy_titles_returns_longest_first_parent_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "areas",
                "learn-agentic-ai",
                "node_type: sprockets/area\n"
                "uuid: area-1\n"
                "title: Learn Agentic AI\n",
            )
            write_node(
                vault,
                "projects",
                "phase-4-multi-agent",
                "node_type: sprockets/project\n"
                "uuid: project-1\n"
                "title: Phase 4 - Multi-Agent Architecture\n",
            )
            specialist = sprockets_specialist.SprocketsSpecialist(
                sprockets_specialist.SprocketsSpecialistConfig(vault_dir=vault)
            )

            self.assertEqual(
                specialist.hierarchy_titles(),
                ["Phase 4 - Multi-Agent Architecture", "Learn Agentic AI"],
            )

    def test_ambiguous_parent_matches_reports_hierarchy_matches_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "projects",
                "phase-2-hardening",
                "node_type: sprockets/project\n"
                "uuid: project-1\n"
                "title: Phase 2 - Hardening\n",
            )
            write_node(
                vault,
                "projects",
                "phase-2-handoff",
                "node_type: sprockets/project\n"
                "uuid: project-2\n"
                "title: Phase 2 - Handoff\n",
            )
            write_node(
                vault,
                "contacts",
                "phase-2-contact",
                "node_type: sprockets/contact\n"
                "uuid: contact-1\n"
                "title: Phase 2 Contact\n",
            )
            specialist = sprockets_specialist.SprocketsSpecialist(
                sprockets_specialist.SprocketsSpecialistConfig(vault_dir=vault)
            )

            matches = specialist.ambiguous_parent_matches("Phase 2")

            self.assertCountEqual(
                [title for _, title, _ in matches],
                ["Phase 2 - Hardening", "Phase 2 - Handoff"],
            )

    def test_main_prints_read_only_inventory_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "areas",
                "learn-agentic-ai",
                "node_type: sprockets/area\n"
                "uuid: area-1\n"
                "title: Learn Agentic AI\n",
            )
            buf = io.StringIO()

            with redirect_stdout(buf):
                sprockets_specialist.main(["--vault", str(vault), "--inventory"])

            output = buf.getvalue()
            self.assertIn("Sprockets specialist inventory preview", output)
            self.assertIn("- hierarchy nodes: 1", output)
            self.assertIn("- writes: no", output)

    def test_main_prints_parent_match_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "projects",
                "phase-3-memory-enhancement",
                "node_type: sprockets/project\n"
                "uuid: project-1\n"
                "title: Phase 3 - Memory Enhancement\n",
            )
            buf = io.StringIO()

            with redirect_stdout(buf):
                sprockets_specialist.main(
                    ["--vault", str(vault), "--parent-match", "Phase 3 - Memory"]
                )

            output = buf.getvalue()
            self.assertIn("Sprockets specialist parent match preview", output)
            self.assertIn("- result: matched", output)
            self.assertIn("- parent: [[phase-3-memory-enhancement]]", output)


if __name__ == "__main__":
    unittest.main()

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

    def test_hierarchy_proposal_preview_accepts_project_under_goal_without_writing(self):
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
            specialist = sprockets_specialist.SprocketsSpecialist(
                sprockets_specialist.SprocketsSpecialistConfig(vault_dir=vault)
            )

            preview = specialist.hierarchy_proposal_preview(
                "project",
                "Phase 5 - Voice Interface",
                "Build Sprockets-Cogs",
            )

            self.assertEqual(preview.node_type, "sprockets/project")
            self.assertEqual(preview.slug, "phase-5---voice-interface")
            self.assertEqual(preview.parent_slug, "build-sprockets-cogs")
            self.assertEqual(preview.parent_title, "Build Sprockets-Cogs")
            self.assertEqual(preview.issues, ())
            self.assertFalse((vault / "Sprockets" / "projects" / "phase-5-voice-interface.md").exists())

    def test_hierarchy_proposal_preview_requires_goal_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            specialist = sprockets_specialist.SprocketsSpecialist(
                sprockets_specialist.SprocketsSpecialistConfig(vault_dir=vault)
            )

            preview = specialist.hierarchy_proposal_preview("goal", "Build Trademark Digger")

            self.assertEqual(preview.node_type, "sprockets/goal")
            self.assertIn("sprockets/goal requires a parent", preview.issues)

    def test_hierarchy_proposal_preview_rejects_parent_for_area(self):
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
            specialist = sprockets_specialist.SprocketsSpecialist(
                sprockets_specialist.SprocketsSpecialistConfig(vault_dir=vault)
            )

            preview = specialist.hierarchy_proposal_preview(
                "area",
                "Public Portfolio",
                "Learn Agentic AI",
            )

            self.assertEqual(preview.node_type, "sprockets/area")
            self.assertIn("sprockets/area does not accept a parent", preview.issues)

    def test_hierarchy_proposal_preview_detects_duplicate_titles(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
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

            preview = specialist.hierarchy_proposal_preview(
                "project",
                "Phase 4 - Multi-Agent Architecture",
                "Missing Goal",
            )

            self.assertEqual(preview.duplicate_slug, "phase-4-multi-agent")
            self.assertIn(
                "duplicate sprockets/project title exists: Phase 4 - Multi-Agent Architecture "
                "(phase-4-multi-agent)",
                preview.issues,
            )

    def test_hierarchy_proposal_preview_reports_ambiguous_parent(self):
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
                "areas",
                "learn-advanced-ai",
                "node_type: sprockets/area\n"
                "uuid: area-2\n"
                "title: Learn Advanced AI\n",
            )
            specialist = sprockets_specialist.SprocketsSpecialist(
                sprockets_specialist.SprocketsSpecialistConfig(vault_dir=vault)
            )

            preview = specialist.hierarchy_proposal_preview("goal", "Study model routing", "Learn AI")

            self.assertTrue(any(issue.startswith("ambiguous parent hint") for issue in preview.issues))

    def test_format_hierarchy_proposal_preview_marks_review_required(self):
        preview = sprockets_specialist.SprocketsHierarchyProposalPreview(
            node_type="sprockets/project",
            title="Phase 5 - Voice Interface",
            slug="phase-5-voice-interface",
            parent_hint="Build Sprockets-Cogs",
            parent_slug="build-sprockets-cogs",
            parent_title="Build Sprockets-Cogs",
        )

        output = sprockets_specialist.format_sprockets_specialist_preview(preview)

        self.assertIn("Sprockets specialist hierarchy proposal preview", output)
        self.assertIn("- review required: yes", output)
        self.assertIn("- writes: no", output)
        self.assertIn("- parent: [[build-sprockets-cogs]] (Build Sprockets-Cogs)", output)
        self.assertIn("- issues: none", output)

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

    def test_main_prints_hierarchy_proposal_preview(self):
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
                sprockets_specialist.main(
                    [
                        "--vault",
                        str(vault),
                        "--propose",
                        "goal",
                        "--title",
                        "Build a public portfolio",
                        "--parent",
                        "Learn Agentic AI",
                    ]
                )

            output = buf.getvalue()
            self.assertIn("Sprockets specialist hierarchy proposal preview", output)
            self.assertIn("- node type: sprockets/goal", output)
            self.assertIn("- parent: [[learn-agentic-ai]] (Learn Agentic AI)", output)
            self.assertIn("- writes: no", output)


if __name__ == "__main__":
    unittest.main()

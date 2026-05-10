import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agentic_loop
import inspect_hierarchy
import networkx as nx
import vault_graph
from models import validate_node


def write_node(vault: Path, folder: str, slug: str, metadata: str = "") -> Path:
    path = vault / "Sprockets" / folder / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{metadata}---\n\n# {slug}\n")
    return path


class Stage10AParentResolutionTests(unittest.TestCase):
    def test_vault_graph_path_can_be_configured_from_environment(self):
        original_env = os.environ.copy()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["SPROCKETS_COGS_VAULT_DIR"] = str(Path(tmp) / "vault")
                reloaded = importlib.reload(vault_graph)

                self.assertEqual(reloaded.VAULT_DIR, Path(tmp) / "vault")
                self.assertEqual(
                    reloaded.sprockets_dirs()[0],
                    Path(tmp) / "vault" / "Sprockets" / "areas",
                )
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(vault_graph)

    def test_build_graph_reads_metadata_and_child_parent_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "projects",
                "stage-10a",
                "node_type: sprockets/project\n"
                "uuid: project-1\n"
                "title: Stage 10A\n",
            )
            write_node(
                vault,
                "tasks",
                "harden-parent-resolution",
                "node_type: sprockets/task\n"
                "uuid: task-1\n"
                "title: Harden parent resolution\n"
                "parent: [[stage-10a]]\n",
            )

            graph = vault_graph.build_graph(vault)

            self.assertEqual(graph.nodes["stage-10a"]["title"], "Stage 10A")
            self.assertEqual(graph.nodes["stage-10a"]["node_type"], "sprockets/project")
            self.assertEqual(graph.nodes["stage-10a"]["uuid"], "project-1")
            self.assertTrue(graph.has_edge("harden-parent-resolution", "stage-10a"))

    def test_build_graph_accepts_obsidian_wikilink_aliases_and_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(vault, "projects", "stage-10a", "title: Stage 10A\n")
            write_node(
                vault,
                "tasks",
                "aliased-task",
                "title: Aliased task\n"
                "parent: [[stage-10a#Plan|Stage 10A plan]]\n",
            )

            graph = vault_graph.build_graph(vault)

            self.assertTrue(graph.has_edge("aliased-task", "stage-10a"))

    def test_build_graph_skips_unreadable_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(vault, "projects", "good-project", "title: Good Project\n")
            bad = vault / "Sprockets" / "projects" / "bad-project.md"
            bad.write_text("---\n: bad yaml\n---\n\n# bad\n")

            graph = vault_graph.build_graph(vault)

            self.assertIn("good-project", graph.nodes)
            self.assertNotIn("bad-project", graph.nodes)

    def test_find_node_by_title_handles_match_and_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "projects",
                "sprockets-builder-roadmap",
                "uuid: roadmap-1\n"
                "title: Sprockets Builder Roadmap\n",
            )
            graph = vault_graph.build_graph(vault)

            self.assertEqual(
                vault_graph.find_node_by_title(graph, "builder roadmap"),
                ("sprockets-builder-roadmap", "roadmap-1"),
            )
            self.assertIsNone(vault_graph.find_node_by_title(graph, "dentist appointment"))

    def test_find_node_by_title_can_limit_parent_candidates_by_node_type(self):
        graph = nx.DiGraph()
        graph.add_node(
            "alex-rivera",
            title="Alex Rivera",
            uuid="contact-1",
            node_type="sprockets/contact",
        )
        graph.add_node(
            "jordan-project",
            title="Alex Project",
            uuid="project-1",
            node_type="sprockets/project",
        )

        self.assertEqual(
            vault_graph.find_node_by_title(
                graph,
                "Alex",
                allowed_node_types=vault_graph.HIERARCHY_PARENT_NODE_TYPES,
            ),
            ("jordan-project", "project-1"),
        )

    def test_find_node_by_title_declines_ambiguous_close_matches(self):
        graph = nx.DiGraph()
        graph.add_node(
            "phase-2-hardening",
            title="Phase 2 - Hardening",
            uuid="project-1",
            node_type="sprockets/project",
        )
        graph.add_node(
            "phase-2-handoff",
            title="Phase 2 - Handoff",
            uuid="project-2",
            node_type="sprockets/project",
        )

        self.assertIsNone(
            vault_graph.find_node_by_title(
                graph,
                "Phase 2",
                allowed_node_types=vault_graph.HIERARCHY_PARENT_NODE_TYPES,
            )
        )
        self.assertEqual(
            vault_graph.find_node_by_title(
                graph,
                "Phase 2 - Hardening",
                allowed_node_types=vault_graph.HIERARCHY_PARENT_NODE_TYPES,
            ),
            ("phase-2-hardening", "project-1"),
        )

        ambiguous = vault_graph.ambiguous_title_matches(
            graph,
            "Phase 2",
            allowed_node_types=vault_graph.HIERARCHY_PARENT_NODE_TYPES,
        )
        self.assertCountEqual(
            [title for _, title, _ in ambiguous],
            ["Phase 2 - Handoff", "Phase 2 - Hardening"],
        )

    def test_resolve_parents_sets_parent_from_vault_title_match(self):
        node = validate_node({
            "node_type": "sprockets/task",
            "title": "Harden parent resolution",
            "parent_hint": "Builder Roadmap",
            "confidence": "high",
        })
        graph = nx.DiGraph()
        graph.add_node(
            "sprockets-builder-roadmap",
            title="Sprockets Builder Roadmap",
            uuid="roadmap-1",
            node_type="sprockets/project",
        )

        with patch.object(agentic_loop, "build_graph", return_value=graph):
            resolved = agentic_loop.resolve_parents([node])

        self.assertEqual(resolved[0].parent, "[[sprockets-builder-roadmap]]")

    def test_resolve_parents_ignores_non_hierarchy_title_matches(self):
        node = validate_node({
            "node_type": "sprockets/task",
            "title": "Call Alex",
            "parent_hint": "Alex Rivera",
            "confidence": "high",
        })
        graph = nx.DiGraph()
        graph.add_node(
            "alex-rivera",
            title="Alex Rivera",
            uuid="contact-1",
            node_type="sprockets/contact",
        )

        with patch.object(agentic_loop, "build_graph", return_value=graph):
            resolved = agentic_loop.resolve_parents([node])

        self.assertEqual(resolved[0].parent, "")

    def test_resolve_parents_preserves_existing_parent(self):
        node = validate_node({
            "node_type": "sprockets/task",
            "title": "Harden parent resolution",
            "parent": "[[manual-parent]]",
            "parent_hint": "Builder Roadmap",
            "confidence": "high",
        })
        graph = nx.DiGraph()
        graph.add_node(
            "sprockets-builder-roadmap",
            title="Sprockets Builder Roadmap",
            uuid="roadmap-1",
            node_type="sprockets/project",
        )

        with patch.object(agentic_loop, "build_graph", return_value=graph):
            resolved = agentic_loop.resolve_parents([node])

        self.assertEqual(resolved[0].parent, "[[manual-parent]]")

    def test_resolve_parents_leaves_unmatched_hint_unlinked(self):
        node = validate_node({
            "node_type": "sprockets/task",
            "title": "Call Alex",
            "parent_hint": "Does Not Exist",
            "confidence": "high",
        })
        graph = nx.DiGraph()
        graph.add_node("known-project", title="Known Project", uuid="known-1")

        with patch.object(agentic_loop, "build_graph", return_value=graph):
            resolved = agentic_loop.resolve_parents([node])

        self.assertEqual(resolved[0].parent, "")

    def test_resolve_parents_is_noop_when_graph_is_empty(self):
        node = validate_node({
            "node_type": "sprockets/task",
            "title": "Call Alex",
            "parent_hint": "Known Project",
            "confidence": "high",
        })
        empty_graph = nx.DiGraph()

        with patch.object(agentic_loop, "build_graph", return_value=empty_graph):
            resolved = agentic_loop.resolve_parents([node])

        self.assertEqual(resolved[0].parent, "")


class Stage10BHierarchyReadinessTests(unittest.TestCase):
    def test_existing_hierarchy_chain_is_graph_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "areas",
                "career",
                "node_type: sprockets/area\n"
                "uuid: area-1\n"
                "title: Career\n",
            )
            write_node(
                vault,
                "goals",
                "bar-exam",
                "node_type: sprockets/goal\n"
                "uuid: goal-1\n"
                "title: Pass the bar exam\n"
                "parent: [[career]]\n",
            )
            write_node(
                vault,
                "projects",
                "study-plan-q2",
                "node_type: sprockets/project\n"
                "uuid: project-1\n"
                "title: Study plan Q2\n"
                "parent: [[bar-exam]]\n",
            )
            write_node(
                vault,
                "tasks",
                "read-chapters-4-6",
                "node_type: sprockets/task\n"
                "uuid: task-1\n"
                "title: Read chapters 4-6\n"
                "parent: [[study-plan-q2]]\n",
            )

            graph = vault_graph.build_graph(vault)

            self.assertEqual(graph.nodes["career"]["node_type"], "sprockets/area")
            self.assertEqual(graph.nodes["bar-exam"]["node_type"], "sprockets/goal")
            self.assertEqual(graph.nodes["study-plan-q2"]["node_type"], "sprockets/project")
            self.assertTrue(graph.has_edge("bar-exam", "career"))
            self.assertTrue(graph.has_edge("study-plan-q2", "bar-exam"))
            self.assertTrue(graph.has_edge("read-chapters-4-6", "study-plan-q2"))

    def test_task_parent_hint_resolves_to_existing_project(self):
        node = validate_node({
            "node_type": "sprockets/task",
            "title": "Read chapters 4-6",
            "parent_hint": "Study plan Q2",
            "confidence": "high",
        })
        graph = nx.DiGraph()
        graph.add_node(
            "study-plan-q2",
            title="Study plan Q2",
            uuid="project-1",
            node_type="sprockets/project",
        )

        with patch.object(agentic_loop, "build_graph", return_value=graph):
            resolved = agentic_loop.resolve_parents([node])

        self.assertEqual(resolved[0].parent, "[[study-plan-q2]]")

    def test_project_can_link_directly_under_area_when_no_goal_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "areas",
                "career",
                "node_type: sprockets/area\n"
                "uuid: area-1\n"
                "title: Career\n",
            )
            write_node(
                vault,
                "projects",
                "portfolio-refresh",
                "node_type: sprockets/project\n"
                "uuid: project-1\n"
                "title: Portfolio refresh\n"
                "parent: [[career]]\n",
            )

            graph = vault_graph.build_graph(vault)

            self.assertTrue(graph.has_edge("portfolio-refresh", "career"))

    def test_missing_hierarchy_target_leaves_node_unlinked(self):
        node = validate_node({
            "node_type": "sprockets/task",
            "title": "Draft proposal",
            "parent_hint": "Nonexistent client project",
            "confidence": "high",
        })
        graph = nx.DiGraph()
        graph.add_node(
            "operations",
            title="Operations",
            uuid="area-1",
            node_type="sprockets/area",
        )

        with patch.object(agentic_loop, "build_graph", return_value=graph):
            resolved = agentic_loop.resolve_parents([node])

        self.assertEqual(resolved[0].parent, "")

    def test_hierarchy_inspection_reports_empty_hierarchy_without_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            lines, issues = inspect_hierarchy.inspect_hierarchy(vault)

            self.assertIn("No hierarchy nodes found.", lines)
            self.assertEqual(issues, [])

    def test_hierarchy_inspection_flags_invalid_parent_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "projects",
                "study-plan-q2",
                "node_type: sprockets/project\n"
                "uuid: project-1\n"
                "title: Study plan Q2\n",
            )
            write_node(
                vault,
                "goals",
                "bar-exam",
                "node_type: sprockets/goal\n"
                "uuid: goal-1\n"
                "title: Pass the bar exam\n"
                "parent: [[study-plan-q2]]\n",
            )

            _, issues = inspect_hierarchy.inspect_hierarchy(vault)

            self.assertIn("study-plan-q2: sprockets/project has no parent", issues)
            self.assertIn(
                "bar-exam: sprockets/goal parent study-plan-q2 has invalid type sprockets/project",
                issues,
            )

    def test_build_hierarchy_context_lists_frontmatter_titles_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "areas",
                "learn-agentic-ai",
                "node_type: sprockets/area\n"
                "uuid: area-1\n"
                "title: Learn Agentic AI\n",
            ).write_text(
                "---\n"
                "node_type: sprockets/area\n"
                "uuid: area-1\n"
                "title: Learn Agentic AI\n"
                "---\n\n"
                "Private reflection text should not enter classifier context.\n"
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
            write_node(
                vault,
                "projects",
                "phase-2-hardening",
                "node_type: sprockets/project\n"
                "uuid: project-1\n"
                "title: Phase 2 - Hardening\n"
                "parent: [[build-sprockets-cogs]]\n",
            )

            with patch.object(agentic_loop, "build_graph", return_value=vault_graph.build_graph(vault)):
                lines = agentic_loop._build_hierarchy_context()

            self.assertEqual(
                lines,
                [
                    "Area: Learn Agentic AI",
                    "Goal: Build Sprockets-Cogs (under Learn Agentic AI)",
                    "Project: Phase 2 - Hardening (under Build Sprockets-Cogs)",
                ],
            )
            self.assertNotIn("Private reflection", "\n".join(lines))

    def test_build_context_includes_known_hierarchy_parent_targets(self):
        with patch.object(agentic_loop, "DAILY_DIR", Path("/tmp/no-such-daily-dir")), \
             patch.object(agentic_loop, "get_entities_by_tier", return_value=[]), \
             patch.object(
                 agentic_loop,
                 "_build_hierarchy_context",
                 return_value=["Project: Phase 2 - Hardening (under Build Sprockets-Cogs)"],
             ):
            context = agentic_loop.build_context()

        self.assertIn("Already in today's note: (none)", context)
        self.assertIn("Known hierarchy parent targets:", context)
        self.assertIn("Project: Phase 2 - Hardening", context)

    def test_ensure_hierarchy_tasks_adds_project_scoped_task(self):
        raw_nodes = [
            {
                "raw": "Need to write live verification notes for Phase 2 - Hardening",
                "type_hint": "task",
            }
        ]
        classified = [
            {
                "node_type": "cogs/daily",
                "title": "2 verification notes for Phase 2 - Hardening",
                "item_text": "2 verification notes for Phase 2 - Hardening",
                "date": "2026-04-22",
                "confidence": "high",
            }
        ]
        graph = nx.DiGraph()
        graph.add_node(
            "phase-2-hardening",
            title="Phase 2 - Hardening",
            uuid="project-1",
            node_type="sprockets/project",
        )

        with patch.object(agentic_loop, "build_graph", return_value=graph), \
             patch.object(agentic_loop, "datetime") as fake_datetime:
            fake_datetime.now.return_value.strftime.return_value = "2026-05-03"
            result = agentic_loop.ensure_hierarchy_tasks(raw_nodes, classified)

        self.assertEqual(len(result), 2)
        task = result[1]
        self.assertEqual(task["node_type"], "sprockets/task")
        self.assertEqual(task["title"], "Write live verification notes for Phase 2 - Hardening")
        self.assertEqual(task["parent_hint"], "Phase 2 - Hardening")

    def test_ensure_hierarchy_tasks_does_not_invent_missing_parent(self):
        raw_nodes = [
            {
                "raw": "Need to write notes for Missing Project",
                "type_hint": "task",
            }
        ]
        graph = nx.DiGraph()
        graph.add_node(
            "phase-2-hardening",
            title="Phase 2 - Hardening",
            uuid="project-1",
            node_type="sprockets/project",
        )

        with patch.object(agentic_loop, "build_graph", return_value=graph):
            result = agentic_loop.ensure_hierarchy_tasks(raw_nodes, [])

        self.assertEqual(result, [])

    def test_apply_explicit_hierarchy_hints_links_notes(self):
        raw_nodes = [
            {
                "raw": "Reflection on Phase 2 - Hardening: code guards beat prompt hopes.",
                "type_hint": "note",
            }
        ]
        classified = [
            {
                "node_type": "sprockets/note",
                "title": "Code guards beat prompt hopes",
                "item_text": "code guards beat prompt hopes",
                "date": "2026-05-03",
                "confidence": "high",
            }
        ]
        graph = nx.DiGraph()
        graph.add_node(
            "phase-2-hardening",
            title="Phase 2 - Hardening",
            uuid="project-1",
            node_type="sprockets/project",
        )

        with patch.object(agentic_loop, "build_graph", return_value=graph):
            result = agentic_loop.apply_explicit_hierarchy_hints(raw_nodes, classified)

        self.assertEqual(result[0]["parent_hint"], "Phase 2 - Hardening")

    def test_apply_explicit_hierarchy_hints_does_not_use_partial_project_names(self):
        raw_nodes = [
            {
                "raw": "Reflection on Phase 2: this remains too broad.",
                "type_hint": "note",
            }
        ]
        classified = [
            {
                "node_type": "sprockets/note",
                "title": "Phase 2 reflection",
                "item_text": "this remains too broad",
                "date": "2026-05-03",
                "confidence": "high",
            }
        ]
        graph = nx.DiGraph()
        graph.add_node(
            "phase-2-hardening",
            title="Phase 2 - Hardening",
            uuid="project-1",
            node_type="sprockets/project",
        )
        graph.add_node(
            "phase-2-handoff",
            title="Phase 2 - Handoff",
            uuid="project-2",
            node_type="sprockets/project",
        )

        with patch.object(agentic_loop, "build_graph", return_value=graph):
            result = agentic_loop.apply_explicit_hierarchy_hints(raw_nodes, classified)

        self.assertNotIn("parent_hint", result[0])

    def test_ambiguous_hierarchy_parent_hints_route_to_review(self):
        node = validate_node({
            "node_type": "sprockets/note",
            "title": "Phase 2 reflection",
            "parent_hint": "Phase 2",
            "confidence": "high",
        })
        graph = nx.DiGraph()
        graph.add_node(
            "phase-2-hardening",
            title="Phase 2 - Hardening",
            uuid="project-1",
            node_type="sprockets/project",
        )
        graph.add_node(
            "phase-2-handoff",
            title="Phase 2 - Handoff",
            uuid="project-2",
            node_type="sprockets/project",
        )
        written = []

        with patch.object(agentic_loop, "build_graph", return_value=graph), \
             patch.object(agentic_loop, "write_to_review", side_effect=lambda raw, reason: written.append((raw, reason))):
            result = agentic_loop.route_ambiguous_hierarchy_parent_hints_to_review([node])

        self.assertEqual(result, [])
        self.assertEqual(written[0][0]["title"], "Phase 2 reflection")
        self.assertIn("ambiguous hierarchy parent_hint", written[0][1])
        self.assertIn("Phase 2 - Hardening", written[0][1])
        self.assertIn("Phase 2 - Handoff", written[0][1])

    def test_unambiguous_hierarchy_parent_hints_do_not_route_to_review(self):
        node = validate_node({
            "node_type": "sprockets/note",
            "title": "Hardening reflection",
            "parent_hint": "Phase 2 - Hardening",
            "confidence": "high",
        })
        graph = nx.DiGraph()
        graph.add_node(
            "phase-2-hardening",
            title="Phase 2 - Hardening",
            uuid="project-1",
            node_type="sprockets/project",
        )

        with patch.object(agentic_loop, "build_graph", return_value=graph), \
             patch.object(agentic_loop, "write_to_review") as write_to_review:
            result = agentic_loop.route_ambiguous_hierarchy_parent_hints_to_review([node])

        self.assertEqual(result, [node])
        write_to_review.assert_not_called()

    def test_process_input_routes_ambiguous_parent_hint_to_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            processing_dir = root / "processing"
            archive_dir = root / "archive"
            review_dir = root / "review"
            daily_dir = root / "daily"
            input_dir.mkdir()
            input_path = input_dir / "ambiguous.input"
            input_path.write_text("---\nsession_id: ambiguous-test\n---\n\nReflection on Phase 2.\n")
            graph = nx.DiGraph()
            graph.add_node(
                "phase-2-hardening",
                title="Phase 2 - Hardening",
                uuid="project-1",
                node_type="sprockets/project",
            )
            graph.add_node(
                "phase-2-handoff",
                title="Phase 2 - Handoff",
                uuid="project-2",
                node_type="sprockets/project",
            )
            raw_nodes = [{"raw": "Reflection on Phase 2", "type_hint": "note"}]
            classified = [
                {
                    "node_type": "sprockets/note",
                    "title": "Phase 2 reflection",
                    "item_text": "Reflection on Phase 2",
                    "date": "2026-05-03",
                    "confidence": "high",
                    "parent_hint": "Phase 2",
                }
            ]

            with patch.object(agentic_loop, "INPUT_DIR", input_dir), \
                 patch.object(agentic_loop, "PROCESSING_DIR", processing_dir), \
                 patch.object(agentic_loop, "ARCHIVE_DIR", archive_dir), \
                 patch.object(agentic_loop, "REVIEW_DIR", review_dir), \
                 patch.object(agentic_loop, "DAILY_DIR", daily_dir), \
                 patch.object(agentic_loop, "build_context", return_value=""), \
                 patch.object(agentic_loop, "extract_nodes", return_value=raw_nodes), \
                 patch.object(agentic_loop, "classify_nodes", return_value=classified), \
                 patch.object(agentic_loop, "build_graph", return_value=graph), \
                 patch.object(agentic_loop, "write_node") as write_node:
                agentic_loop.ensure_runtime_dirs()
                agentic_loop.process_input(input_path)

            write_node.assert_not_called()
            self.assertTrue((archive_dir / "ambiguous.input").exists())
            review_files = list(review_dir.glob("*.md"))
            self.assertEqual(len(review_files), 1)
            review_text = review_files[0].read_text()
            self.assertIn("ambiguous hierarchy parent_hint", review_text)
            self.assertIn('"title": "Phase 2 reflection"', review_text)
            daily_files = list(daily_dir.glob("*.md"))
            self.assertEqual(len(daily_files), 1)
            self.assertIn("Processed 0 node(s)", daily_files[0].read_text())


if __name__ == "__main__":
    unittest.main()

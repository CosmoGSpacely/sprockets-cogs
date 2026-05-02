import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agentic_loop
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
        )

        with patch.object(agentic_loop, "build_graph", return_value=graph):
            resolved = agentic_loop.resolve_parents([node])

        self.assertEqual(resolved[0].parent, "[[sprockets-builder-roadmap]]")

    def test_resolve_parents_leaves_unmatched_hint_unlinked(self):
        node = validate_node({
            "node_type": "sprockets/task",
            "title": "Call Jordan",
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
            "title": "Call Jordan",
            "parent_hint": "Known Project",
            "confidence": "high",
        })
        empty_graph = nx.DiGraph()

        with patch.object(agentic_loop, "build_graph", return_value=empty_graph):
            resolved = agentic_loop.resolve_parents([node])

        self.assertEqual(resolved[0].parent, "")


if __name__ == "__main__":
    unittest.main()

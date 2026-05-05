import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

import embeddings
from retrieval_eval import build_experimental_retriever
from retrieval_memory import expand_top_memory_result_graph
from retrieval_strategies import (
    expand_retrieval_neighbors,
    expand_retrieval_neighbors_with_reasons,
    graph_reason_priority,
    hybrid_retrieve_with_trace,
)
from retrieval_types import RetrievalNode


def write_node(vault: Path, folder: str, slug: str, metadata: str = "", body: str = "") -> Path:
    path = vault / "Sprockets" / folder / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{metadata}---\n\n{body}\n")
    return path


class Stage20GraphRetrievalTests(unittest.TestCase):
    def test_graph_expansion_adds_project_parent_and_children(self):
        goal = RetrievalNode(
            node_id="goals/build-sprockets-cogs",
            title="Build Sprockets-Cogs",
            node_type="sprockets/goal",
            path=Path("build-sprockets-cogs.md"),
        )
        project = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("phase-3-memory-enhancement.md"),
            parent_slugs=("build-sprockets-cogs",),
        )
        task = RetrievalNode(
            node_id="tasks/add-memory-index-maintenance",
            title="Add memory index maintenance",
            node_type="sprockets/task",
            path=Path("add-memory-index-maintenance.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )
        note = RetrievalNode(
            node_id="notes/phase-3-memory-notes",
            title="Phase 3 memory notes",
            node_type="sprockets/note",
            path=Path("phase-3-memory-notes.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )

        expanded = expand_retrieval_neighbors(
            (project,),
            (goal, project, task, note),
            limit=4,
        )

        self.assertEqual(
            [node.node_id for node in expanded],
            [
                "projects/phase-3-memory-enhancement",
                "goals/build-sprockets-cogs",
                "tasks/add-memory-index-maintenance",
                "notes/phase-3-memory-notes",
            ],
        )

    def test_graph_expansion_adds_sibling_tasks_and_notes(self):
        project = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("phase-3-memory-enhancement.md"),
        )
        seed_task = RetrievalNode(
            node_id="tasks/add-retrieval-traces",
            title="Add retrieval traces",
            node_type="sprockets/task",
            path=Path("add-retrieval-traces.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )
        sibling_task = RetrievalNode(
            node_id="tasks/add-graph-aware-retrieval",
            title="Add graph-aware retrieval",
            node_type="sprockets/task",
            path=Path("add-graph-aware-retrieval.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )
        sibling_note = RetrievalNode(
            node_id="notes/phase-3-memory-notes",
            title="Phase 3 memory notes",
            node_type="sprockets/note",
            path=Path("phase-3-memory-notes.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )

        expanded = expand_retrieval_neighbors(
            (seed_task,),
            (project, seed_task, sibling_task, sibling_note),
            limit=4,
        )

        self.assertEqual(
            [node.node_id for node in expanded],
            [
                "tasks/add-retrieval-traces",
                "projects/phase-3-memory-enhancement",
                "tasks/add-graph-aware-retrieval",
                "notes/phase-3-memory-notes",
            ],
        )

    def test_graph_expansion_keeps_sibling_results_bounded(self):
        project = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("phase-3-memory-enhancement.md"),
        )
        seed_task = RetrievalNode(
            node_id="tasks/add-retrieval-traces",
            title="Add retrieval traces",
            node_type="sprockets/task",
            path=Path("add-retrieval-traces.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )
        sibling_task = RetrievalNode(
            node_id="tasks/add-graph-aware-retrieval",
            title="Add graph-aware retrieval",
            node_type="sprockets/task",
            path=Path("add-graph-aware-retrieval.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )

        expanded = expand_retrieval_neighbors(
            (seed_task,),
            (project, seed_task, sibling_task),
            limit=2,
        )

        self.assertEqual(
            [node.node_id for node in expanded],
            [
                "tasks/add-retrieval-traces",
                "projects/phase-3-memory-enhancement",
            ],
        )

    def test_graph_expansion_reports_compact_reasons(self):
        project = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("phase-3-memory-enhancement.md"),
        )
        seed_task = RetrievalNode(
            node_id="tasks/add-retrieval-traces",
            title="Add retrieval traces",
            node_type="sprockets/task",
            path=Path("add-retrieval-traces.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )
        sibling_note = RetrievalNode(
            node_id="notes/phase-3-memory-notes",
            title="Phase 3 memory notes",
            node_type="sprockets/note",
            path=Path("phase-3-memory-notes.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )

        expanded, reasons = expand_retrieval_neighbors_with_reasons(
            (seed_task,),
            (project, seed_task, sibling_note),
            limit=3,
        )

        self.assertEqual(
            [node.node_id for node in expanded],
            [
                "tasks/add-retrieval-traces",
                "projects/phase-3-memory-enhancement",
                "notes/phase-3-memory-notes",
            ],
        )
        self.assertEqual(reasons["tasks/add-retrieval-traces"], "direct")
        self.assertEqual(
            reasons["projects/phase-3-memory-enhancement"],
            "parent of tasks/add-retrieval-traces",
        )
        self.assertEqual(
            reasons["notes/phase-3-memory-notes"],
            "sibling of tasks/add-retrieval-traces via phase-3-memory-enhancement",
        )

    def test_graph_reasons_prefer_structure_over_title_mentions(self):
        project = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("phase-3-memory-enhancement.md"),
        )
        seed_task = RetrievalNode(
            node_id="tasks/review-stage-20-for-phase-3---memory-enhancement",
            title="Review Stage 20 for Phase 3 - Memory Enhancement",
            node_type="sprockets/task",
            path=Path("review-stage-20-for-phase-3---memory-enhancement.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )

        expanded, reasons = expand_retrieval_neighbors_with_reasons(
            (seed_task,),
            (project, seed_task),
            limit=2,
        )

        self.assertEqual(
            [node.node_id for node in expanded],
            [
                "tasks/review-stage-20-for-phase-3---memory-enhancement",
                "projects/phase-3-memory-enhancement",
            ],
        )
        self.assertEqual(
            reasons["projects/phase-3-memory-enhancement"],
            "parent of tasks/review-stage-20-for-phase-3---memory-enhancement",
        )

    def test_graph_reason_priority_keeps_direct_hits_strongest(self):
        self.assertGreater(graph_reason_priority("direct"), graph_reason_priority("parent of tasks/a"))
        self.assertGreater(
            graph_reason_priority("parent of tasks/a"),
            graph_reason_priority("title mention in tasks/a"),
        )

    def test_hybrid_graph_trace_explains_graph_results(self):
        project = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("phase-3-memory-enhancement.md"),
        )
        task = RetrievalNode(
            node_id="tasks/add-retrieval-traces",
            title="Add retrieval traces",
            node_type="sprockets/task",
            path=Path("add-retrieval-traces.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )
        note = RetrievalNode(
            node_id="notes/phase-3-memory-notes",
            title="Phase 3 memory notes",
            node_type="sprockets/note",
            path=Path("phase-3-memory-notes.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )

        results, trace = hybrid_retrieve_with_trace(
            "retrieval traces",
            (project, task, note),
            lambda _query: [task],
            expand_graph=True,
            retriever_name="hybrid-graph-vault",
        )

        self.assertEqual(trace.retriever_name, "hybrid-graph-vault")
        self.assertEqual(trace.result_ids, tuple(node.node_id for node in results))
        self.assertIn("graph expansion applied", trace.notes)
        self.assertIn(
            "projects/phase-3-memory-enhancement graph=parent of tasks/add-retrieval-traces",
            trace.result_summaries,
        )

    def test_memory_embedding_graph_gated_vault_expands_parent_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            project_path = write_node(
                vault,
                "projects",
                "phase-3-memory-enhancement",
                "node_type: sprockets/project\n"
                "title: Phase 3 - Memory Enhancement\n",
            )
            task_path = write_node(
                vault,
                "tasks",
                "write-retrieval-trace-notes",
                "node_type: sprockets/task\n"
                "title: Write retrieval trace notes\n"
                "parent: [[phase-3-memory-enhancement]]\n",
            )
            project = RetrievalNode(
                node_id="projects/phase-3-memory-enhancement",
                title="Phase 3 - Memory Enhancement",
                node_type="sprockets/project",
                path=project_path,
            )
            task = RetrievalNode(
                node_id="tasks/write-retrieval-trace-notes",
                title="Write retrieval trace notes",
                node_type="sprockets/task",
                path=task_path,
                parent_slugs=("phase-3-memory-enhancement",),
            )

            with patch("embeddings.build_embedding_index") as mock_build_index:
                with patch("embeddings.embed_text") as mock_embed_text:
                    mock_build_index.return_value = (
                        embeddings.EmbeddedNode(node=task, vector=(1.0, 0.0)),
                    )
                    mock_embed_text.return_value = [1.0, 0.0]

                    retriever = build_experimental_retriever(
                        "memory-embedding-graph-gated-vault",
                        vault,
                    )
                    results = list(retriever.retrieve("retrieval trace notes"))
                    trace = retriever.trace("retrieval trace notes")

        self.assertEqual(retriever.name, "memory-embedding-graph-gated-vault")
        self.assertEqual(results[0].node_id, "tasks/write-retrieval-trace-notes")
        self.assertIn("projects/phase-3-memory-enhancement", [node.node_id for node in results])
        self.assertIn("graph expansion applied", trace.notes)
        self.assertIn(
            "projects/phase-3-memory-enhancement graph=parent of tasks/write-retrieval-trace-notes",
            trace.result_summaries,
        )

    def test_memory_embedding_graph_gated_vault_still_withholds_low_confidence_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            project_path = write_node(
                vault,
                "projects",
                "phase-3-memory-enhancement",
                "node_type: sprockets/project\n"
                "title: Phase 3 - Memory Enhancement\n",
            )
            note_path = write_node(
                vault,
                "notes",
                "unanchored-note",
                "node_type: sprockets/note\n"
                "title: Unanchored note\n",
            )
            project = RetrievalNode(
                node_id="projects/phase-3-memory-enhancement",
                title="Phase 3 - Memory Enhancement",
                node_type="sprockets/project",
                path=project_path,
            )
            note = RetrievalNode(
                node_id="notes/unanchored-note",
                title="Unanchored note",
                node_type="sprockets/note",
                path=note_path,
            )

            with patch("embeddings.build_embedding_index") as mock_build_index:
                with patch("embeddings.embed_text") as mock_embed_text:
                    mock_build_index.return_value = (
                        embeddings.EmbeddedNode(node=project, vector=(1.0, 0.0)),
                        embeddings.EmbeddedNode(node=note, vector=(0.99, 0.01)),
                    )
                    mock_embed_text.return_value = [1.0, 0.0]

                    retriever = build_experimental_retriever(
                        "memory-embedding-graph-gated-vault",
                        vault,
                    )
                    results = list(retriever.retrieve("What deserves attention next?"))
                    trace = retriever.trace("What deserves attention next?")

        self.assertEqual(results, [])
        self.assertEqual(trace.result_ids, ())
        self.assertIn("confidence gate withheld low-confidence results", trace.notes)
        self.assertNotIn("graph expansion applied", trace.notes)

    def test_top_memory_graph_expansion_preserves_direct_hits_before_siblings(self):
        project = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("phase-3-memory-enhancement.md"),
        )
        seed_task = RetrievalNode(
            node_id="tasks/write-retrieval-trace-notes",
            title="Write retrieval trace notes",
            node_type="sprockets/task",
            path=Path("write-retrieval-trace-notes.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )
        direct_project = RetrievalNode(
            node_id="projects/learn-how-to-bring-a-project-to-production",
            title="Learn how to bring a project to production",
            node_type="sprockets/project",
            path=Path("learn-how-to-bring-a-project-to-production.md"),
        )
        direct_note = RetrievalNode(
            node_id="notes/idea-build-a-weekly-review-template",
            title="Idea: build a weekly review template",
            node_type="sprockets/note",
            path=Path("idea-build-a-weekly-review-template.md"),
        )
        sibling_task = RetrievalNode(
            node_id="tasks/review-stage-19-trace-reporting",
            title="Review Stage 19 trace reporting",
            node_type="sprockets/task",
            path=Path("review-stage-19-trace-reporting.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )

        expanded, reasons = expand_top_memory_result_graph(
            [seed_task, direct_project, direct_note],
            (project, seed_task, direct_project, direct_note, sibling_task),
            limit=4,
        )

        self.assertEqual(
            [node.node_id for node in expanded],
            [
                "tasks/write-retrieval-trace-notes",
                "projects/phase-3-memory-enhancement",
                "projects/learn-how-to-bring-a-project-to-production",
                "notes/idea-build-a-weekly-review-template",
            ],
        )
        self.assertEqual(
            reasons["projects/phase-3-memory-enhancement"],
            "parent of tasks/write-retrieval-trace-notes",
        )
        self.assertNotIn("tasks/review-stage-19-trace-reporting", reasons)


if __name__ == "__main__":
    unittest.main()

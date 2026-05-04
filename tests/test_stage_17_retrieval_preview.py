import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_index import MemoryQuery, RetrievalConfidence, RetrievalTrace
from production_retrieval import ProductionRetrievalStatus
from retrieval_eval import ExperimentalRetriever, RetrievalNode
from retrieval_preview import (
    format_context_preview,
    format_memory_guard_preview,
    format_preview,
    format_production_return_preview,
    format_status,
    preview_production_return,
    preview_memory_guard,
    preview_retrieval,
)


class Stage17RetrievalPreviewTests(unittest.TestCase):
    def test_preview_retrieval_uses_gated_memory_by_default(self):
        node = RetrievalNode(
            node_id="projects/learn-how-to-bring-a-project-to-production",
            title="Learn how to bring a project to production",
            node_type="sprockets/project",
            path=Path("/vault/Sprockets/projects/production.md"),
        )
        trace = RetrievalTrace(
            query=MemoryQuery(text="What should run beyond my laptop?"),
            retriever_name="in-memory",
            result_ids=(node.node_id,),
            confidence=RetrievalConfidence(
                level="high",
                action="use",
                reasons=("anchored top result",),
            ),
        )
        experimental = ExperimentalRetriever(
            name="memory-embedding-gated-vault",
            nodes=(node,),
            retriever=lambda _query: (node,),
            trace_provider=lambda _query: trace,
        )

        with patch("retrieval_preview.build_experimental_retriever") as mock_build:
            mock_build.return_value = experimental
            with tempfile.TemporaryDirectory() as tmp:
                vault = Path(tmp)
                preview = preview_retrieval("What should run beyond my laptop?", vault)

        mock_build.assert_called_once_with("memory-embedding-gated-vault", vault)
        self.assertEqual(preview.results, (node,))
        self.assertEqual(preview.trace, trace)

    def test_format_preview_lists_results_and_trace(self):
        node = RetrievalNode(
            node_id="notes/reflection-on-phase-2---hierarchy",
            title="Reflection on Phase 2 - Hierarchy",
            node_type="sprockets/note",
            path=Path("/vault/Sprockets/notes/reflection.md"),
        )
        trace = RetrievalTrace(
            query=MemoryQuery(text="Find hierarchy reflection"),
            retriever_name="in-memory",
            result_ids=(node.node_id,),
            notes=("records scanned: 1",),
            result_summaries=(
                "notes/reflection-on-phase-2---hierarchy score=2 reasons=title parts=title=2",
            ),
            quality_flags=("low top margin: 0.01",),
            confidence=RetrievalConfidence(
                level="medium",
                action="use",
                reasons=("low top margin: 0.01",),
            ),
        )

        output = format_preview(
            preview_retrieval_result(
                query="Find hierarchy reflection",
                results=(node,),
                trace=trace,
            ),
            show_trace=True,
        )

        self.assertIn("Sprockets-Cogs retrieval preview", output)
        self.assertIn("- retriever: memory-embedding-gated-vault", output)
        self.assertIn("1. notes/reflection-on-phase-2---hierarchy [sprockets/note]", output)
        self.assertIn("Trace", output)
        self.assertIn("- confidence: medium/use", output)
        self.assertIn("- results:", output)

    def test_format_preview_handles_unavailable_trace(self):
        output = format_preview(
            preview_retrieval_result(
                query="Find memory",
                results=(),
                trace=None,
            ),
            show_trace=True,
        )

        self.assertIn("- results: 0", output)
        self.assertIn("- unavailable", output)

    def test_format_context_preview_formats_results_as_prompt_context(self):
        node = RetrievalNode(
            node_id="notes/memory",
            title="Memory",
            node_type="sprockets/note",
            path=Path("/vault/memory.md"),
        )

        output = format_context_preview(
            preview_retrieval_result(
                query="Find memory",
                results=(node,),
                trace=None,
            )
        )

        self.assertIn("Relevant memory:", output)
        self.assertIn("Use these only as lookup hints", output)
        self.assertIn("- notes/memory [sprockets/note] Memory", output)

    def test_format_context_preview_reports_no_memory(self):
        output = format_context_preview(
            preview_retrieval_result(
                query="Find memory",
                results=(),
                trace=None,
            )
        )

        self.assertEqual(output, "Relevant memory: (none)")

    def test_format_status_summarizes_guarded_production_retrieval(self):
        output = format_status(
            ProductionRetrievalStatus(
                enabled=False,
                context_enabled=False,
                retriever_name="memory-embedding-gated-vault",
                vault_dir=Path("/vault"),
                raw_retriever_name="embedding-vault",
                allowed_retrievers=("memory-embedding-gated-vault", "memory-vault"),
                node_limit=5,
                text_limit=240,
            )
        )

        self.assertIn("Sprockets-Cogs production retrieval status", output)
        self.assertIn("- memory retrieval: disabled", output)
        self.assertIn("- enable env: SPROCKETS_COGS_MEMORY_RETRIEVAL", output)
        self.assertIn("- memory context: disabled", output)
        self.assertIn("- context env: SPROCKETS_COGS_MEMORY_CONTEXT", output)
        self.assertIn("- retriever: memory-embedding-gated-vault", output)
        self.assertIn("- retriever env accepted: no", output)
        self.assertIn("- raw retriever env: embedding-vault", output)
        self.assertIn("- allowed retrievers: memory-embedding-gated-vault, memory-vault", output)
        self.assertIn("- production node limit: 5", output)
        self.assertIn("- node limit env: SPROCKETS_COGS_MEMORY_NODE_LIMIT", output)
        self.assertIn("- production text limit: 240", output)
        self.assertIn("- text limit env: SPROCKETS_COGS_MEMORY_TEXT_LIMIT", output)
        self.assertIn("- vault: /vault", output)

    def test_preview_memory_guard_uses_top_hierarchy_result(self):
        project = RetrievalNode(
            node_id="projects/learn-how-to-bring-a-project-to-production",
            title="Learn how to bring a project to production",
            node_type="sprockets/project",
            path=Path("/vault/Sprockets/projects/production.md"),
        )
        note = RetrievalNode(
            node_id="notes/run-anywhere",
            title="Run anywhere note",
            node_type="sprockets/note",
            path=Path("/vault/Sprockets/notes/run-anywhere.md"),
        )

        guard = preview_memory_guard(
            preview_retrieval_result(
                query="Need to draft a deployment checklist so this can run beyond my laptop.",
                results=(note, project),
                trace=None,
            )
        )

        self.assertEqual(
            guard.parent_title,
            "Learn how to bring a project to production",
        )
        self.assertEqual(
            guard.parent_node_id,
            "projects/learn-how-to-bring-a-project-to-production",
        )
        self.assertTrue(guard.task_like)
        self.assertTrue(guard.would_apply_parent_hint)
        self.assertTrue(guard.would_add_hierarchy_task)
        self.assertEqual(
            guard.derived_task_title,
            "Draft a deployment checklist so this can run beyond my laptop.",
        )

    def test_format_memory_guard_preview_is_read_only(self):
        project = RetrievalNode(
            node_id="projects/production",
            title="Production",
            node_type="sprockets/project",
            path=Path("/vault/Sprockets/projects/production.md"),
        )
        guard = preview_memory_guard(
            preview_retrieval_result(
                query="Need to make the service portable",
                results=(project,),
                trace=None,
            )
        )

        output = format_memory_guard_preview(guard)

        self.assertIn("Sprockets-Cogs memory guard preview", output)
        self.assertIn("- top hierarchy parent: Production", output)
        self.assertIn("- parent node: projects/production [sprockets/project]", output)
        self.assertIn("- would apply parent_hint: yes", output)
        self.assertIn("- would add Sprockets task if classifier emits daily-only: yes", output)
        self.assertIn("- derived task title: Make the service portable", output)
        self.assertIn("- writes: none", output)

    def test_preview_production_return_respects_disabled_flag(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("retrieval_preview.retrieve_with_gated_memory") as mock_retrieve:
                preview = preview_production_return("Find memory", Path("/vault"))

        self.assertFalse(preview.enabled)
        self.assertEqual(preview.results, ())
        mock_retrieve.assert_not_called()

    def test_preview_production_return_uses_compact_adapter_when_enabled(self):
        node = RetrievalNode(
            node_id="projects/production",
            title="Production",
            node_type="sprockets/project",
            path=Path("/vault/Sprockets/projects/production.md"),
            parent_slugs=("build-sprockets-cogs",),
            text="Compact production payload.",
        )

        with patch.dict(
            "os.environ",
            {"SPROCKETS_COGS_MEMORY_RETRIEVAL": "1"},
            clear=True,
        ):
            with patch("retrieval_preview.retrieve_with_gated_memory") as mock_retrieve:
                mock_retrieve.return_value = (node,)
                preview = preview_production_return("Find memory", Path("/vault"))

        self.assertTrue(preview.enabled)
        self.assertEqual(preview.results, (node,))
        mock_retrieve.assert_called_once_with("Find memory", Path("/vault"))

    def test_format_production_return_preview_lists_compact_nodes(self):
        node = RetrievalNode(
            node_id="projects/production",
            title="Production",
            node_type="sprockets/project",
            path=Path("/vault/Sprockets/projects/production.md"),
            parent_slugs=("build-sprockets-cogs",),
            text="Compact production payload.",
        )

        output = format_production_return_preview(
            production_return_preview_result(
                query="Find production",
                enabled=True,
                results=(node,),
            )
        )

        self.assertIn("Sprockets-Cogs production retrieval return preview", output)
        self.assertIn("- memory retrieval enabled: yes", output)
        self.assertIn("- results: 1", output)
        self.assertIn("1. projects/production [sprockets/project] Production", output)
        self.assertIn("parents: build-sprockets-cogs", output)
        self.assertIn("text: Compact production payload.", output)
        self.assertIn("- writes: none", output)

    def test_format_production_return_preview_reports_adapter_error(self):
        output = format_production_return_preview(
            production_return_preview_result(
                query="Find production",
                enabled=True,
                results=(),
                error="embedding service offline",
            )
        )

        self.assertIn("- error: embedding service offline", output)
        self.assertIn("- results: 0", output)


def preview_retrieval_result(
    query: str,
    results: tuple[RetrievalNode, ...],
    trace: object | None,
):
    from retrieval_preview import RetrievalPreview

    return RetrievalPreview(
        query=query,
        retriever_name="memory-embedding-gated-vault",
        vault_dir=Path("/vault"),
        results=results,
        trace=trace,
    )


def production_return_preview_result(
    query: str,
    enabled: bool,
    results: tuple[RetrievalNode, ...],
    error: str = "",
):
    from retrieval_preview import ProductionReturnPreview

    return ProductionReturnPreview(
        query=query,
        vault_dir=Path("/vault"),
        enabled=enabled,
        results=results,
        error=error,
    )

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_index import MemoryQuery, RetrievalConfidence, RetrievalTrace
from production_retrieval import ProductionRetrievalStatus
from retrieval_eval import ExperimentalRetriever, RetrievalNode
from retrieval_preview import format_preview, format_status, preview_retrieval


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

    def test_format_status_summarizes_guarded_production_retrieval(self):
        output = format_status(
            ProductionRetrievalStatus(
                enabled=False,
                retriever_name="memory-embedding-gated-vault",
                vault_dir=Path("/vault"),
            )
        )

        self.assertIn("Sprockets-Cogs production retrieval status", output)
        self.assertIn("- memory retrieval: disabled", output)
        self.assertIn("- enable env: SPROCKETS_COGS_MEMORY_RETRIEVAL", output)
        self.assertIn("- retriever: memory-embedding-gated-vault", output)
        self.assertIn("- vault: /vault", output)


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

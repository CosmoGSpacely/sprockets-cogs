import os
import unittest
from pathlib import Path
from unittest.mock import patch

import agentic_loop
import production_retrieval
from retrieval_eval import ExperimentalRetriever, RetrievalNode


class Stage17ProductionRetrievalTests(unittest.TestCase):
    def test_memory_retrieval_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(production_retrieval.memory_retrieval_enabled())

    def test_memory_retrieval_flag_accepts_truthy_values(self):
        for value in ("1", "true", "yes", "on", " TRUE "):
            with self.subTest(value=value):
                with patch.dict(
                    os.environ,
                    {production_retrieval.MEMORY_RETRIEVAL_ENV: value},
                    clear=True,
                ):
                    self.assertTrue(production_retrieval.memory_retrieval_enabled())

    def test_memory_context_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(production_retrieval.memory_context_enabled())

    def test_memory_context_flag_accepts_truthy_values(self):
        for value in ("1", "true", "yes", "on", " TRUE "):
            with self.subTest(value=value):
                with patch.dict(
                    os.environ,
                    {production_retrieval.MEMORY_CONTEXT_ENV: value},
                    clear=True,
                ):
                    self.assertTrue(production_retrieval.memory_context_enabled())

    def test_configured_memory_retriever_defaults_to_gated_memory(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                production_retrieval.configured_memory_retriever(),
                "memory-embedding-gated-vault",
            )

    def test_configured_memory_retriever_rejects_unsafe_experimental_modes(self):
        with patch.dict(
            os.environ,
            {production_retrieval.RETRIEVER_ENV: "hybrid-graph-intent-vault"},
            clear=True,
        ):
            self.assertEqual(
                production_retrieval.configured_memory_retriever(),
                "memory-embedding-gated-vault",
            )
            self.assertEqual(
                production_retrieval.raw_memory_retriever_config(),
                "hybrid-graph-intent-vault",
            )

    def test_production_retrieval_status_reports_flag_retriever_and_vault(self):
        with patch.dict(
            os.environ,
            {
                production_retrieval.MEMORY_RETRIEVAL_ENV: "yes",
                production_retrieval.MEMORY_CONTEXT_ENV: "on",
                production_retrieval.RETRIEVER_ENV: "memory-vault",
            },
            clear=True,
        ):
            status = production_retrieval.production_retrieval_status(Path("/vault"))

        self.assertTrue(status.enabled)
        self.assertTrue(status.context_enabled)
        self.assertEqual(status.retriever_name, "memory-vault")
        self.assertEqual(status.raw_retriever_name, "memory-vault")
        self.assertTrue(status.retriever_env_accepted)
        self.assertEqual(status.vault_dir, Path("/vault"))
        self.assertEqual(status.enable_env, production_retrieval.MEMORY_RETRIEVAL_ENV)
        self.assertEqual(status.context_env, production_retrieval.MEMORY_CONTEXT_ENV)
        self.assertEqual(status.retriever_env, production_retrieval.RETRIEVER_ENV)
        self.assertEqual(
            set(status.allowed_retrievers),
            {"memory-embedding-gated-vault", "memory-vault"},
        )

    def test_production_retrieval_status_reports_rejected_retriever_env(self):
        with patch.dict(
            os.environ,
            {production_retrieval.RETRIEVER_ENV: "embedding-vault"},
            clear=True,
        ):
            status = production_retrieval.production_retrieval_status(Path("/vault"))

        self.assertEqual(status.retriever_name, "memory-embedding-gated-vault")
        self.assertEqual(status.raw_retriever_name, "embedding-vault")
        self.assertFalse(status.retriever_env_accepted)

    def test_retrieve_with_gated_memory_uses_configured_experimental_retriever(self):
        node = RetrievalNode(
            node_id="projects/learn-how-to-bring-a-project-to-production",
            title="Learn how to bring a project to production",
            node_type="sprockets/project",
            path=Path("/vault/Sprockets/projects/production.md"),
        )
        experimental = ExperimentalRetriever(
            name="memory-vault",
            nodes=(node,),
            retriever=lambda _query: (node, "not-a-node"),
        )

        with patch.dict(
            os.environ,
            {production_retrieval.RETRIEVER_ENV: "memory-vault"},
            clear=True,
        ):
            with patch("production_retrieval.build_experimental_retriever") as mock_build:
                mock_build.return_value = experimental
                results = production_retrieval.retrieve_with_gated_memory(
                    "production readiness",
                    Path("/vault"),
                )

        mock_build.assert_called_once_with("memory-vault", Path("/vault"))
        self.assertEqual(results, (node,))

    def test_format_retrieval_context_compacts_nodes_for_prompt_use(self):
        node = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("/vault/Sprockets/projects/phase-3-memory-enhancement.md"),
            parent_slugs=("build-sprockets-cogs",),
            text="This project covers retrieval readiness.\nIt should remain compact.",
        )

        context = production_retrieval.format_retrieval_context((node,))

        self.assertIn("Relevant memory:", context)
        self.assertIn("Use these only as lookup hints", context)
        self.assertIn("Do not copy memory text into title, item_text, date", context)
        self.assertIn("For parent_hint, use the exact title", context)
        self.assertIn(
            "- projects/phase-3-memory-enhancement [sprockets/project] Phase 3 - Memory Enhancement",
            context,
        )
        self.assertIn("parents: build-sprockets-cogs", context)
        self.assertIn("text: This project covers retrieval readiness. It should remain compact.", context)

    def test_format_retrieval_context_limits_nodes_and_text(self):
        first = RetrievalNode(
            node_id="notes/first",
            title="First",
            node_type="sprockets/note",
            path=Path("/vault/first.md"),
            text="abcdefghijklmnopqrstuvwxyz",
        )
        second = RetrievalNode(
            node_id="notes/second",
            title="Second",
            node_type="sprockets/note",
            path=Path("/vault/second.md"),
        )

        context = production_retrieval.format_retrieval_context(
            (first, second),
            node_limit=1,
            text_limit=10,
        )

        self.assertIn("notes/first", context)
        self.assertIn("text: abcdefghij...", context)
        self.assertNotIn("notes/second", context)

    def test_format_retrieval_context_returns_empty_for_no_nodes(self):
        self.assertEqual(production_retrieval.format_retrieval_context(()), "")

    def test_agentic_loop_retrieval_stays_empty_when_flag_is_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("production_retrieval.retrieve_with_gated_memory") as mock_retrieve:
                results = agentic_loop.retrieve_relevant_nodes("memory")

        self.assertEqual(results, [])

    def test_agentic_loop_context_for_input_omits_memory_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(agentic_loop, "build_context", return_value="Base context"):
                with patch.object(agentic_loop, "retrieve_relevant_nodes") as mock_retrieve:
                    context = agentic_loop.build_context_for_input("Find memory")

        self.assertEqual(context, "Base context")
        mock_retrieve.assert_not_called()

    def test_agentic_loop_context_for_input_can_append_relevant_memory(self):
        node = RetrievalNode(
            node_id="notes/memory",
            title="Memory",
            node_type="sprockets/note",
            path=Path("/vault/Sprockets/notes/memory.md"),
        )

        with patch.dict(
            os.environ,
            {production_retrieval.MEMORY_CONTEXT_ENV: "1"},
            clear=True,
        ):
            with patch.object(agentic_loop, "build_context", return_value="Base context"):
                with patch.object(agentic_loop, "retrieve_relevant_nodes") as mock_retrieve:
                    mock_retrieve.return_value = [node]
                    context = agentic_loop.build_context_for_input("Find memory")

        self.assertIn("Base context", context)
        self.assertIn("Relevant memory:", context)
        self.assertIn("Do not copy memory text into title, item_text, date", context)
        self.assertIn("- notes/memory [sprockets/note] Memory", context)
        mock_retrieve.assert_called_once_with("Find memory")

    def test_agentic_loop_retrieval_uses_adapter_when_flag_is_enabled(self):
        node = RetrievalNode(
            node_id="notes/memory",
            title="Memory",
            node_type="sprockets/note",
            path=Path("/vault/Sprockets/notes/memory.md"),
        )

        with patch.dict(
            os.environ,
            {production_retrieval.MEMORY_RETRIEVAL_ENV: "1"},
            clear=True,
        ):
            with patch("production_retrieval.retrieve_with_gated_memory") as mock_retrieve:
                mock_retrieve.return_value = (node,)
                results = agentic_loop.retrieve_relevant_nodes("memory")

        self.assertEqual(results, [node])
        mock_retrieve.assert_called_once_with("memory", agentic_loop.VAULT_DIR)

    def test_agentic_loop_retrieval_falls_back_empty_on_adapter_error(self):
        with patch.dict(
            os.environ,
            {production_retrieval.MEMORY_RETRIEVAL_ENV: "1"},
            clear=True,
        ):
            with patch("production_retrieval.retrieve_with_gated_memory") as mock_retrieve:
                mock_retrieve.side_effect = RuntimeError("offline")
                results = agentic_loop.retrieve_relevant_nodes("memory")

        self.assertEqual(results, [])

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

    def test_configured_memory_retriever_defaults_to_gated_memory(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                production_retrieval.configured_memory_retriever(),
                "memory-embedding-gated-vault",
            )

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

    def test_agentic_loop_retrieval_stays_empty_when_flag_is_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("production_retrieval.retrieve_with_gated_memory") as mock_retrieve:
                results = agentic_loop.retrieve_relevant_nodes("memory")

        self.assertEqual(results, [])
        mock_retrieve.assert_not_called()

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

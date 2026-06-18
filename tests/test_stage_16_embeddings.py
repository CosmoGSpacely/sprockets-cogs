import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import specialists.rudi.embeddings as embeddings
from specialists.rudi.retrieval_eval import RetrievalNode


class Stage16EmbeddingTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(embeddings)

    def test_embed_model_defaults_to_nomic_embed_text(self):
        with patch.dict(os.environ, {}, clear=True):
            reloaded = importlib.reload(embeddings)

        self.assertEqual(reloaded.DEFAULT_EMBED_MODEL, "nomic-embed-text")
        self.assertEqual(reloaded.EMBED_MODEL, "nomic-embed-text")
        self.assertEqual(reloaded.DEFAULT_EMBED_KEEP_ALIVE, "24h")
        self.assertEqual(reloaded.EMBED_KEEP_ALIVE, "24h")
        self.assertEqual(
            reloaded.DEFAULT_EMBED_CACHE_PATH,
            Path.home() / ".cache" / "sprockets-cogs" / "specialists.rudi.embeddings.json",
        )

    def test_embed_model_can_be_overridden_by_environment(self):
        with patch.dict(os.environ, {"SPROCKETS_COGS_EMBED_MODEL": "test-embed-model"}):
            reloaded = importlib.reload(embeddings)

        self.assertEqual(reloaded.EMBED_MODEL, "test-embed-model")

    def test_embed_keep_alive_can_be_overridden_by_environment(self):
        with patch.dict(os.environ, {"SPROCKETS_COGS_EMBED_KEEP_ALIVE": "1h"}):
            reloaded = importlib.reload(embeddings)

        self.assertEqual(reloaded.EMBED_KEEP_ALIVE, "1h")

    def test_embed_cache_path_can_be_overridden_by_environment(self):
        with patch.dict(os.environ, {"SPROCKETS_COGS_EMBED_CACHE_PATH": "/tmp/test-embeddings.json"}):
            reloaded = importlib.reload(embeddings)

        self.assertEqual(reloaded.EMBED_CACHE_PATH, Path("/tmp/test-embeddings.json"))

    @patch("specialists.rudi.embeddings.ollama.embed")
    def test_embed_text_returns_single_numeric_vector(self, mock_embed):
        mock_embed.return_value = {"embeddings": [[1, 2.5, -3]]}

        vector = embeddings.embed_text("memory probe")

        self.assertEqual(vector, [1.0, 2.5, -3.0])
        mock_embed.assert_called_once_with(
            model="nomic-embed-text",
            input="memory probe",
            keep_alive="24h",
        )

    @patch("specialists.rudi.embeddings.ollama.embed")
    def test_embed_text_accepts_explicit_model(self, mock_embed):
        mock_embed.return_value = {"embeddings": [[0.1]]}

        embeddings.embed_text("memory probe", model="alternate-model")

        mock_embed.assert_called_once_with(
            model="alternate-model",
            input="memory probe",
            keep_alive="24h",
        )

    def test_embed_text_rejects_empty_text(self):
        with self.assertRaisesRegex(ValueError, "text cannot be empty"):
            embeddings.embed_text("   ")

    @patch("specialists.rudi.embeddings.ollama.embed")
    def test_embed_text_rejects_missing_embeddings(self, mock_embed):
        mock_embed.return_value = {}

        with self.assertRaisesRegex(embeddings.EmbeddingError, "missing embeddings list"):
            embeddings.embed_text("memory probe")

    @patch("specialists.rudi.embeddings.ollama.embed")
    def test_embed_text_wraps_client_errors(self, mock_embed):
        mock_embed.side_effect = ConnectionError("ollama is down")

        with self.assertRaisesRegex(embeddings.EmbeddingError, "embedding request failed"):
            embeddings.embed_text("memory probe")

    @patch("specialists.rudi.embeddings.ollama.embed")
    def test_embed_text_rejects_multiple_embeddings_for_single_text(self, mock_embed):
        mock_embed.return_value = {"embeddings": [[0.1], [0.2]]}

        with self.assertRaisesRegex(embeddings.EmbeddingError, "expected exactly one embedding"):
            embeddings.embed_text("memory probe")

    @patch("specialists.rudi.embeddings.ollama.embed")
    def test_embed_text_rejects_non_numeric_vector(self, mock_embed):
        mock_embed.return_value = {"embeddings": [["not-a-number"]]}

        with self.assertRaisesRegex(embeddings.EmbeddingError, "only numbers"):
            embeddings.embed_text("memory probe")

    def test_node_embedding_text_includes_stable_identity_metadata_and_body(self):
        node = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path="phase-3-memory-enhancement.md",
            parent_slugs=("build-sprockets-cogs",),
            text="Improve memory retrieval.",
        )

        text = embeddings.node_embedding_text(node)

        self.assertEqual(
            text,
            "id: projects/phase-3-memory-enhancement\n"
            "type: sprockets/project\n"
            "title: Phase 3 - Memory Enhancement\n"
            "parents: build-sprockets-cogs\n"
            "text: Improve memory retrieval.",
        )

    def test_node_embedding_text_omits_empty_optional_fields(self):
        node = RetrievalNode(
            node_id="contacts/alex-rivera",
            title="Alex Rivera",
            node_type="sprockets/contact",
            path="alex-rivera.md",
        )

        text = embeddings.node_embedding_text(node)

        self.assertEqual(
            text,
            "id: contacts/alex-rivera\n"
            "type: sprockets/contact\n"
            "title: Alex Rivera",
        )

    @patch("specialists.rudi.embeddings.embed_text")
    def test_embed_node_embeds_stable_node_text(self, mock_embed_text):
        mock_embed_text.return_value = [0.1, 0.2]
        node = RetrievalNode(
            node_id="daily/2026-05-03",
            title="Sun 03 May 2026",
            node_type="cogs/daily",
            path="Sun 03 May 2026.md",
            text="- [ ] Continue Stage 16",
        )

        vector = embeddings.embed_node(node, model="test-embed-model")

        self.assertEqual(vector, [0.1, 0.2])
        mock_embed_text.assert_called_once_with(
            "id: daily/2026-05-03\n"
            "type: cogs/daily\n"
            "title: Sun 03 May 2026\n"
            "text: - [ ] Continue Stage 16",
            model="test-embed-model",
        )

    @patch("specialists.rudi.embeddings.embed_text")
    def test_build_embedding_index_pairs_nodes_with_vectors(self, mock_embed_text):
        nodes = [
            RetrievalNode(
                node_id="projects/phase-3-memory-enhancement",
                title="Phase 3 - Memory Enhancement",
                node_type="sprockets/project",
                path="phase-3-memory-enhancement.md",
            ),
            RetrievalNode(
                node_id="contacts/alex-rivera",
                title="Alex Rivera",
                node_type="sprockets/contact",
                path="alex-rivera.md",
            ),
        ]
        mock_embed_text.side_effect = [[1, 0], [0, 1]]

        index = embeddings.build_embedding_index(nodes, model="test-embed-model")

        self.assertEqual([item.node.node_id for item in index], [
            "projects/phase-3-memory-enhancement",
            "contacts/alex-rivera",
        ])
        self.assertEqual(index[0].vector, (1.0, 0.0))
        self.assertEqual(index[1].vector, (0.0, 1.0))
        mock_embed_text.assert_any_call(
            "id: projects/phase-3-memory-enhancement\n"
            "type: sprockets/project\n"
            "title: Phase 3 - Memory Enhancement",
            model="test-embed-model",
        )
        mock_embed_text.assert_any_call(
            "id: contacts/alex-rivera\n"
            "type: sprockets/contact\n"
            "title: Alex Rivera",
            model="test-embed-model",
        )

    @patch("specialists.rudi.embeddings.embed_text")
    def test_build_embedding_index_reuses_cached_vectors(self, mock_embed_text):
        node = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path="phase-3-memory-enhancement.md",
            text="Memory retrieval.",
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache = embeddings.JsonEmbeddingCache(Path(tmp) / "specialists.rudi.embeddings.json")
            text = embeddings.node_embedding_text(node)
            cache.set(
                node.node_id,
                "test-embed-model",
                embeddings.embedding_text_hash(text),
                [0.1, 0.2],
            )

            index = embeddings.build_embedding_index(
                [node],
                model="test-embed-model",
                cache=cache,
            )

        self.assertEqual(index[0].vector, (0.1, 0.2))
        mock_embed_text.assert_not_called()

    @patch("specialists.rudi.embeddings.embed_text")
    def test_build_embedding_index_updates_cache_when_text_changes(self, mock_embed_text):
        mock_embed_text.return_value = [0.3, 0.4]
        node = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path="phase-3-memory-enhancement.md",
            text="New memory retrieval text.",
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache = embeddings.JsonEmbeddingCache(Path(tmp) / "specialists.rudi.embeddings.json")
            cache.set(node.node_id, "test-embed-model", "old-hash", [0.1, 0.2])

            index = embeddings.build_embedding_index(
                [node],
                model="test-embed-model",
                cache=cache,
            )
            text_hash = embeddings.embedding_text_hash(embeddings.node_embedding_text(node))
            cached_vector = cache.get(node.node_id, "test-embed-model", text_hash)

        self.assertEqual(index[0].vector, (0.3, 0.4))
        self.assertEqual(cached_vector, (0.3, 0.4))
        mock_embed_text.assert_called_once()

    def test_json_embedding_cache_ignores_unknown_schema_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "specialists.rudi.embeddings.json"
            path.write_text('{"schema_version": 999, "entries": {"node": "old"}}')
            cache = embeddings.JsonEmbeddingCache(path)

            self.assertIsNone(cache.get("node", "model", "hash"))

    @patch("specialists.rudi.embeddings.embed_text")
    def test_retrieve_by_embedding_ranks_nodes_by_cosine_similarity(self, mock_embed_text):
        mock_embed_text.return_value = [1, 0]
        memory = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path="phase-3-memory-enhancement.md",
        )
        contact = RetrievalNode(
            node_id="contacts/alex-rivera",
            title="Alex Rivera",
            node_type="sprockets/contact",
            path="alex-rivera.md",
        )
        index = (
            embeddings.EmbeddedNode(node=contact, vector=(0.0, 1.0)),
            embeddings.EmbeddedNode(node=memory, vector=(0.9, 0.1)),
        )

        results = embeddings.retrieve_by_embedding(
            "run beyond my laptop",
            index,
            limit=1,
            model="test-embed-model",
        )

        self.assertEqual([node.node_id for node in results], [
            "projects/phase-3-memory-enhancement",
        ])
        mock_embed_text.assert_called_once_with("run beyond my laptop", model="test-embed-model")

    @patch("specialists.rudi.embeddings.embed_text")
    def test_retrieve_by_embedding_tiebreaks_by_node_id(self, mock_embed_text):
        mock_embed_text.return_value = [1, 0]
        later = RetrievalNode(
            node_id="projects/zeta",
            title="Zeta",
            node_type="sprockets/project",
            path="zeta.md",
        )
        earlier = RetrievalNode(
            node_id="projects/alpha",
            title="Alpha",
            node_type="sprockets/project",
            path="alpha.md",
        )
        index = (
            embeddings.EmbeddedNode(node=later, vector=(1.0, 0.0)),
            embeddings.EmbeddedNode(node=earlier, vector=(1.0, 0.0)),
        )

        results = embeddings.retrieve_by_embedding("project", index)

        self.assertEqual([node.node_id for node in results], [
            "projects/alpha",
            "projects/zeta",
        ])

    @patch("specialists.rudi.embeddings.embed_text")
    def test_retrieve_by_embedding_rejects_dimension_mismatch(self, mock_embed_text):
        mock_embed_text.return_value = [1, 0]
        node = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path="phase-3-memory-enhancement.md",
        )
        index = (embeddings.EmbeddedNode(node=node, vector=(1.0,)),)

        with self.assertRaisesRegex(embeddings.EmbeddingError, "dimensions do not match"):
            embeddings.retrieve_by_embedding("memory", index)

    @patch("specialists.rudi.embeddings.embed_text")
    def test_retrieve_by_embedding_returns_empty_for_non_positive_limit(self, mock_embed_text):
        results = embeddings.retrieve_by_embedding("memory", (), limit=0)

        self.assertEqual(results, [])
        mock_embed_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()

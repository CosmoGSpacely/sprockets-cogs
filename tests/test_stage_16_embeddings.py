import importlib
import os
import unittest
from unittest.mock import patch

import embeddings


class Stage16EmbeddingTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(embeddings)

    def test_embed_model_defaults_to_nomic_embed_text(self):
        with patch.dict(os.environ, {}, clear=True):
            reloaded = importlib.reload(embeddings)

        self.assertEqual(reloaded.DEFAULT_EMBED_MODEL, "nomic-embed-text")
        self.assertEqual(reloaded.EMBED_MODEL, "nomic-embed-text")

    def test_embed_model_can_be_overridden_by_environment(self):
        with patch.dict(os.environ, {"SPROCKETS_COGS_EMBED_MODEL": "test-embed-model"}):
            reloaded = importlib.reload(embeddings)

        self.assertEqual(reloaded.EMBED_MODEL, "test-embed-model")

    @patch("embeddings.ollama.embed")
    def test_embed_text_returns_single_numeric_vector(self, mock_embed):
        mock_embed.return_value = {"embeddings": [[1, 2.5, -3]]}

        vector = embeddings.embed_text("memory probe")

        self.assertEqual(vector, [1.0, 2.5, -3.0])
        mock_embed.assert_called_once_with(model="nomic-embed-text", input="memory probe")

    @patch("embeddings.ollama.embed")
    def test_embed_text_accepts_explicit_model(self, mock_embed):
        mock_embed.return_value = {"embeddings": [[0.1]]}

        embeddings.embed_text("memory probe", model="alternate-model")

        mock_embed.assert_called_once_with(model="alternate-model", input="memory probe")

    def test_embed_text_rejects_empty_text(self):
        with self.assertRaisesRegex(ValueError, "text cannot be empty"):
            embeddings.embed_text("   ")

    @patch("embeddings.ollama.embed")
    def test_embed_text_rejects_missing_embeddings(self, mock_embed):
        mock_embed.return_value = {}

        with self.assertRaisesRegex(embeddings.EmbeddingError, "missing embeddings list"):
            embeddings.embed_text("memory probe")

    @patch("embeddings.ollama.embed")
    def test_embed_text_wraps_client_errors(self, mock_embed):
        mock_embed.side_effect = ConnectionError("ollama is down")

        with self.assertRaisesRegex(embeddings.EmbeddingError, "embedding request failed"):
            embeddings.embed_text("memory probe")

    @patch("embeddings.ollama.embed")
    def test_embed_text_rejects_multiple_embeddings_for_single_text(self, mock_embed):
        mock_embed.return_value = {"embeddings": [[0.1], [0.2]]}

        with self.assertRaisesRegex(embeddings.EmbeddingError, "expected exactly one embedding"):
            embeddings.embed_text("memory probe")

    @patch("embeddings.ollama.embed")
    def test_embed_text_rejects_non_numeric_vector(self, mock_embed):
        mock_embed.return_value = {"embeddings": [["not-a-number"]]}

        with self.assertRaisesRegex(embeddings.EmbeddingError, "only numbers"):
            embeddings.embed_text("memory probe")


if __name__ == "__main__":
    unittest.main()

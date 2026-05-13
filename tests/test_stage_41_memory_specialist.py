import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import memory_specialist
import production_retrieval


class Stage41MemorySpecialistTests(unittest.TestCase):
    def test_cache_inventory_reports_missing_cache_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "missing.json"
            specialist = memory_specialist.MemorySpecialist(
                memory_specialist.MemorySpecialistConfig(embedding_cache_path=cache_path)
            )

            inventory = specialist.cache_inventory()

            self.assertEqual(inventory.path, cache_path)
            self.assertFalse(inventory.exists)
            self.assertFalse(inventory.readable)
            self.assertFalse(cache_path.exists())

    def test_cache_inventory_reads_entry_models_and_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "embeddings.json"
            cache_path.write_text(json.dumps({
                "schema_version": 1,
                "entries": {
                    "projects/phase-3": {
                        "model": "nomic-embed-text",
                        "text_hash": "abc",
                        "vector": [0.1, 0.2, 0.3],
                    },
                    "notes/memory": {
                        "model": "other-embed",
                        "text_hash": "def",
                        "vector": [0.4, 0.5],
                    },
                },
            }))
            specialist = memory_specialist.MemorySpecialist(
                memory_specialist.MemorySpecialistConfig(embedding_cache_path=cache_path)
            )

            inventory = specialist.cache_inventory()

            self.assertTrue(inventory.exists)
            self.assertTrue(inventory.readable)
            self.assertEqual(inventory.schema_version, 1)
            self.assertEqual(inventory.entry_count, 2)
            self.assertEqual(inventory.models, ("nomic-embed-text", "other-embed"))
            self.assertEqual(inventory.vector_dimensions, (2, 3))

    def test_cache_inventory_reports_unreadable_cache_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "embeddings.json"
            cache_path.write_text(json.dumps({"schema_version": 1, "entries": []}))
            specialist = memory_specialist.MemorySpecialist(
                memory_specialist.MemorySpecialistConfig(embedding_cache_path=cache_path)
            )

            inventory = specialist.cache_inventory()

            self.assertTrue(inventory.exists)
            self.assertFalse(inventory.readable)
            self.assertEqual(inventory.error, "entries must be an object")

    def test_inventory_includes_production_retrieval_status_without_running_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_dir = Path(tmp) / "vault"
            cache_path = Path(tmp) / "embeddings.json"
            cache_path.write_text(json.dumps({"schema_version": 1, "entries": {}}))
            specialist = memory_specialist.MemorySpecialist(
                memory_specialist.MemorySpecialistConfig(
                    vault_dir=vault_dir,
                    embedding_cache_path=cache_path,
                    embedding_model="test-embed",
                    embedding_keep_alive="1h",
                )
            )

            with patch.dict(
                "os.environ",
                {
                    production_retrieval.MEMORY_RETRIEVAL_ENV: "1",
                    production_retrieval.MEMORY_CONTEXT_ENV: "0",
                    production_retrieval.RETRIEVER_ENV: "memory-vault",
                },
                clear=True,
            ):
                inventory = specialist.inventory()

            self.assertEqual(inventory.config.vault_dir, vault_dir)
            self.assertEqual(inventory.config.embedding_model, "test-embed")
            self.assertTrue(inventory.production_status.enabled)
            self.assertFalse(inventory.production_status.context_enabled)
            self.assertEqual(inventory.production_status.retriever_name, "memory-vault")

    def test_format_cache_inventory_marks_read_only(self):
        cache = memory_specialist.EmbeddingCacheInventory(
            path=Path("/cache/embeddings.json"),
            exists=True,
            readable=True,
            schema_version=1,
            entry_count=3,
            models=("nomic-embed-text",),
            vector_dimensions=(768,),
        )

        output = memory_specialist.format_cache_inventory(cache)

        self.assertIn("Memory specialist embedding cache inventory", output)
        self.assertIn("- entries: 3", output)
        self.assertIn("- models: nomic-embed-text", output)
        self.assertIn("- vector dimensions: 768", output)
        self.assertIn("- writes: no", output)

    def test_main_prints_inventory_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_dir = Path(tmp) / "vault"
            cache_path = Path(tmp) / "embeddings.json"
            cache_path.write_text(json.dumps({"schema_version": 1, "entries": {}}))
            buf = io.StringIO()

            with redirect_stdout(buf):
                memory_specialist.main(
                    [
                        "--vault-dir",
                        str(vault_dir),
                        "--cache-path",
                        str(cache_path),
                        "--inventory",
                    ]
                )

            output = buf.getvalue()
            self.assertIn("Memory specialist inventory preview", output)
            self.assertIn("- cache entries: 0", output)
            self.assertIn("- writes: no", output)

    def test_main_prints_cache_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "embeddings.json"
            cache_path.write_text(json.dumps({"schema_version": 1, "entries": {}}))
            buf = io.StringIO()

            with redirect_stdout(buf):
                memory_specialist.main(["--cache-path", str(cache_path), "--cache"])

            output = buf.getvalue()
            self.assertIn("Memory specialist embedding cache inventory", output)
            self.assertIn("- entries: 0", output)
            self.assertIn("- writes: no", output)


if __name__ == "__main__":
    unittest.main()

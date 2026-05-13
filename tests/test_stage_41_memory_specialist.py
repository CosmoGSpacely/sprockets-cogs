import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import memory_specialist
import production_retrieval
from retrieval_eval import RetrievalNode
from retrieval_preview import RetrievalPreview, ProductionReturnPreview


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

    def test_retrieval_preview_delegates_to_existing_preview_without_writes(self):
        node = RetrievalNode(
            node_id="projects/production",
            title="Production",
            node_type="sprockets/project",
            path=Path("/vault/Sprockets/projects/production.md"),
        )
        expected = RetrievalPreview(
            query="run beyond laptop",
            retriever_name="memory-vault",
            vault_dir=Path("/vault"),
            results=(node,),
        )
        specialist = memory_specialist.MemorySpecialist(
            memory_specialist.MemorySpecialistConfig(vault_dir=Path("/vault"))
        )

        with patch("memory_specialist.retrieval_preview_module.preview_retrieval") as mock_preview:
            mock_preview.return_value = expected
            preview = specialist.retrieval_preview("run beyond laptop", retriever_name="memory-vault")

        self.assertEqual(preview, expected)
        mock_preview.assert_called_once_with(
            "run beyond laptop",
            vault_dir=Path("/vault"),
            retriever_name="memory-vault",
        )

    def test_context_preview_formats_existing_preview_without_enabling_context(self):
        specialist = memory_specialist.MemorySpecialist()

        with patch.object(specialist, "retrieval_preview") as mock_preview:
            mock_preview.return_value = RetrievalPreview(
                query="find memory",
                retriever_name="memory-embedding-gated-vault",
                vault_dir=Path("/vault"),
                results=(),
            )
            output = specialist.context_preview("find memory")

        self.assertEqual(output, "Relevant memory: (none)")

    def test_memory_guard_preview_delegates_to_existing_guard_preview(self):
        project = RetrievalNode(
            node_id="projects/production",
            title="Production",
            node_type="sprockets/project",
            path=Path("/vault/Sprockets/projects/production.md"),
        )
        specialist = memory_specialist.MemorySpecialist()

        with patch.object(specialist, "retrieval_preview") as mock_preview:
            mock_preview.return_value = RetrievalPreview(
                query="Need to make this portable",
                retriever_name="memory-embedding-gated-vault",
                vault_dir=Path("/vault"),
                results=(project,),
            )
            guard = specialist.memory_guard_preview("Need to make this portable")

        self.assertEqual(guard.parent_title, "Production")
        self.assertTrue(guard.would_apply_parent_hint)
        self.assertTrue(guard.would_add_hierarchy_task)

    def test_production_return_preview_delegates_to_existing_adapter_preview(self):
        expected = ProductionReturnPreview(
            query="find memory",
            vault_dir=Path("/vault"),
            enabled=False,
            results=(),
        )
        specialist = memory_specialist.MemorySpecialist(
            memory_specialist.MemorySpecialistConfig(vault_dir=Path("/vault"))
        )

        with patch("memory_specialist.retrieval_preview_module.preview_production_return") as mock_preview:
            mock_preview.return_value = expected
            preview = specialist.production_return_preview("find memory")

        self.assertEqual(preview, expected)
        mock_preview.assert_called_once_with("find memory", vault_dir=Path("/vault"))

    def test_format_retrieval_preview_marks_memory_boundary_and_read_only(self):
        node = RetrievalNode(
            node_id="notes/memory",
            title="Memory",
            node_type="sprockets/note",
            path=Path("/vault/Sprockets/notes/memory.md"),
        )

        output = memory_specialist.format_retrieval_preview(
            RetrievalPreview(
                query="find memory",
                retriever_name="memory-embedding-gated-vault",
                vault_dir=Path("/vault"),
                results=(node,),
            )
        )

        self.assertIn("Memory specialist retrieval preview", output)
        self.assertIn("- writes: no", output)
        self.assertIn("Sprockets-Cogs retrieval preview", output)
        self.assertIn("1. notes/memory [sprockets/note] Memory", output)

    def test_main_prints_retrieval_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_dir = Path(tmp) / "vault"
            node = RetrievalNode(
                node_id="projects/production",
                title="Production",
                node_type="sprockets/project",
                path=vault_dir / "Sprockets" / "projects" / "production.md",
            )
            buf = io.StringIO()

            with patch("memory_specialist.retrieval_preview_module.preview_retrieval") as mock_preview:
                mock_preview.return_value = RetrievalPreview(
                    query="find production",
                    retriever_name="memory-vault",
                    vault_dir=vault_dir,
                    results=(node,),
                )
                with redirect_stdout(buf):
                    memory_specialist.main(
                        [
                            "--vault-dir",
                            str(vault_dir),
                            "--retriever",
                            "memory-vault",
                            "--retrieval",
                            "find production",
                        ]
                    )

            output = buf.getvalue()
            self.assertIn("Memory specialist retrieval preview", output)
            self.assertIn("- writes: no", output)
            self.assertIn("1. projects/production [sprockets/project] Production", output)

    def test_main_prints_memory_guard_preview(self):
        node = RetrievalNode(
            node_id="projects/production",
            title="Production",
            node_type="sprockets/project",
            path=Path("/vault/Sprockets/projects/production.md"),
        )
        buf = io.StringIO()

        with patch("memory_specialist.retrieval_preview_module.preview_retrieval") as mock_preview:
            mock_preview.return_value = RetrievalPreview(
                query="Need to make this portable",
                retriever_name="memory-embedding-gated-vault",
                vault_dir=Path("/vault"),
                results=(node,),
            )
            with redirect_stdout(buf):
                memory_specialist.main(["--memory-guard", "Need to make this portable"])

        output = buf.getvalue()
        self.assertIn("Memory specialist guard preview", output)
        self.assertIn("- top hierarchy parent: Production", output)
        self.assertIn("- writes: no", output)

    def test_main_prints_production_return_preview(self):
        buf = io.StringIO()

        with patch("memory_specialist.retrieval_preview_module.preview_production_return") as mock_preview:
            mock_preview.return_value = ProductionReturnPreview(
                query="find memory",
                vault_dir=Path("/vault"),
                enabled=False,
                results=(),
            )
            with redirect_stdout(buf):
                memory_specialist.main(["--production-return", "find memory"])

        output = buf.getvalue()
        self.assertIn("Memory specialist production return preview", output)
        self.assertIn("Sprockets-Cogs production retrieval return preview", output)
        self.assertIn("- writes: no", output)

    def test_trace_report_reads_jsonl_sink_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "memory-parent-traces.jsonl"
            trace_path.write_text(
                json.dumps({
                    "schema_version": 1,
                    "created_at": "2026-05-04T12:04:00+00:00",
                    "decision": "selected",
                    "retrieved_count": 5,
                    "parent_title": "Production",
                    "parent_node_id": "projects/production",
                    "parent_node_type": "sprockets/project",
                })
            )
            specialist = memory_specialist.MemorySpecialist(
                memory_specialist.MemorySpecialistConfig(memory_trace_path=trace_path)
            )

            output = specialist.trace_report()

        self.assertIn("Sprockets-Cogs memory guard log report", output)
        self.assertIn("- events: 1", output)
        self.assertIn("parent: Production", output)

    def test_trace_report_can_read_service_log_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "service.log"
            log_path.write_text(
                "2026-05-04T10:01:02-0400 host python[123]: "
                "Memory parent guard selected: parent='Phase 3' "
                "node_id=projects/phase-3 node_type=sprockets/project retrieved=3\n"
            )
            specialist = memory_specialist.MemorySpecialist()

            output = specialist.trace_report(file_path=log_path)

        self.assertIn("- events: 1", output)
        self.assertIn("parent: Phase 3", output)
        self.assertIn("parent node: projects/phase-3 [sprockets/project]", output)

    def test_format_trace_report_marks_memory_boundary_and_read_only(self):
        output = memory_specialist.format_trace_report("Sprockets-Cogs memory guard log report\n- events: 0")

        self.assertIn("Memory specialist trace report", output)
        self.assertIn("- writes: no", output)
        self.assertIn("Sprockets-Cogs memory guard log report", output)

    def test_main_prints_trace_report_from_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "memory-parent-traces.jsonl"
            trace_path.write_text(
                json.dumps({
                    "schema_version": 1,
                    "created_at": "2026-05-04T12:04:00+00:00",
                    "decision": "selected",
                    "retrieved_count": 5,
                    "parent_title": "Production",
                    "parent_node_id": "projects/production",
                    "parent_node_type": "sprockets/project",
                })
            )
            buf = io.StringIO()

            with redirect_stdout(buf):
                memory_specialist.main(["--jsonl", str(trace_path), "--traces"])

        output = buf.getvalue()
        self.assertIn("Memory specialist trace report", output)
        self.assertIn("- writes: no", output)
        self.assertIn("parent: Production", output)

    def test_main_prints_trace_report_from_log_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "service.log"
            log_path.write_text(
                "2026-05-04T10:03:04-0400 host python[123]: "
                "Memory parent guard skipped: "
                "reason=no hierarchy parent in retrieved nodes "
                "top_node_id=contacts/taylor-reed "
                "top_node_type=sprockets/contact retrieved=5\n"
            )
            buf = io.StringIO()

            with redirect_stdout(buf):
                memory_specialist.main(["--file", str(log_path), "--decision", "skipped", "--traces"])

        output = buf.getvalue()
        self.assertIn("Memory specialist trace report", output)
        self.assertIn("- decision filter: skipped", output)
        self.assertIn("top node: contacts/taylor-reed [sprockets/contact]", output)


if __name__ == "__main__":
    unittest.main()

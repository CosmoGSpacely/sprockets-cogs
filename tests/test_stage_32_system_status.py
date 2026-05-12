import tempfile
import unittest
from pathlib import Path

import job_status
import production_retrieval
import system_status


class Stage32SystemStatusTests(unittest.TestCase):
    def test_format_system_status_includes_runtime_review_memory_and_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = system_status.RuntimeStatus(
                model="test-model",
                sc_root=root / "sc",
                input_dir=root / "sc" / "input",
                processing_dir=root / "sc" / "processing",
                archive_dir=root / "sc" / "archive",
                output_dir=root / "sc" / "output",
                vault_dir=root / "vault",
                embed_model="test-embed",
                embed_keep_alive="1h",
                embed_cache_path=root / "embeddings.json",
            )
            retrieval = production_retrieval.ProductionRetrievalStatus(
                enabled=True,
                context_enabled=False,
                retriever_name="memory-embedding-gated-vault",
                vault_dir=root / "vault",
                raw_retriever_name="memory-embedding-gated-vault",
                allowed_retrievers=("memory-embedding-gated-vault", "memory-vault"),
                node_limit=5,
                text_limit=240,
            )
            status = system_status.SystemStatus(
                runtime=runtime,
                review_report={
                    "total": 2,
                    "parseable": 1,
                    "unparseable": 1,
                    "by_source": {},
                    "by_node_type": {},
                    "by_confidence": {},
                    "by_reason": {},
                },
                retrieval_status=retrieval,
                jobs=(
                    job_status.MaintenanceJobStatus(
                        job=job_status.NIGHTLY_JOB,
                        service=job_status.UnitStatus(
                            name="sprockets-cogs-nightly.service",
                            exists=True,
                            load_state="loaded",
                            active_state="inactive",
                            sub_state="dead",
                            unit_file_state="static",
                            result="success",
                            last_exit_status="0",
                        ),
                        timer=job_status.UnitStatus(
                            name="sprockets-cogs-nightly.timer",
                            exists=True,
                            load_state="loaded",
                            active_state="active",
                            sub_state="waiting",
                            unit_file_state="enabled",
                        ),
                    ),
                ),
            )

            output = system_status.format_system_status(status)

            self.assertIn("Sprockets-Cogs status", output)
            self.assertIn("- model: test-model", output)
            self.assertIn("- embedding model: test-embed", output)
            self.assertIn("- total: 2", output)
            self.assertIn("- memory retrieval: enabled", output)
            self.assertIn("- memory context: disabled", output)
            self.assertIn("nightly: Nightly Cogs carry safety net", output)
            self.assertIn("sprockets-cogs-nightly.timer", output)

    def test_build_runtime_status_uses_configured_module_values(self):
        runtime = system_status.build_runtime_status()

        self.assertEqual(runtime.model, system_status.agentic_loop.MODEL)
        self.assertEqual(runtime.vault_dir, system_status.agentic_loop.VAULT_DIR)
        self.assertEqual(runtime.embed_model, system_status.embeddings.EMBED_MODEL)
        self.assertEqual(runtime.embed_cache_path, system_status.embeddings.EMBED_CACHE_PATH)


if __name__ == "__main__":
    unittest.main()

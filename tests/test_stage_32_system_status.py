import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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
                service=system_status.ServiceStatus(
                    unit=job_status.UnitStatus(
                        name="sprockets-cogs.service",
                        exists=True,
                        load_state="loaded",
                        active_state="active",
                        sub_state="running",
                        unit_file_state="enabled",
                        result="success",
                        last_exit_status="0",
                    ),
                    main_pid=1234,
                    env={
                        "SPROCKETS_COGS_MODEL": "test-model",
                        "SPROCKETS_COGS_MEMORY_RETRIEVAL": "1",
                        "SPROCKETS_COGS_MEMORY_CONTEXT": "0",
                    },
                ),
                directories=system_status.DirectoryStatus(
                    pending_inputs=1,
                    processing_files=0,
                    archived_inputs=12,
                    output_files=1,
                    memory_trace_exists=True,
                    oldest_pending_input="capture.input",
                ),
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
            self.assertIn("sprockets-cogs.service", output)
            self.assertIn("- main pid: 1234", output)
            self.assertIn("SPROCKETS_COGS_MEMORY_RETRIEVAL: 1", output)
            self.assertIn("Runtime queues", output)
            self.assertIn("- pending .input files: 1", output)
            self.assertIn("- oldest pending input: capture.input", output)
            self.assertIn("- memory trace file exists: yes", output)
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

    def test_build_directory_status_counts_runtime_files_without_reading_contents(self):
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
            runtime.input_dir.mkdir(parents=True)
            runtime.processing_dir.mkdir(parents=True)
            runtime.archive_dir.mkdir(parents=True)
            runtime.output_dir.mkdir(parents=True)
            (runtime.input_dir / "b.input").write_text("newer")
            (runtime.input_dir / "a.input").write_text("older")
            (runtime.input_dir / "ignore.txt").write_text("ignore")
            (runtime.processing_dir / "active.input").write_text("processing")
            (runtime.archive_dir / "done.input").write_text("archived")
            (runtime.archive_dir / "note.md").write_text("not counted")
            (runtime.output_dir / system_status.agentic_loop.MEMORY_TRACE_FILENAME).write_text("{}\n")

            status = system_status.build_directory_status(runtime)

        self.assertEqual(status.pending_inputs, 2)
        self.assertEqual(status.processing_files, 1)
        self.assertEqual(status.archived_inputs, 1)
        self.assertEqual(status.output_files, 1)
        self.assertTrue(status.memory_trace_exists)
        self.assertIn(status.oldest_pending_input, {"a.input", "b.input"})

    @patch("system_status.read_process_env")
    @patch("system_status.subprocess.run")
    def test_build_service_status_reads_selected_running_process_env(self, mock_run, mock_read_env):
        mock_run.return_value = Mock(
            stdout=(
                "LoadState=loaded\n"
                "ActiveState=active\n"
                "SubState=running\n"
                "UnitFileState=enabled\n"
                "Result=success\n"
                "ExecMainStatus=0\n"
                "MainPID=1234\n"
            ),
            stderr="",
            returncode=0,
        )
        mock_read_env.return_value = (
            {
                "SPROCKETS_COGS_MEMORY_RETRIEVAL": "1",
                "SPROCKETS_COGS_MEMORY_CONTEXT": "0",
            },
            None,
        )

        status = system_status.build_service_status()

        self.assertTrue(status.unit.exists)
        self.assertEqual(status.main_pid, 1234)
        self.assertEqual(status.env["SPROCKETS_COGS_MEMORY_RETRIEVAL"], "1")
        mock_read_env.assert_called_once_with(1234)

    @patch("system_status.subprocess.run")
    def test_build_service_status_reports_unavailable_systemd_bus(self, mock_run):
        mock_run.return_value = Mock(
            stdout="",
            stderr="Failed to connect to bus: Operation not permitted",
            returncode=1,
        )

        status = system_status.build_service_status()

        self.assertFalse(status.unit.exists)
        self.assertIn("Failed to connect to bus", status.env_error)

    def test_read_process_env_filters_selected_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc_root = Path(tmp)
            pid_dir = proc_root / "999"
            pid_dir.mkdir()
            environ = pid_dir / "environ"
            environ.write_bytes(
                b"SPROCKETS_COGS_MEMORY_RETRIEVAL=1\0"
                b"SECRET_TOKEN=do-not-report\0"
                b"SPROCKETS_COGS_MEMORY_CONTEXT=0\0"
            )

            env, error = system_status.read_process_env(999, proc_root=proc_root)

        self.assertIsNone(error)
        self.assertEqual(env["SPROCKETS_COGS_MEMORY_RETRIEVAL"], "1")
        self.assertEqual(env["SPROCKETS_COGS_MEMORY_CONTEXT"], "0")
        self.assertNotIn("SECRET_TOKEN", env)


if __name__ == "__main__":
    unittest.main()

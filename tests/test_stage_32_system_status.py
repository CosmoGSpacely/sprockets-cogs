import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import job_status
import production_retrieval
from specialists import SPECIALISTS
import system_status


class Stage32SystemStatusTests(unittest.TestCase):
    def build_sample_system_status(self, root: Path) -> system_status.SystemStatus:
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
        return system_status.SystemStatus(
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
            specialists=SPECIALISTS,
            directories=system_status.DirectoryStatus(
                pending_inputs=1,
                processing_files=0,
                archived_inputs=12,
                output_files=1,
                memory_trace_exists=True,
                oldest_pending_input="capture.input",
            ),
            models=system_status.ModelAvailabilityStatus(
                ollama_available=True,
                configured_model="test-model",
                embedding_model="test-embed",
                installed_models=("test-model", "test-embed"),
            ),
            planning=system_status.PlanningStatus(
                cogs_dir=root / "vault" / "Cogs",
                reference_date="2026-05-12",
                daily_count=3,
                weekly_count=1,
                monthly_count=1,
                annual_count=1,
                daily_legacy_count=2,
                daily_iso_count=1,
                daily_invalid_count=0,
                current_weekly_name="2026-W20.md",
                current_weekly_exists=True,
                current_monthly_name="2026-05.md",
                current_monthly_exists=True,
                current_annual_name="2026.md",
                current_annual_exists=True,
                current_5wow_anchor="2026-05",
            ),
            backup_sync=system_status.BackupSyncStatus(
                vault_dir=root / "vault",
                sc_root=root / "sc",
                code_repo=root / "repo",
                vault_exists=True,
                sc_root_exists=True,
                code_repo_exists=True,
                timeshift_home_note="system snapshots only",
                syncthing_note="replication/sync only",
                github_note="protects committed repository history",
                backup_gap="vault and SC runtime need point-in-time backup",
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

    def test_format_system_status_includes_runtime_review_memory_and_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = self.build_sample_system_status(root)

            output = system_status.format_system_status(status)

            self.assertIn("Sprockets-Cogs status", output)
            self.assertIn("- model: test-model", output)
            self.assertIn("sprockets-cogs.service", output)
            self.assertIn("- main pid: 1234", output)
            self.assertIn("SPROCKETS_COGS_MEMORY_RETRIEVAL: 1", output)
            self.assertIn("Runtime queues", output)
            self.assertIn("Specialists", output)
            self.assertIn("- Rosie: Intake and classification; Always-on file watcher service (always-on)", output)
            self.assertIn("- RUDI: Reasoning, orchestration, and memory/retrieval", output)
            self.assertIn("- message bus: contract/rehearsal only, not live dispatch", output)
            self.assertIn("- pending .input files: 1", output)
            self.assertIn("- oldest pending input: capture.input", output)
            self.assertIn("- memory trace file exists: yes", output)
            self.assertIn("- embedding model: test-embed", output)
            self.assertIn("Models", output)
            self.assertIn("- ollama available: yes", output)
            self.assertIn("- configured model installed: yes", output)
            self.assertIn("- embedding model installed: yes", output)
            self.assertIn("Planning notes", output)
            self.assertIn("- current weekly 2026-W20.md: exists", output)
            self.assertIn("- current monthly 2026-05.md: exists", output)
            self.assertIn("- current annual 2026.md: exists", output)
            self.assertIn("- current planning ready: yes", output)
            self.assertIn("- 5WOW monthly anchor: 2026-05", output)
            self.assertIn("Backup and sync posture", output)
            self.assertIn("- vault exists: yes", output)
            self.assertIn("- Syncthing: replication/sync only", output)
            self.assertIn("- gap: vault and SC runtime need point-in-time backup", output)
            self.assertIn("- total: 2", output)
            self.assertIn("- memory retrieval: enabled", output)
            self.assertIn("- memory context: disabled", output)
            self.assertIn("nightly: Nightly Cogs carry safety net", output)
            self.assertIn("sprockets-cogs-nightly.timer", output)

    def test_main_accepts_argv_for_direct_cli_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = self.build_sample_system_status(Path(tmp))
            stdout = StringIO()

            with patch("system_status.build_system_status", return_value=status), redirect_stdout(stdout):
                system_status.main(["--show-env"])

        output = stdout.getvalue()
        self.assertIn("Sprockets-Cogs status", output)
        self.assertIn("Environment", output)
        self.assertIn("SPROCKETS_COGS_MODEL", output)

    def test_build_runtime_status_uses_configured_module_values(self):
        runtime = system_status.build_runtime_status()

        self.assertEqual(runtime.model, system_status.agentic_loop.MODEL)
        self.assertEqual(runtime.vault_dir, system_status.agentic_loop.VAULT_DIR)
        self.assertEqual(runtime.embed_model, system_status.embeddings.EMBED_MODEL)
        self.assertEqual(runtime.embed_cache_path, system_status.embeddings.EMBED_CACHE_PATH)

    def test_parse_ollama_list_reads_model_names(self):
        output = (
            "NAME                           ID              SIZE      MODIFIED\n"
            "qwen3.5:9b-32k-cosmo          abc123          7.0 GB    2 days ago\n"
            "nomic-embed-text:latest        def456          274 MB    3 days ago\n"
        )

        models = system_status.parse_ollama_list(output)

        self.assertEqual(models, ("qwen3.5:9b-32k-cosmo", "nomic-embed-text:latest"))

    def test_model_availability_accepts_implicit_latest_tag(self):
        status = system_status.ModelAvailabilityStatus(
            ollama_available=True,
            configured_model="test-model",
            embedding_model="nomic-embed-text",
            installed_models=("test-model:latest", "nomic-embed-text:latest"),
        )

        self.assertTrue(status.configured_model_installed)
        self.assertTrue(status.embedding_model_installed)

    @patch("system_status.subprocess.run")
    def test_build_model_availability_status_reports_installed_models(self, mock_run):
        runtime = system_status.RuntimeStatus(
            model="qwen3.5:9b-32k-cosmo",
            sc_root=Path("/tmp/sc"),
            input_dir=Path("/tmp/sc/input"),
            processing_dir=Path("/tmp/sc/processing"),
            archive_dir=Path("/tmp/sc/archive"),
            output_dir=Path("/tmp/sc/output"),
            vault_dir=Path("/tmp/vault"),
            embed_model="nomic-embed-text:latest",
            embed_keep_alive="24h",
            embed_cache_path=Path("/tmp/embeddings.json"),
        )
        mock_run.return_value = Mock(
            stdout=(
                "NAME                           ID              SIZE      MODIFIED\n"
                "qwen3.5:9b-32k-cosmo          abc123          7.0 GB    2 days ago\n"
                "nomic-embed-text:latest        def456          274 MB    3 days ago\n"
            ),
            stderr="",
            returncode=0,
        )

        status = system_status.build_model_availability_status(runtime)

        self.assertTrue(status.ollama_available)
        self.assertTrue(status.configured_model_installed)
        self.assertTrue(status.embedding_model_installed)
        mock_run.assert_called_once()

    @patch("system_status.subprocess.run")
    def test_build_model_availability_status_reports_unavailable_ollama(self, mock_run):
        runtime = system_status.RuntimeStatus(
            model="test-model",
            sc_root=Path("/tmp/sc"),
            input_dir=Path("/tmp/sc/input"),
            processing_dir=Path("/tmp/sc/processing"),
            archive_dir=Path("/tmp/sc/archive"),
            output_dir=Path("/tmp/sc/output"),
            vault_dir=Path("/tmp/vault"),
            embed_model="test-embed",
            embed_keep_alive="24h",
            embed_cache_path=Path("/tmp/embeddings.json"),
        )
        mock_run.return_value = Mock(
            stdout="",
            stderr="could not connect to ollama",
            returncode=1,
        )

        status = system_status.build_model_availability_status(runtime)

        self.assertFalse(status.ollama_available)
        self.assertIn("could not connect", status.error)

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

    def test_build_planning_status_reports_current_note_presence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cogs_dir = root / "vault" / "Cogs"
            (cogs_dir / "daily").mkdir(parents=True)
            (cogs_dir / "weekly").mkdir(parents=True)
            (cogs_dir / "monthly").mkdir(parents=True)
            (cogs_dir / "annual").mkdir(parents=True)
            (cogs_dir / "daily" / "Tue 12 May 2026.md").write_text("# legacy\n")
            (cogs_dir / "weekly" / "2026-W20.md").write_text("# week\n")
            (cogs_dir / "monthly" / "2026-05.md").write_text("# month\n")
            (cogs_dir / "annual" / "2026.md").write_text("# year\n")
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

            status = system_status.build_planning_status(runtime, "2026-05-12")

        self.assertEqual(status.current_weekly_name, "2026-W20.md")
        self.assertTrue(status.current_weekly_exists)
        self.assertTrue(status.current_monthly_exists)
        self.assertTrue(status.current_annual_exists)
        self.assertTrue(status.current_planning_ready)
        self.assertEqual(status.current_5wow_anchor, "2026-05")

    def test_build_backup_sync_status_reports_known_gap_without_external_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "vault").mkdir()
            (root / "sc").mkdir()
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

            status = system_status.build_backup_sync_status(runtime)

        self.assertTrue(status.vault_exists)
        self.assertTrue(status.sc_root_exists)
        self.assertIn("not treated as covered", status.timeshift_home_note)
        self.assertIn("not a point-in-time backup", status.syncthing_note)
        self.assertIn("vault and SC runtime", status.backup_gap)

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

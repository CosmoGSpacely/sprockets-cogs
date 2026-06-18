import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import specialists.uniblab.backup as sc_backup


class Stage63ScBackupTests(unittest.TestCase):
    def test_preview_includes_durable_operational_paths_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "sc"
            (sc_root / "archive").mkdir(parents=True)
            (sc_root / "output").mkdir()
            (sc_root / "processing").mkdir()
            (sc_root / "input").mkdir()
            (sc_root / "archive" / "done.input").write_text("done", encoding="utf-8")
            (sc_root / "output" / "review-packet.md").write_text("packet", encoding="utf-8")
            (sc_root / "entity_state.json").write_text("{}", encoding="utf-8")
            (sc_root / "processing" / "active.input").write_text("active", encoding="utf-8")
            (sc_root / "input" / "pending.input").write_text("pending", encoding="utf-8")

            preview = sc_backup.build_backup_preview(sc_root)

        included_labels = {item.label for item in preview.included_paths}
        excluded_labels = {item.label for item in preview.excluded_paths}
        self.assertEqual(included_labels, {"archive", "output", "entity_state"})
        self.assertIn("input", excluded_labels)
        self.assertIn("processing", excluded_labels)
        self.assertEqual(preview.included_file_count, 3)
        self.assertTrue(any("processing/ is non-empty" in warning for warning in preview.warnings))
        self.assertTrue(any("input/ contains 1 file" in warning for warning in preview.warnings))

    def test_preview_can_include_input_for_stuck_intake_debugging(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "sc"
            (sc_root / "archive").mkdir(parents=True)
            (sc_root / "input").mkdir()
            (sc_root / "input" / "pending.input").write_text("pending", encoding="utf-8")

            preview = sc_backup.build_backup_preview(sc_root, include_input=True)

        included_labels = {item.label for item in preview.included_paths}
        self.assertIn("input", included_labels)
        self.assertFalse(any("pass --include-input" in warning for warning in preview.warnings))

    def test_format_preview_is_read_only_and_names_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "sc"
            (sc_root / "archive").mkdir(parents=True)
            (sc_root / "archive" / "done.input").write_text("done", encoding="utf-8")

            output = sc_backup.format_backup_preview(sc_backup.build_backup_preview(sc_root))

        self.assertIn("SC backup preview", output)
        self.assertIn("- writes: no", output)
        self.assertIn("Included paths", output)
        self.assertIn("archive", output)
        self.assertIn("Excluded paths", output)

    def test_cli_json_preview_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "sc"
            (sc_root / "archive").mkdir(parents=True)
            (sc_root / "archive" / "done.input").write_text("done", encoding="utf-8")
            stdout = StringIO()

            with redirect_stdout(stdout):
                sc_backup.main(["--sc-root", str(sc_root), "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["writes"], "none")
        self.assertEqual(payload["included_file_count"], 1)
        self.assertTrue(any(item["label"] == "archive" for item in payload["paths"]))

    def test_create_snapshot_copies_durable_paths_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "sc"
            backup_path = Path(tmp) / "backups" / "sc-test"
            (sc_root / "archive").mkdir(parents=True)
            (sc_root / "output").mkdir()
            (sc_root / "processing").mkdir()
            (sc_root / "input").mkdir()
            (sc_root / "archive" / "done.input").write_text("done", encoding="utf-8")
            (sc_root / "output" / "review-packet.md").write_text("packet", encoding="utf-8")
            (sc_root / "entity_state.json").write_text("{}", encoding="utf-8")
            (sc_root / "processing" / "active.input").write_text("active", encoding="utf-8")
            (sc_root / "input" / "pending.input").write_text("pending", encoding="utf-8")

            result = sc_backup.create_backup_snapshot(sc_root, out=backup_path)

            self.assertTrue((result.backup_path / "archive" / "done.input").exists())
            self.assertTrue((result.backup_path / "output" / "review-packet.md").exists())
            self.assertTrue((result.backup_path / "entity_state.json").exists())
            self.assertTrue((result.backup_path / "manifest.json").exists())
            self.assertFalse((result.backup_path / "processing" / "active.input").exists())
            self.assertFalse((result.backup_path / "input" / "pending.input").exists())
            manifest = json.loads((result.backup_path / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["format"], sc_backup.BACKUP_FORMAT)
        self.assertFalse(manifest["include_input"])
        self.assertEqual(manifest["included_file_count"], 3)

    def test_create_snapshot_can_include_input_when_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "sc"
            backup_path = Path(tmp) / "backups" / "sc-test"
            (sc_root / "input").mkdir(parents=True)
            (sc_root / "input" / "pending.input").write_text("pending", encoding="utf-8")

            result = sc_backup.create_backup_snapshot(sc_root, out=backup_path, include_input=True)

            self.assertTrue((result.backup_path / "input" / "pending.input").exists())

    def test_create_snapshot_refuses_existing_out_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "sc"
            backup_path = Path(tmp) / "backups" / "sc-test"
            (sc_root / "archive").mkdir(parents=True)
            backup_path.mkdir(parents=True)

            with self.assertRaises(FileExistsError):
                sc_backup.create_backup_snapshot(sc_root, out=backup_path)

    def test_create_snapshot_refuses_empty_missing_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "missing-sc"
            backup_path = Path(tmp) / "backups" / "sc-test"

            with self.assertRaises(ValueError):
                sc_backup.create_backup_snapshot(sc_root, out=backup_path)

            self.assertFalse(backup_path.exists())

    def test_status_reports_latest_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_root = Path(tmp) / "backups"
            first = backup_root / "sc-20260524-101010"
            second = backup_root / "sc-20260524-111010"
            first.mkdir(parents=True)
            second.mkdir()

            status = sc_backup.build_backup_status(backup_root)

        self.assertTrue(status.exists)
        self.assertEqual(status.snapshot_count, 2)
        self.assertEqual(status.latest_snapshot, second)

    def test_cli_status_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_root = Path(tmp) / "backups"
            stdout = StringIO()

            with redirect_stdout(stdout):
                sc_backup.main(["--status", "--backup-root", str(backup_root), "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["writes"], "none")
        self.assertFalse(payload["exists"])

    def test_cli_create_writes_snapshot_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "sc"
            backup_path = Path(tmp) / "backups" / "sc-test"
            (sc_root / "archive").mkdir(parents=True)
            (sc_root / "archive" / "done.input").write_text("done", encoding="utf-8")
            stdout = StringIO()

            with redirect_stdout(stdout):
                sc_backup.main(["--create", "--sc-root", str(sc_root), "--out", str(backup_path), "--json"])

            payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["writes"], "backup")
        self.assertEqual(payload["copied_file_count"], 1)
        self.assertEqual(payload["backup_path"], str(backup_path))

    def test_verify_snapshot_checks_manifest_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "sc"
            backup_path = Path(tmp) / "backups" / "sc-test"
            (sc_root / "archive").mkdir(parents=True)
            (sc_root / "archive" / "done.input").write_text("done", encoding="utf-8")
            sc_backup.create_backup_snapshot(sc_root, out=backup_path)

            verification = sc_backup.verify_backup_snapshot(backup_path)

        self.assertTrue(verification.ok)
        self.assertEqual(len(verification.checks), 1)
        self.assertEqual(verification.checks[0].label, "archive")
        self.assertEqual(verification.checks[0].actual_file_count, 1)

    def test_verify_snapshot_reports_missing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_path = Path(tmp) / "backups" / "sc-test"
            backup_path.mkdir(parents=True)

            verification = sc_backup.verify_backup_snapshot(backup_path)

        self.assertFalse(verification.ok)
        self.assertTrue(any("missing manifest" in issue for issue in verification.issues))

    def test_restore_preview_is_read_only_and_names_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "sc"
            backup_path = Path(tmp) / "backups" / "sc-test"
            restore_to = Path(tmp) / "restore-inspect"
            (sc_root / "archive").mkdir(parents=True)
            (sc_root / "archive" / "done.input").write_text("done", encoding="utf-8")
            sc_backup.create_backup_snapshot(sc_root, out=backup_path)

            preview = sc_backup.build_restore_preview(backup_path, restore_to)
            output = sc_backup.format_restore_preview(preview)

        self.assertTrue(preview.verification.ok)
        self.assertEqual(preview.targets[0].target, restore_to / "archive")
        self.assertFalse((restore_to / "archive").exists())
        self.assertIn("- writes: no", output)
        self.assertIn("Would copy", output)

    def test_restore_preview_warns_about_existing_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "sc"
            backup_path = Path(tmp) / "backups" / "sc-test"
            restore_to = Path(tmp) / "restore-inspect"
            (sc_root / "archive").mkdir(parents=True)
            (sc_root / "archive" / "done.input").write_text("done", encoding="utf-8")
            (restore_to / "archive").mkdir(parents=True)
            sc_backup.create_backup_snapshot(sc_root, out=backup_path)

            preview = sc_backup.build_restore_preview(backup_path, restore_to)

        self.assertTrue(any("target exists" in warning for warning in preview.warnings))

    def test_cli_verify_defaults_to_latest_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "sc"
            backup_root = Path(tmp) / "backups"
            (sc_root / "archive").mkdir(parents=True)
            (sc_root / "archive" / "done.input").write_text("done", encoding="utf-8")
            sc_backup.create_backup_snapshot(sc_root, backup_root=backup_root)
            stdout = StringIO()

            with redirect_stdout(stdout):
                sc_backup.main(["--verify", "--backup-root", str(backup_root), "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["writes"], "none")
        self.assertTrue(payload["ok"])

    def test_cli_restore_preview_requires_restore_to(self):
        stderr = StringIO()

        with redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            sc_backup.main(["--restore-preview", "--backup", "/tmp/backup"])

        self.assertEqual(caught.exception.code, 2)

    def test_cli_restore_preview_json_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc_root = Path(tmp) / "sc"
            backup_path = Path(tmp) / "backups" / "sc-test"
            restore_to = Path(tmp) / "restore-inspect"
            (sc_root / "archive").mkdir(parents=True)
            (sc_root / "archive" / "done.input").write_text("done", encoding="utf-8")
            sc_backup.create_backup_snapshot(sc_root, out=backup_path)
            stdout = StringIO()

            with redirect_stdout(stdout):
                sc_backup.main(
                    [
                        "--restore-preview",
                        "--backup",
                        str(backup_path),
                        "--restore-to",
                        str(restore_to),
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["writes"], "none")
        self.assertTrue(payload["backup_ok"])
        self.assertEqual(payload["targets"][0]["target"], str(restore_to / "archive"))


if __name__ == "__main__":
    unittest.main()

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import specialists.uniblab.ops as ops
import specialists.uniblab.retention as retention
import specialists.uniblab.vault_backup as vault_backup


class Stage127OperationsFloorTests(unittest.TestCase):
    def test_vault_backup_preview_includes_vault_content_and_excludes_volatile_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault_dir = root / "vault"
            backup_root = root / "vault-backups"
            (vault_dir / "Cogs").mkdir(parents=True)
            (vault_dir / "Cogs" / "2026-06-24.md").write_text("today", encoding="utf-8")
            (vault_dir / ".obsidian").mkdir()
            (vault_dir / ".obsidian" / "workspace.json").write_text("{}", encoding="utf-8")

            preview = vault_backup.build_vault_backup_preview(vault_dir, backup_root=backup_root)
            output = vault_backup.format_vault_backup_preview(preview)

        included = {item.label for item in preview.included_items}
        excluded = {item.label for item in preview.excluded_items}
        self.assertIn("Cogs", included)
        self.assertIn(".obsidian", excluded)
        self.assertIn("Syncthing: sync only, not point-in-time backup", output)
        self.assertEqual(preview.included_file_count, 1)

    def test_vault_backup_json_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_dir = Path(tmp) / "vault"
            vault_dir.mkdir()
            stdout = StringIO()

            with redirect_stdout(stdout):
                vault_backup.main(["--vault-dir", str(vault_dir), "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["writes"], "none")
        self.assertEqual(payload["vault_dir"], str(vault_dir))

    def test_retention_report_flags_large_or_many_targets_without_deleting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sc_root = root / "sc"
            archive = sc_root / "archive"
            archive.mkdir(parents=True)
            for index in range(1000):
                (archive / f"{index}.input").write_text("x", encoding="utf-8")

            report = retention.build_retention_report(
                sc_root=sc_root,
                runtime_backup_root=root / "runtime-backups",
                vault_backup_root=root / "vault-backups",
            )
            output = retention.format_retention_report(report)

        self.assertIn("Retention status", output)
        self.assertIn("- writes: no", output)
        self.assertTrue(any("runtime archive has many files" in warning for warning in report.warnings))

    def test_ops_summary_does_not_print_secret_values(self):
        fake_unit = ops.job_status.UnitStatus(
            name="sprockets-cogs.service",
            exists=True,
            active_state="active",
            sub_state="running",
            unit_file_state="enabled",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / "env"
            env_file.write_text("TELEGRAM_BOT_TOKEN=secret-token\n", encoding="utf-8")
            vault_dir = root / "vault"
            vault_dir.mkdir()
            with patch("specialists.uniblab.ops.job_status.get_user_unit_status", return_value=fake_unit):
                with patch("specialists.uniblab.ops.build_linger_status", return_value=ops.LingerStatus(True, True, "enabled")):
                    with patch(
                        "specialists.uniblab.ops.vault_backup.build_vault_backup_preview",
                        return_value=vault_backup.build_vault_backup_preview(vault_dir, backup_root=root / "vault-backups"),
                    ):
                        with patch(
                            "specialists.uniblab.ops.retention.build_retention_report",
                            return_value=retention.build_retention_report(
                                sc_root=root / "sc",
                                runtime_backup_root=root / "runtime-backups",
                                vault_backup_root=root / "vault-backups",
                            ),
                        ):
                            summary = ops.build_ops_summary(env_file=env_file)
                            output = ops.format_ops_summary(summary)

        self.assertIn("env file exists: yes", output)
        self.assertIn("env values printed: no", output)
        self.assertNotIn("secret-token", output)


if __name__ == "__main__":
    unittest.main()

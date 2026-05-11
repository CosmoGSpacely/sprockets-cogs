import tempfile
import unittest
from pathlib import Path

import job_status
import job_supervisor


class Stage27JobSupervisorTests(unittest.TestCase):
    def test_build_install_preview_uses_user_unit_targets_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_unit_dir = Path(tmp) / "systemd" / "user"

            preview = job_supervisor.build_install_preview(job_status.NIGHTLY_JOB, user_unit_dir)

            self.assertEqual(preview.service_target, user_unit_dir / "sprockets-cogs-nightly.service")
            self.assertEqual(preview.timer_target, user_unit_dir / "sprockets-cogs-nightly.timer")
            self.assertFalse(user_unit_dir.exists())
            self.assertIn(("systemctl", "--user", "daemon-reload"), preview.commands)
            self.assertIn(
                ("systemctl", "--user", "enable", "--now", "sprockets-cogs-nightly.timer"),
                preview.commands,
            )

    def test_format_install_preview_lists_sources_targets_and_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            preview = job_supervisor.build_install_preview(job_status.NIGHTLY_JOB, Path(tmp))

            output = job_supervisor.format_install_preview(preview)

            self.assertIn("nightly: install preview", output)
            self.assertIn("- writes: no", output)
            self.assertIn("service source:", output)
            self.assertIn("service target:", output)
            self.assertIn("timer source:", output)
            self.assertIn("timer target:", output)
            self.assertIn("systemctl --user daemon-reload", output)
            self.assertIn("systemctl --user enable --now sprockets-cogs-nightly.timer", output)
            self.assertIn("run the report and dry-run before installing", output)

    def test_disable_preview_lists_safe_pause_commands_without_writing(self):
        preview = job_supervisor.build_disable_preview(job_status.NIGHTLY_JOB)

        output = job_supervisor.format_command_preview(preview)

        self.assertIn("nightly: disable preview", output)
        self.assertIn("- writes: no", output)
        self.assertIn("systemctl --user disable --now sprockets-cogs-nightly.timer", output)
        self.assertIn("systemctl --user status sprockets-cogs-nightly.timer", output)
        self.assertIn(
            "systemctl --user reset-failed sprockets-cogs-nightly.service sprockets-cogs-nightly.timer",
            output,
        )
        self.assertIn("automatic maintenance should pause", output)

    def test_recovery_preview_lists_status_report_dry_run_and_logs(self):
        preview = job_supervisor.build_recovery_preview(job_status.NIGHTLY_JOB)

        output = job_supervisor.format_command_preview(preview)

        self.assertIn("nightly: recovery preview", output)
        self.assertIn("- writes: no", output)
        self.assertIn("scripts/job-status nightly", output)
        self.assertIn("scripts/nightly --report", output)
        self.assertIn("scripts/nightly --dry-run", output)
        self.assertIn("journalctl --user -u sprockets-cogs-nightly.service --since 24 hours ago", output)
        self.assertIn("systemctl --user status sprockets-cogs-nightly.timer", output)
        self.assertIn("systemctl --user status sprockets-cogs-nightly.service", output)
        self.assertIn("systemctl --user start sprockets-cogs-nightly.service", output)
        self.assertIn("before manually starting the service", output)


if __name__ == "__main__":
    unittest.main()

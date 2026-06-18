import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import specialists.uniblab.job_status as job_status


class Stage27JobStatusTests(unittest.TestCase):
    def test_parse_systemctl_show_reads_key_values(self):
        parsed = job_status.parse_systemctl_show(
            "LoadState=loaded\n"
            "ActiveState=active\n"
            "SubState=waiting\n"
            "UnitFileState=enabled\n"
            "Result=success\n"
            "ExecMainStatus=0\n"
        )

        self.assertEqual(parsed["LoadState"], "loaded")
        self.assertEqual(parsed["ActiveState"], "active")
        self.assertEqual(parsed["ExecMainStatus"], "0")

    def test_unit_status_marks_not_found_as_missing(self):
        status = job_status.unit_status_from_show(
            "sprockets-cogs-nightly.timer",
            {
                "LoadState": "not-found",
                "ActiveState": "inactive",
                "SubState": "dead",
                "UnitFileState": "",
            },
        )

        self.assertFalse(status.exists)
        self.assertEqual(status.load_state, "not-found")

    def test_format_job_status_includes_dry_run_and_log_commands(self):
        status = job_status.MaintenanceJobStatus(
            job=job_status.NIGHTLY_JOB,
            service=job_status.UnitStatus(
                name="sprockets-cogs-nightly.service",
                exists=False,
                load_state="not-found",
            ),
            timer=job_status.UnitStatus(
                name="sprockets-cogs-nightly.timer",
                exists=False,
                load_state="not-found",
            ),
        )

        output = job_status.format_job_status(status)

        self.assertIn("nightly: Nightly Cogs carry safety net", output)
        self.assertIn("sprockets-cogs-nightly.service", output)
        self.assertIn("sprockets-cogs-nightly.timer", output)
        self.assertIn("service template:", output)
        self.assertIn("timer template:", output)
        self.assertIn("report: scripts/nightly --report", output)
        self.assertIn("dry run: scripts/nightly --dry-run", output)
        self.assertIn("logs: journalctl --user -u sprockets-cogs-nightly.service", output)
        self.assertIn("timer is not installed", output)

    def test_format_job_status_distinguishes_unavailable_systemd_bus(self):
        status = job_status.MaintenanceJobStatus(
            job=job_status.NIGHTLY_JOB,
            service=job_status.unavailable_unit_status(
                "sprockets-cogs-nightly.service",
                "Failed to connect to bus: Operation not permitted",
            ),
            timer=job_status.unavailable_unit_status(
                "sprockets-cogs-nightly.timer",
                "Failed to connect to bus: Operation not permitted",
            ),
        )

        output = job_status.format_job_status(status)

        self.assertIn("unavailable (Failed to connect to bus", output)
        self.assertIn("user systemd status is unavailable", output)
        self.assertNotIn("timer is not installed", output)

    def test_nightly_systemd_templates_are_conservative_user_units(self):
        service = job_status.NIGHTLY_JOB.service_template.read_text()
        timer = job_status.NIGHTLY_JOB.timer_template.read_text()

        self.assertIn("Type=oneshot", service)
        self.assertIn("WorkingDirectory=/home/cosmo/sprockets-cogs", service)
        self.assertIn("ExecStart=/home/cosmo/sprockets-cogs/scripts/nightly", service)
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("OnCalendar=*-*-* 04:30:00", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("Unit=sprockets-cogs-nightly.service", timer)
        self.assertIn("WantedBy=timers.target", timer)

    def test_main_accepts_argv_for_direct_cli_tests(self):
        status = job_status.MaintenanceJobStatus(
            job=job_status.NIGHTLY_JOB,
            service=job_status.UnitStatus(
                name="sprockets-cogs-nightly.service",
                exists=False,
                load_state="not-found",
            ),
            timer=job_status.UnitStatus(
                name="sprockets-cogs-nightly.timer",
                exists=False,
                load_state="not-found",
            ),
        )
        stdout = StringIO()

        with patch("specialists.uniblab.job_status.build_job_status", return_value=status), redirect_stdout(stdout):
            job_status.main(["nightly"])

        output = stdout.getvalue()
        self.assertIn("nightly: Nightly Cogs carry safety net", output)
        self.assertIn("timer is not installed", output)


if __name__ == "__main__":
    unittest.main()

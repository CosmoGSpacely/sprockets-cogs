import unittest

import job_status


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
        self.assertIn("report: scripts/nightly --report", output)
        self.assertIn("dry run: scripts/nightly --dry-run", output)
        self.assertIn("logs: journalctl --user -u sprockets-cogs-nightly.service", output)
        self.assertIn("timer is not installed", output)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

import phase86_status


class Stage98Phase86StatusTests(unittest.TestCase):
    def write_builder_files(self, root: Path) -> None:
        phase_dir = root / "stages" / "phase-086-implementation-interruption-promotion"
        phase_dir.mkdir(parents=True)
        (phase_dir / "README.md").write_text(
            "| Stage | Focus | Promotions |\n"
            "|---|---|---|\n"
            "| 98 | Promotion system and structural guard baseline | 1, 9, 10 |\n"
            "| 99 | Real-task model and capability decision | 2, 6, 11, 12 |\n"
        )
        (root / "STATUS.md").write_text(
            "- Behaviors promoted during Phase 8.6 so far: **1**.\n"
        )
        (root / "DEFERRED.md").write_text(
            "| ID | Item | Disposition | Notes |\n"
            "|---|---|---|---|\n"
            "| D027 | Open WebUI pipe | Scheduled - Phase 8.6 Stage 103 Open WebUI prove-or-kill | Prove or kill. |\n"
            "| D080 | Wrong project association | Phase 8.6 Promotion 8 acceptance item | **Trigger fired.** Build fixture. |\n"
            "| D091 | Maybe later idea | Keep deferred | No trigger yet. |\n"
        )

    def test_build_phase86_status_reads_builder_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_builder_files(root)

            status = phase86_status.build_phase86_status(root)

        self.assertEqual(status.promoted_count, 1)
        self.assertEqual([stage.number for stage in status.stages], ["98", "99"])
        self.assertEqual([row.deferred_id for row in status.phase86_scheduled_rows], ["D027", "D080"])
        self.assertEqual([row.deferred_id for row in status.fired_trigger_rows], ["D080"])
        self.assertEqual([row.deferred_id for row in status.unscheduled_rows], ["D091"])

    def test_format_phase86_status_names_counts_and_stage_homes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_builder_files(root)
            status = phase86_status.build_phase86_status(root)

        output = phase86_status.format_phase86_status(status)

        self.assertIn("Phase 8.6 promotion status", output)
        self.assertIn("- live behaviors promoted: 1", output)
        self.assertIn("- active stage ledgers: 2", output)
        self.assertIn("Stage 98: Promotion system and structural guard baseline", output)
        self.assertIn("D027: Open WebUI pipe -> Stage 103", output)
        self.assertIn("D080: Wrong project association -> Stage 105", output)
        self.assertIn("D091: Maybe later idea", output)


if __name__ == "__main__":
    unittest.main()

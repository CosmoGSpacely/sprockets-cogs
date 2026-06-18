import tempfile
import unittest
import io
from contextlib import redirect_stdout
from pathlib import Path

import specialists.cogs.nightly as nightly
import specialists.astro.vault as vault


class Stage145NightlyCarryTests(unittest.TestCase):
    def test_build_nightly_plan_includes_only_open_blocks_through_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            old_note = vault.ensure_daily_note("2026-05-01", daily_dir)
            old_note.write_text(
                old_note.read_text()
                + "- [ ] Carry me\n"
                  "- [>] Already carried\n"
                  "- [-] Cancelled\n"
                  "- [x] Done\n"
            )
            future_note = vault.ensure_daily_note("2026-05-03", daily_dir)
            future_note.write_text(future_note.read_text() + "- [ ] Not yet\n")

            plan = nightly.build_nightly_plan(
                daily_dir=daily_dir,
                through_date="2026-05-02",
                destination_date="2026-05-04",
            )

            self.assertEqual(len(plan["items"]), 1)
            self.assertEqual(plan["items"][0]["item_text"], "Carry me")
            self.assertEqual(plan["items"][0]["destination_date"], "2026-05-04")

    def test_nightly_apply_respects_already_acted_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            old_note = vault.ensure_daily_note("2026-05-01", daily_dir)
            old_note.write_text(
                old_note.read_text()
                + "- [ ] Carry me\n"
                  "- [>] Already carried\n"
                  "- [-] Cancelled\n"
                  "- [x] Done\n"
            )
            plan = nightly.build_nightly_plan(
                daily_dir=daily_dir,
                through_date="2026-05-02",
                destination_date="2026-05-04",
            )

            results = nightly.apply_plan_document(plan)

            destination = vault.daily_note_path("2026-05-04", daily_dir)
            old_text = old_note.read_text()
            self.assertEqual(len(results), 1)
            self.assertIn("- [>] Carry me", old_text)
            self.assertIn("- [>] Already carried", old_text)
            self.assertIn("- [-] Cancelled", old_text)
            self.assertIn("- [x] Done", old_text)
            self.assertIn("- [ ] Carry me", destination.read_text())

    def test_nightly_report_summarizes_plan_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            old_note = vault.ensure_daily_note("2026-05-01", daily_dir)
            old_note.write_text(old_note.read_text() + "- [ ] Carry me\n")

            plan = nightly.build_nightly_plan(
                daily_dir=daily_dir,
                through_date="2026-05-02",
                destination_date="2026-05-04",
            )
            output = nightly.format_nightly_report(
                plan,
                daily_dir=daily_dir,
                through_date="2026-05-02",
                destination_date="2026-05-04",
            )

            self.assertIn("Nightly carry report", output)
            self.assertIn("- open candidates: 1", output)
            self.assertIn("- planned actions: carry: 1", output)
            self.assertIn("- writes: no", output)
            self.assertIn("scripts/nightly --dry-run --through 2026-05-02 --to 2026-05-04", output)
            self.assertIn("scripts/nightly --through 2026-05-02 --to 2026-05-04", output)
            self.assertIn("- [ ] Carry me", old_note.read_text())

    def test_nightly_report_cli_delegates_through_cogs_specialist_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            old_note = vault.ensure_daily_note("2026-05-01", daily_dir)
            old_note.write_text(old_note.read_text() + "- [ ] Carry me\n")
            buf = io.StringIO()

            with redirect_stdout(buf):
                nightly.main(
                    [
                        "--report",
                        "--daily-dir",
                        str(daily_dir),
                        "--through",
                        "2026-05-02",
                        "--to",
                        "2026-05-04",
                    ]
                )

            output = buf.getvalue()
            self.assertIn("Nightly carry report", output)
            self.assertIn("- open candidates: 1", output)
            self.assertIn("- writes: no", output)
            self.assertIn("- [ ] Carry me", old_note.read_text())
            self.assertFalse(vault.daily_note_path("2026-05-04", daily_dir).exists())


if __name__ == "__main__":
    unittest.main()

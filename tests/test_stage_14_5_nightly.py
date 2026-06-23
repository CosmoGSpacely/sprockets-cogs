import tempfile
import unittest
import io
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

import specialists.cogs.nightly as nightly
import specialists.astro.vault as vault


class Stage145NightlyCarryTests(unittest.TestCase):
    def test_default_window_carries_yesterday_into_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            yesterday = vault.ensure_daily_note("2026-06-18", daily_dir)
            yesterday.write_text(yesterday.read_text() + "- [ ] Carry yesterday\n")
            today = vault.ensure_daily_note("2026-06-19", daily_dir)
            today.write_text(today.read_text() + "- [ ] Keep today open\n")

            original_today = nightly._today
            try:
                nightly._today = lambda: datetime(2026, 6, 19, 4, 30)
                plan = nightly.build_nightly_plan(daily_dir=daily_dir)
            finally:
                nightly._today = original_today

            self.assertEqual(plan["default_destination_date"], "2026-06-19")
            self.assertEqual(len(plan["items"]), 1)
            self.assertEqual(plan["items"][0]["item_text"], "Carry yesterday")
            self.assertEqual(plan["items"][0]["source"]["date"], "2026-06-18")
            self.assertEqual(plan["items"][0]["destination_date"], "2026-06-19")

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
            self.assertIn("- horizon reference: 2026-05-04", output)
            self.assertIn("- horizon creates:", output)
            self.assertIn("- writes: no", output)
            self.assertIn("scripts/nightly --dry-run --through 2026-05-02 --to 2026-05-04", output)
            self.assertIn("scripts/nightly --through 2026-05-02 --to 2026-05-04", output)
            self.assertIn("- [ ] Carry me", old_note.read_text())
            self.assertFalse((daily_dir / "2026" / "2026-05-5WOW.md").exists())

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
            self.assertIn("- horizon reference: 2026-05-04", output)
            self.assertIn("- writes: no", output)
            self.assertIn("- [ ] Carry me", old_note.read_text())
            self.assertFalse(vault.daily_note_path("2026-05-04", daily_dir).exists())

    def test_nightly_dry_run_previews_horizon_before_carry_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            old_note = vault.ensure_daily_note("2026-05-01", daily_dir)
            old_note.write_text(old_note.read_text() + "- [ ] Carry me\n")
            buf = io.StringIO()

            with redirect_stdout(buf):
                nightly.main(
                    [
                        "--dry-run",
                        "--daily-dir",
                        str(daily_dir),
                        "--through",
                        "2026-05-02",
                        "--to",
                        "2026-05-04",
                    ]
                )

            output = buf.getvalue()
            self.assertIn("Astro horizon ensure preview", output)
            self.assertIn("- reference: 2026-05-04", output)
            self.assertIn("- writes: no", output)
            self.assertIn("1 carry action(s) would be applied", output)
            self.assertFalse((daily_dir / "2026" / "2026-05-5WOW.md").exists())

    def test_nightly_apply_ensures_horizon_then_hands_off_to_carry(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            old_note = vault.ensure_daily_note("2026-05-01", daily_dir)
            old_note.write_text(old_note.read_text() + "- [ ] Carry me\n")
            buf = io.StringIO()

            with redirect_stdout(buf):
                nightly.main(
                    [
                        "--daily-dir",
                        str(daily_dir),
                        "--through",
                        "2026-05-02",
                        "--to",
                        "2026-05-04",
                    ]
                )

            output = buf.getvalue()
            self.assertIn("Astro horizon ensure", output)
            self.assertIn("created 5wow:", output)
            self.assertIn("created 12mf:", output)
            self.assertIn("Cogs automatic carry handoff", output)
            self.assertTrue((daily_dir / "2026" / "2026-05-5WOW.md").exists())
            self.assertTrue((daily_dir / "2026" / "2026-05-12MF.md").exists())
            self.assertIn("- [>] Carry me", old_note.read_text())
            self.assertIn("- [ ] Carry me", vault.daily_note_path("2026-05-04", daily_dir).read_text())


if __name__ == "__main__":
    unittest.main()

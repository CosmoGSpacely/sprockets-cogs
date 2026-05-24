import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import sc_backup


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


if __name__ == "__main__":
    unittest.main()

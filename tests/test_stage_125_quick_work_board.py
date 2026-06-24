from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import specialists.uniblab.archive_report as archive_report


class Stage125QuickWorkBoardTests(unittest.TestCase):
    def test_archive_report_names_recent_processed_and_ignored_inputs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_dir = root / "archive"
            input_dir = root / "input"
            archive_dir.mkdir()
            input_dir.mkdir()
            (archive_dir / "telegram-1.input").write_text(
                "---\nsource: telegram\nsession_id: s1\n---\n\nCall Tom\n",
                encoding="utf-8",
            )
            (input_dir / "notes.txt").write_text("ignored", encoding="utf-8")

            report = archive_report.build_archive_report(archive_dir, input_dir)
            output = archive_report.format_archive_report(report)

        self.assertIn("telegram-1.input source=telegram session=s1", output)
        self.assertIn("notes.txt: ignored because Rosie only processes .input files", output)

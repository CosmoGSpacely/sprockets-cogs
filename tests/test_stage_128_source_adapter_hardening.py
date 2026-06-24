import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import frontmatter

from specialists.orbit.adapters import source_surfaces
from specialists.rosie import loop as rosie_loop


class Stage128SourceAdapterHardeningTests(unittest.TestCase):
    def test_source_input_writes_are_collision_safe_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"

            first = source_surfaces.write_source_input(
                source="discord",
                content="same payload",
                input_dir=input_dir,
                source_id="message-1",
            )
            second = source_surfaces.write_source_input(
                source="discord",
                content="same payload",
                input_dir=input_dir,
                source_id="message-1",
            )

        self.assertNotEqual(first.name, second.name)
        self.assertEqual(first.name, "discord-message-1.input")
        self.assertEqual(second.name, "discord-message-1-2.input")

    def test_adapter_reject_writes_reason_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            rejected_dir = Path(tmp) / "rejected"

            path = source_surfaces.write_adapter_reject(
                source="discord",
                reason="not allowlisted",
                rejected_dir=rejected_dir,
                text="hello bot",
                source_id="message-2",
            )
            post = frontmatter.load(path)

        self.assertEqual(post["source"], "discord")
        self.assertEqual(post["reason"], "not allowlisted")
        self.assertEqual(post["writes"], "rejected")
        self.assertEqual(post.content, "hello bot")

    def test_adapter_status_reports_archived_and_newest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            archive_dir = root / "archive"
            rejected_dir = root / "rejected"
            source_surfaces.write_source_input(
                source="discord",
                content="pending",
                input_dir=input_dir,
                source_id="pending-1",
            )
            archived = source_surfaces.write_source_input(
                source="open-webui",
                content="archived",
                input_dir=archive_dir,
                source_id="archive-1",
            )
            reject = source_surfaces.write_adapter_reject(
                source="discord",
                reason="bad shape",
                rejected_dir=rejected_dir,
            )

            status = source_surfaces.build_adapter_status(
                input_dir,
                rejected_dir,
                archive_dir,
            )
            output = source_surfaces.format_adapter_status(status)

        self.assertEqual(status.by_source, {"discord": 1})
        self.assertEqual(status.archived_by_source, {"open-webui": 1})
        self.assertEqual(status.newest_archived_by_source, {"open-webui": archived.name})
        self.assertEqual(status.newest_rejected, reject.name)
        self.assertIn("archived by source", output)
        self.assertIn("open-webui: 1", output)

    def test_sc_adapter_console_ingest_reject_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            rejected_dir = root / "rejected"
            archive_dir = root / "archive"
            stdout = StringIO()

            with redirect_stdout(stdout):
                source_surfaces.adapters_main([
                    "ingest",
                    "--source",
                    "open-webui",
                    "--text",
                    "capture this",
                    "--input-dir",
                    str(input_dir),
                    "--source-id",
                    "web-1",
                ])
                source_surfaces.adapters_main([
                    "reject",
                    "--source",
                    "discord",
                    "--reason",
                    "not allowlisted",
                    "--rejected-dir",
                    str(rejected_dir),
                ])
                source_surfaces.adapters_main([
                    "status",
                    "--input-dir",
                    str(input_dir),
                    "--rejected-dir",
                    str(rejected_dir),
                    "--archive-dir",
                    str(archive_dir),
                ])

            output = stdout.getvalue()
            self.assertTrue((input_dir / "open-webui-web-1.input").exists())
            self.assertEqual(len(tuple(rejected_dir.glob("*.reject.md"))), 1)

        self.assertIn("Adapter ingest", output)
        self.assertIn("Adapter reject", output)
        self.assertIn("pending .input files: 1", output)
        self.assertIn("rejected files: 1", output)

    def test_process_once_console_can_report_empty_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stdout = StringIO()

            with redirect_stdout(stdout):
                source_surfaces.adapters_main([
                    "process-once",
                    "--input-dir",
                    str(root / "input"),
                    "--processing-dir",
                    str(root / "processing"),
                    "--archive-dir",
                    str(root / "archive"),
                    "--output-dir",
                    str(root / "output"),
                ])

            output = stdout.getvalue()

        self.assertIn("Adapter process-once", output)
        self.assertIn("processed inputs: 0", output)

    def test_rosie_archive_preserves_existing_archive_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_dir = root / "archive"
            processing_dir = root / "processing"
            archive_dir.mkdir()
            processing_dir.mkdir()
            existing = archive_dir / "same.input"
            existing.write_text("existing", encoding="utf-8")
            incoming = processing_dir / "same.input"
            incoming.write_text("incoming", encoding="utf-8")

            with patch.object(rosie_loop, "ARCHIVE_DIR", archive_dir):
                rosie_loop.archive_input(incoming)

            archived = sorted(path.name for path in archive_dir.glob("*.input"))
            self.assertEqual(archived, ["same-2.input", "same.input"])
            self.assertEqual((archive_dir / "same.input").read_text(encoding="utf-8"), "existing")
            self.assertEqual((archive_dir / "same-2.input").read_text(encoding="utf-8"), "incoming")


if __name__ == "__main__":
    unittest.main()

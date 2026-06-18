import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import frontmatter

import specialists.orbit.adapters.input_adapter as input_adapter
import specialists.orbit.adapters.markitdown_adapter as markitdown_adapter


class Stage56MarkItDownAdapterTests(unittest.TestCase):
    def test_convert_text_like_document_without_markitdown_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = Path(tmp) / "note.md"
            document.write_text("# Demo\n\nCapture this document.", encoding="utf-8")

            conversion = markitdown_adapter.convert_document(document)

            self.assertEqual(conversion.converter, "text")
            self.assertIn("Capture this document", conversion.markdown)
            self.assertFalse(conversion.truncated)
            self.assertFalse(conversion.review_recommended)

    def test_convert_document_rejects_large_source_before_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = Path(tmp) / "large.txt"
            document.write_text("abcdef", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "too large"):
                markitdown_adapter.convert_document(document, max_bytes=3)

    def test_convert_document_can_truncate_and_recommend_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = Path(tmp) / "long.txt"
            document.write_text("0123456789", encoding="utf-8")

            conversion = markitdown_adapter.convert_document(
                document,
                max_markdown_chars=5,
            )

            self.assertEqual(conversion.markdown, "01234")
            self.assertTrue(conversion.truncated)
            self.assertTrue(conversion.review_recommended)
            self.assertIn("truncated", conversion.review_reason)

    def test_document_envelope_uses_shared_input_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = Path(tmp) / "paper.txt"
            document.write_text("Important document notes.", encoding="utf-8")
            conversion = markitdown_adapter.convert_document(document)

            envelope = markitdown_adapter.document_envelope(conversion)
            rendered = frontmatter.loads(input_adapter.render_input_file(envelope))

            self.assertEqual(envelope.source, "markitdown")
            self.assertEqual(envelope.modality, "document")
            self.assertTrue(envelope.idempotency_key.startswith("markitdown:"))
            self.assertEqual(rendered["metadata"]["document_name"], "paper.txt")
            self.assertEqual(rendered["metadata"]["review_recommended"], "no")
            self.assertEqual(rendered["attachments"][0]["name"], "paper.txt")
            self.assertIn("Important document notes", rendered.content)

    def test_preview_cli_is_read_only_and_shows_rendered_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = Path(tmp) / "paper.txt"
            document.write_text("Important document notes.", encoding="utf-8")
            stdout = StringIO()

            with redirect_stdout(stdout):
                markitdown_adapter.main([str(document)])

            output = stdout.getvalue()
            self.assertIn("MarkItDown document preview", output)
            self.assertIn("- writes: no", output)
            self.assertIn("Input adapter preview", output)
            self.assertIn("source: markitdown", output)

    def test_preview_cli_json_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = Path(tmp) / "paper.txt"
            document.write_text("Important document notes.", encoding="utf-8")
            stdout = StringIO()

            with redirect_stdout(stdout):
                markitdown_adapter.main([str(document), "--json"])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["writes"], "none")
            self.assertEqual(payload["frontmatter"]["source"], "markitdown")
            self.assertIn("Important document notes", payload["content"])

    def test_preview_cli_write_requires_input_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = Path(tmp) / "paper.txt"
            document.write_text("Important document notes.", encoding="utf-8")
            stderr = StringIO()

            with self.assertRaises(SystemExit) as raised, redirect_stderr(stderr):
                markitdown_adapter.main([str(document), "--write"])

            self.assertEqual(raised.exception.code, 2)
            self.assertIn("--input-dir is required", stderr.getvalue())

    def test_preview_cli_write_creates_input_file_when_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = Path(tmp) / "paper.txt"
            input_dir = Path(tmp) / "input"
            document.write_text("Important document notes.", encoding="utf-8")
            stdout = StringIO()

            with redirect_stdout(stdout):
                markitdown_adapter.main([
                    str(document),
                    "--write",
                    "--input-dir",
                    str(input_dir),
                ])

            files = list(input_dir.glob("*.input"))
            self.assertEqual(len(files), 1)
            self.assertIn("MarkItDown document write", stdout.getvalue())
            self.assertIn("Important document notes", files[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

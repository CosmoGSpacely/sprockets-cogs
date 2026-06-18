import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile

import frontmatter

import specialists.orbit.adapters.input_adapter as input_adapter
import specialists.orbit.adapters.input_adapter_preview as input_adapter_preview


class Stage53InputAdapterTests(unittest.TestCase):
    def test_render_input_file_uses_frontmatter_plus_body(self):
        envelope = input_adapter.InputEnvelope(
            content="Capture this idea.",
            source="telegram",
            session_id="chat-123",
            modality="text",
            source_id="msg-456",
            idempotency_key="telegram:chat-123:msg-456",
            metadata={"author": "cosmo"},
        )

        rendered = input_adapter.render_input_file(envelope)
        post = frontmatter.loads(rendered)

        self.assertEqual(post.content, "Capture this idea.")
        self.assertEqual(post["adapter_contract"], "stage-53")
        self.assertEqual(post["source"], "telegram")
        self.assertEqual(post["session_id"], "chat-123")
        self.assertEqual(post["modality"], "text")
        self.assertEqual(post["source_id"], "msg-456")
        self.assertEqual(post["idempotency_key"], "telegram:chat-123:msg-456")
        self.assertEqual(post["metadata"]["author"], "cosmo")

    def test_filename_is_deterministic_and_does_not_expose_content(self):
        envelope = input_adapter.InputEnvelope(
            content="Need to call Alex about the private invoice amount.",
            source="telegram bot",
            source_id="message/123",
        )

        filename = input_adapter.input_filename(envelope)

        self.assertEqual(filename, "telegram-bot-message123.input")
        self.assertNotIn("invoice", filename)
        self.assertEqual(filename, input_adapter.input_filename(envelope))

    def test_session_id_falls_back_to_source_and_content_hash(self):
        envelope = input_adapter.InputEnvelope(
            content="One-off note",
            source="MarkItDown",
            modality="document",
        )

        session_id = input_adapter.input_session_id(envelope)

        self.assertTrue(session_id.startswith("markitdown-"))
        self.assertEqual(session_id, input_adapter.input_session_id(envelope))

    def test_attachment_metadata_requires_reference_and_renders_without_empty_fields(self):
        attachment = input_adapter.InputAttachment(
            name="paper.pdf",
            media_type="application/pdf",
            path="/tmp/paper.pdf",
        )
        envelope = input_adapter.InputEnvelope(
            content="Document summary",
            source="markitdown",
            modality="document",
            attachments=(attachment,),
        )

        post = frontmatter.loads(input_adapter.render_input_file(envelope))

        self.assertEqual(post["attachments"][0]["name"], "paper.pdf")
        self.assertEqual(post["attachments"][0]["media_type"], "application/pdf")
        self.assertEqual(post["attachments"][0]["path"], "/tmp/paper.pdf")
        self.assertNotIn("url", post["attachments"][0])

    def test_rejects_empty_required_fields(self):
        with self.assertRaisesRegex(ValueError, "content cannot be empty"):
            input_adapter.InputEnvelope(content=" ", source="cli")

        with self.assertRaisesRegex(ValueError, "source cannot be empty"):
            input_adapter.InputEnvelope(content="hello", source="")

        with self.assertRaisesRegex(ValueError, "attachment must include"):
            input_adapter.InputAttachment(name="empty")

    def test_preview_is_read_only_and_shows_exact_rendered_file(self):
        envelope = input_adapter.InputEnvelope(
            content="Preview me",
            source="cli",
            session_id="preview-session",
        )

        preview = input_adapter.preview_input_file(envelope)

        self.assertIn("Input adapter preview", preview)
        self.assertIn("- writes: no", preview)
        self.assertIn("- filename: cli-preview-session.input", preview)
        self.assertIn("session_id: preview-session", preview)
        self.assertIn("Preview me", preview)

    def test_preview_cli_prints_read_only_input_file(self):
        stdout = StringIO()

        with redirect_stdout(stdout):
            input_adapter_preview.main([
                "--source",
                "telegram",
                "--session-id",
                "chat-123",
                "--source-id",
                "msg-456",
                "--metadata",
                "author=cosmo",
                "Remember the adapter boundary",
            ])

        output = stdout.getvalue()
        self.assertIn("Input adapter preview", output)
        self.assertIn("- writes: no", output)
        self.assertIn("- filename: telegram-msg-456.input", output)
        self.assertIn("source: telegram", output)
        self.assertIn("session_id: chat-123", output)
        self.assertIn("Remember the adapter boundary", output)

    def test_preview_cli_json_is_machine_readable(self):
        stdout = StringIO()

        with redirect_stdout(stdout):
            input_adapter_preview.main([
                "--json",
                "--source",
                "markitdown",
                "--modality",
                "document",
                "--attachment",
                "name=paper.pdf,path=/tmp/paper.pdf,media_type=application/pdf",
                "Summarize this document",
            ])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["writes"], "none")
        self.assertTrue(payload["filename"].startswith("markitdown-"))
        self.assertEqual(payload["frontmatter"]["modality"], "document")
        self.assertEqual(payload["frontmatter"]["attachments"][0]["name"], "paper.pdf")

    def test_preview_cli_reports_metadata_errors_without_traceback(self):
        stderr = StringIO()

        with self.assertRaises(SystemExit) as raised, redirect_stderr(stderr):
            input_adapter_preview.main([
                "--source",
                "cli",
                "--metadata",
                "bad-metadata",
                "Hello",
            ])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("metadata entries must use KEY=VALUE", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_write_input_file_uses_final_name_and_refuses_collision(self):
        envelope = input_adapter.InputEnvelope(
            content="Queue me",
            source="cli",
            session_id="queue-session",
        )
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"

            result = input_adapter.write_input_file(envelope, input_dir)

            self.assertEqual(result.path, input_dir / "cli-queue-session.input")
            self.assertTrue(result.path.exists())
            self.assertFalse((input_dir / ".cli-queue-session.input.tmp").exists())
            self.assertIn("Queue me", result.path.read_text(encoding="utf-8"))
            with self.assertRaises(FileExistsError):
                input_adapter.write_input_file(envelope, input_dir)

    def test_preview_cli_write_requires_input_dir(self):
        stderr = StringIO()

        with self.assertRaises(SystemExit) as raised, redirect_stderr(stderr):
            input_adapter_preview.main([
                "--write",
                "--source",
                "cli",
                "Hello",
            ])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--input-dir is required with --write", stderr.getvalue())

    def test_preview_cli_write_creates_input_file_only_when_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            stdout = StringIO()

            with redirect_stdout(stdout):
                input_adapter_preview.main([
                    "--write",
                    "--input-dir",
                    str(input_dir),
                    "--source",
                    "cli",
                    "--session-id",
                    "write-session",
                    "Write me",
                ])

            path = input_dir / "cli-write-session.input"
            self.assertTrue(path.exists())
            self.assertIn("Input adapter write", stdout.getvalue())
            self.assertIn("- writes: input", stdout.getvalue())
            self.assertIn("Write me", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

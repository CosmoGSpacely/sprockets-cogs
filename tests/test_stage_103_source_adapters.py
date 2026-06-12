import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import frontmatter

from specialists.adapters import source_surfaces, telegram_polling


def telegram_update(update_id=1001, message_id=42, text="Capture from Telegram"):
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "from": {"id": 777, "is_bot": False, "username": "cosmo"},
            "chat": {"id": 888, "type": "private"},
            "date": 1770000000,
            "text": text,
        },
    }


class Stage103SourceAdapterTests(unittest.TestCase):
    def test_telegram_poll_once_writes_allowlisted_input_and_tracks_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"

            result = telegram_polling.poll_telegram_once(
                token="secret-token",
                input_dir=input_dir,
                allowed_user_ids=frozenset({777}),
                allowed_chat_ids=frozenset(),
                opener=lambda *_args, **_kwargs: {
                    "ok": True,
                    "result": [telegram_update()],
                },
            )

            files = list(input_dir.glob("*.input"))
            self.assertEqual(len(files), 1)
            self.assertEqual(result.fetched, 1)
            self.assertEqual(result.allowed, 1)
            self.assertEqual(result.next_offset, 1002)
            post = frontmatter.load(files[0])
            self.assertEqual(post["source"], "telegram")
            self.assertEqual(post["metadata"]["telegram_chat_id"], "888")
            self.assertEqual(post.content, "Capture from Telegram")

    def test_telegram_poll_once_ignores_non_allowlisted_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = telegram_polling.poll_telegram_once(
                token="secret-token",
                input_dir=Path(tmp) / "input",
                allowed_user_ids=frozenset({111}),
                allowed_chat_ids=frozenset(),
                opener=lambda *_args, **_kwargs: {
                    "ok": True,
                    "result": [telegram_update()],
                },
            )

        self.assertEqual(len(result.written), 0)
        self.assertEqual(result.ignored, ("update 1001: not allowlisted",))

    def test_discord_and_open_webui_proofs_write_source_envelopes(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            discord = source_surfaces.write_source_input(
                source="discord",
                content="Discord capture",
                input_dir=input_dir,
                session_id="discord-channel-1",
                source_id="discord-message-1",
            )
            webui = source_surfaces.write_source_input(
                source="open-webui",
                content="Open WebUI capture",
                input_dir=input_dir,
                session_id="open-webui-chat-1",
                source_id="open-webui-message-1",
            )

            discord_post = frontmatter.load(discord)
            webui_post = frontmatter.load(webui)

        self.assertEqual(discord_post["source"], "discord")
        self.assertEqual(discord_post.content, "Discord capture")
        self.assertEqual(webui_post["source"], "open-webui")
        self.assertEqual(webui_post.content, "Open WebUI capture")

    def test_adapter_status_reports_sources_ignored_and_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            rejected_dir = root / "rejected"
            source_surfaces.write_source_input(
                source="discord",
                content="Discord capture",
                input_dir=input_dir,
                source_id="discord-message-1",
            )
            (input_dir / "notes.txt").write_text("ignored", encoding="utf-8")
            rejected_dir.mkdir()
            (rejected_dir / "bad.json").write_text("bad", encoding="utf-8")

            status = source_surfaces.build_adapter_status(input_dir, rejected_dir)
            output = source_surfaces.format_adapter_status(status)

        self.assertEqual(status.pending_inputs, 1)
        self.assertEqual(status.ignored_files, 1)
        self.assertEqual(status.rejected_files, 1)
        self.assertEqual(status.by_source, {"discord": 1})
        self.assertIn("Adapter intake status", output)
        self.assertIn("- discord: 1", output)

    def test_source_ack_preview_stays_read_only(self):
        envelope = source_surfaces.acknowledgement_from_source(
            "discord",
            "discord-channel-1",
            "Captured.",
        )
        output = source_surfaces.format_response_preview(envelope)

        self.assertIn("Response route preview", output)
        self.assertIn("- writes: no", output)
        self.assertIn("- source: discord", output)
        self.assertIn("- sink: local", output)

    def test_discord_cli_writes_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = StringIO()

            with redirect_stdout(stdout):
                source_surfaces.discord_main([
                    "--input-dir",
                    str(Path(tmp) / "input"),
                    "--source-id",
                    "message-1",
                    "Discord",
                    "capture",
                ])

            output = stdout.getvalue()

        self.assertIn("Discord adapter proof", output)
        self.assertIn("- writes: input", output)


if __name__ == "__main__":
    unittest.main()

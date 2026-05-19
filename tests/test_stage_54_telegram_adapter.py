import json
import os
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import frontmatter

import input_adapter
import telegram_adapter
import telegram_adapter_preview


def sample_update(text="Capture from Telegram"):
    return {
        "update_id": 1001,
        "message": {
            "message_id": 42,
            "from": {
                "id": 777,
                "is_bot": False,
                "first_name": "Cosmo",
                "username": "cosmo",
            },
            "chat": {
                "id": 888,
                "first_name": "Cosmo",
                "username": "cosmo",
                "type": "private",
            },
            "date": 1770000000,
            "text": text,
        },
    }


class Stage54TelegramAdapterTests(unittest.TestCase):
    def test_parse_update_extracts_text_message(self):
        message = telegram_adapter.parse_telegram_update(sample_update())

        self.assertEqual(message.update_id, 1001)
        self.assertEqual(message.message_id, 42)
        self.assertEqual(message.chat_id, 888)
        self.assertEqual(message.from_user_id, 777)
        self.assertEqual(message.username, "cosmo")
        self.assertEqual(message.chat_type, "private")
        self.assertEqual(message.text, "Capture from Telegram")

    def test_parse_update_rejects_non_text_message(self):
        update = sample_update()
        del update["message"]["text"]

        with self.assertRaisesRegex(ValueError, "text cannot be empty"):
            telegram_adapter.parse_telegram_update(update)

    def test_telegram_envelope_uses_stage_53_input_contract(self):
        envelope = telegram_adapter.telegram_envelope(
            telegram_adapter.parse_telegram_update(sample_update())
        )

        rendered = frontmatter.loads(input_adapter.render_input_file(envelope))

        self.assertEqual(envelope.source, "telegram")
        self.assertEqual(envelope.session_id, "telegram-chat-888")
        self.assertEqual(envelope.source_id, "chat-888-message-42")
        self.assertEqual(envelope.idempotency_key, "telegram:888:42")
        self.assertEqual(rendered.content, "Capture from Telegram")

    def test_allowlist_requires_configured_user_or_chat(self):
        message = telegram_adapter.parse_telegram_update(sample_update())

        self.assertFalse(
            telegram_adapter.telegram_message_is_allowed(
                message,
                allowed_user_ids=frozenset(),
                allowed_chat_ids=frozenset(),
            )
        )
        self.assertTrue(
            telegram_adapter.telegram_message_is_allowed(
                message,
                allowed_user_ids=frozenset({777}),
                allowed_chat_ids=frozenset(),
            )
        )
        self.assertFalse(
            telegram_adapter.telegram_message_is_allowed(
                message,
                allowed_user_ids=frozenset({111}),
                allowed_chat_ids=frozenset(),
            )
        )

    def test_allowlist_env_parses_comma_separated_ids(self):
        users, chats = telegram_adapter.telegram_allowlist_from_env({
            "SPROCKETS_COGS_TELEGRAM_ALLOWED_USER_IDS": "777, 778",
            "SPROCKETS_COGS_TELEGRAM_ALLOWED_CHAT_IDS": "888",
        })

        self.assertEqual(users, frozenset({777, 778}))
        self.assertEqual(chats, frozenset({888}))

    def test_preview_cli_is_read_only_and_shows_allowlist_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            update_path = Path(tmp) / "update.json"
            update_path.write_text(json.dumps(sample_update()), encoding="utf-8")
            stdout = StringIO()

            with patch.dict(
                os.environ,
                {"SPROCKETS_COGS_TELEGRAM_ALLOWED_USER_IDS": "777"},
                clear=False,
            ), redirect_stdout(stdout):
                telegram_adapter_preview.main(["--update-json", str(update_path)])

            output = stdout.getvalue()
            self.assertIn("Telegram adapter preview", output)
            self.assertIn("- writes: no", output)
            self.assertIn("- allowed: yes", output)
            self.assertIn("telegram:888:42", output)

    def test_preview_cli_write_requires_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            update_path = Path(tmp) / "update.json"
            update_path.write_text(json.dumps(sample_update()), encoding="utf-8")
            stderr = StringIO()

            with self.assertRaises(SystemExit) as raised, redirect_stderr(stderr):
                telegram_adapter_preview.main([
                    "--update-json",
                    str(update_path),
                    "--write",
                    "--input-dir",
                    str(Path(tmp) / "input"),
                ])

            self.assertEqual(raised.exception.code, 2)
            self.assertIn("telegram message is not allowlisted", stderr.getvalue())

    def test_preview_cli_write_creates_input_when_allowlisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            update_path = Path(tmp) / "update.json"
            input_dir = Path(tmp) / "input"
            update_path.write_text(json.dumps(sample_update()), encoding="utf-8")
            stdout = StringIO()

            with patch.dict(
                os.environ,
                {"SPROCKETS_COGS_TELEGRAM_ALLOWED_CHAT_IDS": "888"},
                clear=False,
            ), redirect_stdout(stdout):
                telegram_adapter_preview.main([
                    "--update-json",
                    str(update_path),
                    "--write",
                    "--input-dir",
                    str(input_dir),
                ])

            files = list(input_dir.glob("*.input"))
            self.assertEqual(len(files), 1)
            self.assertIn("Telegram adapter write", stdout.getvalue())
            self.assertIn("- allowed: yes", stdout.getvalue())
            self.assertIn("Capture from Telegram", files[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

import agentic_loop
import input_adapter
import response_routing
import telegram_response
from telegram_adapter import TelegramMessage, telegram_envelope


class FakeTelegramResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return b'{"ok": true, "result": {"message_id": 999}}'


class Stage55TelegramResponseTests(unittest.TestCase):
    def test_build_send_message_request_posts_chat_and_text(self):
        request = telegram_response.build_send_message_request(
            token="secret-token",
            chat_id="888",
            text="Queued.",
        )

        self.assertEqual(request.get_method(), "POST")
        self.assertIn("/botsecret-token/sendMessage", request.full_url)
        payload = parse_qs(request.data.decode("utf-8"))
        self.assertEqual(payload["chat_id"], ["888"])
        self.assertEqual(payload["text"], ["Queued."])

    def test_send_telegram_response_rejects_review_required_route(self):
        envelope = telegram_response.telegram_response_envelope(
            chat_id="888",
            response_type=response_routing.ResponseType.REVIEW_REQUIRED,
            text="Needs review.",
        )

        with self.assertRaisesRegex(ValueError, "not sendable"):
            telegram_response.send_telegram_response(
                envelope,
                token="secret-token",
                opener=lambda request, timeout: FakeTelegramResponse(),
            )

    def test_send_telegram_response_uses_route_target(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return FakeTelegramResponse()

        envelope = telegram_response.telegram_response_envelope(
            chat_id="888",
            response_type=response_routing.ResponseType.ACKNOWLEDGEMENT,
            text="Queued.",
        )

        payload = telegram_response.send_telegram_response(
            envelope,
            token="secret-token",
            opener=opener,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(len(calls), 1)
        request, timeout = calls[0]
        self.assertEqual(timeout, 10)
        self.assertEqual(parse_qs(request.data.decode("utf-8"))["chat_id"], ["888"])

    def test_preview_cli_uses_input_file_without_contacting_telegram(self):
        with tempfile.TemporaryDirectory() as tmp:
            message = TelegramMessage(
                update_id=1001,
                message_id=42,
                chat_id=888,
                from_user_id=777,
                text="Capture from Telegram",
            )
            input_path = Path(tmp) / "telegram.input"
            input_path.write_text(
                input_adapter.render_input_file(telegram_envelope(message)),
                encoding="utf-8",
            )
            env_file = Path(tmp) / "env"
            env_file.write_text(
                "SPROCKETS_COGS_TELEGRAM_BOT_TOKEN=secret-token\n",
                encoding="utf-8",
            )
            stdout = StringIO()

            with redirect_stdout(stdout):
                telegram_response.main([
                    "--input-file",
                    str(input_path),
                    "--env-file",
                    str(env_file),
                    "Queued.",
                ])

            output = stdout.getvalue()
            self.assertIn("Telegram response preview", output)
            self.assertIn("- contacts Telegram: no", output)
            self.assertIn("- token configured: yes", output)
            self.assertIn("- sink: telegram", output)
            self.assertIn("- target: 888", output)
            self.assertNotIn("secret-token", output)

    def test_preview_cli_rejects_send_without_send_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "env"
            env_file.write_text(
                "SPROCKETS_COGS_TELEGRAM_BOT_TOKEN=secret-token\n",
                encoding="utf-8",
            )
            stdout = StringIO()

            with redirect_stdout(stdout):
                telegram_response.main([
                    "--chat-id",
                    "888",
                    "--env-file",
                    str(env_file),
                    "Queued.",
                ])

            output = stdout.getvalue()
            self.assertIn("- contacts Telegram: no", output)
            self.assertIn("- would_send: yes", output)

    def test_cli_requires_text(self):
        stderr = StringIO()

        with self.assertRaises(SystemExit) as raised, redirect_stderr(stderr):
            telegram_response.main(["--chat-id", "888"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("response text is required", stderr.getvalue())

    def test_cli_send_review_required_does_not_build_telegram_request(self):
        stderr = StringIO()

        with (
            patch("telegram_response.build_send_message_request") as build_request,
            self.assertRaises(SystemExit) as raised,
            redirect_stderr(stderr),
        ):
            telegram_response.main([
                "--chat-id",
                "888",
                "--response-type",
                "review_required",
                "--send",
                "Needs review.",
            ])

        self.assertEqual(raised.exception.code, 2)
        self.assertFalse(build_request.called)
        self.assertIn("not sendable to Telegram", stderr.getvalue())

    def test_agentic_loop_send_response_stays_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_note = Path(tmp) / "daily.md"
            daily_note.write_text("# Daily\n", encoding="utf-8")

            with (
                patch.object(agentic_loop, "_ensure_daily_note", return_value=daily_note),
                patch("telegram_response.send_telegram_response", Mock()) as send_mock,
            ):
                agentic_loop.send_response("telegram-chat-888", "Processed 1 node.")

            self.assertFalse(send_mock.called)
            self.assertIn("agent: Processed 1 node.", daily_note.read_text(encoding="utf-8"))

    def test_agentic_loop_processed_ack_sends_to_telegram_source(self):
        context = response_routing.ResponseContext(
            source="telegram",
            session_id="telegram-chat-888",
            metadata={"telegram_chat_id": "888"},
        )

        with (
            patch("telegram_response.merged_env_with_file", return_value={
                "SPROCKETS_COGS_TELEGRAM_BOT_TOKEN": "secret-token",
            }),
            patch("telegram_response.send_telegram_response", return_value={
                "ok": True,
                "result": {"message_id": 999},
            }) as send_mock,
        ):
            agentic_loop.send_processed_ack("telegram-chat-888", [], context)

        self.assertEqual(send_mock.call_count, 1)
        envelope = send_mock.call_args.args[0]
        self.assertEqual(envelope.text, "Processed 0 items.")
        self.assertEqual(envelope.response_type, response_routing.ResponseType.PROCESSED)

    def test_agentic_loop_processed_ack_skips_telegram_when_token_missing(self):
        context = response_routing.ResponseContext(
            source="telegram",
            session_id="telegram-chat-888",
            metadata={"telegram_chat_id": "888"},
        )

        with (
            patch("telegram_response.merged_env_with_file", return_value={}),
            patch("telegram_response.send_telegram_response") as send_mock,
        ):
            agentic_loop.send_processed_ack("telegram-chat-888", [], context)

        self.assertFalse(send_mock.called)


if __name__ == "__main__":
    unittest.main()

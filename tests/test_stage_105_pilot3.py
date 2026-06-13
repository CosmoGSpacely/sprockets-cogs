import tempfile
import unittest
from pathlib import Path

import frontmatter

from specialists.orbit import pilot3


def telegram_update(update_id=1001, message_id=42, text="Pilot 3 Telegram input"):
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


class Stage105Pilot3Tests(unittest.TestCase):
    def test_readiness_reports_telegram_orbit_surface_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / "env"
            env_file.write_text(
                "\n".join([
                    "SPROCKETS_COGS_TELEGRAM_BOT_TOKEN=secret",
                    "SPROCKETS_COGS_TELEGRAM_ALLOWED_USER_IDS=777",
                    "SPROCKETS_COGS_TELEGRAM_ALLOWED_CHAT_IDS=888",
                ]),
                encoding="utf-8",
            )
            review_dir = root / "review"
            review_dir.mkdir()
            (review_dir / "pending.md").write_text("review", encoding="utf-8")

            readiness = pilot3.build_readiness(
                input_dir=root / "input",
                archive_dir=root / "archive",
                review_dir=review_dir,
                env_file=env_file,
            )
            output = pilot3.format_readiness(readiness)

        self.assertTrue(readiness.token_configured)
        self.assertEqual(readiness.allowed_users, 1)
        self.assertEqual(readiness.allowed_chats, 1)
        self.assertEqual(readiness.review_items, 1)
        self.assertIn("Pilot 3 readiness", output)
        self.assertIn("Telegram through Orbit", output)
        self.assertIn("writes: no", output)

    def test_telegram_once_writes_input_and_can_observe_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / "env"
            env_file.write_text(
                "\n".join([
                    "SPROCKETS_COGS_TELEGRAM_BOT_TOKEN=secret",
                    "SPROCKETS_COGS_TELEGRAM_ALLOWED_USER_IDS=777",
                ]),
                encoding="utf-8",
            )
            input_dir = root / "input"
            archive_dir = root / "archive"
            offset_path = root / "offset.json"

            run = pilot3.run_telegram_once(
                input_dir=input_dir,
                archive_dir=archive_dir,
                env_file=env_file,
                offset_path=offset_path,
                opener=lambda *_args, **_kwargs: {
                    "ok": True,
                    "result": [telegram_update()],
                },
            )

            written = run.poll.written[0].path
            archive_dir.mkdir()
            archived = archive_dir / written.name
            archived.write_text(written.read_text(encoding="utf-8"), encoding="utf-8")
            written.unlink()

            archived_paths, pending, timed_out = pilot3.wait_for_telegram_processing(
                [written],
                archive_dir=archive_dir,
                seconds=0.01,
            )
            archived_post = frontmatter.load(archived)
            loaded_offset = pilot3.load_telegram_offset(offset_path)

        self.assertEqual(run.poll.allowed, 1)
        self.assertEqual(len(run.poll.written), 1)
        self.assertEqual(run.saved_offset, 1002)
        self.assertEqual(loaded_offset, 1002)
        self.assertEqual(archived_paths, (archived,))
        self.assertEqual(pending, ())
        self.assertFalse(timed_out)
        self.assertEqual(archived_post["source"], "telegram")

    def test_telegram_once_uses_persisted_offset_and_skips_archived_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / "env"
            env_file.write_text(
                "\n".join([
                    "SPROCKETS_COGS_TELEGRAM_BOT_TOKEN=secret",
                    "SPROCKETS_COGS_TELEGRAM_ALLOWED_USER_IDS=777",
                ]),
                encoding="utf-8",
            )
            input_dir = root / "input"
            processing_dir = root / "processing"
            archive_dir = root / "archive"
            archive_dir.mkdir()
            offset_path = root / "offset.json"
            pilot3.save_telegram_offset(offset_path, 1001)
            (archive_dir / "telegram-telegram88842.input").write_text(
                "already processed",
                encoding="utf-8",
            )
            seen_offsets = []

            def opener(_token, *, offset, **_kwargs):
                seen_offsets.append(offset)
                return {"ok": True, "result": [telegram_update()]}

            run = pilot3.run_telegram_once(
                input_dir=input_dir,
                processing_dir=processing_dir,
                archive_dir=archive_dir,
                env_file=env_file,
                offset_path=offset_path,
                opener=opener,
            )
            loaded_offset = pilot3.load_telegram_offset(offset_path)

        self.assertEqual(seen_offsets, [1001])
        self.assertEqual(len(run.poll.written), 0)
        self.assertEqual(
            run.poll.ignored,
            ("update 1001: duplicate telegram-telegram88842.input",),
        )
        self.assertEqual(run.saved_offset, 1002)
        self.assertEqual(loaded_offset, 1002)

    def test_telegram_run_formats_no_message_as_pilot_friction(self):
        run = pilot3.Pilot3TelegramRun(
            poll=pilot3.TelegramPollResult(
                fetched=0,
                supported=0,
                allowed=0,
                written=(),
                ignored=(),
                next_offset=None,
            ),
            archived=(),
            still_pending=(),
            timed_out=False,
        )

        output = pilot3.format_telegram_run(run)

        self.assertIn("pilot friction", output)
        self.assertIn("no allowlisted Telegram text input was available", output)


if __name__ == "__main__":
    unittest.main()

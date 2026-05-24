import tempfile
import unittest
import json
from pathlib import Path

import agentic_loop
import review
import review_specialist


class Stage62DailyHardeningTests(unittest.TestCase):
    def test_validate_output_defaults_missing_cogs_daily_date(self):
        valid, invalid = agentic_loop.validate_output(
            [
                {
                    "node_type": "cogs/daily",
                    "item_text": "Bare daily item",
                    "confidence": "high",
                }
            ],
            default_cogs_date="2026-05-24",
        )

        self.assertEqual(len(invalid), 0)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0].date, "2026-05-24")

    def test_validate_output_rejects_suspicious_fallback_cogs_date(self):
        valid, invalid = agentic_loop.validate_output(
            [
                {
                    "node_type": "cogs/daily",
                    "item_text": "Bad fallback date",
                    "date": "2023-10-05",
                    "confidence": "high",
                }
            ],
            default_cogs_date="2026-05-24",
            reject_non_default_cogs_date=True,
        )

        self.assertEqual(valid, [])
        self.assertEqual(len(invalid), 1)
        self.assertIn("suspicious cogs/daily date", invalid[0][2])

    def test_validate_output_allows_explicit_cogs_date_outside_strict_fallback(self):
        valid, invalid = agentic_loop.validate_output(
            [
                {
                    "node_type": "cogs/daily",
                    "item_text": "Remember an old note",
                    "date": "2023-10-05",
                    "confidence": "high",
                }
            ],
            default_cogs_date="2026-05-24",
        )

        self.assertEqual(len(invalid), 0)
        self.assertEqual(valid[0].date, "2023-10-05")

    def test_review_approval_defaults_missing_cogs_date_from_created_frontmatter(self):
        raw = {
            "node_type": "cogs/daily",
            "item_text": "Review daily item",
            "confidence": "high",
        }

        normalized = review.normalize_review_raw(
            raw,
            reason="confidence: low",
            source_date="2026-05-24",
        )

        self.assertEqual(normalized["date"], "2026-05-24")

    def test_review_specialist_rejects_openai_fallback_bad_cogs_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_dir = root / "review"
            review_dir.mkdir()
            _write_review_file(
                review_dir / "bad-date.md",
                reason="openai_fallback_candidate: confidence: low",
                created="2026-05-24",
                raw={
                    "node_type": "cogs/daily",
                    "item_text": "Bad fallback date",
                    "date": "2023-10-05",
                    "confidence": "low",
                },
            )
            specialist = review_specialist.ReviewSpecialist(
                review_specialist.ReviewSpecialistConfig(review_dir=review_dir)
            )
            packet = root / "packet.md"
            packet.write_text(
                specialist.packet_preview()
                .replace("status: pending", "status: approved")
                .replace("| bad-date.md |  |", "| bad-date.md | approve |")
            )

            preview = specialist.packet_apply_preview(packet)

            self.assertEqual(preview.approve_count, 0)
            self.assertEqual(preview.rejected_count, 1)
            self.assertIn("suspicious cogs/daily date", preview.actions[0].issue)


def _write_review_file(path: Path, *, reason: str, created: str, raw: dict) -> None:
    path.write_text(
        "---\n"
        "node_type: review\n"
        "reviewed: false\n"
        f"created: {created}\n"
        "---\n\n"
        f"**Reason:** {reason}\n\n"
        f"```json\n{json.dumps(raw, indent=2)}\n```\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()

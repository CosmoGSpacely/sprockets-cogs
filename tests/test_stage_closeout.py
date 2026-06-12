import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import stage_closeout


class StageCloseoutTests(unittest.TestCase):
    def test_render_closeout_includes_all_outcome_sections(self):
        block = stage_closeout.render_closeout(
            stage_closeout.StageCloseout(
                stage="99",
                title="Model decision promoted.",
                summary=("A/B ran.",),
                promoted=("Gemma service posture.",),
                killed=("JSON-contract write authority.",),
                scheduled=("Pilot friction follow-up.",),
                commands=("scripts/check -> OK",),
                notes=("No vault writes from harness.",),
                timestamp="2026-06-12T08:30:00",
            )
        )

        self.assertIn("## Closeout Evidence - 2026-06-12T08:30:00", block)
        self.assertIn("Stage: 99", block)
        self.assertIn("- Gemma service posture.", block)
        self.assertIn("### Commands", block)

    def test_append_closeout_preserves_existing_stage_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "GROK.md"
            path.write_text("# Stage\n")

            stage_closeout.append_closeout(path, "## Closeout Evidence\n")

            self.assertEqual(path.read_text(), "# Stage\n\n## Closeout Evidence\n")

    def test_main_previews_closeout_block(self):
        buffer = StringIO()

        with redirect_stdout(buffer):
            stage_closeout.main([
                "--stage",
                "99",
                "--title",
                "Stage closed",
                "--summary",
                "A/B ran.",
                "--promoted",
                "Gemma posture.",
            ])

        output = buffer.getvalue()
        self.assertIn("Stage: 99", output)
        self.assertIn("- A/B ran.", output)
        self.assertIn("- Gemma posture.", output)


if __name__ == "__main__":
    unittest.main()

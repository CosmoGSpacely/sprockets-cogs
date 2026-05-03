import tempfile
import unittest
from pathlib import Path

import vault


class Stage145CarryPrimitiveTests(unittest.TestCase):
    def test_ensure_daily_note_creates_expected_cogs_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)

            path = vault.ensure_daily_note("2026-05-04", daily_dir)

            self.assertEqual(path.name, "Mon 04 May 2026.md")
            text = path.read_text()
            self.assertIn("node_type: cogs/daily", text)
            self.assertIn("date: 2026-05-04", text)
            self.assertIn("# Mon 04 May 2026", text)

    def test_append_cogs_item_text_skips_existing_item_across_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily_dir = Path(tmp)
            path = vault.ensure_daily_note("2026-05-04", daily_dir)
            path.write_text(path.read_text() + "- [>] Call Jordan\n")

            appended = vault.append_cogs_item_text("2026-05-04", "Call Jordan", daily_dir)

            self.assertFalse(appended)
            self.assertEqual(path.read_text().count("Call Jordan"), 1)

    def test_parse_cogs_blocks_keeps_child_lines_with_parent(self):
        content = (
            "---\n---\n\n"
            "# Mon 04 May 2026\n\n"
            "- [ ] WALMART\n"
            "  - [ ] return battery\n"
            "  - [ ] buy vitamins\n"
            "- [x] Done thing\n"
            "- [ ] Call Jordan\n"
            "plain note\n"
        )

        blocks = vault.parse_cogs_blocks(content)

        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].item_text, "WALMART")
        self.assertEqual(blocks[0].lines, (
            "- [ ] WALMART",
            "  - [ ] return battery",
            "  - [ ] buy vitamins",
        ))
        self.assertEqual(blocks[1].item_text, "Call Jordan")

    def test_parse_cogs_blocks_can_include_carried_and_cancelled_states(self):
        content = "- [>] Carried\n- [-] Cancelled\n- [ ] Open\n"

        blocks = vault.parse_cogs_blocks(content, states={" ", ">", "-"})

        self.assertEqual([block.state for block in blocks], [">", "-", " "])

    def test_mark_block_state_changes_only_parent_marker(self):
        content = "- [ ] WALMART\n  - [ ] return battery\n"
        block = vault.parse_cogs_blocks(content)[0]

        marked = vault.mark_block_state(content, block, ">")

        self.assertEqual(marked, "- [>] WALMART\n  - [ ] return battery\n")

    def test_mark_block_state_rejects_unknown_state(self):
        block = vault.parse_cogs_blocks("- [ ] Call Jordan\n")[0]

        with self.assertRaises(ValueError):
            vault.mark_block_state("- [ ] Call Jordan\n", block, "?")


if __name__ == "__main__":
    unittest.main()

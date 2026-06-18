import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import specialists.adapters.markitdown_batch as markitdown_batch


class Stage57MarkItDownBatchTests(unittest.TestCase):
    def test_batch_plan_reports_ready_and_blocked_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text("# A\n\nCapture A.", encoding="utf-8")
            (root / "b.bin").write_bytes(b"binary")
            (root / "c.pdf").write_bytes(b"%PDF")

            plan = markitdown_batch.build_batch_plan(root)

            statuses = {item.relative_path: item.status for item in plan.items}
            self.assertEqual(statuses["a.md"], "ready")
            self.assertEqual(statuses["b.bin"], "unsupported")
            self.assertEqual(statuses["c.pdf"], "requires_markitdown")
            self.assertEqual(plan.ready_count, 1)
            self.assertEqual(plan.blocked_count, 2)

    def test_batch_plan_can_scan_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "nested"
            nested.mkdir()
            (nested / "a.md").write_text("Nested capture.", encoding="utf-8")

            shallow = markitdown_batch.build_batch_plan(root)
            recursive = markitdown_batch.build_batch_plan(root, recursive=True)

            self.assertEqual(len(shallow.items), 0)
            self.assertEqual(len(recursive.items), 1)
            self.assertEqual(recursive.items[0].relative_path, "nested/a.md")

    def test_batch_apply_writes_ready_inputs_and_skips_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "docs"
            input_dir = Path(tmp) / "input"
            root.mkdir()
            (root / "a.md").write_text("# A\n\nCapture A.", encoding="utf-8")
            (root / "b.bin").write_bytes(b"binary")
            plan = markitdown_batch.build_batch_plan(root)

            result = markitdown_batch.apply_batch_plan(plan, input_dir)

            self.assertEqual(result.written_count, 1)
            self.assertEqual(result.skipped_count, 1)
            files = list(input_dir.glob("*.input"))
            self.assertEqual(len(files), 1)
            self.assertIn("Capture A", files[0].read_text(encoding="utf-8"))

    def test_batch_apply_is_idempotent_by_skipping_existing_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "docs"
            input_dir = Path(tmp) / "input"
            root.mkdir()
            (root / "a.md").write_text("# A\n\nCapture A.", encoding="utf-8")
            plan = markitdown_batch.build_batch_plan(root)

            first = markitdown_batch.apply_batch_plan(plan, input_dir)
            second = markitdown_batch.apply_batch_plan(plan, input_dir)

            self.assertEqual(first.written_count, 1)
            self.assertEqual(second.written_count, 0)
            self.assertEqual(second.items[0].status, "skipped_existing")

    def test_batch_apply_honors_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "docs"
            input_dir = Path(tmp) / "input"
            root.mkdir()
            (root / "a.md").write_text("A", encoding="utf-8")
            (root / "b.md").write_text("B", encoding="utf-8")
            plan = markitdown_batch.build_batch_plan(root)

            result = markitdown_batch.apply_batch_plan(plan, input_dir, limit=1)

            self.assertEqual(result.written_count, 1)
            self.assertEqual(result.items[1].status, "skipped_limit")

    def test_cli_plan_is_read_only_and_json_shaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text("A", encoding="utf-8")
            stdout = StringIO()

            with redirect_stdout(stdout):
                markitdown_batch.main([str(root), "--json"])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["ready_count"], 1)
            self.assertEqual(payload["items"][0]["status"], "ready")

    def test_cli_apply_requires_input_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text("A", encoding="utf-8")
            stderr = StringIO()

            with self.assertRaises(SystemExit) as raised, redirect_stderr(stderr):
                markitdown_batch.main([str(root), "--apply"])

            self.assertEqual(raised.exception.code, 2)
            self.assertIn("--input-dir is required", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

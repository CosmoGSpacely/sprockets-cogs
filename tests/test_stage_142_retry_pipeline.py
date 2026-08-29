"""Stage 142 slice 2b: a retried node gets the full node-scoped pipeline.

**The capture harness cannot verify this.** It calls `extract_nodes` and
`classify_nodes` and never calls `validate_output`, so the retry path is
outside everything Stages 138-142 have scored. That is part of why the
omission survived: no measurement covered it. Verification here is end to end
through `process_input`, which is the only place the retry branch runs.

The defect: `ensure_cogs_companions` guarantees every `sprockets/task` has a
`cogs/daily` companion, so the task appears on the day it belongs to. It ran
in the main pass and not on retry, so a node that failed validation once and
came back correct on the second attempt was written **without its companion**
and never showed up on the day.
"""
from __future__ import annotations

import unittest
from datetime import datetime as _real_datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from specialists.rosie import loop as agentic_loop


class FakeDateTime:
    """Pins `now()` without disabling the rest of `datetime`.

    `ensure_cogs_companions` calls `datetime.strptime` to validate a task's
    date before creating its companion, so a double that only offers
    `strftime` makes the step raise - and the companion silently not appear,
    which is the exact symptom this file is testing for.
    """

    @classmethod
    def now(cls):
        return cls()

    @classmethod
    def strptime(cls, value, fmt):
        return _real_datetime.strptime(value, fmt)

    def strftime(self, fmt):
        if fmt == "%H:%M":
            return "09:00"
        if fmt == "%Y%m%d_%H%M%S_%f":
            return "20260617_090000_000000"
        return "2026-06-17"


#: First classify reply: a cogs/daily carrying a malformed date. That fails
#: `validate_output` with a reason other than "confidence: low", which is the
#: condition that routes a node to retry rather than straight to review.
FIRST_REPLY = [
    {
        "node_type": "cogs/daily",
        "title": "Fix the tractor hydraulics",
        "item_text": "Fix the tractor hydraulics",
        "date": "not-a-date",
        "confidence": "high",
    }
]

#: Retry reply: a valid sprockets/task. `ensure_cogs_companions` should now
#: give it a cogs/daily companion. Before slice 2b that step did not run on
#: retry, so the task was written to the graph and never appeared on its day.
RETRY_REPLY = [
    {
        "node_type": "sprockets/task",
        "title": "Fix the tractor hydraulics",
        "item_text": "Fix the tractor hydraulics",
        "date": "2026-06-17",
        "confidence": "high",
    }
]


class RetryRunsNodeScopedStepsTests(unittest.TestCase):
    def _run(self):
        """Drive one capture whose only node fails, then succeeds on retry."""

        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        dirs = {
            name: root / name
            for name in ("input", "processing", "archive", "output")
        }
        daily_dir = root / "vault" / "Cogs" / "daily"
        review_dir = root / "vault" / "review"
        for path in list(dirs.values()) + [daily_dir, review_dir]:
            path.mkdir(parents=True)

        input_path = dirs["input"] / "retry-companion.input"
        input_path.write_text(
            "---\nsession_id: stage142b\nsource: telegram\n---\n\n"
            "Fix the tractor hydraulics\n",
            encoding="utf-8",
        )

        replies = [FIRST_REPLY, RETRY_REPLY]
        self.classify_calls = 0

        def fake_classify(*args, **kwargs):
            self.classify_calls += 1
            return replies.pop(0) if replies else []

        with patch.object(agentic_loop, "INPUT_DIR", dirs["input"]), \
             patch.object(agentic_loop, "PROCESSING_DIR", dirs["processing"]), \
             patch.object(agentic_loop, "ARCHIVE_DIR", dirs["archive"]), \
             patch.object(agentic_loop, "OUTPUT_DIR", dirs["output"]), \
             patch.object(agentic_loop, "DAILY_DIR", daily_dir), \
             patch.object(agentic_loop, "REVIEW_DIR", review_dir), \
             patch.object(agentic_loop, "datetime", FakeDateTime), \
             patch.object(agentic_loop, "build_context_for_input", return_value=""), \
             patch.object(agentic_loop, "extract_nodes",
                          return_value=[{"raw": "Fix the tractor hydraulics",
                                         "type_hint": "task"}]), \
             patch.object(agentic_loop, "classify_nodes", side_effect=fake_classify), \
             patch.object(agentic_loop, "memory_parent_trace") as memory_trace, \
             patch.object(agentic_loop, "write_memory_parent_trace"), \
             patch.object(agentic_loop, "route_openai_fallback_to_review",
                          return_value=False), \
             patch.object(agentic_loop, "send_processed_ack"):
            memory_trace.return_value.parent_title = ""
            memory_trace.return_value.selected = False
            memory_trace.return_value.retrieved_count = 0
            memory_trace.return_value.reason = "disabled"
            agentic_loop.process_input(input_path)

        return daily_dir, review_dir, dirs["archive"]

    def test_the_retry_path_actually_ran(self):
        """Guard on the test itself. An earlier draft used a shape that did
        not actually fail validation, so retry never fired and the companion
        assertion would have been measuring the main pass. Counting the
        classify calls is what makes this test honest."""

        self._run()
        self.assertEqual(
            self.classify_calls, 2,
            "classify ran once, so no retry happened and this file proves "
            "nothing about the retry pipeline",
        )

    def test_a_retried_task_gets_its_companion_cog(self):
        """The slice 2b fix. Before it, this note did not exist: the task was
        written to the graph and never appeared on its day."""

        daily_dir, _, _ = self._run()
        note = daily_dir / "2026-06-17 Wed.md"
        self.assertTrue(note.exists(), f"no daily note in {list(daily_dir.iterdir())}")
        self.assertIn("Fix the tractor hydraulics", note.read_text(encoding="utf-8"))


class RetryStepSelectionIsLiveTests(unittest.TestCase):
    """The declaration and the running code must agree, since the fix is a
    one-line change to a selector that nothing else would catch."""

    def test_retry_selector_returns_ten_steps(self):
        from specialists.rosie import pipeline

        selected = pipeline.retry_steps(agentic_loop.PIPELINE)
        self.assertEqual(len(selected), 10)
        self.assertNotIn(
            "route_structural_guard_to_review", {s.name for s in selected}
        )


if __name__ == "__main__":
    unittest.main()

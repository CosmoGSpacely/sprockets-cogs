from datetime import datetime, timezone
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import agentic_loop
from memory_guards import MemoryParentTrace
from memory_trace_log import (
    append_memory_parent_trace,
    memory_parent_trace_record,
    read_memory_parent_trace_records,
)
from retrieval_trace_report import format_memory_guard_jsonl_report


class Stage19MemoryTraceLogTests(unittest.TestCase):
    def test_memory_parent_trace_record_captures_selected_parent(self):
        trace = MemoryParentTrace(
            parent_title="Production",
            parent_node_id="projects/production",
            parent_node_type="sprockets/project",
            retrieved_count=5,
        )

        record = memory_parent_trace_record(
            trace,
            created_at=datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(record.created_at, "2026-05-04T12:00:00+00:00")
        self.assertEqual(record.decision, "selected")
        self.assertEqual(record.parent_title, "Production")
        self.assertEqual(record.parent_node_id, "projects/production")
        self.assertEqual(record.parent_node_type, "sprockets/project")
        self.assertEqual(record.retrieved_count, 5)
        self.assertEqual(record.reason, "")

    def test_memory_parent_trace_record_captures_skipped_parent(self):
        trace = MemoryParentTrace(
            top_node_id="contacts/tom-reilly",
            top_node_type="sprockets/contact",
            retrieved_count=4,
        )

        record = memory_parent_trace_record(
            trace,
            created_at=datetime(2026, 5, 4, 12, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(record.decision, "skipped")
        self.assertEqual(record.reason, "no hierarchy parent in retrieved nodes")
        self.assertEqual(record.top_node_id, "contacts/tom-reilly")
        self.assertEqual(record.top_node_type, "sprockets/contact")
        self.assertEqual(record.retrieved_count, 4)
        self.assertEqual(record.parent_title, "")

    def test_append_memory_parent_trace_writes_jsonl_record(self):
        trace = MemoryParentTrace(
            parent_title="Phase 3",
            parent_node_id="projects/phase-3",
            parent_node_type="sprockets/project",
            retrieved_count=3,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "output" / "memory-parent-traces.jsonl"
            append_memory_parent_trace(
                trace,
                path,
                created_at=datetime(2026, 5, 4, 12, 2, tzinfo=timezone.utc),
            )

            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["decision"], "selected")
        self.assertEqual(payload["parent_title"], "Phase 3")
        self.assertNotIn("input", payload)
        self.assertNotIn("query", payload)

    def test_read_memory_parent_trace_records_skips_bad_lines(self):
        lines = [
            "",
            "{not-json",
            json.dumps({"schema_version": 999}),
            json.dumps({
                "schema_version": 1,
                "created_at": "2026-05-04T12:03:00+00:00",
                "decision": "skipped",
                "retrieved_count": 2,
                "reason": "no hierarchy parent in retrieved nodes",
                "top_node_id": "contacts/tom-reilly",
                "top_node_type": "sprockets/contact",
            }),
        ]

        records = read_memory_parent_trace_records(lines)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].decision, "skipped")
        self.assertEqual(records[0].top_node_id, "contacts/tom-reilly")

    def test_format_memory_guard_jsonl_report_uses_durable_records(self):
        lines = [
            json.dumps({
                "schema_version": 1,
                "created_at": "2026-05-04T12:04:00+00:00",
                "decision": "selected",
                "retrieved_count": 5,
                "parent_title": "Production",
                "parent_node_id": "projects/production",
                "parent_node_type": "sprockets/project",
            })
        ]

        output = format_memory_guard_jsonl_report(lines)

        self.assertIn("- events: 1", output)
        self.assertIn("2026-05-04T12:04:00+00:00 selected", output)
        self.assertIn("parent: Production", output)
        self.assertIn("parent node: projects/production [sprockets/project]", output)

    def test_agentic_loop_memory_trace_path_uses_current_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            with patch.object(agentic_loop, "OUTPUT_DIR", output_dir):
                with patch.dict("os.environ", {}, clear=True):
                    path = agentic_loop.memory_trace_path()

        self.assertEqual(path, output_dir / "memory-parent-traces.jsonl")

    def test_agentic_loop_memory_trace_path_allows_explicit_override(self):
        with patch.dict(
            "os.environ",
            {"SPROCKETS_COGS_MEMORY_TRACE_PATH": "/tmp/custom-traces.jsonl"},
            clear=True,
        ):
            path = agentic_loop.memory_trace_path()

        self.assertEqual(path, Path("/tmp/custom-traces.jsonl"))


if __name__ == "__main__":
    unittest.main()

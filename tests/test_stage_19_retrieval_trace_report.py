import unittest

from retrieval_trace_report import (
    format_memory_guard_report,
    parse_memory_guard_log,
    parse_memory_guard_log_line,
)


class Stage19RetrievalTraceReportTests(unittest.TestCase):
    def test_parse_selected_memory_parent_guard_line(self):
        line = (
            "2026-05-04T10:01:02-0400 CogswellCogs python[123]: "
            "Memory parent guard selected: "
            "parent='Phase 3 - Memory Enhancement' "
            "node_id=projects/phase-3-memory-enhancement "
            "node_type=sprockets/project retrieved=5"
        )

        event = parse_memory_guard_log_line(line)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.timestamp, "2026-05-04T10:01:02-0400")
        self.assertEqual(event.decision, "selected")
        self.assertEqual(event.parent_title, "Phase 3 - Memory Enhancement")
        self.assertEqual(event.parent_node_id, "projects/phase-3-memory-enhancement")
        self.assertEqual(event.parent_node_type, "sprockets/project")
        self.assertEqual(event.retrieved_count, 5)

    def test_parse_skipped_memory_parent_guard_line(self):
        line = (
            "May 04 10:03:04 CogswellCogs python[123]: "
            "Memory parent guard skipped: "
            "reason=no hierarchy parent in retrieved nodes "
            "top_node_id=contacts/tom-reilly "
            "top_node_type=sprockets/contact retrieved=5"
        )

        event = parse_memory_guard_log_line(line)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.timestamp, "May 04 10:03:04")
        self.assertEqual(event.decision, "skipped")
        self.assertEqual(event.reason, "no hierarchy parent in retrieved nodes")
        self.assertEqual(event.top_node_id, "contacts/tom-reilly")
        self.assertEqual(event.top_node_type, "sprockets/contact")
        self.assertEqual(event.retrieved_count, 5)

    def test_parse_memory_guard_log_ignores_unrelated_lines(self):
        lines = [
            "2026-05-04T10:01:00-0400 service started",
            (
                "2026-05-04T10:01:02-0400 host python[123]: "
                "Memory parent guard selected: parent='Production' "
                "node_id=projects/production node_type=sprockets/project retrieved=3"
            ),
        ]

        events = parse_memory_guard_log(lines)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].parent_title, "Production")

    def test_format_memory_guard_report_lists_selected_and_skipped_events(self):
        events = parse_memory_guard_log([
            (
                "2026-05-04T10:01:02-0400 host python[123]: "
                "Memory parent guard selected: parent='Production' "
                "node_id=projects/production node_type=sprockets/project retrieved=3"
            ),
            (
                "2026-05-04T10:03:04-0400 host python[123]: "
                "Memory parent guard skipped: "
                "reason=no hierarchy parent in retrieved nodes "
                "top_node_id=contacts/tom-reilly "
                "top_node_type=sprockets/contact retrieved=5"
            ),
        ])

        output = format_memory_guard_report(events)

        self.assertIn("Sprockets-Cogs memory guard log report", output)
        self.assertIn("- events: 2", output)
        self.assertIn("selected", output)
        self.assertIn("parent: Production", output)
        self.assertIn("parent node: projects/production [sprockets/project]", output)
        self.assertIn("skipped", output)
        self.assertIn("reason: no hierarchy parent in retrieved nodes", output)
        self.assertIn("top node: contacts/tom-reilly [sprockets/contact]", output)

    def test_format_memory_guard_report_applies_limit_to_recent_events(self):
        events = parse_memory_guard_log([
            (
                "2026-05-04T10:01:02-0400 host python[123]: "
                "Memory parent guard selected: parent='First' "
                "node_id=projects/first node_type=sprockets/project retrieved=3"
            ),
            (
                "2026-05-04T10:02:02-0400 host python[123]: "
                "Memory parent guard selected: parent='Second' "
                "node_id=projects/second node_type=sprockets/project retrieved=3"
            ),
        ])

        output = format_memory_guard_report(events, limit=1)

        self.assertIn("- events: 1", output)
        self.assertNotIn("parent: First", output)
        self.assertIn("parent: Second", output)

    def test_format_memory_guard_report_handles_empty_events(self):
        output = format_memory_guard_report(())

        self.assertIn("- events: 0", output)
        self.assertIn("no selected/skipped memory parent guard events found", output)


if __name__ == "__main__":
    unittest.main()

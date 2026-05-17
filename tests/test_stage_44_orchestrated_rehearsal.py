import io
import json
import unittest
from contextlib import redirect_stdout

import orchestrated_rehearsal as rehearsal
import orchestrator_contract as orchestrator


class Stage44OrchestratedRehearsalTests(unittest.TestCase):
    def test_rehearsal_trace_routes_and_builds_handoff_without_execution(self):
        request = orchestrator.WorkRequest(
            source="cli",
            request_id="trace-44",
            content="show review packet",
        )

        trace = rehearsal.build_rehearsal_trace(request)

        self.assertEqual(trace.decision.specialist, "review")
        self.assertEqual(trace.handoff.trace_id, "trace-44")
        self.assertEqual(trace.handoff.recipient, "review")
        self.assertEqual(trace.specialist_command, ("scripts/review-specialist", "--inventory"))
        self.assertFalse(trace.appends_message)
        self.assertFalse(trace.executes_specialist)
        self.assertFalse(trace.writes)

    def test_specialist_preview_commands_are_read_only_boundary_commands(self):
        cases = [
            ("check service status", "operations", ("scripts/status",)),
            ("run memory benchmark", "memory", ("scripts/memory-specialist", "--retrieval-preview", "run memory benchmark")),
            ("run nightly carry report", "cogs", ("scripts/cogs-specialist", "--inventory")),
            ("propose project parent", "sprockets", ("scripts/sprockets-specialist", "--inventory")),
            ("show review packet", "review", ("scripts/review-specialist", "--inventory")),
        ]

        for content, specialist, command in cases:
            with self.subTest(content=content):
                request = orchestrator.WorkRequest(source="cli", request_id=f"trace-{specialist}", content=content)
                trace = rehearsal.build_rehearsal_trace(request)
                self.assertEqual(trace.decision.specialist, specialist)
                self.assertEqual(trace.specialist_command, command)

    def test_capture_rehearsal_uses_capture_preview_for_input_source(self):
        request = orchestrator.WorkRequest(
            source="/home/cosmo/sc/input/example.input",
            request_id="trace-capture",
            content="Need to draft release notes.",
        )

        trace = rehearsal.build_rehearsal_trace(request)

        self.assertEqual(trace.decision.specialist, "extractor-classifier")
        self.assertEqual(trace.specialist_command, ("scripts/capture-preview", "Need to draft release notes."))

    def test_format_rehearsal_trace_reports_no_writes(self):
        request = orchestrator.WorkRequest(source="cli", request_id="trace-ops", content="check status")
        trace = rehearsal.build_rehearsal_trace(request)

        output = rehearsal.format_rehearsal_trace(trace)

        self.assertIn("Orchestrated rehearsal preview", output)
        self.assertIn("- selected specialist: operations", output)
        self.assertIn("- appends message: no", output)
        self.assertIn("- executes specialist: no", output)
        self.assertIn("- writes: no", output)

    def test_rehearsal_json_payload_is_machine_readable(self):
        request = orchestrator.WorkRequest(source="cli", request_id="trace-memory", content="run memory benchmark")
        trace = rehearsal.build_rehearsal_trace(request)

        payload = json.loads(rehearsal.format_rehearsal_trace_json(trace))

        self.assertEqual(payload["decision"]["specialist"], "memory")
        self.assertEqual(payload["handoff"]["trace_id"], "trace-memory")
        self.assertEqual(payload["specialist_command"][0], "scripts/memory-specialist")
        self.assertFalse(payload["appends_message"])
        self.assertFalse(payload["executes_specialist"])
        self.assertFalse(payload["writes"])

    def test_main_prints_human_and_json_rehearsals(self):
        human = io.StringIO()
        with redirect_stdout(human):
            rehearsal.main(["--source", "cli", "--request-id", "trace-review", "show", "review", "packet"])

        machine = io.StringIO()
        with redirect_stdout(machine):
            rehearsal.main(["--json", "--source", "cli", "--request-id", "trace-status", "check", "status"])

        self.assertIn("Orchestrated rehearsal preview", human.getvalue())
        payload = json.loads(machine.getvalue())
        self.assertEqual(payload["decision"]["specialist"], "operations")


if __name__ == "__main__":
    unittest.main()

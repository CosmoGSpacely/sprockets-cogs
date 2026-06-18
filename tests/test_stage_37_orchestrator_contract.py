import io
import json
import unittest
from contextlib import redirect_stdout

import specialists.rudi.orchestrator_contract as orch


class Stage37OrchestratorContractTests(unittest.TestCase):
    def test_input_source_routes_to_capture(self):
        request = orch.WorkRequest(
            source="/home/cosmo/sc/input/quick-capture.input",
            content="Need to draft release notes.",
        )

        decision = orch.route_work_request(request)

        self.assertEqual(decision.specialist, "extractor-classifier")
        self.assertEqual(decision.mode, "capture")
        self.assertEqual(decision.write_posture, "proven-writes-only")
        self.assertEqual(decision.review, "not-required")

    def test_review_request_routes_to_review_boundary(self):
        request = orch.WorkRequest(
            source="cli",
            content="Show me the review packet for pending approvals.",
        )

        decision = orch.route_work_request(request)

        self.assertEqual(decision.specialist, "review")
        self.assertEqual(decision.mode, "review")
        self.assertEqual(decision.write_posture, "human-approved-only")
        self.assertEqual(decision.review, "required")

    def test_status_request_routes_to_operations_read_only(self):
        request = orch.WorkRequest(
            source="cli",
            content="Check service health and nightly timer status.",
        )

        decision = orch.route_work_request(request)

        self.assertEqual(decision.specialist, "operations")
        self.assertEqual(decision.mode, "operations")
        self.assertEqual(decision.write_posture, "read-only")
        self.assertEqual(decision.review, "not-required")

    def test_retrieval_request_routes_to_memory_read_only(self):
        request = orch.WorkRequest(
            source="cli",
            content="Run a retrieval benchmark preview for memory traces.",
        )

        decision = orch.route_work_request(request)

        self.assertEqual(decision.specialist, "memory")
        self.assertEqual(decision.mode, "retrieval")
        self.assertEqual(decision.write_posture, "read-only")

    def test_cogs_maintenance_request_uses_guarded_writes(self):
        request = orch.WorkRequest(
            source="cli",
            content="Run nightly carry report for weekly planning.",
        )

        decision = orch.route_work_request(request)

        self.assertEqual(decision.specialist, "cogs")
        self.assertEqual(decision.mode, "maintenance")
        self.assertEqual(decision.write_posture, "guarded-maintenance-writes")
        self.assertEqual(decision.review, "recommended")

    def test_hierarchy_request_routes_to_sprockets_planning_review(self):
        request = orch.WorkRequest(
            source="cli",
            content="Propose a project parent for this hierarchy item.",
        )

        decision = orch.route_work_request(request)

        self.assertEqual(decision.specialist, "sprockets")
        self.assertEqual(decision.mode, "planning")
        self.assertEqual(decision.write_posture, "proposal-or-review-only")
        self.assertEqual(decision.review, "required")

    def test_unknown_request_falls_back_to_review(self):
        request = orch.WorkRequest(source="cli", content="Something unusual.")

        decision = orch.route_work_request(request)

        self.assertEqual(decision.specialist, "review")
        self.assertEqual(decision.confidence, "low")
        self.assertEqual(decision.review, "required")

    def test_explicit_mode_overrides_keyword_routing(self):
        request = orch.WorkRequest(
            source="cli",
            mode="retrieval",
            content="review status and approvals",
        )

        decision = orch.route_work_request(request)

        self.assertEqual(decision.specialist, "memory")
        self.assertEqual(decision.mode, "retrieval")

    def test_unknown_mode_raises_clear_error(self):
        with self.assertRaisesRegex(ValueError, "unknown workflow mode"):
            orch.normalize_mode("chaos")

    def test_format_route_decision_is_deterministic(self):
        request = orch.WorkRequest(source="cli", content="status")
        decision = orch.route_work_request(request)

        output = orch.format_route_decision(request, decision)

        self.assertIn("Orchestrator route preview", output)
        self.assertIn("- selected mode: operations", output)
        self.assertIn("- specialist: operations", output)
        self.assertIn("- write posture: read-only", output)

    def test_main_prints_preview(self):
        buf = io.StringIO()

        with redirect_stdout(buf):
            orch.main(["--source", "cli", "check", "status"])

        output = buf.getvalue()
        self.assertIn("Orchestrator route preview", output)
        self.assertIn("- specialist: operations", output)

    def test_route_fixtures_match_expected_decisions(self):
        fixture_names = {fixture.name for fixture in orch.ROUTE_FIXTURES}

        self.assertIn("capture-input", fixture_names)
        self.assertIn("unknown-review", fixture_names)

        for fixture in orch.ROUTE_FIXTURES:
            with self.subTest(fixture=fixture.name):
                decision = orch.route_work_request(fixture.request)
                self.assertEqual(decision.specialist, fixture.expected_specialist)
                self.assertEqual(decision.mode, fixture.expected_mode)
                self.assertEqual(decision.write_posture, fixture.expected_write_posture)
                self.assertEqual(decision.review, fixture.expected_review)

    def test_route_decision_json_payload_is_stable_and_machine_readable(self):
        request = orch.WorkRequest(source="cli", content="check status")
        decision = orch.route_work_request(request)

        output = orch.format_route_decision_json(request, decision)
        payload = json.loads(output)

        self.assertEqual(payload["request"]["source"], "cli")
        self.assertEqual(payload["decision"]["specialist"], "operations")
        self.assertEqual(payload["decision"]["mode"], "operations")
        self.assertEqual(payload["decision"]["write_posture"], "read-only")

    def test_main_can_print_json_preview(self):
        buf = io.StringIO()

        with redirect_stdout(buf):
            orch.main(["--json", "--source", "cli", "check", "status"])

        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["decision"]["specialist"], "operations")
        self.assertEqual(payload["decision"]["review"], "not-required")

    def test_route_handoff_message_wraps_decision_without_execution(self):
        request = orch.WorkRequest(
            source="cli",
            request_id="trace-43",
            content="show review packet",
        )
        decision = orch.route_work_request(request)

        message = orch.route_handoff_message(request, decision)

        self.assertEqual(message.trace_id, "trace-43")
        self.assertEqual(message.idempotency_key, "trace-43:review:review")
        self.assertEqual(message.sender, "orchestrator")
        self.assertEqual(message.recipient, "review")
        self.assertEqual(message.kind, "review.handoff-preview")
        self.assertFalse(message.payload["execution"]["executed"])
        self.assertEqual(message.payload["decision"]["write_posture"], "human-approved-only")

    def test_format_route_handoff_reports_no_writes_or_execution(self):
        request = orch.WorkRequest(source="cli", request_id="trace-ops", content="check status")
        decision = orch.route_work_request(request)

        output = orch.format_route_handoff(request, decision)

        self.assertIn("Orchestrator handoff message preview", output)
        self.assertIn("- recipient: operations", output)
        self.assertIn("- writes: no", output)
        self.assertIn("- executes recipient: no", output)

    def test_main_can_print_handoff_json_preview(self):
        buf = io.StringIO()

        with redirect_stdout(buf):
            orch.main(
                [
                    "--handoff-preview",
                    "--json",
                    "--source",
                    "cli",
                    "--request-id",
                    "trace-memory",
                    "run",
                    "memory",
                    "benchmark",
                ]
            )

        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["executes_recipient"])
        self.assertEqual(payload["writes"], "no")
        self.assertEqual(payload["message"]["recipient"], "memory")
        self.assertEqual(payload["message"]["trace_id"], "trace-memory")


if __name__ == "__main__":
    unittest.main()

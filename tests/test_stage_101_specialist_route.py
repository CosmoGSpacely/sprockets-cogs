import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from specialists import routing as specialist_route
import specialists.uniblab.phase86_status as phase86_status


class Stage101SpecialistRouteTests(unittest.TestCase):
    def test_route_records_all_six_specialists_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            builder = root / "builder"
            builder.mkdir()
            (builder / "STATUS.md").write_text(
                "- Behaviors promoted during Phase 8.6 so far: **8**.\n"
            )
            phase_dir = builder / "stages" / "phase-086-implementation-interruption-promotion"
            phase_dir.mkdir(parents=True)
            (phase_dir / "README.md").write_text(
                "| Stage | Focus | Promotions |\n"
                "|---|---|---|\n"
                "| 101 | All-specialist routing pass | 4, 15 |\n"
            )
            (builder / "DEFERRED.md").write_text("")

            result = specialist_route.run_all_specialist_route(
                "Project: Remount front tractor tires; Cog: Saturday buy valves.",
                input_id="test-route",
                vault_dir=root / "vault",
                cogs_dir=root / "vault" / "Cogs",
                review_dir=root / "vault" / "review",
                builder_dir=builder,
            )

        self.assertEqual(
            result.specialist_ids(),
            ("rosie", "rudi", "sprockets", "cogs", "jane", "uniblab"),
        )
        self.assertTrue(all(event.writes == "no" for event in result.events))
        self.assertIn("packet", result.events[0].decision)
        self.assertEqual(result.events[4].artifact, "ReviewProposal")
        self.assertIn("phase86_promoted=8", result.events[5].result)

    def test_payload_is_machine_readable(self):
        events = (
            specialist_route.SpecialistAuditEvent(
                input_id="route",
                specialist="rosie",
                action="capture",
                artifact="NormalizedInput",
                decision="continue",
                timestamp="2026-06-12T10:00:00-04:00",
                result="ok",
            ),
        )
        result = specialist_route.AllSpecialistRouteResult(
            input_id="route",
            input_text="Project: Test; Cog: Do thing.",
            events=events,
        )

        payload = specialist_route.route_result_payload(result)

        self.assertEqual(payload["specialists"], ["rosie"])
        self.assertEqual(payload["events"][0]["artifact"], "NormalizedInput")
        self.assertEqual(payload["writes"], "no")

    def test_format_route_result_shows_audit_events(self):
        event = specialist_route.SpecialistAuditEvent(
            input_id="route",
            specialist="jane",
            action="review_packet_boundary",
            artifact="ReviewProposal",
            decision="present",
            timestamp="2026-06-12T10:00:00-04:00",
            result="proposal=one",
        )
        result = specialist_route.AllSpecialistRouteResult(
            input_id="route",
            input_text="Project: Test; Cog: Do thing.",
            events=(event,),
        )

        output = specialist_route.format_route_result(result)

        self.assertIn("Sprockets-Cogs all-specialist route", output)
        self.assertIn("- specialists: jane", output)
        self.assertIn("artifact: ReviewProposal", output)
        self.assertIn("writes: no", output)

    def test_main_prints_json_route(self):
        route = specialist_route.AllSpecialistRouteResult(
            input_id="route",
            input_text="Project: Test; Cog: Do thing.",
            events=(
                specialist_route.SpecialistAuditEvent(
                    input_id="route",
                    specialist="rosie",
                    action="capture",
                    artifact="NormalizedInput",
                    decision="continue",
                    timestamp="2026-06-12T10:00:00-04:00",
                    result="ok",
                ),
            ),
        )
        buf = io.StringIO()

        with patch("specialists.routing.run_all_specialist_route", return_value=route):
            with redirect_stdout(buf):
                specialist_route.main(["--json", "Project:", "Test"])

        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["input_id"], "route")
        self.assertEqual(payload["specialists"], ["rosie"])

    def test_phase86_status_empty_builder_is_still_safe_for_uniblab_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = phase86_status.build_phase86_status(Path(tmp))

        self.assertEqual(status.stages, ())
        self.assertEqual(status.deferred_rows, ())


if __name__ == "__main__":
    unittest.main()

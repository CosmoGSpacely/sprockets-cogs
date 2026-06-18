import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import specialists.rudi.agent_message_bus as bus


class Stage43AgentMessageBusTests(unittest.TestCase):
    def test_new_message_creates_required_trace_and_idempotency_fields(self):
        message = bus.new_message(
            sender="orchestrator",
            recipient="memory",
            kind="retrieval-preview",
            payload={"query": "phase 4"},
        )

        self.assertTrue(message.message_id)
        self.assertEqual(message.trace_id, message.message_id)
        self.assertEqual(message.idempotency_key, message.message_id)
        self.assertEqual(message.status, "pending")
        self.assertEqual(message.payload["query"], "phase 4")

    def test_message_round_trips_through_dict(self):
        message = bus.AgentMessage(
            message_id="m1",
            trace_id="t1",
            idempotency_key="k1",
            sender="orchestrator",
            recipient="review",
            kind="packet-preview",
            payload={"file": "review-packet.md"},
            created_at="2026-05-17T00:00:00Z",
        )

        reloaded = bus.message_from_dict(bus.message_to_dict(message))

        self.assertEqual(reloaded, message)

    def test_message_requires_identity_and_valid_status(self):
        with self.assertRaisesRegex(ValueError, "message_id is required"):
            bus.AgentMessage(
                message_id="",
                trace_id="t1",
                idempotency_key="k1",
                sender="orchestrator",
                recipient="review",
                kind="packet-preview",
            )
        with self.assertRaisesRegex(ValueError, "unknown message status"):
            bus.AgentMessage(
                message_id="m1",
                trace_id="t1",
                idempotency_key="k1",
                sender="orchestrator",
                recipient="review",
                kind="packet-preview",
                status="claimed",
            )

    def test_file_message_bus_appends_and_dedupes_by_idempotency_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "messages" / "bus.jsonl"
            message = bus.AgentMessage(
                message_id="m1",
                trace_id="trace-1",
                idempotency_key="same-work",
                sender="orchestrator",
                recipient="cogs",
                kind="nightly-report",
            )
            duplicate = bus.AgentMessage(
                message_id="m2",
                trace_id="trace-2",
                idempotency_key="same-work",
                sender="orchestrator",
                recipient="cogs",
                kind="nightly-report",
            )
            message_bus = bus.FileMessageBus(path)

            first = message_bus.append(message)
            second = message_bus.append(duplicate)

            self.assertTrue(first.appended)
            self.assertFalse(second.appended)
            self.assertEqual(second.message.message_id, "m1")
            self.assertEqual(len(message_bus.messages()), 1)

    def test_file_message_bus_filters_and_status_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bus.jsonl"
            message_bus = bus.FileMessageBus(path)
            message_bus.append(_message("m1", "review", "pending"))
            message_bus.append(_message("m2", "memory", "done"))
            message_bus.append(_message("m3", "review", "failed"))

            status = message_bus.status()
            review_messages = message_bus.messages(recipient="review")
            failed_review = message_bus.messages(recipient="review", status="failed")

            self.assertEqual(status.total, 3)
            self.assertEqual(status.pending, 1)
            self.assertEqual(status.done, 1)
            self.assertEqual(status.failed, 1)
            self.assertEqual([message.message_id for message in review_messages], ["m1", "m3"])
            self.assertEqual([message.message_id for message in failed_review], ["m3"])

    def test_main_prints_status_list_and_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bus.jsonl"
            append_out = io.StringIO()
            with redirect_stdout(append_out):
                bus.main(
                    [
                        "--path",
                        str(path),
                        "--append",
                        "--sender",
                        "orchestrator",
                        "--to",
                        "review",
                        "--kind",
                        "packet-preview",
                        "--trace-id",
                        "trace-1",
                        "--idempotency-key",
                        "packet-1",
                        "--payload",
                        json.dumps({"packet": "review-packet.md"}),
                    ]
                )

            status_out = io.StringIO()
            with redirect_stdout(status_out):
                bus.main(["--path", str(path), "--status"])

            list_out = io.StringIO()
            with redirect_stdout(list_out):
                bus.main(["--path", str(path), "--recipient", "review", "--list"])

            self.assertIn("- action: appended", append_out.getvalue())
            self.assertIn("- total: 1", status_out.getvalue())
            self.assertIn("orchestrator->review", list_out.getvalue())


def _message(message_id: str, recipient: str, status: bus.MessageStatus) -> bus.AgentMessage:
    return bus.AgentMessage(
        message_id=message_id,
        trace_id=f"trace-{message_id}",
        idempotency_key=f"key-{message_id}",
        sender="orchestrator",
        recipient=recipient,
        kind="preview",
        status=status,
        created_at="2026-05-17T00:00:00Z",
    )

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import specialists.rudi.agent_message_bus as agent_message_bus
import specialists.cogs.carry as carry
import specialists.cogs.planning as cogs_planning
import specialists.jane.specialist as review_specialist


class Stage50CliErgonomicsTests(unittest.TestCase):
    def test_carry_without_action_exits_nonzero_with_action_hint(self):
        stderr = io.StringIO()

        with self.assertRaises(SystemExit) as raised, redirect_stderr(stderr):
            carry.main([])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("choose --list, --plan", stderr.getvalue())

    def test_agent_message_bus_rejects_invalid_json_payload_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            stderr = io.StringIO()

            with self.assertRaises(SystemExit) as raised, redirect_stderr(stderr):
                agent_message_bus.main([
                    "--path",
                    str(Path(tmp) / "messages.jsonl"),
                    "--append",
                    "--payload",
                    "{not-json",
                ])

            self.assertEqual(raised.exception.code, 2)
            output = stderr.getvalue()
            self.assertIn("--payload must be valid JSON", output)
            self.assertNotIn("Traceback", output)

    def test_agent_message_bus_rejects_non_object_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            stderr = io.StringIO()

            with self.assertRaises(SystemExit) as raised, redirect_stderr(stderr):
                agent_message_bus.main([
                    "--path",
                    str(Path(tmp) / "messages.jsonl"),
                    "--append",
                    "--payload",
                    "[]",
                ])

            self.assertEqual(raised.exception.code, 2)
            self.assertIn("--payload must be a JSON object", stderr.getvalue())

    def test_representative_help_text_marks_write_posture(self):
        carry_help = _help_for(carry.main, ["--help"])
        planning_help = _help_for(cogs_planning.main, ["--help"])
        bus_help = agent_message_bus.build_parser().format_help()
        review_help = review_specialist.build_parser().format_help()

        self.assertIn("Read-only;", carry_help)
        self.assertIn("exits nonzero if invalid", carry_help)
        self.assertIn("Writes Cogs daily notes", carry_help)
        self.assertIn("Read-only;", planning_help)
        self.assertIn("does not", planning_help)
        self.assertIn("rename files", planning_help)
        self.assertIn("Writes Cogs planning notes", planning_help)
        self.assertIn("Read-only", bus_help)
        self.assertIn("Writes the JSONL bus", bus_help)
        self.assertIn("file, not the vault", bus_help)
        self.assertIn("Writes only --packet-path", review_help)


def _help_for(main_func, argv):
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        with unittest.TestCase().assertRaises(SystemExit) as raised:
            main_func(argv)
    if raised.exception.code not in (0, None):
        raise AssertionError(f"help exited with unexpected code {raised.exception.code!r}")
    return stdout.getvalue()


if __name__ == "__main__":
    unittest.main()

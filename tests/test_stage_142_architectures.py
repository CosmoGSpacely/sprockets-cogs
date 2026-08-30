"""Stage 142 slice 1: the seven call architectures, driven by a fake client.

These tests do not measure anything - the experiment does that. They assert
the plumbing is honest, because a candidate that silently makes two calls while
claiming one, or that loses its raw_nodes without saying so, would produce a
number that reads as a result and is not one.
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime
from types import SimpleNamespace

from specialists.rosie import architectures
from specialists.rosie.architectures import ARCHITECTURES
from specialists.rosie.extractor_classifier import (
    ExtractClassifier,
    ExtractClassifierConfig,
)


class FakeResponse(SimpleNamespace):
    pass


def _response(payload: dict) -> FakeResponse:
    return FakeResponse(
        message=SimpleNamespace(content=json.dumps(payload)),
        prompt_eval_count=100,
        eval_count=20,
        total_duration=1_000_000_000,
        load_duration=0,
        prompt_eval_duration=200_000_000,
        eval_duration=800_000_000,
    )


EXTRACT_REPLY = {"items": [{"raw": "Call the vet", "type_hint": "task"}]}
CLASSIFY_REPLY = {"nodes": [{
    "node_type": "cogs/daily", "title": "Call the vet",
    "item_text": "Call the vet", "date": "2026-06-12", "confidence": "high",
}]}
STAGED_REPLY = {"nodes": [{
    "raw": "Call the vet", "type_hint": "task",
    "node_type": "cogs/daily", "title": "Call the vet",
    "item_text": "Call the vet", "date": "2026-06-12", "confidence": "high",
}]}
HIERARCHY_REPLY = {"decisions": [{"index": 0, "parent_hint": "Farm"}]}


class RecordingClient:
    """Answers by inspecting which schema it was handed, so one client serves
    every architecture without the test knowing the call order."""

    def __init__(self, staged_confidence="high"):
        self.calls: list[dict] = []
        self.staged_confidence = staged_confidence

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        schema = kwargs.get("format") or {}
        props = schema.get("properties", {})
        if "items" in props:
            return _response(EXTRACT_REPLY)
        if "decisions" in props:
            return _response(HIERARCHY_REPLY)
        node_props = props.get("nodes", {}).get("items", {}).get("properties", {})
        if "raw" in node_props:
            reply = json.loads(json.dumps(STAGED_REPLY))
            reply["nodes"][0]["confidence"] = self.staged_confidence
            return _response(reply)
        return _response(CLASSIFY_REPLY)


def _classifier(client):
    return ExtractClassifier(ExtractClassifierConfig(model="fake"), chat_client=client)


NOW = datetime(2026, 6, 12, 9, 0)
CONFIG = SimpleNamespace(use_examples=True, context_max_chars=2000)


def _run(name, content="Call the vet", context="", client=None):
    client = client or RecordingClient()
    classifier = _classifier(client)
    run = ARCHITECTURES[name](classifier, content, NOW, context, CONFIG)
    return run, client, classifier


class RegistryTests(unittest.TestCase):
    def test_all_candidates_are_registered(self):
        """Seven call-architecture candidates, plus the slice 6 prompt ladder.

        The ladder arms share `preserve-extract`'s call shape and vary only the
        prompt surface, so they are not new candidates - they retire when
        slice 6 promotes whichever rung wins.
        """

        self.assertEqual(sorted(ARCHITECTURES), [
            "conditional", "one-flat", "one-staged", "preserve-extract",
            "preserve-nocalendar", "preserve-noexamples", "preserve-noprose",
            "segmented", "two-call", "two-seam-decision",
        ])

    def test_every_architecture_produces_nodes(self):
        for name in ARCHITECTURES:
            with self.subTest(architecture=name):
                run, _, _ = _run(name, context="Areas: Farm")
                self.assertTrue(run.classified_nodes, name)


class Slice6LadderTests(unittest.TestCase):
    """Each rung must actually differ from the one below it.

    The ladder's whole purpose is attributing a movement to one change, so an
    arm that silently sends the same prompt as its predecessor would produce a
    "no effect" reading that measured nothing (finding 79).
    """

    def _prompt_surface(self, name) -> str:
        _, client, _ = _run(name)
        return json.dumps([call["messages"] for call in client.calls])

    def test_rungs_remove_the_multi_day_rule_in_order(self):
        base = self._prompt_surface("preserve-extract")
        noprose = self._prompt_surface("preserve-noprose")
        noexamples = self._prompt_surface("preserve-noexamples")

        # The prose lives only in classify; extract's copy is already gone.
        self.assertIn("Multi-day settings", base)
        self.assertNotIn("Multi-day settings", noprose)

        # The examples survive the prose removal, and that is the point.
        self.assertIn("working from home all week", noprose)
        self.assertNotIn("all week", noexamples)

    def test_nocalendar_drops_the_workday_list_from_both_calls(self):
        with_calendar = self._prompt_surface("preserve-noexamples")
        without = self._prompt_surface("preserve-nocalendar")

        self.assertEqual(with_calendar.count("This week's workdays"), 2)
        self.assertNotIn("This week's workdays", without)
        self.assertIn("Today: 2026-06-12", without)

    def test_every_rung_keeps_the_two_call_seam_and_raw_nodes(self):
        for name in ("preserve-noprose", "preserve-noexamples", "preserve-nocalendar"):
            with self.subTest(architecture=name):
                run, client, _ = _run(name)
                self.assertEqual(len(client.calls), 2)
                self.assertTrue(run.raw_nodes)

    def test_removal_helpers_refuse_to_no_op(self):
        """A drifted prompt must fail loudly rather than produce a duplicate arm."""

        with self.assertRaises(ValueError):
            architectures._without_block("some prompt", "absent block", "label")
        with self.assertRaises(ValueError):
            architectures._without_pair(
                architectures.EXTRACT_EXAMPLES, 0, "working from home all week"
            )


class CallCountTests(unittest.TestCase):
    """The experiment's whole subject. A candidate claiming one call must make
    one call."""

    def test_two_call_makes_two(self):
        _, client, _ = _run("two-call")
        self.assertEqual(len(client.calls), 2)

    def test_preserve_extract_makes_two(self):
        _, client, _ = _run("preserve-extract")
        self.assertEqual(len(client.calls), 2)

    def test_one_flat_makes_one(self):
        _, client, _ = _run("one-flat")
        self.assertEqual(len(client.calls), 1)

    def test_one_staged_makes_one(self):
        _, client, _ = _run("one-staged")
        self.assertEqual(len(client.calls), 1)

    def test_segmented_makes_one_when_it_segments(self):
        _, client, _ = _run("segmented", content="Saturday:\n- Walmart")
        self.assertEqual(len(client.calls), 1)

    def test_segmented_makes_two_when_it_declines(self):
        """The fallback is the honest cost of a hybrid, and it must be
        visible rather than hidden inside a one-call claim."""

        run, client, _ = _run(
            "segmented",
            content="um okay so i need to call Frank and pick up feed and "
                    "there's a dentist thing thursday at eight thirty",
        )
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(any("fell back" in note for note in run.notes))

    def test_conditional_makes_one_when_confident(self):
        _, client, _ = _run("conditional", client=RecordingClient("high"))
        self.assertEqual(len(client.calls), 1)

    def test_conditional_escalates_on_low_confidence(self):
        run, client, _ = _run("conditional", client=RecordingClient("low"))
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(any("escalated" in note for note in run.notes))


class ObservabilityTests(unittest.TestCase):
    def test_one_flat_reports_that_it_lost_raw_nodes(self):
        """Candidate 3's real cost. Silently returning [] would let it win on
        accuracy and cost while removing the inspection point where findings
        44, 55, and 61 were diagnosed."""

        run, _, _ = _run("one-flat")
        self.assertEqual(run.raw_nodes, [])
        self.assertTrue(any("raw_nodes" in note for note in run.notes))

    def test_one_staged_preserves_raw_nodes(self):
        """Candidate 4 exists precisely to keep this."""

        run, _, _ = _run("one-staged")
        self.assertEqual(run.raw_nodes, [{"raw": "Call the vet", "type_hint": "task"}])

    def test_staged_echo_fields_do_not_leak_into_nodes(self):
        """`raw` and `type_hint` are not node fields. Leaving them on would
        fail validation and grade the plumbing rather than the architecture."""

        run, _, _ = _run("one-staged")
        for node in run.classified_nodes:
            self.assertNotIn("raw", node)
            self.assertNotIn("type_hint", node)

    def test_segmented_reports_its_segment_count(self):
        run, _, _ = _run("segmented", content="Saturday:\n- Walmart\n- Home Depot")
        self.assertEqual(len(run.raw_nodes), 2)
        self.assertTrue(any("segmented" in note for note in run.notes))


class MergedPromptTests(unittest.TestCase):
    def test_merged_prompt_declares_exactly_one_output_format(self):
        """Each half declares its own envelope. Two would tell the model to
        emit both."""

        self.assertEqual(architectures.MERGED_SYSTEM.count("Output format:"), 1)

    def test_merged_prompt_carries_doctrine_from_both_halves(self):
        merged = architectures.MERGED_SYSTEM
        self.assertIn("type_hint values:", merged)      # from extract
        self.assertIn("node_type rules:", merged)       # from classify
        self.assertIn("Counted repeats", merged)

    def test_merged_prompt_drops_the_hand_off_framing(self):
        """"Given extracted items" is false in a merged call - there is no
        prior call to have extracted them."""

        self.assertNotIn("Given extracted items", architectures.MERGED_SYSTEM)

    def test_staged_prompt_asks_for_the_echo(self):
        self.assertIn("raw", architectures.MERGED_STAGED_SYSTEM)
        self.assertIn("do not rewrite it", architectures.MERGED_STAGED_SYSTEM)

    def test_preserve_prompt_forbids_computing(self):
        prompt = architectures.PRESERVE_EXTRACT_SYSTEM
        self.assertIn("PRESERVE, NEVER COMPUTE", prompt)
        self.assertNotIn("using the workdays list", prompt)

    def test_staged_schema_requires_the_echo_fields(self):
        required = architectures.STAGED_SCHEMA["properties"]["nodes"]["items"]["required"]
        self.assertIn("raw", required)
        self.assertIn("type_hint", required)


class HierarchySeamTests(unittest.TestCase):
    def test_second_call_applies_parent_hints(self):
        run, client, _ = _run("two-seam-decision", context="Areas: Farm")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(run.classified_nodes[0]["parent_hint"], "Farm")

    def test_second_call_is_skipped_without_context(self):
        """With no hierarchy in context there is nothing to decide, and paying
        a call to be told so is the cost this candidate is accused of."""

        run, client, _ = _run("two-seam-decision", context="")
        self.assertEqual(len(client.calls), 1)
        self.assertTrue(any("skipped" in note for note in run.notes))


if __name__ == "__main__":
    unittest.main()

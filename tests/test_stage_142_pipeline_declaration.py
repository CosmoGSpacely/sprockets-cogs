"""Stage 142 slice 2: the declared pipeline and the truncation fix.

Two changes, tested separately because only one of them changes behaviour.

`pipeline.py` is a pure refactor - the same functions in the same order - so
its tests assert structure and ordering, and the real proof is the harness
score holding.

`ModelOutputError` **does** change behaviour, deliberately (D104, finding 73):
a reply that cannot be parsed used to become an empty node list, so the
capture was consumed, wrote nothing, and reported success.
"""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from specialists.rosie import pipeline
from specialists.rosie.extractor_classifier import (
    ExtractClassifier,
    ExtractClassifierConfig,
    ModelOutputError,
)
from specialists.rosie.pipeline import CaptureState, PipelineStep, run_pipeline


def _state(**overrides):
    base = dict(
        content="Call the vet",
        raw_nodes=[{"raw": "Call the vet", "type_hint": "task"}],
        classified=[{"node_type": "cogs/daily", "title": "Call the vet"}],
        source_date="2026-06-12",
        session_id="s1",
    )
    base.update(overrides)
    return CaptureState(**base)


def _step(name, scope="nodes", pure=True, fn=None):
    return PipelineStep(name, scope, pure, fn or (lambda s: None), retry_note="test")


class RunnerTests(unittest.TestCase):
    def test_steps_run_in_declared_order(self):
        order = []
        steps = [_step(n, fn=lambda s, n=n: order.append(n)) for n in ("a", "b", "c")]
        run_pipeline(_state(), steps)
        self.assertEqual(order, ["a", "b", "c"])

    def test_steps_run_is_recorded(self):
        steps = [_step("a"), _step("b")]
        state = run_pipeline(_state(), steps)
        self.assertEqual(state.steps_run, ["a", "b"])

    def test_termination_stops_the_chain(self):
        """The structural guard ends a capture. Steps after it must not run -
        that is the early return the inline version did with `return`."""

        order = []

        def terminate(state):
            order.append("guard")
            state.terminated = True

        steps = [
            _step("before", fn=lambda s: order.append("before")),
            _step("guard", scope="capture", fn=terminate),
            _step("after", fn=lambda s: order.append("after")),
        ]
        state = run_pipeline(_state(), steps)
        self.assertEqual(order, ["before", "guard"])
        self.assertTrue(state.terminated)
        self.assertNotIn("after", state.steps_run)

    def test_scope_filter_selects_a_subset(self):
        order = []
        steps = [
            _step("capture_step", scope="capture", fn=lambda s: order.append("capture_step")),
            _step("node_step", scope="nodes", fn=lambda s: order.append("node_step")),
        ]
        run_pipeline(_state(), steps, only_scope="nodes")
        self.assertEqual(order, ["node_step"])

    def test_a_step_can_replace_the_node_list(self):
        def double(state):
            state.classified = state.classified * 2

        state = run_pipeline(_state(), [_step("double", fn=double)])
        self.assertEqual(len(state.classified), 2)


class RetrySelectionTests(unittest.TestCase):
    def test_retry_includes_exactly_the_three_inline_steps(self):
        steps = [_step(n) for n in pipeline.RETRY_INCLUDED] + [_step("other")]
        selected = [s.name for s in pipeline.retry_steps(steps)]
        self.assertEqual(selected, list(pipeline.RETRY_INCLUDED))

    def test_omissions_are_split_into_correct_and_defect(self):
        correct = [n for n, r in pipeline.RETRY_OMISSIONS.items() if r.startswith("CORRECT")]
        defect = [n for n, r in pipeline.RETRY_OMISSIONS.items() if r.startswith("DEFECT")]
        self.assertEqual(len(correct), 3)
        self.assertEqual(len(defect), 7)

    def test_capture_scoped_omissions_are_all_correct(self):
        """A whole-capture decision should never be re-made on a retried
        subset, so no capture-scoped step may be marked a defect."""

        from specialists.rosie import loop

        for step in loop.PIPELINE:
            if step.scope == "capture" and step.name in pipeline.RETRY_OMISSIONS:
                with self.subTest(step=step.name):
                    self.assertTrue(
                        pipeline.RETRY_OMISSIONS[step.name].startswith("CORRECT")
                    )

    def test_ensure_cogs_companions_is_a_recorded_defect(self):
        """Named explicitly because it is the most user-visible of the seven:
        a retried task never gets its companion Cog, so it does not appear on
        the day it belongs to."""

        self.assertTrue(
            pipeline.RETRY_OMISSIONS["ensure_cogs_companions"].startswith("DEFECT")
        )


def _reply(content, eval_count=10):
    return SimpleNamespace(
        message=SimpleNamespace(content=content),
        prompt_eval_count=100,
        eval_count=eval_count,
        total_duration=0,
        load_duration=0,
        prompt_eval_duration=0,
        eval_duration=0,
    )


class TruncationRaisesTests(unittest.TestCase):
    """D104. The behaviour change in this slice."""

    def _classifier(self, content, eval_count=10):
        return ExtractClassifier(
            ExtractClassifierConfig(model="fake"),
            chat_client=lambda **kw: _reply(content, eval_count),
        )

    def test_truncated_extract_raises_rather_than_returning_empty(self):
        truncated = '{"items": [{"raw": "Call the vet", "type_h'
        with self.assertRaises(ModelOutputError):
            self._classifier(truncated).extract_nodes("Call the vet")

    def test_truncated_classify_raises_rather_than_returning_empty(self):
        truncated = '{"nodes": [{"node_type": "cogs/da'
        with self.assertRaises(ModelOutputError):
            self._classifier(truncated).classify_nodes(
                [{"raw": "x", "type_hint": "task"}], ""
            )

    def test_the_error_reports_the_completion_count(self):
        """4,096 in this field is the num_predict cap, which is how a
        truncation is told apart from a malformed short reply."""

        with self.assertRaises(ModelOutputError) as caught:
            self._classifier('{"items": [{"raw', eval_count=4096).extract_nodes("x")
        self.assertEqual(caught.exception.completion_tokens, 4096)
        self.assertIn("4096", str(caught.exception))
        self.assertIn("truncation", str(caught.exception))

    def test_valid_empty_output_is_still_empty_not_an_error(self):
        """`empty-greeting` must keep working. Restraint and truncation used
        to be the same observation; they must not become the same error."""

        classifier = self._classifier('{"items": []}')
        self.assertEqual(classifier.extract_nodes("Hello"), [])

    def test_a_complete_reply_is_unaffected(self):
        payload = {"nodes": [{"node_type": "cogs/daily", "title": "Yoga"}]}
        classifier = self._classifier(json.dumps(payload))
        nodes = classifier.classify_nodes([{"raw": "yoga", "type_hint": "appointment"}], "")
        self.assertEqual(nodes, payload["nodes"])


if __name__ == "__main__":
    unittest.main()

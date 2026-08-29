"""Stage 139 slice 6: harness scores the live post-classify chain.

The harness reaches into specialist internals instead of driving capture
through `loop.py` (deferred as D099). That shortcut is what let it score a
path the product does not run for two whole stages - Stage 139 finding 34.
These tests are the guard that makes the shortcut survivable: if `loop.py`
changes its post-classify sequence, the drift test fails and names the list
the harness has to be updated to match.
"""
from __future__ import annotations

import inspect
import re
import unittest

from specialists.rosie import loop, pipeline
from specialists.uniblab import capture_harness


class PostClassifyDriftTests(unittest.TestCase):
    """Guards the harness against the live pipeline moving underneath it."""

    def _live_sequence(self) -> list[str]:
        """The post-classify chain, read from the declaration.

        Stage 142 A1 turned the chain into data, so this reads `loop.PIPELINE`
        instead of regexing the source of a 200-line function. The old parser
        had to stop before the retry block because the retry block repeated the
        chain by hand - which is precisely where an uncovered copy lived.
        """

        return [step.name for step in loop.PIPELINE]

    def test_harness_matches_live_post_classify_order(self):
        self.assertEqual(
            self._live_sequence(),
            list(capture_harness.LIVE_POST_CLASSIFY_STEPS),
            "loop.py's post-classify chain changed; update "
            "capture_harness.LIVE_POST_CLASSIFY_STEPS and "
            "apply_live_post_classify to match, or the harness will score a "
            "path the product does not run",
        )

    def test_harness_calls_every_step_it_models(self):
        source = inspect.getsource(capture_harness.apply_live_post_classify)
        for step in capture_harness.MODELED_STEPS:
            self.assertIn(step + "(", source, step)

    def test_every_live_step_is_either_modeled_or_explained(self):
        """No step may be silently skipped - that is how finding 34 happened."""

        for step in capture_harness.LIVE_POST_CLASSIFY_STEPS:
            self.assertTrue(
                step in capture_harness.MODELED_STEPS
                or step in capture_harness.UNMODELED_STEPS,
                f"{step} is neither modeled nor explained in UNMODELED_STEPS",
            )

    def test_modeled_and_unmodeled_do_not_overlap(self):
        overlap = set(capture_harness.MODELED_STEPS) & set(capture_harness.UNMODELED_STEPS)
        self.assertEqual(overlap, set())


class DeclarationIsAuthoritativeTests(unittest.TestCase):
    """Stage 142 A1/A3. A declaration nothing executes is documentation."""

    def test_process_input_runs_the_pipeline(self):
        source = inspect.getsource(loop.process_input)
        self.assertIn("run_pipeline(", source)
        self.assertIn("PIPELINE", source)

    def test_process_input_does_not_call_steps_inline(self):
        """The whole point. If a step is called directly, the declaration is
        no longer the order that runs, and the drift guard above - which now
        reads the declaration - would be checking a fiction."""

        source = inspect.getsource(loop.process_input)
        for step in loop.PIPELINE:
            self.assertNotIn(
                f"{step.name}(", source,
                f"{step.name} is called inline in process_input; it belongs to "
                "PIPELINE, and calling it directly makes the declaration a lie",
            )

    def test_every_step_declares_a_scope_and_purity(self):
        for step in loop.PIPELINE:
            with self.subTest(step=step.name):
                self.assertIn(step.scope, ("capture", "nodes"))
                self.assertIsInstance(step.pure, bool)
                self.assertTrue(step.retry_note.strip(), "missing retry_note")

    def test_every_modeled_step_is_pure(self):
        """The implication runs one way only. The harness is read-only by
        contract, so it can run a step only if that step has no side effects.

        The converse is false, and conflating them is a mistake this test
        originally made: `apply_memory_parent_title` and
        `ensure_memory_hierarchy_tasks` are pure functions the harness still
        cannot run, because their `memory_parent` input needs live RUDI
        retrieval. Purity is a property of the step; modelability also depends
        on whether its inputs exist outside the live path.
        """

        for step in loop.PIPELINE:
            if step.name in capture_harness.MODELED_STEPS:
                with self.subTest(step=step.name):
                    self.assertTrue(
                        step.pure,
                        f"{step.name} is modeled by the read-only harness but "
                        "declared impure",
                    )

    def test_pure_but_unmodeled_steps_say_why(self):
        """A pure step the harness skips needs a recorded reason, or the gap
        looks like an oversight rather than a missing input."""

        for step in loop.PIPELINE:
            if step.pure and step.name not in capture_harness.MODELED_STEPS:
                with self.subTest(step=step.name):
                    self.assertIn(step.name, capture_harness.UNMODELED_STEPS)


class RetryPathDriftTests(unittest.TestCase):
    """Stage 142 A2/A3. The retry path re-ran three of thirteen steps and the
    reason was recorded nowhere. The old drift guard stopped parsing before
    this block, so the second copy was entirely uncovered."""

    def test_retry_uses_the_same_declaration(self):
        source = inspect.getsource(loop.process_input)
        self.assertIn("retry_steps(PIPELINE)", source)

    def test_retry_selection_matches_the_recorded_set(self):
        selected = [step.name for step in pipeline.retry_steps(loop.PIPELINE)]
        self.assertEqual(selected, list(pipeline.RETRY_INCLUDED))

    def test_every_step_is_included_or_its_omission_explained(self):
        """No step may be silently absent from retry. This is finding 34's
        lesson applied to the copy nobody was checking."""

        for step in loop.PIPELINE:
            with self.subTest(step=step.name):
                self.assertTrue(
                    step.name in pipeline.RETRY_INCLUDED
                    or step.name in pipeline.RETRY_OMISSIONS,
                    f"{step.name} neither re-runs on retry nor explains why not",
                )

    def test_included_and_omitted_do_not_overlap(self):
        overlap = set(pipeline.RETRY_INCLUDED) & set(pipeline.RETRY_OMISSIONS)
        self.assertEqual(overlap, set())

    def test_omissions_are_classified_correct_or_defect(self):
        """Each omission states which it is, so the seven defects cannot be
        mistaken for design."""

        for name, reason in pipeline.RETRY_OMISSIONS.items():
            with self.subTest(step=name):
                self.assertTrue(
                    reason.startswith("CORRECT") or reason.startswith("DEFECT"),
                    f"{name}: omission reason must begin CORRECT or DEFECT",
                )

    def test_the_known_defect_count_is_pinned(self):
        """Seven per-node steps are skipped on retry, so a retried node gets a
        different pipeline than one that passed first time. Pinned so fixing
        them is a deliberate, measured change rather than a drift."""

        defects = [n for n, r in pipeline.RETRY_OMISSIONS.items() if r.startswith("DEFECT")]
        self.assertEqual(len(defects), 7, sorted(defects))


class PostClassifyBehaviorTests(unittest.TestCase):
    def test_returns_nodes_unchanged_when_nothing_applies(self):
        raw = [{"raw": "Relocate turtle", "type_hint": "task"}]
        nodes = [
            {
                "node_type": "cogs/daily",
                "title": "Relocate turtle",
                "item_text": "Relocate turtle",
                "date": "2026-06-12",
                "confidence": "high",
            }
        ]
        out, steps = capture_harness.apply_live_post_classify(raw, nodes, "2026-06-12")
        self.assertEqual([n["date"] for n in out], ["2026-06-12"])
        self.assertNotIn("apply_runtime_date_context", steps)

    def test_reports_the_step_that_changed_something(self):
        """Attribution: a score movement must name the step responsible."""

        raw = [{"raw": "dentist thing thursday", "type_hint": "appointment"}]
        nodes = [
            {
                "node_type": "cogs/daily",
                "title": "DENTIST",
                "item_text": "DENTIST",
                "date": "2026-06-11",
                "confidence": "high",
            }
        ]
        out, steps = capture_harness.apply_live_post_classify(raw, nodes, "2026-06-12")
        self.assertEqual(out[0]["date"], "2026-06-18")
        self.assertIn("apply_runtime_date_context", steps)

    def test_does_not_mutate_the_input_list(self):
        raw = [{"raw": "dentist thing thursday", "type_hint": "appointment"}]
        nodes = [
            {
                "node_type": "cogs/daily",
                "title": "DENTIST",
                "item_text": "DENTIST",
                "date": "2026-06-11",
                "confidence": "high",
            }
        ]
        capture_harness.apply_live_post_classify(raw, nodes, "2026-06-12")
        self.assertEqual(nodes[0]["date"], "2026-06-11")


class ConfigTests(unittest.TestCase):
    def test_full_pipeline_is_the_default(self):
        """The product's own path is the default; raw classify is the opt-in."""

        self.assertTrue(capture_harness.HarnessConfig(model="m").full_pipeline)

    def test_raw_classify_is_labelled(self):
        config = capture_harness.HarnessConfig(model="m", full_pipeline=False)
        self.assertIn("rawclassify", config.label)
        self.assertNotIn("rawclassify", capture_harness.HarnessConfig(model="m").label)


if __name__ == "__main__":
    unittest.main()


class CallTimingSerializationTests(unittest.TestCase):
    """Stage 142 slice 0a - the cost half of the architecture experiment.

    `CallStats` has captured prefill, load, and total durations since Stage 138,
    but only `eval_seconds` reached the JSON report, so every cost claim in
    Stages 138-141 rested on wall-clock subtraction.
    """

    def _report(self, **stat_kwargs):
        stat = capture_harness.CallStats(
            call="extract", model="m", prompt_chars=100, **stat_kwargs
        )
        result = capture_harness.FixtureResult(
            config_label="m",
            fixture_id="f",
            category="c",
            raw_nodes=[],
            classified_nodes=[],
            elapsed_seconds=1.0,
            matched=0,
            expected_count=0,
            actual_count=0,
            call_stats=(stat,),
        )
        payload = capture_harness.results_to_dict([result])
        return payload["results"][0]["calls"][0]

    def test_every_duration_is_serialized(self):
        call = self._report(
            prompt_tokens=100,
            completion_tokens=10,
            eval_seconds=0.5,
            prompt_eval_seconds=0.25,
            load_seconds=1.5,
            total_seconds=2.25,
        )
        self.assertEqual(call["eval_seconds"], 0.5)
        self.assertEqual(call["prompt_eval_seconds"], 0.25)
        self.assertEqual(call["load_seconds"], 1.5)
        self.assertEqual(call["total_seconds"], 2.25)

    def test_zero_is_a_measurement_not_a_gap(self):
        """A warm model reports 0.0 load. That must not serialize as null -
        'no load time' and 'not measured' are different claims."""

        call = self._report(load_seconds=0.0, eval_seconds=0.0)
        self.assertEqual(call["load_seconds"], 0.0)
        self.assertEqual(call["eval_seconds"], 0.0)
        self.assertIsNotNone(call["load_seconds"])

    def test_absent_stays_absent(self):
        """A client that omits durations must not report fabricated zeros."""

        call = self._report(prompt_tokens=100)
        for key in ("eval_seconds", "prompt_eval_seconds", "load_seconds", "total_seconds"):
            self.assertIsNone(call[key], key)

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

from specialists.rosie import loop
from specialists.uniblab import capture_harness


class PostClassifyDriftTests(unittest.TestCase):
    """Guards the harness against the live pipeline moving underneath it."""

    def _live_sequence(self) -> list[str]:
        """The post-classify calls `loop.py` makes, in source order.

        Read from the source of the capture function rather than from an
        import list, so a step that is imported but never called - or called
        in a different order - is still caught.
        """

        source = inspect.getsource(loop)
        body = source.split("classified = classify_nodes(", 1)[1]
        # Stop before the retry block, which repeats the same chain.
        body = body.split("valid_nodes, invalid_triples = validate_output", 1)[0]
        found = []
        pattern = r"^\s+(?:classified.*?=\s*)?((?:apply|route|ensure|log|write)_[a-z_]+)\("
        for name in re.findall(pattern, body, re.M):
            if name not in found:
                found.append(name)
        return found

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

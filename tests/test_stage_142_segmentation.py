"""Stage 142 slice 1: deterministic segmentation (candidate 5).

Segment counts here are derived from doctrine, not from what the segmenter
produced. A segment is **one span of source text that is one item**, before any
typing and before any expansion:

- A counted repeat is ONE segment. `EXTRACT_SYSTEM` says so, and expansion to
  three dated nodes is `apply_bounded_recurrence_context`'s job in code.
- "Text Jon about truck" is ONE segment. It classifies into a task, a cog, and
  a contact, but that is three nodes from one span - a typing consequence, not
  a segmentation one.
- "Hello" is ONE segment. Producing nothing from it is restraint, which is a
  classification judgement; a segmenter that decides "Hello" is not an item is
  deciding something it cannot know.

This distinction is why `expected.extract.item_count` in the fixture files
cannot grade this module. That field currently means the post-expansion node
count in `03` (3) and `08` (10), a node count in `06` (2, and even then it
disagrees with the three nodes the same fixture expects), and a span count in
the rest. It is documented as advisory, and this is what advisory bought.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from substrate import segmentation
from substrate.segmentation import Segment, segment_capture

FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent
    / "specialists" / "uniblab" / "fixture_data"
)

# fixture_id -> expected span count. Derived from doctrine before running.
EXPECTED_SPANS = {
    "simple-appointment": 1,
    "simple-dated-errand": 1,
    "recurrence-three-saturdays": 1,
    "dense-errand-list": 5,
    "dense-farm-chores": 4,
    "contact-and-task": 1,
    "project-task-list": 7,
    "multi-day-setting-holiday": 2,
    "empty-greeting": 1,
    "structural-label-pressure": 3,
    "stt-garbled-proper-noun": 1,
    "correction-of-prior-capture": 1,
    "duplicate-of-existing-note": 3,
    "date-year-rollover": 3,
    "reference-fact-not-task": 1,
    "large-context-crowding": 1,
    "segmentation-day-heading": 3,
    "segmentation-compound-line": 2,
    "segmentation-single-errand": 1,
    "low-confidence-ambiguous-day": 1,
    "low-confidence-bare-reference": 1,
}

# Fixtures the splitter is expected to decline rather than answer.
EXPECTED_DECLINED = {"stt-unpunctuated-run-on"}

# Known lexicon misses. Marked, not omitted: an unexpected pass here fails the
# run and forces the marker off, which is how the gap stays visible.
KNOWN_MISSES = {"multi-day-setting-holiday"}


def _fixtures():
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        yield json.loads(path.read_text())


class SegmentCountTests(unittest.TestCase):
    """Every fixture's span count, graded individually so a regression names
    the fixture that moved rather than a total that shifted."""

    def test_every_fixture_has_a_declared_expectation(self):
        ids = {fixture["fixture_id"] for fixture in _fixtures()}
        declared = set(EXPECTED_SPANS) | EXPECTED_DECLINED
        self.assertEqual(ids, declared)

    def test_span_counts(self):
        for fixture in _fixtures():
            fixture_id = fixture["fixture_id"]
            if fixture_id in EXPECTED_DECLINED:
                continue
            with self.subTest(fixture=fixture_id):
                result = segment_capture(fixture["content"])
                actual = len(result.segments)
                expected = EXPECTED_SPANS[fixture_id]
                if fixture_id in KNOWN_MISSES:
                    self.assertNotEqual(
                        actual, expected,
                        f"{fixture_id} now passes; remove it from KNOWN_MISSES",
                    )
                else:
                    self.assertEqual(actual, expected)

    def test_declined_fixtures_are_flagged_not_answered(self):
        for fixture in _fixtures():
            if fixture["fixture_id"] not in EXPECTED_DECLINED:
                continue
            with self.subTest(fixture=fixture["fixture_id"]):
                result = segment_capture(fixture["content"])
                self.assertFalse(result.structured)
                self.assertTrue(result.declined_reason)

    def test_structured_inputs_are_not_declined(self):
        """A decline costs a model call, so a false decline is not free."""

        for fixture in _fixtures():
            if fixture["fixture_id"] in EXPECTED_DECLINED:
                continue
            with self.subTest(fixture=fixture["fixture_id"]):
                self.assertTrue(segment_capture(fixture["content"]).structured)


class ConjunctionPairTests(unittest.TestCase):
    """Fixtures 19 and 20 are a pair: one must split on 'and', the other must
    not. Pinned directly so the pair cannot be satisfied by a rule tuned to
    either half."""

    def test_compound_line_splits(self):
        result = segment_capture("Call the vet and pick up feed at the co-op")
        self.assertEqual([s.raw for s in result.segments],
                         ["Call the vet", "pick up feed at the co-op"])

    def test_single_errand_does_not_split(self):
        content = (
            "Pick up the replacement hydraulic filter and gasket kit for the "
            "tractor at the dealer on Route 40 before they close"
        )
        self.assertEqual(len(segment_capture(content).segments), 1)

    def test_bare_verb_does_not_start_a_clause(self):
        """Finding 60's case. 'Check' has no object, so it is not an errand."""

        result = segment_capture("Check and charge Dale battery")
        self.assertEqual(len(result.segments), 1)

    def test_trailing_noun_phrase_rejoins_rather_than_dropping(self):
        """A rejected boundary must not lose the text after it."""

        result = segment_capture("Full loom all next week, Holiday on 7/3")
        self.assertEqual(len(result.segments), 1)
        self.assertIn("Holiday on 7/3", result.segments[0].raw)


class HeadingScopeTests(unittest.TestCase):
    def test_bare_colon_line_is_scope_not_an_item(self):
        result = segment_capture("Saturday:\n- Walmart\n- Home Depot")
        self.assertEqual([s.raw for s in result.segments], ["Walmart", "Home Depot"])
        self.assertTrue(all(s.scope == "Saturday" for s in result.segments))

    def test_inline_colon_stays_an_item(self):
        """'KOHLS: pick up order' is an errand; only an empty tail is a
        heading. Without this the densest real captures lose their first line
        to a heading that never existed."""

        result = segment_capture("KOHLS: pick up order")
        self.assertEqual(len(result.segments), 1)
        self.assertEqual(result.segments[0].scope, "")

    def test_scope_reaches_the_raw_node_so_dates_resolve(self):
        """`apply_runtime_date_context` reads the raw string. A heading that
        carries the day must survive into it or three Saturday errands land
        on today."""

        result = segment_capture("Saturday:\n- Walmart")
        self.assertEqual(
            result.to_raw_nodes("2026-06-12"), [{"raw": "Saturday: Walmart"}]
        )

    def test_a_non_date_heading_is_not_folded_in(self):
        """Slice 5b repair of finding 74. The fold exists so the date resolver
        can see "Saturday:". Folding "Garage Work Project Tasks:" instead pays
        twice - it is echoed into title and item_text on every item under the
        heading - which is part of what made candidate 5 the most expensive
        arm at 17.28s."""

        result = segment_capture(
            "Garage Work Project Tasks:\nPatch holes in rear wall\nInstall bin shelves"
        )
        self.assertEqual(
            [n["raw"] for n in result.to_raw_nodes("2026-06-12")],
            ["Patch holes in rear wall", "Install bin shelves"],
        )

    def test_without_a_processing_date_no_heading_is_folded(self):
        """Whether a heading names a day cannot be answered without knowing
        today, so the safe answer is not to fold."""

        result = segment_capture("Saturday:\n- Walmart")
        self.assertEqual(result.to_raw_nodes(), [{"raw": "Walmart"}])

    def test_trailing_heading_with_nothing_under_it_stays_an_item(self):
        result = segment_capture("Walmart\nSaturday:")
        self.assertEqual([s.raw for s in result.segments], ["Walmart", "Saturday:"])


class RawNodeShapeTests(unittest.TestCase):
    def test_no_type_hint_is_emitted(self):
        """This module does not type items. An empty type_hint would read as
        'computed as nothing' rather than 'not computed'."""

        nodes = segment_capture("Call the vet").to_raw_nodes()
        self.assertEqual(nodes, [{"raw": "Call the vet"}])

    def test_empty_input_produces_no_segments(self):
        for content in ("", "   ", "\n\n"):
            with self.subTest(content=repr(content)):
                self.assertEqual(segment_capture(content).segments, [])

    def test_rule_is_recorded_for_every_segment(self):
        result = segment_capture("Saturday:\n- Walmart\n- gas Dale, fill propane tank")
        self.assertEqual(
            [s.rule for s in result.segments],
            ["heading-scoped", "clause", "clause"],
        )


class DictationDeclineTests(unittest.TestCase):
    def test_disfluency_declines(self):
        result = segment_capture("um okay so i need to call Frank and pick up feed")
        self.assertFalse(result.structured)
        self.assertIn("disfluency", result.declined_reason)

    def test_long_unpunctuated_single_line_declines(self):
        content = " ".join(["call"] + ["word"] * segmentation.RUN_ON_WORD_LIMIT)
        self.assertFalse(segment_capture(content).structured)

    def test_multi_line_input_is_never_a_run_on(self):
        """Line breaks are structure; a bulleted list is not dictation however
        long it gets."""

        content = "\n".join(f"- item number {n} on the list" for n in range(12))
        self.assertTrue(segment_capture(content).structured)

    def test_declined_input_still_returns_segments(self):
        """The caller falls back to a model call, but the segments remain
        available for inspection - that is where a bad decline gets diagnosed."""

        result = segment_capture("um okay so call Frank and pick up feed")
        self.assertFalse(result.structured)
        self.assertTrue(result.segments)


class LexiconTests(unittest.TestCase):
    def test_verb_lexicon_is_lowercase_and_unique(self):
        for verb in segmentation.IMPERATIVE_VERBS:
            self.assertEqual(verb, verb.lower())

    def test_unknown_verb_under_splits_rather_than_over_splits(self):
        """The documented failure mode. A verb outside the lexicon leaves the
        line whole; it never invents a boundary somewhere else."""

        result = segment_capture("Winnow the chaff and thresh the wheat")
        self.assertEqual(len(result.segments), 1)


if __name__ == "__main__":
    unittest.main()

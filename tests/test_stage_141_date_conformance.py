"""Stage 141 slice 2: date conformance suite.

Deterministic, no model call. Establishes what `time_context.py` gets right
*before* anything is changed, so the slice 2b substrate move and the slice 3
resolver decision both have a fixed reference.

Known defects are marked `@unittest.expectedFailure` with the finding they
came from, rather than being omitted or asserted-as-correct. That keeps the
suite green while the defects stay visible, and when one is fixed the test
reports an unexpected success, which fails the run and forces the marker off.
A defect that is silently absent from a conformance suite is a defect that
comes back.

Anchors: 2026-06-12 is a Friday. 2026-12-29 is a Tuesday, chosen so its
answers cross both a month and a year boundary.
"""
from __future__ import annotations

import unittest

from substrate.time_context import (
    apply_runtime_date_context,
    resolve_relative_cogs_horizon,
)


FRIDAY = "2026-06-12"
YEAR_END = "2026-12-29"


def _daily(title, date, item_text=None):
    return {
        "node_type": "cogs/daily",
        "title": title,
        "item_text": item_text or title,
        "date": date,
        "confidence": "high",
    }


class PhraseResolutionTests(unittest.TestCase):
    """What the resolver gets right today. These are regression locks."""

    def assert_resolves(self, phrase, expected, anchor=FRIDAY):
        result = resolve_relative_cogs_horizon(phrase, anchor)
        self.assertIsNotNone(result, f"{phrase!r} resolved to nothing")
        self.assertEqual(result[0], expected, f"{phrase!r} from {anchor}")

    def test_today_and_tomorrow(self):
        self.assert_resolves("today", "2026-06-12")
        self.assert_resolves("tomorrow", "2026-06-13")

    def test_forward_weekday_from_friday(self):
        """The next occurrence, not this week's already-past one."""

        self.assert_resolves("monday", "2026-06-15")
        self.assert_resolves("thursday", "2026-06-18")

    def test_next_prefix_matches_bare_weekday(self):
        self.assert_resolves("next monday", "2026-06-15")
        self.assert_resolves("next friday", "2026-06-19")

    def test_relative_offset(self):
        self.assert_resolves("in two days", "2026-06-14")

    def test_month_rollover(self):
        self.assert_resolves("next month", "2026-07-01")

    def test_year_rollover(self):
        """Stage 139 slice 5a produced 2020 dates from a 2026 anchor; the
        deterministic path crosses the boundary correctly."""

        self.assert_resolves("next tuesday", "2027-01-05", anchor=YEAR_END)
        self.assert_resolves("tomorrow", "2026-12-30", anchor=YEAR_END)

    def test_weekend_days_resolve(self):
        """Saturdays are legitimate dates. Stage 139 slice 5a banned them in
        the prompt and took recall from 1.000 to 0.886."""

        self.assert_resolves("saturday", "2026-06-13")
        self.assert_resolves("sunday", "2026-06-14")


class KnownGapsTests(unittest.TestCase):
    """Phrases the resolver does not handle. Documented, not asserted away."""

    def test_day_of_month_is_unsupported(self):
        """"the 3rd" returns nothing, so the model's answer stands unchecked.

        This is why `date-year-rollover` depends on model arithmetic for its
        propane-bill item.
        """

        self.assertIsNone(resolve_relative_cogs_horizon("the 3rd", FRIDAY))
        self.assertIsNone(resolve_relative_cogs_horizon("on the 3rd", YEAR_END))

    def test_backward_references_are_unsupported(self):
        """Capture rarely needs "yesterday", but corrections do - and
        correction intent is Stage 141 deliverable D10."""

        self.assertIsNone(resolve_relative_cogs_horizon("yesterday", FRIDAY))

    def test_this_and_next_weekday_are_indistinguishable(self):
        """Pins the current wrong behavior. Delete when NextWeekdayTests pass."""

        this_sat = resolve_relative_cogs_horizon("this saturday", FRIDAY)
        next_sat = resolve_relative_cogs_horizon("next saturday", FRIDAY)
        self.assertEqual(this_sat[0], next_sat[0])


class NextWeekdayTests(unittest.TestCase):
    """Doctrine settled by the product owner 2026-08-28: "next Saturday" means
    the **second** Saturday after today, not the first.

    So from Friday 2026-06-12: "this saturday" is 06-13, "next saturday" is
    06-20. The resolver currently returns 06-13 for both, which silently books
    the user a week early - the same failure shape as finding 43.

    Scope note: this governs the singular phrase. "next 3 Saturdays" is a
    counted recurrence handled elsewhere, and Stage 132D fixed its first
    occurrence at the next Saturday after the source timestamp. Changing the
    singular must not move the counted form.
    """

    @unittest.expectedFailure
    def test_next_weekday_is_the_second_occurrence(self):
        result = resolve_relative_cogs_horizon("next saturday", FRIDAY)
        self.assertEqual(result[0], "2026-06-20")

    @unittest.expectedFailure
    def test_next_weekday_across_year_boundary(self):
        """From Tuesday 2026-12-29: this friday 2027-01-01, next friday
        2027-01-08."""

        result = resolve_relative_cogs_horizon("next friday", YEAR_END)
        self.assertEqual(result[0], "2027-01-08")

    def test_bare_weekday_stays_the_first_occurrence(self):
        """"saturday" alone is unqualified and keeps meaning the next one."""

        self.assertEqual(
            resolve_relative_cogs_horizon("saturday", FRIDAY)[0], "2026-06-13"
        )


class WeekOffsetTests(unittest.TestCase):
    def test_a_week_from_friday(self):
        """Stage 139 finding 43. Matches the bare weekday and ignores the
        offset, turning a one-day model miss into a seven-day error."""

        result = resolve_relative_cogs_horizon("a week from Friday", FRIDAY)
        self.assertEqual(result[0], "2026-06-19")

    def test_a_week_from_friday_across_year_boundary(self):
        result = resolve_relative_cogs_horizon("a week from Friday", YEAR_END)
        self.assertEqual(result[0], "2027-01-08")

    def test_multi_week_offset(self):
        self.assertEqual(
            resolve_relative_cogs_horizon("two weeks from Monday", FRIDAY)[0],
            "2026-06-29",
        )

    def test_offset_survives_a_trailing_time(self):
        """Real captures carry a time; the offset must still win over the
        bare weekday that follows it."""

        self.assertEqual(
            resolve_relative_cogs_horizon("a week from friday at 3pm", FRIDAY)[0],
            "2026-06-19",
        )


class PositionalAlignmentTests(unittest.TestCase):
    """Stage 139 finding 42 - the highest-severity defect carried into 141."""

    def _misaligned(self):
        """One raw item becomes two nodes, as the named-person rule requires.

        Every later classified index is then offset from its raw item.
        """

        raw = [
            {"raw": "call Frank Ott about the tractor loan", "type_hint": "task"},
            {"raw": "pick up feed at the co-op", "type_hint": "task"},
            {"raw": "dentist thing thursday at 8:30am", "type_hint": "appointment"},
        ]
        classified = [
            {
                "node_type": "sprockets/task",
                "title": "Call Frank Ott",
                "item_text": "Call Frank Ott",
                "date": FRIDAY,
                "confidence": "high",
            },
            _daily("Call Frank Ott", FRIDAY),
            _daily("Pick up feed at the co-op", FRIDAY),
            _daily("8:30a DENTIST", "2026-06-11"),
        ]
        return raw, classified

    def test_aligned_input_resolves_correctly(self):
        """Control: with one node per raw item, the resolver is right."""

        raw = [{"raw": "dentist thing thursday at 8:30am", "type_hint": "appointment"}]
        out, decisions = apply_runtime_date_context(
            raw, [_daily("8:30a DENTIST", "2026-06-11")], FRIDAY
        )
        self.assertEqual(out[0]["date"], "2026-06-18")
        self.assertEqual(len(decisions), 1)

    @unittest.expectedFailure
    def test_does_not_move_an_unrelated_node(self):
        """The feed errand has no date phrase and must not be moved."""

        raw, classified = self._misaligned()
        out, _ = apply_runtime_date_context(raw, classified, FRIDAY)
        feed = next(n for n in out if "feed" in n["title"].lower())
        self.assertEqual(feed["date"], FRIDAY)

    @unittest.expectedFailure
    def test_resolves_the_node_that_owns_the_phrase(self):
        """"thursday" belongs to the dentist item, wherever it sits."""

        raw, classified = self._misaligned()
        out, _ = apply_runtime_date_context(raw, classified, FRIDAY)
        dentist = next(n for n in out if "DENTIST" in n["title"])
        self.assertEqual(dentist["date"], "2026-06-18")

    def test_misalignment_is_present_today(self):
        """Pins the current wrong behavior so the fix is visibly a change.

        Delete this test when the two expectedFailure cases above go green.
        """

        raw, classified = self._misaligned()
        out, decisions = apply_runtime_date_context(raw, classified, FRIDAY)
        feed = next(n for n in out if "feed" in n["title"].lower())
        dentist = next(n for n in out if "DENTIST" in n["title"])
        self.assertEqual(feed["date"], "2026-06-18", "feed wrongly moved")
        self.assertEqual(dentist["date"], "2026-06-11", "dentist left unfixed")
        self.assertEqual([d.index for d in decisions], [2])


class EmbeddedDateTests(unittest.TestCase):
    """Stage 141 finding 44 - extract overwrites the phrase the layer needs."""

    def test_layer_fires_when_the_phrase_survives(self):
        raw = [{"raw": "Yoga is tomorrow at 5:30pm", "type_hint": "appointment"}]
        out, decisions = apply_runtime_date_context(
            raw, [_daily("YOGA 5:30p", "2026-06-09")], FRIDAY
        )
        self.assertEqual(out[0]["date"], "2026-06-13")
        self.assertEqual(decisions[0].phrase, "tomorrow")

    def test_layer_is_inert_when_extract_embedded_a_date(self):
        """Same wrong date, same anchor, no phrase left to match.

        This is the mechanism behind Stage 138 findings 1 and 12, and the
        reason `EXTRACT_SYSTEM`'s embed instruction is slice 3's first target.
        """

        raw = [{"raw": "Yoga on 2026-06-09", "type_hint": "appointment"}]
        out, decisions = apply_runtime_date_context(
            raw, [_daily("YOGA 5:30p", "2026-06-09")], FRIDAY
        )
        self.assertEqual(out[0]["date"], "2026-06-09")
        self.assertEqual(decisions, [])


class NonDailyNodeTests(unittest.TestCase):
    def test_only_cogs_daily_is_resolved(self):
        """sprockets/task dates are left alone, by design."""

        raw = [{"raw": "call Frank tomorrow", "type_hint": "task"}]
        task = {
            "node_type": "sprockets/task",
            "title": "Call Frank",
            "item_text": "Call Frank",
            "date": FRIDAY,
            "confidence": "high",
        }
        out, decisions = apply_runtime_date_context(raw, [task], FRIDAY)
        self.assertEqual(out[0]["date"], FRIDAY)
        self.assertEqual(decisions, [])

    def test_input_is_not_mutated(self):
        raw = [{"raw": "yoga tomorrow", "type_hint": "appointment"}]
        node = _daily("YOGA", "2026-06-09")
        apply_runtime_date_context(raw, [node], FRIDAY)
        self.assertEqual(node["date"], "2026-06-09")


if __name__ == "__main__":
    unittest.main()

"""Stage 142 slice 5a: multi-day setting expansion, owned by substrate.

Finding 77: both prompts instruct the model to expand "all next week" into one
item per workday, the model does it badly - a contiguous 19-day run including
weekends on the one fixture that grades it - and **no code did it at all**.
The prompt rule cannot be removed until this exists, or the behaviour vanishes,
which is what `preserve-extract` demonstrated by emitting three nodes where ten
belonged.

The step is deliberately **guarded and therefore mostly inert today**: the
prompts still ask the model to expand, so firing as well would double the
nodes. It becomes load-bearing when slice 6 removes the instruction. Landing it
live-but-guarded is what keeps it from being preview code nothing imports.
"""
from __future__ import annotations

import unittest

from substrate.time_context import (
    apply_multi_day_setting_context,
    multi_day_spans,
)

# Friday. "next week" is 06-15..06-19; "the following week" is 06-22..06-26.
NOW = "2026-06-12"


def _raw(text, type_hint="setting"):
    return [{"raw": text, "type_hint": type_hint}]


def _node(title="FULL LOOM", date=NOW, **extra):
    return {
        "node_type": "cogs/daily", "title": title, "item_text": title,
        "date": date, "confidence": "high", **extra,
    }


class SpanDetectionTests(unittest.TestCase):
    def test_all_next_week_is_five_workdays(self):
        spans = multi_day_spans("Full loom all next week", NOW)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].dates,
                         ("2026-06-15", "2026-06-16", "2026-06-17",
                          "2026-06-18", "2026-06-19"))

    def test_weekends_are_excluded(self):
        """A WFH span covering Saturday is noise the user has to delete."""

        dates = multi_day_spans("WFH all next week", NOW)[0].dates
        self.assertNotIn("2026-06-20", dates)
        self.assertNotIn("2026-06-21", dates)

    def test_until_weekday_truncates_the_span(self):
        spans = multi_day_spans("WFH next week until Wednesday", NOW)
        self.assertEqual(spans[0].dates[-1], "2026-06-17")

    def test_two_spans_in_one_capture(self):
        """The driving fixture. Each span is independent - different lengths,
        neither constraining the other."""

        spans = multi_day_spans(
            "Full loom all next week and the following week until Thursday", NOW
        )
        self.assertEqual(len(spans), 2)
        self.assertEqual(len(spans[0].dates), 5)
        self.assertEqual(spans[1].dates,
                         ("2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25"))

    def test_a_later_until_does_not_truncate_an_earlier_span(self):
        """"until Thursday" belongs to the second span only. Letting it reach
        backwards would silently shorten the first week to four days."""

        spans = multi_day_spans(
            "Full loom all next week and the following week until Thursday", NOW
        )
        self.assertEqual(spans[0].dates[-1], "2026-06-19")

    def test_no_week_phrase_yields_nothing(self):
        self.assertEqual(multi_day_spans("Call the vet Tuesday", NOW), [])

    def test_unparseable_processing_date_is_not_a_crash(self):
        self.assertEqual(multi_day_spans("WFH all next week", "not-a-date"), [])


class ExpansionTests(unittest.TestCase):
    def test_expands_a_setting_the_model_left_whole(self):
        out, decisions = apply_multi_day_setting_context(
            _raw("Full loom all next week"), [_node()], NOW
        )
        self.assertEqual(len(out), 5)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(sorted(n["date"] for n in out)[0], "2026-06-15")

    def test_the_original_node_is_reused_not_duplicated(self):
        """The first date reuses the node so the model's title, item_text and
        confidence survive; an early version cloned it and produced a
        duplicate of the first day."""

        out, _ = apply_multi_day_setting_context(
            _raw("Full loom all next week"), [_node()], NOW
        )
        self.assertEqual(len(out), len({n["date"] for n in out}))

    def test_both_spans_expand(self):
        out, decisions = apply_multi_day_setting_context(
            _raw("Full loom all next week and the following week until Thursday"),
            [_node()], NOW,
        )
        self.assertEqual(len(out), 9)
        self.assertEqual(len(decisions), 2)


class GuardTests(unittest.TestCase):
    """Every one of these is a way the step could make things worse."""

    def test_does_not_double_expand_what_the_model_expanded(self):
        """Both prompts still instruct expansion. Firing as well is how a
        fixture expecting 10 nodes gets 20."""

        already = [_node(date=d) for d in
                   ("2026-06-15", "2026-06-16", "2026-06-17",
                    "2026-06-18", "2026-06-19")]
        out, decisions = apply_multi_day_setting_context(
            _raw("Full loom all next week"), already, NOW
        )
        self.assertEqual(len(out), 5)
        self.assertEqual(decisions, [])

    def test_an_action_next_week_is_not_a_span(self):
        """"Call Tom next week" is one action to do sometime that week, and
        belongs in the weekly carry. Expanding it would replace one carry
        entry with five daily copies - caught by Stage 106's test, not by
        this file, which is why the guard exists."""

        out, decisions = apply_multi_day_setting_context(
            _raw("Call Tom next week", type_hint="task"),
            [_node(title="Call Tom")], NOW,
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(decisions, [])

    def test_a_spanning_item_the_model_typed_as_a_task_still_expands(self):
        """Finding 86 / D108. Under preserve-only extract the model emitted
        "Full loom all next week..." as `type_hint: task` - "Full loom" is a
        garbled company name, not a WFH/ONSITE/HOLIDAY keyword - and the
        `type_hint == "setting"` guard skipped it, producing 2 nodes where 10
        were expected. The span is a property of the phrase, not the type."""

        out, decisions = apply_multi_day_setting_context(
            _raw(
                "Full loom all next week and the following week until Thursday",
                type_hint="task",
            ),
            [_node(title="Full loom")], NOW,
        )

        self.assertEqual(len(out), 9)
        self.assertEqual([d.occurrence_count for d in decisions], [5, 4])

    def test_a_week_horizon_action_is_left_alone(self):
        """`apply_runtime_date_context` may already have decided this is a
        week-horizon carry item, and for an *action* that decision stands.

        Finding 82's real case: expanding "Call Tom next week" would replace
        one weekly carry entry with five daily copies.
        """

        out, _ = apply_multi_day_setting_context(
            _raw("Call Tom next week", type_hint="task"),
            [_node(title="Call Tom", horizon="week")], NOW,
        )
        self.assertEqual(len(out), 1)

    def test_a_week_horizon_span_expands_anyway(self):
        """Finding 95, and this test previously asserted the opposite.

        The old version used "Full loom all next week" - a *spanning* phrase -
        to demonstrate a rule about non-spanning actions, so it conflated the
        two cases and locked in the defect. Stage 145 exposed it:
        `multi-day-setting-holiday` expanded only its second span, because
        "until Thursday" made the resolver call that one a day horizon while
        "all next week" got a week horizon and was skipped.

        The two signals answer different questions - the horizon says *when to
        act*, the span says *how many days it covers* - so a span overrides.
        """

        out, decisions = apply_multi_day_setting_context(
            _raw("Full loom all next week"), [_node(horizon="week")], NOW
        )

        self.assertEqual(len(out), 5)
        self.assertEqual([d.occurrence_count for d in decisions], [5])

    def test_non_cogs_nodes_are_untouched(self):
        task = {"node_type": "sprockets/task", "title": "Full loom",
                "item_text": "Full loom", "date": NOW, "confidence": "high"}
        out, _ = apply_multi_day_setting_context(
            _raw("Full loom all next week"), [task], NOW
        )
        self.assertEqual(len(out), 1)

    def test_an_unmatchable_node_is_skipped(self):
        """No raw match means no raw text, and the step applies nothing rather
        than guessing - the `raw_text_for` contract."""

        out, _ = apply_multi_day_setting_context(
            _raw("Full loom all next week"),
            [_node(title="Completely unrelated errand")], NOW,
        )
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()

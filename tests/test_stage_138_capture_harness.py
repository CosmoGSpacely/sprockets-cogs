import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import specialists.uniblab.capture_harness as capture_harness
from specialists.rosie.extractor_classifier import (
    DEFAULT_CONTEXT_MAX_CHARS,
    CallStats,
    ExtractClassifier,
    ExtractClassifierConfig,
    truncate_context,
)
from specialists.uniblab.capture_fixtures import (
    CaptureFixture,
    ExpectedNode,
    load_capture_fixtures,
)


def _fixture(**overrides):
    base = dict(
        fixture_id="f1",
        content="Yoga is tomorrow at 5:30pm",
        now=datetime(2026, 6, 12, 9, 0),
        category="simple",
        expected_nodes=(
            ExpectedNode(
                node_type="cogs/daily",
                must_include=("yoga",),
                date="2026-06-13",
            ),
        ),
    )
    base.update(overrides)
    return CaptureFixture(**base)


class ScriptedClassifier:
    """Stands in for the model; returns whatever the test scripted."""

    def __init__(self, nodes, raw=None):
        self._nodes = nodes
        self._raw = raw if raw is not None else [{"raw": "x", "type_hint": "task"}]
        self.seen_use_examples = None

    def extract_nodes(self, content, now=None):
        return list(self._raw)

    def classify_nodes(self, raw_nodes, context, use_examples=True, now=None):
        self.seen_use_examples = use_examples
        return [dict(node) for node in self._nodes]


class FixtureSetTests(unittest.TestCase):
    def test_shipped_fixture_set_loads_and_is_well_formed(self):
        fixtures = load_capture_fixtures()

        self.assertGreaterEqual(len(fixtures), 10)
        ids = [item.fixture_id for item in fixtures]
        self.assertEqual(len(ids), len(set(ids)), "fixture ids must be unique")
        for item in fixtures:
            self.assertTrue(item.description, f"{item.fixture_id} needs a description")
            self.assertTrue(item.notes, f"{item.fixture_id} needs notes")
            self.assertIsInstance(item.now, datetime)

    def test_fixture_set_covers_required_categories(self):
        categories = {item.category for item in load_capture_fixtures()}

        for required in ("simple", "dense", "multi-day", "edge", "hard"):
            self.assertIn(required, categories)

    def test_category_and_id_filters(self):
        only = load_capture_fixtures(only=("empty-greeting",))
        self.assertEqual([item.fixture_id for item in only], ["empty-greeting"])

        dense = load_capture_fixtures(categories=("dense",))
        self.assertTrue(dense)
        self.assertTrue(all(item.category == "dense" for item in dense))

    def test_empty_greeting_expects_no_nodes(self):
        fixture = load_capture_fixtures(only=("empty-greeting",))[0]

        self.assertEqual(fixture.expected_nodes, ())
        self.assertEqual(fixture.expected_item_count, 0)


class GradingTests(unittest.TestCase):
    def test_exact_match_passes(self):
        result = capture_harness.run_fixture(
            capture_harness.HarnessConfig(model="m"),
            _fixture(),
            classifier_factory=lambda config: ScriptedClassifier(
                [
                    {
                        "node_type": "cogs/daily",
                        "title": "YOGA 5:30p",
                        "item_text": "YOGA 5:30p",
                        "date": "2026-06-13",
                        "confidence": "high",
                    }
                ]
            ),
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.matched, 1)
        self.assertEqual(result.recall, 1.0)
        self.assertEqual(result.precision, 1.0)

    def test_wrong_date_is_not_a_match(self):
        result = capture_harness.run_fixture(
            capture_harness.HarnessConfig(model="m"),
            _fixture(),
            classifier_factory=lambda config: ScriptedClassifier(
                [
                    {
                        "node_type": "cogs/daily",
                        "title": "YOGA 5:30p",
                        "item_text": "YOGA 5:30p",
                        "date": "2026-06-12",
                        "confidence": "high",
                    }
                ]
            ),
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.matched, 0)
        self.assertTrue(result.missing)
        self.assertTrue(result.extra)

    def test_duplicate_output_cannot_inflate_score(self):
        node = {
            "node_type": "cogs/daily",
            "title": "YOGA 5:30p",
            "item_text": "YOGA 5:30p",
            "date": "2026-06-13",
            "confidence": "high",
        }

        result = capture_harness.run_fixture(
            capture_harness.HarnessConfig(model="m"),
            _fixture(),
            classifier_factory=lambda config: ScriptedClassifier([node, dict(node)]),
        )

        self.assertEqual(result.matched, 1)
        self.assertEqual(result.actual_count, 2)
        self.assertEqual(result.precision, 0.5)
        self.assertFalse(result.passed)

    def test_fabricated_node_on_empty_fixture_fails(self):
        empty = _fixture(fixture_id="empty", content="Hello", expected_nodes=())

        result = capture_harness.run_fixture(
            capture_harness.HarnessConfig(model="m"),
            empty,
            classifier_factory=lambda config: ScriptedClassifier(
                [
                    {
                        "node_type": "sprockets/note",
                        "title": "Hello",
                        "item_text": "Hello",
                        "date": "2026-06-12",
                        "confidence": "low",
                    }
                ]
            ),
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.precision, 0.0)

    def test_empty_fixture_with_empty_output_passes(self):
        empty = _fixture(fixture_id="empty", content="Hello", expected_nodes=())

        result = capture_harness.run_fixture(
            capture_harness.HarnessConfig(model="m"),
            empty,
            classifier_factory=lambda config: ScriptedClassifier([], raw=[]),
        )

        self.assertTrue(result.passed)

    def test_model_error_is_captured_not_raised(self):
        def explode(config):
            raise RuntimeError("model unreachable")

        result = capture_harness.run_fixture(
            capture_harness.HarnessConfig(model="m"),
            _fixture(),
            classifier_factory=explode,
        )

        self.assertFalse(result.passed)
        self.assertIn("model unreachable", result.error)

    def test_guard_expectation_is_scored(self):
        fixture = _fixture(
            fixture_id="guarded",
            content="Area: Farm. Goal: Fix tractor.",
            expected_nodes=(),
            expect_structural_guard=True,
        )

        result = capture_harness.run_fixture(
            capture_harness.HarnessConfig(model="m"),
            fixture,
            classifier_factory=lambda config: ScriptedClassifier([], raw=[]),
        )

        self.assertTrue(result.structural_guard_reasons)
        self.assertTrue(result.guard_ok)


class ConfigAxisTests(unittest.TestCase):
    def test_config_label_distinguishes_axes(self):
        self.assertEqual(capture_harness.HarnessConfig(model="m").label, "m")
        self.assertEqual(
            capture_harness.HarnessConfig(model="m", context_max_chars=8000).label,
            "m/cap8000",
        )
        self.assertEqual(
            capture_harness.HarnessConfig(model="m", use_examples=False).label,
            "m/noexamples",
        )

    def test_use_examples_reaches_the_classify_call(self):
        scripted = ScriptedClassifier([])

        capture_harness.run_fixture(
            capture_harness.HarnessConfig(model="m", use_examples=False),
            _fixture(expected_nodes=()),
            classifier_factory=lambda config: scripted,
        )

        self.assertIs(scripted.seen_use_examples, False)

    def test_context_cap_is_configurable_and_defaults_unchanged(self):
        self.assertEqual(DEFAULT_CONTEXT_MAX_CHARS, 2000)
        self.assertEqual(ExtractClassifierConfig().context_max_chars, 2000)

        long_context = "x" * 5000
        self.assertEqual(len(truncate_context(long_context)), 2000 + len("\n[... truncated]"))

    def test_raised_cap_changes_the_prompt_the_model_sees(self):
        captured = {}

        def fake_chat(**kwargs):
            captured["content"] = kwargs["messages"][-1]["content"]

            class Response:
                class message:
                    content = '{"nodes": []}'

            return Response()

        long_context = "y" * 4000
        for cap, expected_marker in ((2000, True), (6000, False)):
            classifier = ExtractClassifier(
                ExtractClassifierConfig(model="m", context_max_chars=cap),
                chat_client=fake_chat,
            )
            classifier.classify_nodes(
                [{"raw": "a", "type_hint": "task"}],
                long_context,
                now=datetime(2026, 6, 12, 9, 0),
            )
            self.assertEqual("[... truncated]" in captured["content"], expected_marker)


class ReportTests(unittest.TestCase):
    def test_summary_aggregates_across_fixtures(self):
        good = capture_harness.HarnessConfig(model="good")
        bad = capture_harness.HarnessConfig(model="bad")

        def factory(config):
            if config.model == "good":
                return ScriptedClassifier(
                    [
                        {
                            "node_type": "cogs/daily",
                            "title": "YOGA 5:30p",
                            "item_text": "YOGA 5:30p",
                            "date": "2026-06-13",
                            "confidence": "high",
                        }
                    ]
                )
            return ScriptedClassifier([])

        results = capture_harness.run_harness(
            (good, bad), (_fixture(),), classifier_factory=factory
        )
        summary = capture_harness.summarize(results)

        self.assertEqual(summary["good"]["f1"], 1.0)
        self.assertEqual(summary["bad"]["recall"], 0.0)
        self.assertIn("- writes: none", capture_harness.format_results(results))

    def test_results_to_dict_is_machine_readable(self):
        results = capture_harness.run_harness(
            (capture_harness.HarnessConfig(model="m"),),
            (_fixture(expected_nodes=()),),
            classifier_factory=lambda config: ScriptedClassifier([], raw=[]),
        )

        payload = capture_harness.results_to_dict(results)

        self.assertEqual(payload["writes"], "none")
        self.assertEqual(payload["results"][0]["config"], "m")
        json.dumps(payload)

    def test_json_report_carries_model_output_for_diagnosis(self):
        results = capture_harness.run_harness(
            (capture_harness.HarnessConfig(model="m"),),
            (_fixture(),),
            classifier_factory=lambda config: ScriptedClassifier(
                [{"node_type": "cogs/daily", "title": "YOGA", "date": "2026-06-09"}],
                raw=[{"raw": "Yoga on 2026-06-09", "type_hint": "appointment"}],
            ),
        )

        entry = capture_harness.results_to_dict(results)["results"][0]

        self.assertEqual(entry["raw_nodes"][0]["raw"], "Yoga on 2026-06-09")
        self.assertEqual(entry["classified_nodes"][0]["date"], "2026-06-09")

    def test_repeat_runs_each_config_multiple_times(self):
        results = capture_harness.run_harness(
            (capture_harness.HarnessConfig(model="m"),),
            (_fixture(expected_nodes=()),),
            repeat=3,
            classifier_factory=lambda config: ScriptedClassifier([], raw=[]),
        )

        self.assertEqual(len(results), 3)


class TokenInstrumentationTests(unittest.TestCase):
    """Slice 2: real tokenizer counts, not character estimates."""

    def _chat_client(self, prompt_tokens=120, completion_tokens=30):
        def fake_chat(**kwargs):
            class Response:
                class message:
                    # Non-empty items so the classify call is actually reached;
                    # classify_nodes short-circuits on an empty extraction.
                    content = '{"items": [{"raw": "a", "type_hint": "task"}], "nodes": []}'

            Response.prompt_eval_count = prompt_tokens
            Response.eval_count = completion_tokens
            Response.total_duration = 2_000_000_000
            Response.load_duration = 500_000_000
            Response.prompt_eval_duration = 400_000_000
            Response.eval_duration = 1_100_000_000
            return Response()

        return fake_chat

    def test_classify_call_records_token_counts(self):
        classifier = ExtractClassifier(
            ExtractClassifierConfig(model="m"),
            chat_client=self._chat_client(),
        )

        classifier.classify_nodes(
            [{"raw": "a", "type_hint": "task"}],
            "some context",
            now=datetime(2026, 6, 12, 9, 0),
        )

        self.assertEqual(len(classifier.call_stats), 1)
        stats = classifier.call_stats[0]
        self.assertEqual(stats.call, "classify")
        self.assertEqual(stats.prompt_tokens, 120)
        self.assertEqual(stats.completion_tokens, 30)
        self.assertGreater(stats.prompt_chars, 0)

    def test_extract_call_is_recorded_too(self):
        classifier = ExtractClassifier(
            ExtractClassifierConfig(model="m"),
            chat_client=self._chat_client(),
        )

        classifier.extract_nodes("Call Mom", now=datetime(2026, 6, 12, 9, 0))

        self.assertEqual([s.call for s in classifier.call_stats], ["extract"])

    def test_durations_convert_nanoseconds_to_seconds(self):
        classifier = ExtractClassifier(
            ExtractClassifierConfig(model="m"),
            chat_client=self._chat_client(),
        )

        classifier.extract_nodes("Call Mom", now=datetime(2026, 6, 12, 9, 0))
        stats = classifier.call_stats[0]

        self.assertAlmostEqual(stats.total_seconds, 2.0)
        self.assertAlmostEqual(stats.eval_seconds, 1.1)

    def test_chars_per_token_is_measured_not_assumed(self):
        stats = CallStats(
            call="classify", model="m", prompt_chars=400, prompt_tokens=100
        )

        self.assertEqual(stats.chars_per_token, 4.0)

    def test_missing_token_fields_degrade_gracefully(self):
        def bare_chat(**kwargs):
            class Response:
                class message:
                    content = '{"nodes": []}'

            return Response()

        classifier = ExtractClassifier(
            ExtractClassifierConfig(model="m"), chat_client=bare_chat
        )
        classifier.classify_nodes(
            [{"raw": "a", "type_hint": "task"}],
            "ctx",
            now=datetime(2026, 6, 12, 9, 0),
        )

        stats = classifier.call_stats[0]
        self.assertIsNone(stats.prompt_tokens)
        self.assertIsNone(stats.chars_per_token)
        self.assertGreater(stats.prompt_chars, 0)

    def test_harness_aggregates_tokens_across_both_calls(self):
        def factory(config):
            return ExtractClassifier(
                ExtractClassifierConfig(model=config.model),
                chat_client=self._chat_client(prompt_tokens=200, completion_tokens=50),
            )

        result = capture_harness.run_fixture(
            capture_harness.HarnessConfig(model="m"),
            _fixture(expected_nodes=()),
            classifier_factory=factory,
        )

        self.assertEqual(len(result.call_stats), 2)
        self.assertEqual(result.prompt_tokens, 400)
        self.assertEqual(result.completion_tokens, 100)
        self.assertEqual(result.peak_prompt_tokens, 200)

    def test_json_report_carries_per_call_token_detail(self):
        def factory(config):
            return ExtractClassifier(
                ExtractClassifierConfig(model=config.model),
                chat_client=self._chat_client(),
            )

        results = capture_harness.run_harness(
            (capture_harness.HarnessConfig(model="m"),),
            (_fixture(expected_nodes=()),),
            classifier_factory=factory,
        )
        entry = capture_harness.results_to_dict(results)["results"][0]

        self.assertEqual([c["call"] for c in entry["calls"]], ["extract", "classify"])
        self.assertEqual(entry["calls"][0]["prompt_tokens"], 120)
        self.assertIsNotNone(entry["calls"][0]["chars_per_token"])

    def test_context_utilization_uses_resolved_num_ctx(self):
        capture_harness._NUM_CTX_CACHE["fake-model"] = 16384

        def factory(config):
            return ExtractClassifier(
                ExtractClassifierConfig(model=config.model),
                chat_client=self._chat_client(prompt_tokens=1638),
            )

        try:
            results = capture_harness.run_harness(
                (capture_harness.HarnessConfig(model="fake-model"),),
                (_fixture(expected_nodes=()),),
                classifier_factory=factory,
            )
            summary = capture_harness.summarize(results)["fake-model"]
        finally:
            capture_harness._NUM_CTX_CACHE.pop("fake-model", None)

        self.assertEqual(summary["num_ctx"], 16384)
        self.assertAlmostEqual(summary["peak_context_utilization"], 0.0999, places=3)


class LoaderTests(unittest.TestCase):
    def test_missing_optional_fields_get_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "minimal.json"
            path.write_text(
                json.dumps(
                    {
                        "fixture_id": "minimal",
                        "content": "Call Mom",
                        "now": "2026-06-12T09:00:00",
                    }
                )
            )

            fixture = load_capture_fixtures(Path(tmp))[0]

        self.assertEqual(fixture.fixture_id, "minimal")
        self.assertEqual(fixture.expected_nodes, ())
        self.assertIsNone(fixture.expected_item_count)
        self.assertFalse(fixture.expect_structural_guard)
        self.assertIn("Known hierarchy parents", fixture.context)


if __name__ == "__main__":
    unittest.main()

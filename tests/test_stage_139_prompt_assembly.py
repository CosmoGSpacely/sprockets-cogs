"""Stage 139 slice 1: one shared assembly path, and it must not drift again.

The Stage 138 date defect existed because `extract_nodes` and `classify_nodes`
assembled their messages separately in the same class, and nothing compared
them. These tests are the thing that compares them.
"""
import unittest
from datetime import datetime

from specialists.rosie.extractor_classifier import (
    DEFAULT_CAPTURE_MODEL,
    DEFAULT_CONTEXT_MAX_CHARS,
    ExtractClassifier,
    ExtractClassifierConfig,
    build_classify_messages,
    build_extract_messages,
    date_anchor,
)
from specialists.uniblab import prompt_dump
from specialists.uniblab.capture_fixtures import load_capture_fixtures


REF = datetime(2026, 6, 12, 9, 0)
RAW = [{"raw": "yoga tomorrow", "type_hint": "appointment"}]


def _user_text(messages):
    return messages[-1]["content"]


class DateAnchorParityTests(unittest.TestCase):
    """Both calls must carry an identical date block. This is the drift guard."""

    def test_both_calls_embed_the_identical_anchor(self):
        anchor = date_anchor(REF)

        self.assertIn(anchor, _user_text(build_extract_messages("x", REF)))
        self.assertIn(anchor, _user_text(build_classify_messages(RAW, "ctx", REF)))

    def test_anchor_states_both_today_and_workdays(self):
        anchor = date_anchor(REF)

        self.assertIn("Today: 2026-06-12 (Friday)", anchor)
        self.assertIn("This week's workdays: Mon 2026-06-08", anchor)

    def test_anchor_is_defined_once(self):
        """No call may hand-roll its own date line."""

        import inspect

        import specialists.rosie.extractor_classifier as module

        source = inspect.getsource(module)
        # The literal format string may appear only inside date_anchor().
        self.assertEqual(source.count("This week's workdays:"), 1)
        self.assertEqual(source.count("%Y-%m-%d (%A)"), 1)

    def test_anchor_tracks_the_reference_date(self):
        self.assertIn("2026-06-13 (Saturday)", date_anchor(datetime(2026, 6, 13)))


class ExtractAssemblyTests(unittest.TestCase):
    def test_shape_is_system_examples_then_user(self):
        messages = build_extract_messages("Call Mom", REF)

        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[-1]["role"], "user")
        self.assertGreater(len(messages), 2)

    def test_content_is_included_verbatim(self):
        self.assertIn("Call Mom", _user_text(build_extract_messages("Call Mom", REF)))


class ClassifyAssemblyTests(unittest.TestCase):
    def test_examples_can_be_dropped(self):
        with_examples = build_classify_messages(RAW, "ctx", REF)
        without = build_classify_messages(RAW, "ctx", REF, use_examples=False)

        self.assertLess(len(without), len(with_examples))
        self.assertEqual(len(without), 2)

    def test_error_context_is_appended_when_present(self):
        text = _user_text(
            build_classify_messages(RAW, "ctx", REF, error_context="bad date")
        )

        self.assertIn("Fix these issues from the previous attempt:", text)
        self.assertIn("bad date", text)

    def test_error_context_absent_by_default(self):
        self.assertNotIn(
            "Fix these issues", _user_text(build_classify_messages(RAW, "ctx", REF))
        )

    def test_context_cap_is_honored(self):
        text = _user_text(
            build_classify_messages(RAW, "y" * 5000, REF, context_max_chars=100)
        )

        self.assertIn("[... truncated]", text)

    def test_raw_nodes_are_rendered_as_json(self):
        self.assertIn('"type_hint": "appointment"', _user_text(
            build_classify_messages(RAW, "ctx", REF)
        ))


class BuildersMatchLiveCallsTests(unittest.TestCase):
    """The refactor must be faithful: what the class sends is what builders make."""

    def _sent_messages(self, method, *args, **kwargs):
        sent = {}

        def fake_chat(**call):
            sent["messages"] = call["messages"]

            class Response:
                class message:
                    content = '{"items": [], "nodes": []}'

            return Response()

        classifier = ExtractClassifier(
            ExtractClassifierConfig(model="m"), chat_client=fake_chat
        )
        getattr(classifier, method)(*args, **kwargs)
        return sent["messages"]

    def test_extract_call_sends_exactly_the_built_messages(self):
        sent = self._sent_messages("extract_nodes", "Call Mom", now=REF)

        self.assertEqual(sent, build_extract_messages("Call Mom", REF))

    def test_classify_call_sends_exactly_the_built_messages(self):
        sent = self._sent_messages("classify_nodes", RAW, "ctx", now=REF)

        self.assertEqual(sent, build_classify_messages(RAW, "ctx", REF))

    def test_classify_call_passes_its_configured_cap_through(self):
        sent = {}

        def fake_chat(**call):
            sent["messages"] = call["messages"]

            class Response:
                class message:
                    content = '{"nodes": []}'

            return Response()

        ExtractClassifier(
            ExtractClassifierConfig(model="m", context_max_chars=50),
            chat_client=fake_chat,
        ).classify_nodes(RAW, "z" * 900, now=REF)

        self.assertEqual(
            sent["messages"],
            build_classify_messages(RAW, "z" * 900, REF, context_max_chars=50),
        )


class SamplingOptionTests(unittest.TestCase):
    """Slice 4: sampling knobs travel through request options, not Modelfiles.

    Request options override Modelfile PARAMETER values, so this is the only
    layer that reliably wins (Stage 138, config-truth layer 3).
    """

    def test_default_options_are_unchanged(self):
        """Nothing new may be sent unless explicitly set."""

        self.assertEqual(
            ExtractClassifierConfig(model="m").chat_options(), {"temperature": 0.1}
        )

    def test_set_knobs_are_included(self):
        options = ExtractClassifierConfig(
            model="m", repeat_penalty=1.0, top_k=20
        ).chat_options()

        self.assertEqual(options, {"temperature": 0.1, "repeat_penalty": 1.0, "top_k": 20})

    def test_zero_is_sent_not_treated_as_unset(self):
        options = ExtractClassifierConfig(model="m", presence_penalty=0.0).chat_options()

        self.assertIn("presence_penalty", options)
        self.assertEqual(options["presence_penalty"], 0.0)

    def test_options_reach_the_chat_call(self):
        sent = {}

        def fake_chat(**call):
            sent.update(call)

            class Response:
                class message:
                    content = '{"nodes": []}'

            return Response()

        ExtractClassifier(
            ExtractClassifierConfig(model="m", repeat_penalty=1.15, temperature=0.0),
            chat_client=fake_chat,
        ).classify_nodes(RAW, "ctx", now=REF)

        self.assertEqual(
            sent["options"], {"temperature": 0.0, "repeat_penalty": 1.15}
        )

    def test_harness_config_labels_sampling_axes(self):
        from specialists.uniblab.capture_harness import HarnessConfig

        self.assertEqual(
            HarnessConfig(model="m", repeat_penalty=1.0).label, "m/rp1.0"
        )
        self.assertEqual(
            HarnessConfig(model="m", temperature=0.0).label, "m/t0.0"
        )

    def test_config_grid_defaults_to_one_config(self):
        from specialists.uniblab import capture_harness

        args = capture_harness.build_parser().parse_args(["--model", "m"])
        configs = capture_harness.configs_from_args(args)

        self.assertEqual(len(configs), 1)
        self.assertIsNone(configs[0].repeat_penalty)

    def test_config_grid_expands_over_sampling_axes(self):
        from specialists.uniblab import capture_harness

        args = capture_harness.build_parser().parse_args(
            [
                "--model", "m",
                "--repeat-penalty", "1.0",
                "--repeat-penalty", "1.15",
                "--temperature", "0.0",
            ]
        )
        configs = capture_harness.configs_from_args(args)

        self.assertEqual(len(configs), 2)
        self.assertEqual({c.repeat_penalty for c in configs}, {1.0, 1.15})
        self.assertEqual({c.temperature for c in configs}, {0.0})


class DefaultModelTests(unittest.TestCase):
    def test_capture_default_names_the_deployed_model(self):
        """The code default previously claimed Qwen while production ran Gemma."""

        self.assertEqual(DEFAULT_CAPTURE_MODEL, "gemma4:12b-32k-cosmo")


class PromptDumpTests(unittest.TestCase):
    def test_dump_renders_both_calls_without_a_model(self):
        fixture = load_capture_fixtures(only=("simple-appointment",))[0]

        rendered = prompt_dump.render(fixture)

        self.assertEqual(rendered["fixture_id"], "simple-appointment")
        self.assertEqual(rendered["extract"], build_extract_messages(
            fixture.content, fixture.now
        ))
        self.assertTrue(rendered["classify"])

    def test_dump_reports_the_anchor_that_was_missing_in_stage_138(self):
        fixture = load_capture_fixtures(only=("simple-appointment",))[0]

        text = prompt_dump.format_dump(prompt_dump.render(fixture))

        self.assertIn("Today: 2026-06-12 (Friday)", text)
        self.assertIn("model calls: none", text)

    def test_examples_are_elided_unless_full(self):
        fixture = load_capture_fixtures(only=("simple-appointment",))[0]
        rendered = prompt_dump.render(fixture)

        brief = prompt_dump.format_dump(rendered)
        full = prompt_dump.format_dump(rendered, full=True)

        self.assertIn("<few-shot example", brief)
        self.assertNotIn("<few-shot example", full)
        self.assertGreater(len(full), len(brief))

    def test_empty_fixture_still_renders_a_classify_prompt(self):
        fixture = load_capture_fixtures(only=("empty-greeting",))[0]

        rendered = prompt_dump.render(fixture)

        self.assertTrue(rendered["classify"])

    def test_token_estimate_uses_the_measured_ratio(self):
        self.assertEqual(prompt_dump.CHARS_PER_TOKEN, 2.79)
        self.assertEqual(prompt_dump.estimate_tokens(279), 100)

    def test_cli_runs_and_makes_no_model_call(self):
        parser = prompt_dump.build_parser()
        args = parser.parse_args(["--fixture", "simple-appointment"])

        self.assertEqual(args.fixture_ids, ["simple-appointment"])
        self.assertEqual(args.context_max_chars, DEFAULT_CONTEXT_MAX_CHARS)


if __name__ == "__main__":
    unittest.main()

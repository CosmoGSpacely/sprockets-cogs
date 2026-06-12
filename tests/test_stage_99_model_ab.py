import unittest
from dataclasses import replace

import model_ab
import model_capability_probe
from memory_tool_probe import MemoryToolChoice, MemoryToolProbeResult


class FakeClassifier:
    def __init__(self, model):
        self.model = model

    def extract_nodes(self, content, now=None):
        return [{"raw": content, "type_hint": "task"}]

    def classify_nodes(self, raw_nodes, context, now=None):
        if "bad" in self.model:
            return [{"node_type": "unknown", "title": "", "confidence": "low"}]
        return [
            {
                "node_type": "cogs/daily",
                "title": "Call Alex",
                "item_text": "Call Alex",
                "date": "2026-06-12",
                "confidence": "high",
            }
        ]


class Stage99ModelABTests(unittest.TestCase):
    def test_run_ab_scores_valid_nodes_without_writes(self):
        cases = (
            model_ab.CaptureCase(
                case_id="case-1",
                content="Call Alex today",
                source="test",
                expected_terms=("Alex",),
            ),
        )

        results = model_ab.run_ab(
            ("good-model", "bad-model"),
            cases,
            classifier_factory=FakeClassifier,
        )
        output = model_ab.format_results(results)
        summary = model_ab.summarize_results(results)

        self.assertGreater(summary["good-model"]["score"], summary["bad-model"]["score"])
        self.assertEqual(summary["good-model"]["valid_nodes"], 1)
        self.assertEqual(summary["bad-model"]["invalid_nodes"], 1)
        self.assertIn("- writes: none", output)

    def test_structural_guard_pressure_is_reported(self):
        result = model_ab.run_model_case(
            "good-model",
            model_ab.CaptureCase(
                case_id="structural",
                content="Area: Farm. Goal: Fix tractor.",
                source="test",
            ),
            classifier_factory=FakeClassifier,
        )

        self.assertIn("structural label syntax", result.structural_guard_reasons)

    def test_results_to_dict_is_machine_readable(self):
        result = model_ab.ModelCaseResult(
            model="m",
            case_id="c",
            raw_nodes=[],
            classified_nodes=[],
            elapsed_seconds=0.1,
            valid_nodes=0,
            invalid_nodes=0,
            low_confidence_nodes=0,
            expected_terms_found=0,
        )

        payload = model_ab.results_to_dict((result,))

        self.assertEqual(payload["writes"], "none")
        self.assertEqual(payload["results"][0]["model"], "m")


class Stage99CapabilityProbeTests(unittest.TestCase):
    def test_capability_probe_stamps_model_mode_and_write_boundary(self):
        def fake_probe(query, model):
            return MemoryToolProbeResult(
                query=query,
                model=model,
                valid=True,
                tool_choice=MemoryToolChoice(
                    name="search_memory",
                    arguments={"query": query, "reason": "test"},
                ),
            )

        run = model_capability_probe.run_capability_probe(
            "selected-model",
            mode="json-contract",
            queries=("Find memory",),
            json_probe=fake_probe,
        )
        output = model_capability_probe.format_capability_probe(run)
        payload = model_capability_probe.run_to_dict(run)

        self.assertTrue(run.passed)
        self.assertEqual(run.write_authority, "none")
        self.assertEqual(payload["model"], "selected-model")
        self.assertIn("write authority: none", output)

    def test_capability_probe_failure_is_visible(self):
        def fake_probe(query, model):
            return MemoryToolProbeResult(
                query=query,
                model=model,
                valid=False,
                tool_choice=None,
                issue="no tool call",
            )

        run = model_capability_probe.run_capability_probe(
            "selected-model",
            mode="native",
            queries=("Find memory",),
            native_probe=fake_probe,
        )

        self.assertFalse(run.passed)
        self.assertEqual(model_capability_probe.run_to_dict(run)["results"][0]["issue"], "no tool call")


if __name__ == "__main__":
    unittest.main()

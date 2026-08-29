"""Stage 139 slice 5: parent_hint and confidence grading in capture fixtures.

`parent_hint` is absent-vs-empty sensitive, which is the whole point: omitting
the key leaves the field ungraded, while `""` asserts the node carries no
parent. That distinction is what lets a fixture state "borrowing a plausible
real parent is the failure being watched for".
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from specialists.uniblab import capture_fixtures


def _node(**overrides):
    node = {
        "node_type": "sprockets/task",
        "title": "Install bin shelves",
        "item_text": "Install bin shelves",
        "date": "2026-06-12",
        "confidence": "high",
    }
    node.update(overrides)
    return node


class ParentHintMatchingTests(unittest.TestCase):
    def test_omitted_parent_hint_does_not_grade_the_field(self):
        expected = capture_fixtures.ExpectedNode(
            node_type="sprockets/task", must_include=("shelves",)
        )
        self.assertTrue(expected.matches(_node(parent_hint="Farm")))
        self.assertTrue(expected.matches(_node()))

    def test_empty_parent_hint_requires_no_parent(self):
        expected = capture_fixtures.ExpectedNode(
            node_type="sprockets/task", must_include=("shelves",), parent_hint=""
        )
        self.assertTrue(expected.matches(_node()))
        self.assertFalse(expected.matches(_node(parent_hint="Farm")))

    def test_missing_and_null_parent_read_the_same_as_empty(self):
        """A node may omit parent_hint or carry null; both mean no parent."""

        expected = capture_fixtures.ExpectedNode(
            node_type="sprockets/task", must_include=("shelves",), parent_hint=""
        )
        self.assertTrue(expected.matches(_node(parent_hint="")))
        self.assertTrue(expected.matches(_node(parent_hint=None)))

    def test_named_parent_hint_must_match_exactly(self):
        expected = capture_fixtures.ExpectedNode(
            node_type="sprockets/task",
            must_include=("shelves",),
            parent_hint="Garage Work",
        )
        self.assertTrue(expected.matches(_node(parent_hint="Garage Work")))
        self.assertFalse(expected.matches(_node(parent_hint="Farm")))
        self.assertFalse(expected.matches(_node()))

    def test_confidence_graded_only_when_asserted(self):
        ungraded = capture_fixtures.ExpectedNode(node_type="sprockets/task")
        self.assertTrue(ungraded.matches(_node(confidence="low")))

        needs_low = capture_fixtures.ExpectedNode(
            node_type="sprockets/task", confidence="low"
        )
        self.assertTrue(needs_low.matches(_node(confidence="low")))
        self.assertFalse(needs_low.matches(_node(confidence="high")))


class ParentHintLoaderTests(unittest.TestCase):
    def _load(self, node):
        payload = {
            "fixture_id": "f",
            "content": "c",
            "now": "2026-06-12T09:00:00",
            "expected": {"nodes": [node], "allowed_extra": [node]},
        }
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.json"
            path.write_text(json.dumps(payload))
            return capture_fixtures.load_capture_fixture(path)

    def test_absent_key_loads_as_none(self):
        fixture = self._load({"node_type": "sprockets/task"})
        self.assertIsNone(fixture.expected_nodes[0].parent_hint)

    def test_empty_string_survives_loading(self):
        """The absent/empty distinction must not be flattened by the loader."""

        fixture = self._load({"node_type": "sprockets/task", "parent_hint": ""})
        self.assertEqual(fixture.expected_nodes[0].parent_hint, "")

    def test_allowed_extra_gets_the_same_treatment(self):
        fixture = self._load(
            {"node_type": "sprockets/task", "parent_hint": "Farm", "confidence": "low"}
        )
        self.assertEqual(fixture.allowed_extra[0].parent_hint, "Farm")
        self.assertEqual(fixture.allowed_extra[0].confidence, "low")


class FixtureSetIntegrityTests(unittest.TestCase):
    """Guards on the shipped fixture set itself, not on the grading code."""

    def setUp(self):
        self.fixtures = capture_fixtures.load_capture_fixtures()

    def test_every_fixture_loads(self):
        self.assertEqual(len(self.fixtures), 22)

    def test_node_types_are_emittable(self):
        """A fixture asserting a type outside the schema enum can never pass."""

        allowed = {
            "cogs/daily",
            "sprockets/task",
            "sprockets/contact",
            "sprockets/entity",
            "sprockets/note",
        }
        for fixture in self.fixtures:
            for node in fixture.expected_nodes + fixture.allowed_extra:
                self.assertIn(node.node_type, allowed, fixture.fixture_id)

    def test_every_fixture_explains_itself(self):
        for fixture in self.fixtures:
            self.assertTrue(fixture.notes.strip(), fixture.fixture_id)
            self.assertTrue(fixture.source.strip(), fixture.fixture_id)

    def test_allowed_extra_never_duplicates_a_requirement(self):
        """Permission is not credit; an entry that restates a requirement would
        let the same node satisfy both sides."""

        for fixture in self.fixtures:
            for permitted in fixture.allowed_extra:
                self.assertNotIn(permitted, fixture.expected_nodes, fixture.fixture_id)

    def test_stt_and_context_categories_are_present(self):
        categories = {fixture.category for fixture in self.fixtures}
        for required in (
            "stt", "context", "restraint", "mutation", "date",
            "segmentation", "confidence",
        ):
            self.assertIn(required, categories)


if __name__ == "__main__":
    unittest.main()

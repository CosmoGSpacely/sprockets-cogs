import unittest

from pydantic import ValidationError

from graph.fixtures import fixture_paths, load_fixture, load_product_graph_fixture
from graph.models import Cog, CogLocator, Sprocket, SprocketHierarchyEdge
from graph.validators import validate_product_graph, validate_fixture


def fixture_by_id(fixture_id):
    for path in fixture_paths():
        if load_fixture(path)["fixture_id"] == fixture_id:
            return load_product_graph_fixture(path)
    raise AssertionError(f"missing fixture: {fixture_id}")


class Stage76GraphValidatorTests(unittest.TestCase):
    def test_valid_fixtures_pass_contract_validation(self):
        for fixture_id in [
            "minimal_valid_graph",
            "valid_hierarchy_graph",
            "valid_primary_bridge",
            "valid_context_bridges",
        ]:
            with self.subTest(fixture_id=fixture_id):
                result = validate_fixture(fixture_by_id(fixture_id))
                self.assertTrue(result.passed, result.issues)

    def test_cog_without_primary_bridge_fails(self):
        result = validate_fixture(fixture_by_id("invalid_cog_no_primary_bridge"))

        self.assertFalse(result.passed)
        self.assertEqual(result.codes, ("cog_missing_primary_bridge",))

    def test_cog_with_multiple_primary_bridges_fails(self):
        result = validate_fixture(fixture_by_id("invalid_cog_multiple_primary_bridges"))

        self.assertFalse(result.passed)
        self.assertEqual(result.codes, ("cog_multiple_primary_bridges",))

    def test_unresolved_bridge_target_fails(self):
        result = validate_fixture(fixture_by_id("invalid_unresolved_bridge_target"))

        self.assertFalse(result.passed)
        self.assertEqual(result.codes, ("bridge_unresolved_sprocket_target",))

    def test_invalid_context_bridge_role_fails_before_graph_validation(self):
        with self.assertRaises(ValidationError):
            fixture_by_id("invalid_context_bridge_role")

    def test_hierarchy_edges_must_resolve_to_sprockets(self):
        general = Sprocket(id="sprocket-general", kind="area", text="General")
        edge = SprocketHierarchyEdge(
            parent_id=general.id,
            child_id="missing-task",
        )

        result = validate_product_graph(
            sprockets=[general],
            cogs=[],
            hierarchy_edges=[edge],
            bridge_edges=[],
        )

        self.assertEqual(result.codes, ("hierarchy_unresolved_child",))

    def test_current_locator_requires_marker_when_present(self):
        general = Sprocket(id="sprocket-general", kind="area", text="General")
        cog = Cog(
            id="cog-dentist",
            kind="appointment",
            text="DENTIST 8a",
            current_locator=CogLocator(
                horizon="day",
                period="2026-06-05",
                path="Cogs/daily/Fri 05 Jun 2026.md",
            ),
        )

        result = validate_product_graph(
            sprockets=[general],
            cogs=[cog],
            hierarchy_edges=[],
            bridge_edges=[],
        )

        self.assertEqual(
            result.codes,
            ("cog_missing_primary_bridge", "cog_locator_missing_marker"),
        )


if __name__ == "__main__":
    unittest.main()

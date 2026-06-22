import unittest

from pydantic import ValidationError

from graph.fixtures import fixture_paths, load_fixture, load_product_graph_fixture


class Stage75GraphFixtureTests(unittest.TestCase):
    def test_fixture_set_contains_expected_stage_72_cases(self):
        fixture_ids = {load_fixture(path)["fixture_id"] for path in fixture_paths()}

        self.assertEqual(
            fixture_ids,
            {
                "minimal_valid_graph",
                "valid_hierarchy_graph",
                "valid_primary_bridge",
                "valid_context_bridges",
                "invalid_cog_no_primary_bridge",
                "invalid_cog_multiple_primary_bridges",
                "invalid_unresolved_bridge_target",
                "invalid_context_bridge_role",
                "proposal_mutation_command",
                "audit_examples",
            },
        )

    def test_valid_product_graph_fixtures_load_into_models(self):
        valid_ids = {
            "minimal_valid_graph",
            "valid_hierarchy_graph",
            "valid_primary_bridge",
            "valid_context_bridges",
        }

        loaded = {}
        for path in fixture_paths():
            if load_fixture(path)["fixture_id"] in valid_ids:
                fixture = load_product_graph_fixture(path)
                loaded[fixture.fixture_id] = fixture

        self.assertEqual(set(loaded), valid_ids)
        self.assertEqual(loaded["minimal_valid_graph"].bridge_edges[0].role, "primary")
        self.assertEqual(
            loaded["valid_hierarchy_graph"].hierarchy_edges[0].edge_key,
            "sprocket-area-farm:sprocket_hierarchy:sprocket-goal-tractor-ready",
        )
        self.assertEqual(
            loaded["valid_primary_bridge"].cogs[0].current_locator.path,
            "Cogs/2026/06/23/2026-06-06 Sat.md",
        )

    def test_graph_level_invalid_fixtures_still_load_for_stage_76_validators(self):
        invalid_ids = {
            "invalid_cog_no_primary_bridge",
            "invalid_cog_multiple_primary_bridges",
            "invalid_unresolved_bridge_target",
        }

        loaded = {}
        for path in fixture_paths():
            if load_fixture(path)["fixture_id"] in invalid_ids:
                fixture = load_product_graph_fixture(path)
                loaded[fixture.fixture_id] = fixture

        self.assertEqual(set(loaded), invalid_ids)
        self.assertEqual(
            loaded["invalid_cog_no_primary_bridge"].data["expected"]["errors"],
            ["cog_missing_primary_bridge"],
        )
        self.assertEqual(
            loaded["invalid_unresolved_bridge_target"].data["expected"]["errors"],
            ["bridge_unresolved_sprocket_target"],
        )

    def test_invalid_context_bridge_role_fails_model_loading(self):
        path = next(
            path
            for path in fixture_paths()
            if load_fixture(path)["fixture_id"] == "invalid_context_bridge_role"
        )

        with self.assertRaises(ValidationError):
            load_product_graph_fixture(path)

    def test_proposal_and_audit_examples_are_not_product_graph_facts(self):
        proposal = next(
            load_fixture(path)
            for path in fixture_paths()
            if load_fixture(path)["fixture_id"] == "proposal_mutation_command"
        )
        audit = next(
            load_fixture(path)
            for path in fixture_paths()
            if load_fixture(path)["fixture_id"] == "audit_examples"
        )

        self.assertNotIn("graph", proposal)
        self.assertIn("mutation_command", proposal["proposal"])
        self.assertNotIn("graph", audit)
        self.assertEqual(audit["audit"][0]["decision"], "applied_automatic")


if __name__ == "__main__":
    unittest.main()

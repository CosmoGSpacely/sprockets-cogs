import unittest

from pydantic import ValidationError

from graph.fixtures import fixture_paths, load_fixture
from graph.mutations import MutationCommand, command_from_proposal_fixture


class Stage77MutationCommandTests(unittest.TestCase):
    def test_create_cog_command_serializes_for_automatic_path(self):
        command = MutationCommand(
            id="mutation-create-cog-breathe",
            operation="create_cog",
            target_layer="product_graph",
            review_class="automatic",
            payload={
                "cog": {
                    "id": "cog-breathe",
                    "kind": "action",
                    "text": "Breathe",
                },
                "primary_bridge": {
                    "cog_id": "cog-breathe",
                    "sprocket_id": "sprocket-general",
                    "role": "primary",
                },
            },
        )

        packet = command.model_dump(mode="json", exclude_none=True)

        self.assertEqual(packet["operation"], "create_cog")
        self.assertEqual(packet["review_class"], "automatic")
        self.assertLess(command.packet_word_count(), 500)

    def test_same_command_shape_can_be_wrapped_by_review_proposal(self):
        proposal = next(
            load_fixture(path)
            for path in fixture_paths()
            if load_fixture(path)["fixture_id"] == "proposal_mutation_command"
        )

        command = command_from_proposal_fixture(proposal)

        self.assertEqual(command.operation, "create_sprocket_and_bridge")
        self.assertEqual(command.review_class, "review_first")
        self.assertEqual(
            command.payload["bridge"]["sprocket_id"],
            "sprocket-contact-tom",
        )
        self.assertLess(command.packet_word_count(), 500)

    def test_command_rejects_empty_payload_and_unknown_operation(self):
        with self.assertRaises(ValidationError):
            MutationCommand(
                id="mutation-empty",
                operation="create_cog",
                target_layer="product_graph",
                review_class="automatic",
                payload={},
            )

        with self.assertRaises(ValidationError):
            MutationCommand(
                id="mutation-unknown",
                operation="repair_everything",
                target_layer="product_graph",
                review_class="automatic",
                payload={"anything": True},
            )

    def test_render_command_keeps_apply_intent_small(self):
        command = MutationCommand(
            id="mutation-carry-cog",
            operation="carry_cog",
            target_layer="render",
            review_class="automatic",
            payload={
                "cog_id": "cog-buy-tire-valves",
                "from_locator": {
                    "horizon": "day",
                    "period": "2026-06-06",
                    "path": "Cogs/daily/Sat 06 Jun 2026.md",
                    "marker": "line:14",
                },
                "to_locator": {
                    "horizon": "week",
                    "period": "2026-W24",
                    "path": "Cogs/weekly/2026-W24.md",
                    "marker": "carry",
                },
            },
            expected_current_state={"from_marker_state": "open"},
        )

        self.assertEqual(command.target_layer, "render")
        self.assertLess(command.packet_word_count(), 500)


if __name__ == "__main__":
    unittest.main()

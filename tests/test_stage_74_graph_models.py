import unittest

from pydantic import ValidationError

from graph.models import (
    Cog,
    CogLocator,
    Sprocket,
    SprocketCogBridgeEdge,
    SprocketHierarchyEdge,
)


class Stage74GraphModelTests(unittest.TestCase):
    def test_minimal_product_graph_serializes(self):
        general = Sprocket(id="sprocket-general", kind="area", text="General")
        cog = Cog(id="cog-breathe", kind="action", text="Breathe")
        bridge = SprocketCogBridgeEdge(
            cog_id=cog.id,
            sprocket_id=general.id,
            role="primary",
        )

        self.assertEqual(general.model_dump(mode="json")["kind"], "area")
        self.assertEqual(cog.model_dump(mode="json")["text"], "Breathe")
        self.assertEqual(
            bridge.edge_key,
            "cog-breathe:sprocket_cog_bridge:primary:sprocket-general",
        )

    def test_hierarchy_edge_uses_structural_identity(self):
        edge = SprocketHierarchyEdge(
            parent_id="sprocket-area-farm",
            child_id="sprocket-goal-tractor-ready",
        )

        self.assertEqual(
            edge.edge_key,
            "sprocket-area-farm:sprocket_hierarchy:sprocket-goal-tractor-ready",
        )
        self.assertEqual(edge.model_dump(mode="json")["family"], "sprocket_hierarchy")

    def test_cog_locator_stores_current_render_position_only(self):
        locator = CogLocator(
            horizon="day",
            period="2026-06-05",
            path="Cogs/daily/Fri 05 Jun 2026.md",
            marker="line:12",
        )
        cog = Cog(
            id="cog-dentist-august",
            kind="appointment",
            text="DENTIST 8a",
            current_locator=locator,
        )

        serialized = cog.model_dump(mode="json")

        self.assertEqual(serialized["current_locator"]["horizon"], "day")
        self.assertEqual(serialized["current_locator"]["period"], "2026-06-05")
        self.assertNotIn("appearances", serialized)

    def test_context_bridge_roles_share_one_edge_family(self):
        bridge = SprocketCogBridgeEdge(
            cog_id="cog-meet-tom",
            sprocket_id="sprocket-tom",
            role="participant",
        )

        self.assertEqual(bridge.family, "sprocket_cog_bridge")
        self.assertEqual(
            bridge.edge_key,
            "cog-meet-tom:sprocket_cog_bridge:participant:sprocket-tom",
        )

    def test_models_reject_unknown_kinds_and_empty_text(self):
        with self.assertRaises(ValidationError):
            Sprocket(id="sprocket-general", kind="collection", text="Stamps")

        with self.assertRaises(ValidationError):
            Cog(id="cog-empty", kind="action", text="   ")


if __name__ == "__main__":
    unittest.main()

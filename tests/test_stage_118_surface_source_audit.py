import tempfile
import unittest
from pathlib import Path

from specialists.cogs.appearances import appearance_set_for_dated_cog
from substrate.cog_appearance_registry import (
    CogAppearance,
    CogAppearanceRegistry,
    load_registry,
    registry_path,
    save_registry,
)


class Stage118SurfaceSourceAuditTests(unittest.TestCase):
    def test_registry_path_is_hidden_graph_state(self):
        vault = Path("/tmp/vault")

        self.assertEqual(registry_path(vault), vault / ".graph" / "cog-appearances.json")

    def test_registry_round_trips_and_indexes_by_cog_and_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            registry = CogAppearanceRegistry()
            appearance = CogAppearance(
                cog_id="cog-july-3-walmart",
                surface="5wow",
                period="2026-06",
                path="Cogs/2026/2026-06.md",
            )

            registry.upsert(appearance)
            path = save_registry(vault, registry)
            loaded = load_registry(vault)

            self.assertEqual(path, vault / ".graph" / "cog-appearances.json")
            self.assertEqual(loaded.by_cog("cog-july-3-walmart"), [appearance])
            self.assertEqual(loaded.by_path("Cogs/2026/2026-06.md"), [appearance])

    def test_registry_upsert_replaces_same_appearance_key(self):
        registry = CogAppearanceRegistry()
        open_item = CogAppearance(
            cog_id="cog-1",
            surface="day",
            period="2026-07-03",
            path="Cogs/2026/07/27/2026-07-03 Fri.md",
            state="open",
        )
        done_item = open_item.model_copy(update={"state": "done", "marker": "[x]"})

        registry.upsert(open_item)
        registry.upsert(done_item)

        self.assertEqual(registry.appearances, [done_item])

    def test_july_third_cog_can_appear_in_june_window_without_forking(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"

            appearances = appearance_set_for_dated_cog(
                "cog-july-3-walmart",
                "2026-07-03",
                cogs_dir,
                planning_anchor_month="2026-06",
            )

            by_surface = {appearance.surface: appearance for appearance in appearances}
            self.assertEqual(set(by_surface), {"day", "week", "month", "5wow", "forward12"})
            self.assertEqual(by_surface["day"].path, "Cogs/2026/07/27/2026-07-03 Fri.md")
            self.assertEqual(by_surface["week"].period, "2026-W27")
            self.assertEqual(by_surface["month"].period, "2026-07")
            self.assertEqual(by_surface["5wow"].period, "2026-06")
            self.assertEqual(by_surface["5wow"].path, "Cogs/2026/2026-06.md")
            self.assertEqual(by_surface["forward12"].period, "2026-06")
            self.assertEqual(len({appearance.cog_id for appearance in appearances}), 1)

    def test_unrendered_window_anchor_does_not_create_fake_window_appearance(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"

            appearances = appearance_set_for_dated_cog(
                "cog-july-3-walmart",
                "2026-07-03",
                cogs_dir,
            )

            self.assertEqual({appearance.surface for appearance in appearances}, {"day", "week", "month"})


if __name__ == "__main__":
    unittest.main()

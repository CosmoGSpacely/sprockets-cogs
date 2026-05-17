import unittest
from pathlib import Path

from specialists import SPECIALISTS, get_specialist, iter_specialists


class Stage45SpecialistCatalogTests(unittest.TestCase):
    def test_catalog_lists_expected_specialists_in_public_order(self):
        self.assertEqual(
            [specialist.specialist_id for specialist in iter_specialists()],
            ["rosie", "rudi", "cogs", "sprockets", "jane", "uniblab"],
        )

    def test_only_rosie_is_always_on(self):
        always_on = [specialist.specialist_id for specialist in SPECIALISTS if specialist.always_on]

        self.assertEqual(always_on, ["rosie"])

    def test_message_bus_is_rudi_contract_not_live_dispatch(self):
        rudi = get_specialist("rudi")

        self.assertIn("agent_message_bus.py", rudi.implementation_files)
        self.assertIn("scripts/agent-message-bus", rudi.commands)
        self.assertFalse(rudi.live_dispatch)

    def test_catalog_points_to_existing_current_surfaces(self):
        root = Path(__file__).resolve().parents[1]

        for specialist in SPECIALISTS:
            with self.subTest(specialist=specialist.specialist_id):
                for path in specialist.implementation_files + specialist.commands:
                    self.assertTrue((root / path).exists(), path)

    def test_subpackage_definitions_match_catalog(self):
        from specialists.cogs import DEFINITION as cogs
        from specialists.jane import DEFINITION as jane
        from specialists.rosie import DEFINITION as rosie
        from specialists.rudi import DEFINITION as rudi
        from specialists.sprockets import DEFINITION as sprockets
        from specialists.uniblab import DEFINITION as uniblab

        self.assertEqual(
            [rosie, rudi, cogs, sprockets, jane, uniblab],
            list(SPECIALISTS),
        )

    def test_unknown_specialist_raises_key_error(self):
        with self.assertRaises(KeyError):
            get_specialist("orbitty")


if __name__ == "__main__":
    unittest.main()


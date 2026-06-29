import tempfile
import unittest
import json
from pathlib import Path

from specialists.cogs.carry import appearance_summary_for_line, carry_current_line
from specialists.cogs.naming import (
    five_wow_path,
    forward12_path,
    monthly_path,
    nested_daily_path,
    weekly_path,
)
from specialists.cogs.planning import ensure_current_surface
from substrate.cog_appearance_registry import CogAppearance, load_registry, save_registry


class Stage135CarryPluginTests(unittest.TestCase):
    def test_ensure_current_surface_returns_all_canonical_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"
            expected = {
                "day": nested_daily_path("2026-12-31", cogs_dir),
                "week": weekly_path("2026-12-31", cogs_dir),
                "5wow": five_wow_path("2026-12-31", cogs_dir),
                "month": monthly_path("2026-12-31", cogs_dir),
                "12mf": forward12_path("2026-12-31", cogs_dir),
            }

            actual = {
                kind: ensure_current_surface(kind, cogs_dir, "2026-12-31")
                for kind in expected
            }

            self.assertEqual(actual, expected)
            self.assertTrue(all(path.exists() for path in actual.values()))

    def test_current_daily_line_carries_to_next_day_and_preserves_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"
            source = nested_daily_path("2026-06-28", cogs_dir)
            source.parent.mkdir(parents=True)
            source.write_text(
                "---\ndate: 2026-06-28\n---\n\n- [ ] Call Sam\n    bring notes\n"
            )

            result = carry_current_line(source, 5)

            self.assertIn("-> 2026-06-29 (appended; 2 registered appearances; cog-", result)
            self.assertIn("- [>] Call Sam", source.read_text())
            destination = nested_daily_path("2026-06-29", cogs_dir)
            self.assertIn("- [ ] Call Sam\n    bring notes", destination.read_text())
            registry = json.loads((Path(tmp) / ".graph" / "cog-appearances.json").read_text())
            self.assertEqual(len(registry["appearances"]), 2)
            self.assertEqual(
                {item["cog_id"] for item in registry["appearances"]},
                {registry["appearances"][0]["cog_id"]},
            )
            self.assertEqual(
                {item["state"] for item in registry["appearances"]},
                {"open", "carried"},
            )
            summary = appearance_summary_for_line(source, 5)
            self.assertIn("2 registered appearance(s)", summary)

    def test_current_week_line_carries_to_next_week_carry_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"
            source = weekly_path("2026-06-28", cogs_dir)
            source.parent.mkdir(parents=True)
            source.write_text("# Week\n\n## CARRY\n\n- [ ] Order filters\n    size 20x20\n")

            result = carry_current_line(source, 5)

            self.assertIn("-> 2026-W27 CARRY (appended;", result)
            self.assertIn("- [>] Order filters", source.read_text())
            destination = weekly_path("2026-06-29", cogs_dir)
            self.assertIn("## CARRY", destination.read_text())
            self.assertIn("- [ ] Order filters\n    size 20x20", destination.read_text())

    def test_current_month_line_carries_across_year_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"
            source = monthly_path("2026-12-01", cogs_dir)
            source.parent.mkdir(parents=True)
            source.write_text("# Month\n\n## CARRY\n\n- [ ] Renew permit\n    county office\n")

            result = carry_current_line(source, 5)

            self.assertIn("-> 2027-01 CARRY (appended;", result)
            self.assertIn("- [>] Renew permit", source.read_text())
            destination = monthly_path("2027-01-01", cogs_dir)
            self.assertIn("- [ ] Renew permit\n    county office", destination.read_text())

    def test_second_carry_reuses_registered_cog_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"
            first = nested_daily_path("2026-06-28", cogs_dir)
            first.parent.mkdir(parents=True)
            first.write_text("---\ndate: 2026-06-28\n---\n\n- [ ] Call Sam\n")

            first_result = carry_current_line(first, 5)
            second = nested_daily_path("2026-06-29", cogs_dir)
            second_line = next(
                index
                for index, line in enumerate(second.read_text().splitlines(), start=1)
                if line == "- [ ] Call Sam"
            )
            second_result = carry_current_line(second, second_line)

            cog_id = first_result.split("cog-", 1)[1].split(")", 1)[0]
            self.assertIn(f"cog-{cog_id}", second_result)
            registry = json.loads((Path(tmp) / ".graph" / "cog-appearances.json").read_text())
            self.assertEqual(len({item["cog_id"] for item in registry["appearances"]}), 1)
            self.assertEqual(len(registry["appearances"]), 3)

    def test_stale_registry_line_repairs_by_unique_text_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"
            source = nested_daily_path("2026-06-28", cogs_dir)
            source.parent.mkdir(parents=True)
            source.write_text("---\ndate: 2026-06-28\n---\n\n- [ ] Call Sam\n")
            carry_current_line(source, 5)
            source.write_text(source.read_text().replace("\n- [>]", "\n\n- [>]"))

            summary = appearance_summary_for_line(source, 6)

            self.assertIn("2 registered appearance(s)", summary)

    def test_ambiguous_registry_hash_refuses_carry(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"
            source = nested_daily_path("2026-06-28", cogs_dir)
            source.parent.mkdir(parents=True)
            source.write_text("---\ndate: 2026-06-28\n---\n\n- [ ] Call Sam\n")
            carry_current_line(source, 5)
            registry = load_registry(Path(tmp))
            original = registry.by_path("Cogs/2026/06/26/2026-06-28 Sun.md")[0]
            registry.upsert(
                CogAppearance(
                    cog_id="cog-conflict",
                    surface=original.surface,
                    period=original.period,
                    path=original.path,
                    line=original.line,
                    text_hash=original.text_hash,
                    marker=original.marker,
                    state=original.state,
                )
            )
            save_registry(Path(tmp), registry)

            with self.assertRaisesRegex(ValueError, "ambiguous locators"):
                carry_current_line(source, 5)

    def test_current_line_refuses_non_task_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "Cogs" / "2026" / "2026-06.md"
            source.parent.mkdir(parents=True)
            source.write_text("# Month\n")

            with self.assertRaisesRegex(ValueError, "not an open or carried Cogs item"):
                carry_current_line(source, 1)


if __name__ == "__main__":
    unittest.main()

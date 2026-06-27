import tempfile
import unittest
from pathlib import Path

from specialists.astro.planning_html_views import build_planning_html_views
from specialists.cogs.naming import nested_daily_path


class Stage134PlanningHtmlViewTests(unittest.TestCase):
    def test_builds_six_complete_views_from_canonical_daily_cogs(self):
        with tempfile.TemporaryDirectory() as tmp:
            cogs_dir = Path(tmp) / "Cogs"
            daily = nested_daily_path("2026-06-26", cogs_dir)
            daily.parent.mkdir(parents=True)
            daily.write_text(
                "---\nnode_type: cogs/daily\ndate: 2026-06-26\n---\n\n"
                "- [ ] FULLBLOOM\n"
                "- [ ] Pickup CSA\n"
            )

            views = build_planning_html_views(cogs_dir, "2026-06-26")

            self.assertEqual(
                [view.kind for view in views],
                ["day", "week", "5wow", "month", "12mf", "annual"],
            )
            by_kind = {view.kind: view.content for view in views}
            self.assertIn("FULLBLOOM", by_kind["day"])
            self.assertIn("Pickup CSA", by_kind["week"])
            self.assertIn("<table", by_kind["5wow"])
            self.assertNotIn("<th", by_kind["5wow"])
            self.assertIn("<th", by_kind["month"])
            self.assertIn("May 2027", by_kind["12mf"])
            self.assertIn("December", by_kind["annual"])


if __name__ == "__main__":
    unittest.main()

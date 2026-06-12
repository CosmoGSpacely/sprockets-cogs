import csv
import tempfile
import unittest
from pathlib import Path

from specialists.cogswell import collections


class Stage102CogswellBridgeTests(unittest.TestCase):
    def write_stamps_csv(self, path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "collection",
                    "catalog_no",
                    "title",
                    "status",
                    "condition",
                    "location",
                    "notes",
                    "updated",
                    "country",
                    "year",
                    "denomination",
                    "series",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "collection": "stamps",
                    "catalog_no": "C3a",
                    "title": "USA 1918 Inverted Jenny",
                    "status": "missing",
                    "condition": "",
                    "location": "",
                    "notes": "Famous airmail invert.",
                    "updated": "2026-05-06",
                    "country": "USA",
                    "year": "1918",
                    "denomination": "24c",
                    "series": "Airmail",
                }
            )

    def test_init_import_and_query_collection_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "cogswell.sqlite3"
            csv_path = root / "stamps.csv"
            self.write_stamps_csv(csv_path)

            collections.init_db(db)
            imported = collections.import_csv(db, csv_path)
            items = collections.query_items(db, collection="stamps", status="missing")

        self.assertEqual(imported, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].catalog_no, "C3a")
        self.assertEqual(items[0].title, "USA 1918 Inverted Jenny")

    def test_query_format_names_database_facts_without_llm_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "cogswell.sqlite3"
            csv_path = root / "stamps.csv"
            self.write_stamps_csv(csv_path)
            collections.import_csv(db, csv_path)

            output = collections.format_query(collections.query_items(db), db_path=db)

        self.assertIn("Cogswell collection query", output)
        self.assertIn("stamps | C3a | missing | USA 1918 Inverted Jenny", output)

    def test_sync_renders_markdown_and_preserves_human_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "cogswell.sqlite3"
            vault = root / "vault"
            csv_path = root / "stamps.csv"
            self.write_stamps_csv(csv_path)
            collections.import_csv(db, csv_path)

            first_paths = collections.sync_markdown(db, vault)
            first_paths[0].write_text(
                first_paths[0].read_text(encoding="utf-8") + "Human note survives.\n",
                encoding="utf-8",
            )
            second_paths = collections.sync_markdown(db, vault)
            rendered = second_paths[0].read_text(encoding="utf-8")

        self.assertEqual(first_paths, second_paths)
        self.assertIn("cogswell_id:", rendered)
        self.assertIn('catalog_no: "C3a"', rendered)
        self.assertIn("related_sprockets: []", rendered)
        self.assertIn("Human note survives.", rendered)

    def test_bridge_report_links_database_identity_to_rendered_resource(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "cogswell.sqlite3"
            vault = root / "vault"
            csv_path = root / "stamps.csv"
            self.write_stamps_csv(csv_path)
            collections.import_csv(db, csv_path)
            collections.sync_markdown(db, vault)

            report = collections.bridge_report(
                db,
                vault,
                collection="stamps",
                catalog_no="C3a",
            )

        self.assertIn("Cogswell bridge inspection", report)
        self.assertIn("- collection: stamps", report)
        self.assertIn("- catalog_no: C3a", report)
        self.assertIn("- rendered_exists: yes", report)
        self.assertIn("- writes: no", report)


if __name__ == "__main__":
    unittest.main()

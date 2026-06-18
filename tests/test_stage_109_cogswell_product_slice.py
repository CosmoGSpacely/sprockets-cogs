import csv
import json
import tempfile
import unittest
from pathlib import Path

from specialists.cogswell import collections


class Stage109CogswellProductSliceTests(unittest.TestCase):
    def write_micro_csv(self, path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "collection",
                    "item_id",
                    "label",
                    "category",
                    "year",
                    "variant",
                    "resource_ref",
                    "owned",
                    "notes",
                ],
            )
            writer.writeheader()
            writer.writerows(
                [
                    {
                        "collection": "lincoln_cents",
                        "item_id": "lincoln-1909-vdb",
                        "label": "1909 VDB Lincoln cent",
                        "category": "coin",
                        "year": "1909",
                        "variant": "VDB",
                        "resource_ref": "",
                        "owned": "yes",
                        "notes": "Seed checklist row; reference details stay external.",
                    },
                    {
                        "collection": "lincoln_cents",
                        "item_id": "lincoln-1943-steel",
                        "label": "1943 steel Lincoln cent",
                        "category": "coin",
                        "year": "1943",
                        "variant": "steel",
                        "resource_ref": "",
                        "owned": "no",
                        "notes": "",
                    },
                    {
                        "collection": "us_stamps",
                        "item_id": "columbian-1893-1c",
                        "label": "1893 Columbian Exposition 1c",
                        "category": "stamp",
                        "year": "1893",
                        "variant": "1c",
                        "resource_ref": "https://www.si.edu/openaccess",
                        "owned": "no",
                        "notes": "Image/resource behavior sample.",
                    },
                    {
                        "collection": "us_stamps",
                        "item_id": "jenny-1918-24c",
                        "label": "1918 24c Curtiss Jenny",
                        "category": "stamp",
                        "year": "1918",
                        "variant": "ordinary",
                        "resource_ref": "https://www.si.edu/openaccess",
                        "owned": "yes",
                        "notes": "",
                    },
                    {
                        "collection": "us_stamps",
                        "item_id": "jenny-1918-24c-invert",
                        "label": "1918 24c Curtiss Jenny invert",
                        "category": "stamp",
                        "year": "1918",
                        "variant": "invert",
                        "resource_ref": "https://www.si.edu/openaccess",
                        "owned": "no",
                        "notes": "",
                    },
                ]
            )

    def test_micro_dataset_imports_coin_and_stamp_rows_with_lean_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "cogswell.sqlite3"
            csv_path = root / "micro.csv"
            self.write_micro_csv(csv_path)

            imported = collections.import_csv(db, csv_path)
            cents = collections.query_items(db, collection="lincoln_cents")
            stamps = collections.query_items(db, collection="us_stamps")

        self.assertEqual(imported, 5)
        self.assertEqual([item.catalog_no for item in cents], ["lincoln-1909-vdb", "lincoln-1943-steel"])
        self.assertEqual(cents[0].title, "1909 VDB Lincoln cent")
        self.assertEqual(cents[0].status, "have")
        self.assertEqual(len(stamps), 3)
        self.assertEqual(stamps[-1].catalog_no, "jenny-1918-24c-invert")

    def test_sync_renders_resource_sprockets_for_both_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "cogswell.sqlite3"
            vault = root / "vault"
            csv_path = root / "micro.csv"
            self.write_micro_csv(csv_path)
            collections.import_csv(db, csv_path)

            paths = collections.sync_markdown(db, vault)
            rendered = "\n".join(path.read_text(encoding="utf-8") for path in paths)

        self.assertEqual(len(paths), 5)
        self.assertIn("Sprockets/collections/lincoln_cents", str(paths[0]))
        self.assertIn('node_type: "sprockets/reference"', rendered)
        self.assertIn('item_id: "lincoln-1909-vdb"', rendered)
        self.assertIn('resource_ref: "https://www.si.edu/openaccess"', rendered)
        self.assertFalse((vault / "Cogs").exists())

    def test_collection_surface_names_owned_status_and_external_reference_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "cogswell.sqlite3"
            csv_path = root / "micro.csv"
            self.write_micro_csv(csv_path)
            collections.import_csv(db, csv_path)

            surface = collections.format_collection_surface(db)

        self.assertIn("# Cogswell Collection Surface - all collections", surface)
        self.assertIn("| lincoln_cents | yes | 1909 VDB Lincoln cent |", surface)
        self.assertIn("| us_stamps | no | 1918 24c Curtiss Jenny invert |", surface)
        self.assertIn("Detailed catalog facts remain in external reference works.", surface)

    def test_export_recreates_seed_facts_as_json_and_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "cogswell.sqlite3"
            csv_path = root / "micro.csv"
            json_path = root / "export.json"
            export_csv_path = root / "export.csv"
            self.write_micro_csv(csv_path)
            collections.import_csv(db, csv_path)

            collections.export_items(db, json_path, collection="us_stamps")
            collections.export_items(db, export_csv_path, collection="lincoln_cents")
            exported_json = json.loads(json_path.read_text(encoding="utf-8"))
            exported_csv = export_csv_path.read_text(encoding="utf-8")

        self.assertEqual(len(exported_json), 3)
        self.assertEqual(exported_json[0]["collection"], "us_stamps")
        self.assertIn("lincoln-1909-vdb", exported_csv)
        self.assertIn("1909 VDB Lincoln cent", exported_csv)

    def test_packaged_stage109_fixture_csvs_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "cogswell.sqlite3"
            fixture_root = Path("specialists/cogswell/fixture_data")

            lincoln_count = collections.import_csv(db, fixture_root / "stage109_lincoln_cents.csv")
            stamp_count = collections.import_csv(db, fixture_root / "stage109_us_stamps.csv")

        self.assertEqual(lincoln_count, 5)
        self.assertEqual(stamp_count, 5)


if __name__ == "__main__":
    unittest.main()

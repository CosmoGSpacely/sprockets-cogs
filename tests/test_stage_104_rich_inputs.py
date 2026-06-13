import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import frontmatter

from specialists import orbit
from specialists.adapters import rich_inputs


class Stage104RichInputTests(unittest.TestCase):
    def test_orbit_facade_names_source_normalization_boundary(self):
        self.assertIs(orbit.rich_inputs, rich_inputs)

    def test_image_without_text_routes_to_resource_review_without_obligation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "tractor tire.jpg"
            image.write_bytes(b"fake image bytes")

            result = rich_inputs.route_rich_input(
                image,
                input_dir=root / "input",
                resource_dir=root / "resources",
            )

            post = frontmatter.load(result.input_path)
            preserved_exists = result.preserved.preserved_path.exists()

        self.assertEqual(result.route.route, "resource_review")
        self.assertEqual(result.route.kind, "image_resource")
        self.assertTrue(preserved_exists)
        self.assertEqual(post["source"], "rich-resource")
        self.assertEqual(post["metadata"]["silent_obligations_allowed"], "no")
        self.assertIn("Do not create a Cog", post.content)

    def test_image_with_ocr_text_routes_to_extraction_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "receipt.png"
            ocr = root / "receipt.txt"
            image.write_bytes(b"fake image bytes")
            ocr.write_text("Buy tire valves at NAPA.", encoding="utf-8")

            result = rich_inputs.route_rich_input(
                image,
                input_dir=root / "input",
                resource_dir=root / "resources",
                ocr_text_path=ocr,
            )

            post = frontmatter.load(result.input_path)

        self.assertEqual(result.route.route, "extraction")
        self.assertEqual(result.route.kind, "scanned_text")
        self.assertEqual(post["source"], "rich-input")
        self.assertEqual(post.content, "Buy tire valves at NAPA.")
        self.assertEqual(post["metadata"]["route"], "extraction")

    def test_text_document_routes_to_extraction_without_optional_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = root / "poster.txt"
            document.write_text("Poster text to capture.", encoding="utf-8")

            result = rich_inputs.route_rich_input(
                document,
                input_dir=root / "input",
                resource_dir=root / "resources",
            )

            post = frontmatter.load(result.input_path)

        self.assertEqual(result.route.kind, "text_document")
        self.assertEqual(post.content, "Poster text to capture.")
        self.assertEqual(post["attachments"][0]["path"], str(result.preserved.preserved_path))

    def test_cli_writes_preserved_resource_and_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "tractor.jpg"
            image.write_bytes(b"fake image bytes")
            stdout = StringIO()

            with redirect_stdout(stdout):
                rich_inputs.main([
                    str(image),
                    "--input-dir",
                    str(root / "input"),
                    "--resource-dir",
                    str(root / "resources"),
                ])

            output = stdout.getvalue()

        self.assertIn("Rich input routing proof", output)
        self.assertIn("- writes: resource,input", output)
        self.assertIn("- silent obligations allowed: no", output)


if __name__ == "__main__":
    unittest.main()

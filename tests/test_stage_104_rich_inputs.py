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

    def test_media_type_sniffs_webp_even_when_extension_is_jpg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "poster.jpg"
            image.write_bytes(b"RIFF\x10\x00\x00\x00WEBPVP8 ")

            result = rich_inputs.route_rich_input(
                image,
                input_dir=root / "input",
                resource_dir=root / "resources",
            )

            post = frontmatter.load(result.input_path)

        self.assertEqual(result.preserved.media_type, "image/webp")
        self.assertEqual(post["metadata"]["media_type"], "image/webp")

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

    def test_gemma_probe_can_route_scanned_text_to_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "paper.jpeg"
            image.write_bytes(b"\xff\xd8\xff fake jpeg")
            probe = rich_inputs.GemmaImageProbe(
                path=image,
                model="gemma4:12b-32k-cosmo",
                source_kind="scanned_text",
                resource_summary="Notebook page with errands.",
                extracted_text="Harbor Freight: tire changer",
                suggested_route="text_extraction",
                confidence="medium",
                needs_review=True,
                valid_json=True,
                latency_seconds=0.25,
                media_type="image/jpeg",
            )

            result = rich_inputs.route_rich_input(
                image,
                input_dir=root / "input",
                resource_dir=root / "resources",
                gemma_probe=probe,
            )

            post = frontmatter.load(result.input_path)

        self.assertEqual(result.route.route, "extraction")
        self.assertEqual(result.route.kind, "scanned_text")
        self.assertEqual(post.content, "Harbor Freight: tire changer")
        self.assertEqual(post["metadata"]["model_source_kind"], "scanned_text")
        self.assertEqual(post["metadata"]["resource_summary"], "Notebook page with errands.")

    def test_gemma_probe_keeps_artifact_review_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "marchant.jpg"
            image.write_bytes(b"RIFF\x10\x00\x00\x00WEBPVP8 ")
            probe = rich_inputs.GemmaImageProbe(
                path=image,
                model="gemma4:12b-32k-cosmo",
                source_kind="poster_artifact",
                resource_summary="Marchant calculator advertisement.",
                extracted_text="EASE that makes figurework output soar",
                suggested_route="review",
                confidence="high",
                needs_review=True,
                valid_json=True,
                latency_seconds=0.25,
                media_type="image/webp",
            )

            result = rich_inputs.route_rich_input(
                image,
                input_dir=root / "input",
                resource_dir=root / "resources",
                gemma_probe=probe,
            )

            post = frontmatter.load(result.input_path)

        self.assertEqual(result.route.route, "resource_review")
        self.assertEqual(result.route.kind, "artifact_resource")
        self.assertEqual(post["source"], "rich-resource")
        self.assertIn("Marchant calculator advertisement.", post.content)
        self.assertIn("Do not create a Cog", post.content)

    def test_run_gemma_image_probe_uses_ollama_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "tractor.jpg"
            image.write_bytes(b"\xff\xd8\xff fake jpeg")
            calls = []

            class Message:
                content = (
                    '{"source_kind":"object_photo","resource_summary":"tractor tire",'
                    '"extracted_text":"","suggested_route":"resource_sprocket",'
                    '"confidence":"high","needs_review":true}'
                )

            class Response:
                message = Message()

            def fake_chat(**kwargs):
                calls.append(kwargs)
                return Response()

            probe = rich_inputs.run_gemma_image_probe(
                image,
                model="gemma4:12b-32k-cosmo",
                chat_client=fake_chat,
            )

        self.assertTrue(probe.valid_json)
        self.assertEqual(probe.source_kind, "object_photo")
        self.assertEqual(probe.suggested_route, "resource_sprocket")
        self.assertEqual(calls[0]["messages"][0]["images"], [str(image)])
        self.assertIn("format", calls[0])

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

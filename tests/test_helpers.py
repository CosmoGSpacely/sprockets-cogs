import tempfile
import unittest
from pathlib import Path

from tests.helpers import write_sprockets_node


class TestWriteSprocketsNode(unittest.TestCase):
    def test_writes_default_heading_body_and_returns_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)

            path = write_sprockets_node(
                vault,
                "projects",
                "learn-python",
                metadata='type: "sprockets/project"\nstatus: "active"\n',
            )

            self.assertEqual(path, vault / "Sprockets" / "projects" / "learn-python.md")
            self.assertEqual(
                path.read_text(),
                '---\ntype: "sprockets/project"\nstatus: "active"\n---\n\n# learn-python\n',
            )

    def test_preserves_explicit_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)

            path = write_sprockets_node(
                vault,
                "notes",
                "retrieval-note",
                body="Custom body\nwith details",
            )

            self.assertEqual(path.read_text(), "---\n---\n\nCustom body\nwith details\n")


if __name__ == "__main__":
    unittest.main()

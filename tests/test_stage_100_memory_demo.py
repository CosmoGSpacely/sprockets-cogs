import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from specialists.rudi import memory_demo
from specialists.rudi.retrieval_eval import RetrievalNode
from specialists.rudi.retrieval_preview import RetrievalPreview


class Stage100MemoryDemoTests(unittest.TestCase):
    def test_memory_demo_shows_retrieved_evidence_trace_and_read_only_boundary(self):
        node = RetrievalNode(
            node_id="projects/tractor",
            title="Remount front tractor tires",
            node_type="sprockets/project",
            path=Path("/vault/Sprockets/projects/tractor.md"),
            text="Need valves, sealant, and tire mounting kit.",
        )

        with patch("specialists.rudi.memory_specialist.MemorySpecialist.retrieval_preview") as mock_preview:
            mock_preview.return_value = RetrievalPreview(
                query="buy tire mounting kit",
                retriever_name="memory-vault",
                vault_dir=Path("/vault"),
                results=(node,),
            )

            output = memory_demo.build_memory_demo(
                "buy tire mounting kit",
                vault_dir=Path("/vault"),
                retriever_name="memory-vault",
            )

        self.assertIn("Sprockets-Cogs read-only memory demo", output)
        self.assertIn("- writes: no", output)
        self.assertIn("- prompt memory context: unchanged", output)
        self.assertIn("Retrieved Evidence", output)
        self.assertIn("projects/tractor [sprockets/project] Remount front tractor tires", output)
        self.assertIn("Trace", output)
        self.assertIn("Memory Guard", output)
        self.assertIn("- top hierarchy parent: Remount front tractor tires", output)

    def test_main_prints_memory_demo(self):
        node = RetrievalNode(
            node_id="projects/tractor",
            title="Remount front tractor tires",
            node_type="sprockets/project",
            path=Path("/vault/Sprockets/projects/tractor.md"),
        )
        buf = io.StringIO()

        with patch("specialists.rudi.memory_specialist.MemorySpecialist.retrieval_preview") as mock_preview:
            mock_preview.return_value = RetrievalPreview(
                query="find tractor memory",
                retriever_name="memory-vault",
                vault_dir=Path("/vault"),
                results=(node,),
            )
            with redirect_stdout(buf):
                memory_demo.main(
                    [
                        "--vault-dir",
                        "/vault",
                        "--retriever",
                        "memory-vault",
                        "find",
                        "tractor",
                        "memory",
                    ]
                )

        output = buf.getvalue()
        self.assertIn("Sprockets-Cogs read-only memory demo", output)
        self.assertIn("- query: find tractor memory", output)
        self.assertIn("- writes: no", output)


if __name__ == "__main__":
    unittest.main()

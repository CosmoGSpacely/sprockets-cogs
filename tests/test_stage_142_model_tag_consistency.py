"""Stage 142 slice 0: exactly one capture model tag across the project.

The project shipped two tags of the same weights, differing only in `num_ctx`.
Measured with one model resident at a time they were indistinguishable -
1.884s vs 1.906s prefill per capture, 4.201s vs 4.258s decode, 8.40 vs 8.42 GB
resident - because peak prompt is ~2,355 tokens and neither window ever binds.

The 16k tag was selected once `OLLAMA_NUM_PARALLEL=2` broke that tie. Ollama
multiplies `num_ctx` by the slot count, so 16k on two slots allocates the same
KV as 32k did on one; with `q8_0` on top, the server runs two cached prefixes
and still leaves 3,332 MiB free where 32k on two slots left 2,432 MiB.

Having both tags installed was never free. The card holds one 12B model, so
naming the other forces an unload and reload measured at **6.4s** and destroys
every cached prefix. That is far larger than any difference this stage's
candidates are trying to measure, so a stray tag reference does not merely
cost time - it silently corrupts a cost comparison.

This guard is therefore about measurement integrity, not tidiness.
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CANONICAL_CAPTURE_MODEL = "gemma4:12b-16k-cosmo"

#: Any `<family>:<size>-<ctx>-cosmo` tag. Matches the retired ones too, which
#: is the point.
_COSMO_TAG_RE = re.compile(r"\b[\w.]+:[\w.]+-\d+k-cosmo\b")

#: Paths that may legitimately name a retired tag: the archive exists to
#: record them, and this test's own docstring quotes one.
_EXEMPT_PREFIXES = ("archive/", "tests/test_stage_142_model_tag_consistency.py")


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.splitlines()


class CaptureModelTagTests(unittest.TestCase):
    def test_production_modules_agree_on_one_tag(self):
        from specialists.rosie import loop
        from specialists.rosie.extractor_classifier import DEFAULT_CAPTURE_MODEL

        self.assertEqual(DEFAULT_CAPTURE_MODEL, CANONICAL_CAPTURE_MODEL)
        self.assertEqual(loop.DEFAULT_MODEL, CANONICAL_CAPTURE_MODEL)

    def test_no_source_file_names_a_retired_cosmo_tag(self):
        offenders: list[str] = []
        for relative in _tracked_files():
            if relative.startswith(_EXEMPT_PREFIXES):
                continue
            path = REPO / relative
            try:
                text = path.read_text(errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue
            for tag in set(_COSMO_TAG_RE.findall(text)):
                if tag != CANONICAL_CAPTURE_MODEL:
                    offenders.append(f"{relative}: {tag}")
        self.assertEqual(
            offenders, [],
            "retired model tags still referenced; naming one costs a 6.4s "
            "model swap and voids the prefix cache",
        )

    def test_exactly_one_live_modelfile(self):
        """A Modelfile in the repo root is a tag someone can recreate. Keeping
        only the selected one is what stops the pair coming back."""

        live = sorted(p.name for p in REPO.glob("Modelfile.*"))
        self.assertEqual(live, ["Modelfile.gemma4-12b-16k-cosmo"])

    def test_the_live_modelfile_matches_the_canonical_tag(self):
        """The filename and the tag the code names must not drift apart. That
        pairing is the only thing tying the checked-in build recipe to the
        model production actually loads, and the two moved independently once
        already."""

        expected = "Modelfile." + CANONICAL_CAPTURE_MODEL.replace(":", "-")
        self.assertTrue((REPO / expected).is_file(), expected)

    def test_archived_modelfiles_are_kept_not_deleted(self):
        """Stage 140 reopens the model comparison and needs these to exist."""

        archived = sorted(p.name for p in (REPO / "archive" / "modelfiles").glob("Modelfile.*"))
        self.assertEqual(
            archived,
            [
                "Modelfile.gemma4-12b-32k-cosmo",
                "Modelfile.phi4-14b-16k-cosmo",
                "Modelfile.qwen3.5-9b-16k-cosmo",
                "Modelfile.qwen3.5-9b-32k-cosmo",
            ],
        )


if __name__ == "__main__":
    unittest.main()

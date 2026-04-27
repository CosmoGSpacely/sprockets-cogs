"""
review.py — Human-in-the-loop review of low-confidence and failed nodes.

Usage (on Rosie, with venv active):
    python review.py

For each file in vault/review/, shows the reason and node data, then prompts:
  a — approve: validate and write to vault, archive the review file
  d — discard: archive the review file without writing to vault
  s — skip:    leave in review/ for later
"""

import json
import re
import shutil
from pathlib import Path

import frontmatter

from models import validate_node
from agentic_loop import ARCHIVE_DIR, REVIEW_DIR, write_node

# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json(content: str) -> dict | None:
    """Extract the first JSON code block from a review file's Markdown body."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _archive(path: Path, approved: bool) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    dest = ARCHIVE_DIR / path.name
    shutil.move(str(path), dest)
    label = "approved → vault" if approved else "discarded"
    print(f"  → {label}  ({dest.name})")


def _prompt_choice() -> str:
    while True:
        choice = input("  (a)pprove  (d)iscard  (s)kip: ").strip().lower()
        if choice in ("a", "d", "s"):
            return choice
        print("  Enter a, d, or s.")


# ── Main ──────────────────────────────────────────────────────────────────────

def review_all() -> None:
    files = sorted(REVIEW_DIR.glob("*.md"))
    if not files:
        print("Nothing in review/. All clear.")
        return

    print(f"\n{'=' * 60}")
    print(f"  {len(files)} item(s) in review/")
    print(f"{'=' * 60}\n")

    approved = discarded = skipped = 0

    for path in files:
        post = frontmatter.load(str(path))

        reason_match = re.search(r"\*\*Reason:\*\* (.+)", post.content)
        reason = reason_match.group(1).strip() if reason_match else "(unknown)"

        raw = _extract_json(post.content)
        if not raw:
            print(f"[UNPARSEABLE] {path.name} — could not extract JSON, skipping.\n")
            skipped += 1
            continue

        print(f"File:       {path.name}")
        print(f"Reason:     {reason}")
        print(f"node_type:  {raw.get('node_type', '?')}")
        print(f"title:      {raw.get('title', '?')}")
        print(f"item_text:  {raw.get('item_text', '?')}")
        print(f"date:       {raw.get('date', '?')}")
        print(f"confidence: {raw.get('confidence', '?')}")

        choice = _prompt_choice()
        print()

        if choice == "s":
            print("  Skipped.\n")
            skipped += 1
            continue

        if choice == "d":
            _archive(path, approved=False)
            discarded += 1

        elif choice == "a":
            raw["confidence"] = "high"   # human approval overrides model confidence
            try:
                node = validate_node(raw)
                write_node(node)
                _archive(path, approved=True)
                approved += 1
            except Exception as e:
                print(f"  [ERROR] Could not write node: {e}")
                print("  Left in review/ for inspection.")
                skipped += 1

        print()

    print(f"Done.  Approved: {approved}  Discarded: {discarded}  Skipped: {skipped}\n")


if __name__ == "__main__":
    review_all()

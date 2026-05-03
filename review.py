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
import sys
from pathlib import Path

import frontmatter

from models import validate_node
from agentic_loop import ARCHIVE_DIR, REVIEW_DIR, write_node

# ── Helpers ───────────────────────────────────────────────────────────────────

def _review_files(review_dir: Path = REVIEW_DIR) -> list[Path]:
    return sorted(review_dir.glob("*.md"))


def _extract_json(content: str) -> dict | None:
    """Extract the first JSON code block from a review file's Markdown body."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _extract_reason(content: str) -> str:
    reason_match = re.search(r"\*\*Reason:\*\* (.+)", content)
    return reason_match.group(1).strip() if reason_match else "(unknown)"


def summarize_review_file(path: Path) -> dict:
    post = frontmatter.load(str(path))
    raw = _extract_json(post.content)
    reason = _extract_reason(post.content)
    return {
        "file": path.name,
        "reason": reason,
        "source": _source_from_reason(reason),
        "node_type": raw.get("node_type", "?") if raw else "?",
        "title": raw.get("title", "?") if raw else "?",
        "item_text": raw.get("item_text", "?") if raw else "?",
        "date": raw.get("date", "?") if raw else "?",
        "confidence": raw.get("confidence", "?") if raw else "?",
        "parseable": raw is not None,
    }


def list_pending(review_dir: Path = REVIEW_DIR) -> list[dict]:
    return [summarize_review_file(path) for path in _review_files(review_dir)]


def print_pending_count(review_dir: Path = REVIEW_DIR) -> None:
    count = len(_review_files(review_dir))
    print(f"{count} item(s) waiting in {review_dir}")


def print_pending_list(review_dir: Path = REVIEW_DIR) -> None:
    items = list_pending(review_dir)
    if not items:
        print("Nothing in review/. All clear.")
        return
    for item in items:
        parse_note = "" if item["parseable"] else " [UNPARSEABLE]"
        print(f"{item['file']}{parse_note}")
        print(f"  source:     {item['source']}")
        print(f"  reason:     {item['reason']}")
        print(f"  node_type:  {item['node_type']}")
        print(f"  title:      {item['title']}")
        print(f"  item_text:  {item['item_text']}")
        print(f"  date:       {item['date']}")
        print(f"  confidence: {item['confidence']}")


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


def _source_from_reason(reason: str) -> str:
    if reason.startswith("openai_fallback_candidate"):
        return "openai fallback candidate"
    if reason.startswith("openai_fallback_invalid"):
        return "openai fallback invalid"
    if reason.startswith("ambiguous hierarchy parent_hint"):
        return "hierarchy ambiguity"
    if "confidence: low" in reason:
        return "local low confidence"
    if reason.startswith("retry failed"):
        return "local retry failure"
    return "local review"


# ── Main ──────────────────────────────────────────────────────────────────────

def review_all() -> None:
    files = _review_files()
    if not files:
        print("Nothing in review/. All clear.")
        return

    print(f"\n{'=' * 60}")
    print(f"  {len(files)} item(s) in review/")
    print(f"{'=' * 60}\n")

    approved = discarded = skipped = 0

    for path in files:
        summary = summarize_review_file(path)
        reason = summary["reason"]
        raw = _extract_json(frontmatter.load(str(path)).content)
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
    args = sys.argv[1:]
    if args == ["--count"]:
        print_pending_count()
    elif args == ["--list"]:
        print_pending_list()
    elif args in ([], ["--interactive"]):
        review_all()
    else:
        print("Usage: python review.py [--count | --list | --interactive]")
        raise SystemExit(2)

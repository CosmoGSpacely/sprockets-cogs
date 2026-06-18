"""
review.py — Human-in-the-loop review of low-confidence and failed nodes.

Usage (on Rosie, with venv active):
    python -m specialists.jane.review

For each file in vault/review/, shows the reason and node data, then prompts:
  a — approve: validate and write to vault, archive the review file
  d — discard: archive the review file without writing to vault
  s — skip:    leave in review/ for later
"""

import json
import hashlib
import re
import shutil
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import frontmatter

from substrate.models import validate_node
from substrate.node_normalization import normalize_raw_node, review_reason_requires_strict_cogs_date
from specialists.rosie.loop import ARCHIVE_DIR, REVIEW_DIR, write_node

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


def _review_source_date(post: frontmatter.Post) -> str | None:
    created = post.get("created")
    if isinstance(created, date):
        return created.isoformat()
    return created if isinstance(created, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", created) else None


def normalize_review_raw(raw: dict, *, reason: str, source_date: str | None = None) -> dict:
    """Normalize raw review JSON before approval validation."""

    return normalize_raw_node(
        raw,
        default_cogs_date=source_date,
        reject_non_default_cogs_date=review_reason_requires_strict_cogs_date(reason),
    )


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
    items = [summarize_review_file(path) for path in _review_files(review_dir)]
    duplicate_hints = _duplicate_hints(items)
    return [
        {**item, "duplicate_hint": duplicate_hints.get(item["file"], "")}
        for item in items
    ]


def _review_text_key(item: dict) -> str:
    values = [
        str(item.get("item_text") or "").strip(),
        str(item.get("title") or "").strip(),
    ]
    text = next((value for value in values if value and value != "?"), "").lower()
    return " ".join(text.split())


def _duplicate_hints(items: list[dict]) -> dict[str, str]:
    groups: dict[str, list[str]] = {}
    for item in items:
        if not item.get("parseable"):
            continue
        key = _review_text_key(item)
        if not key:
            continue
        groups.setdefault(key, []).append(item["file"])

    hints: dict[str, str] = {}
    group_number = 1
    for files in groups.values():
        if len(files) < 2:
            continue
        label = f"possible duplicate group {group_number}: {', '.join(files)}"
        for file_name in files:
            hints[file_name] = label
        group_number += 1
    return hints


def review_report(review_dir: Path = REVIEW_DIR) -> dict:
    items = list_pending(review_dir)
    return {
        "total": len(items),
        "parseable": sum(1 for item in items if item["parseable"]),
        "unparseable": sum(1 for item in items if not item["parseable"]),
        "by_source": dict(sorted(Counter(item["source"] for item in items).items())),
        "by_node_type": dict(sorted(Counter(item["node_type"] for item in items).items())),
        "by_confidence": dict(sorted(Counter(item["confidence"] for item in items).items())),
        "by_reason": dict(sorted(Counter(item["reason"] for item in items).items())),
    }


def print_pending_count(review_dir: Path = REVIEW_DIR) -> None:
    count = len(_review_files(review_dir))
    print(f"{count} item(s) waiting in {review_dir}")


def _print_counter(label: str, values: dict) -> None:
    print(label)
    if not values:
        print("  (none)")
        return
    for key, count in values.items():
        print(f"  {key}: {count}")


def print_pending_report(review_dir: Path = REVIEW_DIR) -> None:
    report = review_report(review_dir)
    print(f"Review queue report for {review_dir}")
    print(f"total:       {report['total']}")
    print(f"parseable:   {report['parseable']}")
    print(f"unparseable: {report['unparseable']}")
    _print_counter("by source:", report["by_source"])
    _print_counter("by node_type:", report["by_node_type"])
    _print_counter("by confidence:", report["by_confidence"])
    _print_counter("by reason:", report["by_reason"])


def _shorten(value: object, limit: int = 120) -> str:
    text = str(value or "")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _markdown_cell(value: object, limit: int = 80) -> str:
    text = _shorten(value, limit)
    return text.replace("|", "\\|")


def review_queue_fingerprint(review_dir: Path = REVIEW_DIR) -> str:
    """Return a stable fingerprint of pending review-file names and contents."""

    digest = hashlib.sha256()
    for path in _review_files(review_dir):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _packet_frontmatter(review_dir: Path, report: dict, items: list[dict]) -> list[str]:
    """Return the review-packet preview frontmatter contract."""

    lines = [
        "---",
        "type: review-packet",
        "status: pending",
        "queue: review",
        f"item_count: {report['total']}",
        f"parseable_count: {report['parseable']}",
        f"unparseable_count: {report['unparseable']}",
        f"queue_fingerprint: {review_queue_fingerprint(review_dir)}",
    ]
    if items:
        lines.append("review_files:")
        lines.extend(f"  - {item['file']}" for item in items)
    else:
        lines.append("review_files: []")
    lines.extend([
        "---",
        "",
    ])
    return lines


def _packet_item_section(item: dict) -> list[str]:
    """Return one human-readable bounded proposed-change section."""

    parse_note = " [UNPARSEABLE]" if not item["parseable"] else ""
    lines = [
        f"### `{_shorten(item['file'], 80)}`{parse_note}",
        "",
        f"- Source: {_shorten(item['source'], 80)}",
        f"- Proposed node: `{_shorten(item['node_type'], 48)}`",
        f"- Title: {_shorten(item['title'], 120)}",
        f"- Item text: {_shorten(item['item_text'], 160)}",
        f"- Date: {_shorten(item['date'], 48)}",
        f"- Confidence: {_shorten(item['confidence'], 48)}",
        f"- Review reason: {_shorten(item['reason'], 180)}",
        f"- Duplicate hint: {_shorten(item.get('duplicate_hint') or '(none)', 180)}",
        "",
    ]
    return lines


def review_packet_markdown(review_dir: Path = REVIEW_DIR) -> str:
    items = list_pending(review_dir)
    report = review_report(review_dir)
    lines = _packet_frontmatter(review_dir, report, items) + [
        "# Sprockets-Cogs Review Packet",
        "",
        "> Preview only until Jane's guarded apply command is run. Generated",
        "> from the canonical review queue. Fill the Decision table",
        "> with `approve`, `discard`, or `skip`; leave blank for pending. Then",
        "> run Jane's packet import/apply preview before confirmed apply.",
        "",
        "## Summary",
        "",
        f"- Total: {report['total']}",
        f"- Parseable: {report['parseable']}",
        f"- Unparseable: {report['unparseable']}",
        "",
    ]
    if not items:
        lines.extend(["No pending review items.", ""])
        return "\n".join(lines)

    lines.extend([
        "## Items",
        "",
        "| File | Source | Type | Confidence | Date | Title | Reason |",
        "|---|---|---|---|---|---|---|",
    ])
    for item in items:
        parse_note = " [UNPARSEABLE]" if not item["parseable"] else ""
        lines.append(
            "| "
            + " | ".join([
                _markdown_cell(f"{item['file']}{parse_note}", 64),
                _markdown_cell(item["source"], 48),
                _markdown_cell(item["node_type"], 32),
                _markdown_cell(item["confidence"], 24),
                _markdown_cell(item["date"], 24),
                _markdown_cell(item["title"], 80),
                _markdown_cell(item["reason"], 120),
            ])
            + " |"
        )
    lines.append("")
    lines.extend([
        "## Decision",
        "",
        "| File | Decision | Notes |",
        "|---|---|---|",
    ])
    for item in items:
        note = item.get("duplicate_hint", "")
        lines.append(
            "| "
            + " | ".join([
                _markdown_cell(item["file"], 64),
                "",
                _markdown_cell(note, 120),
            ])
            + " |"
        )
    lines.extend([
        "",
        "Decision values: `approve`, `discard`, `skip`, or blank for pending.",
        "Always run packet import/apply preview before confirmed apply.",
        "",
    ])
    lines.extend([
        "## Proposed Changes",
        "",
    ])
    for item in items:
        lines.extend(_packet_item_section(item))
    lines.extend([
        "## Review Commands",
        "",
        "- `scripts/review-specialist --packet-import-preview /home/cosmo/sc/output/review-packet.md`",
        "- `scripts/review-specialist --packet-apply-preview /home/cosmo/sc/output/review-packet.md`",
        "- `scripts/review-specialist --packet-apply /home/cosmo/sc/output/review-packet.md --confirm`",
        "- `scripts/review --list` for per-item terminal details.",
        "",
    ])
    return "\n".join(lines)


def print_review_packet_preview(review_dir: Path = REVIEW_DIR) -> None:
    print(review_packet_markdown(review_dir))


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
        post = frontmatter.load(str(path))
        reason = summary["reason"]
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
                raw = normalize_review_raw(
                    raw,
                    reason=reason,
                    source_date=_review_source_date(post),
                )
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
    elif args == ["--report"]:
        print_pending_report()
    elif args == ["--packet-preview"]:
        print_review_packet_preview()
    elif args in ([], ["--interactive"]):
        review_all()
    else:
        print("Usage: python -m specialists.jane.review [--count | --list | --report | --packet-preview | --interactive]")
        raise SystemExit(2)

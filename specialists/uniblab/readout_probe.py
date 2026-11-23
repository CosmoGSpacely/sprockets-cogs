"""Gemma letter-readout probe (builder repo `GEMMA_REVIEW.md`).

Read-only analysis: no vault writes, no change to the live path or prompts.
Both arms classify the same frozen extract, so extract variance stays out of
the comparison.

Checkpoint 3 (this file so far):

- `freeze` runs the shipped extract call once per fixture and saves the items.
- `labels` derives per-item labels from each fixture's `expected` nodes with
  the grader's own matcher (`ExpectedNode.matches`), and reports - never
  guesses - the items it cannot label.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from specialists.rosie.extractor_classifier import ExtractClassifier
from specialists.uniblab.capture_fixtures import (
    CaptureFixture,
    ExpectedNode,
    load_capture_fixtures,
)


DEFAULT_OUT = (
    Path.home()
    / "sprockets-cogs-builder/stages/phase-14.2-classifier-evaluation/readout-probe"
)

TASK = "sprockets/task"
DAILY = "cogs/daily"


# ── Frozen extract ─────────────────────────────────────────────────────────────


def freeze_extract(
    fixtures: Sequence[CaptureFixture],
    classifier: ExtractClassifier | None = None,
) -> dict[str, Any]:
    """Run the shipped extract once per fixture and return the frozen items."""

    classifier = classifier or ExtractClassifier()
    frozen = []
    for fixture in fixtures:
        before = len(classifier.call_stats)
        items = classifier.extract_nodes(fixture.content, now=fixture.now)
        stats = classifier.call_stats[before:]
        frozen.append({
            "fixture_id": fixture.fixture_id,
            "now": fixture.now.isoformat(),
            "items": items,
            "extract_stats": [asdict(s) for s in stats],
        })
    return {
        "model": classifier.config.model,
        "options": classifier.config.chat_options(),
        "frozen_at": datetime.now().isoformat(timespec="seconds"),
        "fixtures": frozen,
    }


# ── Label derivation ───────────────────────────────────────────────────────────


def item_matches(expected: ExpectedNode, item: dict[str, Any]) -> bool:
    """Apply the grader's matcher to an extracted item's text.

    An extracted item has no type, date or parent yet, so those fields are
    copied from the expectation itself: only the `must_include` terms are
    tested, against the item's preserved text.
    """

    return expected.matches({
        "node_type": expected.node_type,
        "date": expected.date,
        "parent_hint": expected.parent_hint,
        "confidence": expected.confidence,
        "item_text": item.get("raw", ""),
    })


def _label_from_types(types: list[str]) -> tuple[str | None, str | None, str]:
    """Map the node types one item fans out to onto (Q1, Q2, status).

    A task paired with a daily Cog is labelled task, with Q2 carrying the
    pairing (`GEMMA_REVIEW.md` 4.3). Any other mix is excluded as `mixed`.
    """

    kinds = set(types)
    if kinds == {TASK, DAILY}:
        return TASK, "yes", "labelled"
    if kinds == {TASK}:
        return TASK, "no", "labelled"
    if len(kinds) == 1:
        return types[0], None, "labelled"
    return None, None, "mixed"


def derive_labels(fixture: CaptureFixture, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-item Q1/Q2 labels for one fixture's frozen items.

    Status per item:
    - `labelled`: every expected node it matches matches no other item.
    - `ambiguous`: some expected node it matches also matches another item,
      so which item carries that node is not determined by the matcher.
    - `unmatched`: no expected node matches (`allowed_extra` noted if any).
    - `mixed`: a type combination 4.3 does not define a label for.
    Expected nodes matched by no item are reported as `missed`.
    """

    expected = list(fixture.expected_nodes)
    matched = [
        [j for j, node in enumerate(expected) if item_matches(node, item)]
        for item in items
    ]
    holders = {j: [i for i, js in enumerate(matched) if j in js] for j in range(len(expected))}

    out_items = []
    for i, item in enumerate(items):
        js = matched[i]
        types = [expected[j].node_type for j in js]
        record: dict[str, Any] = {
            "index": i,
            "raw": item.get("raw", ""),
            "type_hint": item.get("type_hint", ""),
            "matched_types": types,
            "q1": None,
            "q2": None,
        }
        if not js:
            extra = [n.node_type for n in fixture.allowed_extra if item_matches(n, item)]
            record["status"] = "unmatched"
            if extra:
                record["allowed_extra"] = extra
        elif any(len(holders[j]) > 1 for j in js):
            record["status"] = "ambiguous"
            record["shared_with"] = sorted(
                {k for j in js for k in holders[j] if k != i}
            )
        else:
            q1, q2, status = _label_from_types(types)
            record.update(q1=q1, q2=q2, status=status)
        out_items.append(record)

    missed = [
        {"node_type": expected[j].node_type, "must_include": list(expected[j].must_include),
         "date": expected[j].date}
        for j in range(len(expected)) if not holders[j]
    ]
    return {
        "fixture_id": fixture.fixture_id,
        "category": fixture.category,
        "items": out_items,
        "missed": missed,
    }


def summarise_labels(labelled: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    q1: dict[str, int] = {}
    q2: dict[str, int] = {}
    for fixture in labelled:
        for item in fixture["items"]:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
            if item["q1"]:
                q1[item["q1"]] = q1.get(item["q1"], 0) + 1
            if item["q2"]:
                q2[item["q2"]] = q2.get(item["q2"], 0) + 1
    return {
        "status": counts,
        "q1": q1,
        "q2": q2,
        "missed_nodes": sum(len(f["missed"]) for f in labelled),
    }


def label_frozen(frozen: dict[str, Any], fixtures: Sequence[CaptureFixture]) -> dict[str, Any]:
    by_id = {f.fixture_id: f for f in fixtures}
    labelled = [
        derive_labels(by_id[entry["fixture_id"]], entry["items"])
        for entry in frozen["fixtures"]
    ]
    return {"source_frozen_at": frozen["frozen_at"], "summary": summarise_labels(labelled),
            "fixtures": labelled}


# ── CLI ────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gemma letter-readout probe (read-only)")
    parser.add_argument("command", choices=("freeze", "labels"))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--only", nargs="*", default=(), help="fixture ids")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    fixtures = load_capture_fixtures(only=args.only)
    args.out.mkdir(parents=True, exist_ok=True)
    frozen_path = args.out / "frozen-extract.json"
    if args.command == "freeze":
        if frozen_path.exists():
            raise SystemExit(f"{frozen_path} exists; the extract is frozen once")
        frozen = freeze_extract(fixtures)
        frozen_path.write_text(json.dumps(frozen, indent=1, ensure_ascii=False) + "\n")
        print(f"froze {len(frozen['fixtures'])} fixtures -> {frozen_path}")
        return
    frozen = json.loads(frozen_path.read_text())
    labels = label_frozen(frozen, fixtures)
    labels_path = args.out / "labels.json"
    labels_path.write_text(json.dumps(labels, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(labels["summary"], indent=1))
    print(f"-> {labels_path}")


if __name__ == "__main__":
    main()

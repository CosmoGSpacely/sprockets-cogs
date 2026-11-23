"""Gemma letter-readout probe (builder repo `GEMMA_REVIEW.md`).

Read-only analysis: no vault writes, no change to the live path or prompts.
Both arms classify the same frozen extract, so extract variance stays out of
the comparison.

- `freeze` runs the shipped extract call once per fixture and saves the items.
- `labels` derives per-item labels from each fixture's `expected` nodes with
  the grader's own matcher (`ExpectedNode.matches`), and reports - never
  guesses - the items it cannot label. Hand labels, where accepted, live in a
  separate file and are marked `source: hand`.
- `readout` is the letter readout of arXiv 2610.17205 (one closed question,
  options lettered, probabilities renormalised over the option letters), in
  the layout checkpoint 2 verified against Ollama's Gemma 4 rendering.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import ollama

from specialists.rosie.extractor_classifier import (
    DEFAULT_CONTEXT_MAX_CHARS,
    ExtractClassifier,
    date_anchor,
    truncate_context,
)
from specialists.rosie.prompts import CLASSIFY_SYSTEM
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
CONTACT = "sprockets/contact"
ENTITY = "sprockets/entity"
NOTE = "sprockets/note"
NODE_TYPES = (DAILY, TASK, CONTACT, ENTITY, NOTE)

LETTERS = "ABCDEFGHIJKLMNOP"
TOP_LOGPROBS_CAP = 20
"""Ollama 0.40.16 refuses more (checkpoint 2)."""


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
            record.update(q1=q1, q2=q2, status=status, source="matcher")
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


def apply_hand_labels(labelled: list[dict[str, Any]], hand: list[dict[str, Any]]) -> list[str]:
    """Label ambiguous items from accepted hand labels; return unused entries.

    Only `ambiguous` items take a hand label: a hand label never overrides the
    matcher. An entry that finds no ambiguous item is returned, so a re-frozen
    extract that changed an item's text cannot silently drop a hand label.
    """

    unused = []
    for entry in hand:
        hits = [
            item
            for fixture in labelled if fixture["fixture_id"] == entry["fixture_id"]
            for item in fixture["items"]
            if item["raw"] == entry["raw"] and item["status"] == "ambiguous"
        ]
        if len(hits) != 1:
            unused.append(f"{entry['fixture_id']}: {entry['raw']!r}")
            continue
        hits[0].update(
            status="labelled", source="hand", q1=entry["q1"], q2=entry.get("q2"),
            reason=entry["reason"],
        )
    return unused


def summarise_labels(labelled: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    by_source: dict[str, dict[str, dict[str, int]]] = {}
    for fixture in labelled:
        for item in fixture["items"]:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
            if item["status"] != "labelled":
                continue
            source = by_source.setdefault(item["source"], {"q1": {}, "q2": {}})
            for q in ("q1", "q2"):
                if item[q]:
                    source[q][item[q]] = source[q].get(item[q], 0) + 1
    return {
        "status": counts,
        "by_source": by_source,
        "missed_nodes": sum(len(f["missed"]) for f in labelled),
    }


def label_frozen(
    frozen: dict[str, Any],
    fixtures: Sequence[CaptureFixture],
    hand: list[dict[str, Any]] = (),
) -> dict[str, Any]:
    by_id = {f.fixture_id: f for f in fixtures}
    labelled = [
        derive_labels(by_id[entry["fixture_id"]], entry["items"])
        for entry in frozen["fixtures"]
    ]
    unused = apply_hand_labels(labelled, list(hand))
    return {"source_frozen_at": frozen["frozen_at"], "summary": summarise_labels(labelled),
            "unused_hand_labels": unused, "fixtures": labelled}


# ── Readout ────────────────────────────────────────────────────────────────────


READOUT_SYSTEM = (
    "Apply the supplied criterion to the supplied evidence. Choose exactly one "
    "listed option. Respond with only its uppercase letter, with no explanation "
    "or reasoning."
)
"""The paper's system text (App. A), verbatim."""


@dataclass(frozen=True)
class Readout:
    """One closed question's answer: a probability per option id."""

    probs: dict[str, float]
    """Option id -> probability, renormalised over the option letters."""

    letters: dict[str, str]
    """Option id -> the letter it was shown as."""

    missing: tuple[str, ...]
    """Option ids whose letter fell outside `top_logprobs`, floored."""

    outside_mass: float
    """Top-k probability on tokens that are not option letters."""

    top_token: str
    seconds: float
    prompt_tokens: int | None

    @property
    def answer(self) -> str:
        return max(self.probs, key=self.probs.get)


def readout_messages(evidence: str, criterion: str, options: Sequence[tuple[str, str]]) -> list[dict]:
    """The paper's layout: system text, then one line of JSON (App. A)."""

    user = json.dumps({
        "evidence": evidence,
        "criterion": criterion,
        "options": [
            {"letter": LETTERS[i], "description": f"{option_id}: {text}"}
            for i, (option_id, text) in enumerate(options)
        ],
    }, ensure_ascii=False)
    return [{"role": "system", "content": READOUT_SYSTEM}, {"role": "user", "content": user}]


def _get(obj: Any, key: str) -> Any:
    return obj[key] if isinstance(obj, dict) else getattr(obj, key)


def letter_probs(top_logprobs: Sequence[Any], letters: Sequence[str]) -> tuple[dict[str, float], tuple[str, ...], float]:
    """Renormalise top-k logprobs over the option letters (paper Eq. 1).

    Logprobs differ from logits by a constant, so a softmax over the letters'
    logprobs equals the paper's softmax over their logits. A letter outside
    the top-k is floored at the lowest logprob returned - an upper bound on
    its true value - and reported as missing.
    """

    seen = {_get(t, "token"): _get(t, "logprob") for t in top_logprobs}
    floor = min(seen.values())
    missing = tuple(letter for letter in letters if letter not in seen)
    logp = {letter: seen.get(letter, floor) for letter in letters}
    peak = max(logp.values())
    weights = {letter: math.exp(v - peak) for letter, v in logp.items()}
    total = sum(weights.values())
    outside = sum(math.exp(v) for token, v in seen.items() if token not in letters)
    return {letter: w / total for letter, w in weights.items()}, missing, outside


def readout(
    evidence: str,
    criterion: str,
    options: Sequence[tuple[str, str]],
    *,
    chat_client: Any = None,
    model: str | None = None,
) -> Readout:
    """Ask one closed question; return a probability per option id.

    One call, one generated token, thinking off: Ollama then renders the
    paper's prompt exactly, closed empty thought block included (checkpoint 2).
    """

    if not 2 <= len(options) <= len(LETTERS):
        raise ValueError(f"readout takes 2-{len(LETTERS)} options, got {len(options)}")
    chat_client = chat_client or ollama.chat
    messages = readout_messages(evidence, criterion, options)
    started = time.monotonic()
    response = chat_client(
        model=model or ExtractClassifier().config.model,
        messages=messages,
        think=False,
        logprobs=True,
        top_logprobs=TOP_LOGPROBS_CAP,
        options={"temperature": 0, "num_predict": 1},
    )
    seconds = time.monotonic() - started
    (first,) = _get(response, "logprobs")[:1]
    letters = {option_id: LETTERS[i] for i, (option_id, _) in enumerate(options)}
    by_letter, missing, outside = letter_probs(_get(first, "top_logprobs"), list(letters.values()))
    by_id = {v: k for k, v in letters.items()}
    return Readout(
        probs={option_id: by_letter[letter] for option_id, letter in letters.items()},
        letters=letters,
        missing=tuple(by_id[letter] for letter in missing),
        outside_mass=outside,
        top_token=_get(first, "token"),
        seconds=seconds,
        prompt_tokens=_get(response, "prompt_eval_count") if not isinstance(response, dict)
        else response.get("prompt_eval_count"),
    )


# ── The two questions (GEMMA_REVIEW 4.3) ───────────────────────────────────────


def classify_rule_text(system: str = CLASSIFY_SYSTEM) -> tuple[dict[str, str], str]:
    """Lift the node-type rules and the Tasks block out of `CLASSIFY_SYSTEM`.

    The readout gets the generated call's own rule text, so the arms differ in
    mechanism, not instructions. Raises if the prompt's shape has changed.
    """

    types = dict(re.findall(r"^  ((?:cogs|sprockets)/\w+)\s+(.+)$", system, re.M))
    if set(types) != set(NODE_TYPES):
        raise ValueError(f"CLASSIFY_SYSTEM node_type rules changed: {sorted(types)}")
    tasks = re.search(r"^Tasks:\n(.*?)\n\n", system, re.S | re.M)
    if not tasks:
        raise ValueError("CLASSIFY_SYSTEM has no Tasks: block")
    return types, "Tasks:\n" + tasks.group(1)


def readout_evidence(fixture: CaptureFixture, item_raw: str) -> str:
    """Date anchor, the context the generated call gets, the capture, the item."""

    return (
        f"{date_anchor(fixture.now)}\n\n"
        f"{truncate_context(fixture.context, DEFAULT_CONTEXT_MAX_CHARS)}\n\n"
        f"Capture:\n{fixture.content}\n\n"
        f"Item: {item_raw}"
    )


Q1_CRITERION = (
    "Which node_type should this item become? If it becomes both a "
    "sprockets/task and a cogs/daily, choose sprockets/task."
)
"""The second sentence is 4.3's labelling convention: Q2 carries the pairing."""
Q2_CRITERION = (
    "This item is a sprockets/task. Should it also be placed on a day as a "
    "cogs/daily, making two nodes?"
)


def q1_options(order: str = "forward") -> list[tuple[str, str]]:
    types, _ = classify_rule_text()
    options = [(t, types[t]) for t in NODE_TYPES]
    return options[::-1] if order == "reverse" else options


def q2_options(order: str = "forward") -> list[tuple[str, str]]:
    """Yes/no in the paper's form: A = true, B = false."""

    options = [
        ("true", "two nodes: sprockets/task + cogs/daily"),
        ("false", "sprockets/task only"),
    ]
    return options[::-1] if order == "reverse" else options


def q1_criterion() -> str:
    _, tasks = classify_rule_text()
    return f"{Q1_CRITERION}\n\n{tasks}"


def q2_criterion() -> str:
    _, tasks = classify_rule_text()
    return f"{Q2_CRITERION}\n\n{tasks}"


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
    hand_path = args.out / "hand-labels.json"
    hand = json.loads(hand_path.read_text())["labels"] if hand_path.exists() else []
    labels = label_frozen(frozen, fixtures, hand)
    labels_path = args.out / "labels.json"
    labels_path.write_text(json.dumps(labels, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(labels["summary"], indent=1))
    if labels["unused_hand_labels"]:
        print("UNUSED hand labels:", *labels["unused_hand_labels"], sep="\n  ")
    print(f"-> {labels_path}")


if __name__ == "__main__":
    main()

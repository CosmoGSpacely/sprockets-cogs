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


# ── Arms (GEMMA_REVIEW 4.4) ────────────────────────────────────────────────────


def _labelled_items(labels: dict[str, Any]):
    for fixture in labels["fixtures"]:
        for item in fixture["items"]:
            if item["status"] == "labelled":
                yield fixture["fixture_id"], item


def run_generated_arm(
    frozen: dict[str, Any],
    fixtures: Sequence[CaptureFixture],
    repeats: int = 3,
    classifier: ExtractClassifier | None = None,
) -> list[dict[str, Any]]:
    """Arm G: the shipped `classify_nodes` on the frozen items, repeated."""

    classifier = classifier or ExtractClassifier()
    by_id = {f.fixture_id: f for f in fixtures}
    runs = []
    for repeat in range(repeats):
        for entry in frozen["fixtures"]:
            if not entry["items"]:
                continue
            fixture = by_id[entry["fixture_id"]]
            before = len(classifier.call_stats)
            nodes = classifier.classify_nodes(entry["items"], fixture.context, now=fixture.now)
            stats = classifier.call_stats[before:]
            runs.append({
                "repeat": repeat,
                "fixture_id": fixture.fixture_id,
                "nodes": nodes,
                "seconds": sum(s.total_seconds or 0 for s in stats),
            })
    return runs


def _readout_record(result: Readout) -> dict[str, Any]:
    return {
        "probs": result.probs,
        "answer": result.answer,
        "missing": list(result.missing),
        "outside_mass": result.outside_mass,
        "top_token": result.top_token,
        "seconds": result.seconds,
        "prompt_tokens": result.prompt_tokens,
    }


def run_readout_arms(
    labels: dict[str, Any],
    fixtures: Sequence[CaptureFixture],
    chat_client: Any = None,
) -> list[dict[str, Any]]:
    """Arms R and R-perm: Q1 for every labelled item, Q2 for items labelled task.

    Q2 is gated on the *label*, not on R's Q1 answer, so both arms answer Q2
    on the same items. That is an oracle gate, stated in the report.
    """

    by_id = {f.fixture_id: f for f in fixtures}
    records = []
    for order in ("forward", "reverse"):
        for fixture_id, item in _labelled_items(labels):
            fixture = by_id[fixture_id]
            evidence = readout_evidence(fixture, item["raw"])
            questions = [("q1", q1_criterion(), q1_options(order))]
            if item["q1"] == TASK:
                questions.append(("q2", q2_criterion(), q2_options(order)))
            for question, criterion, options in questions:
                result = readout(evidence, criterion, options, chat_client=chat_client)
                records.append({
                    "order": order, "fixture_id": fixture_id, "index": item["index"],
                    "question": question, **_readout_record(result),
                })
    return records


# ── Report (GEMMA_REVIEW 4.5) ──────────────────────────────────────────────────


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def assign_nodes(items: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> tuple[list[list[dict]], list[dict]]:
    """Assign each generated node to the frozen item its text overlaps most.

    Overlap is the share of the item's word tokens found in the node's title
    and item_text, ties broken by the count of shared tokens - so "Check and
    charge Dale battery" goes to that item, not to a bare "Dale" item that it
    also covers entirely. A node still tied between items, or overlapping none, is
    returned unassigned. This is the step the label matcher cannot do for
    fixtures 06 and 11 (every node there names the same person), so it uses
    the item's own words instead of the fixture's terms.
    """

    assigned: list[list[dict]] = [[] for _ in items]
    unassigned = []
    item_tokens = [_tokens(item.get("raw", "")) for item in items]
    for node in nodes:
        text = _tokens(f"{node.get('title', '')} {node.get('item_text', '')}")
        scores = [
            (len(text & toks) / len(toks), len(text & toks)) if toks else (0.0, 0)
            for toks in item_tokens
        ]
        best = max(scores, default=(0.0, 0))
        winners = [i for i, score in enumerate(scores) if score == best]
        if best[0] == 0.0 or len(winners) > 1:
            unassigned.append(node)
        else:
            assigned[winners[0]].append(node)
    return assigned, unassigned


def generated_answers(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Arm G's answers for one item, from the nodes assigned to it.

    Q1 reduces the node types as the labels do (task + daily -> task); no
    nodes is `none`, any other mix is `mixed` - both wrong for every label.
    Q2 is whether any assigned node is a daily Cog. `task_dated` is whether
    a task node carries a date: under the preserve-only chain that, not a
    paired Cog, is finding 99's failure (Stage 143 GROK), so the D121 slice
    reports both.
    """

    types = [n.get("node_type", "") for n in nodes]
    if not types:
        q1 = "none"
    else:
        q1, _, status = _label_from_types(types)
        q1 = q1 if status == "labelled" else "mixed"
    return {
        "q1": q1,
        "q2": "yes" if DAILY in types else "no",
        "task_dated": any(n.get("node_type") == TASK and n.get("date") for n in nodes),
        "low": any(n.get("confidence") == "low" for n in nodes),
        "types": types,
    }


Q2_IDS = {"yes": "true", "no": "false"}


def fit_temperature(prob_rows: list[dict[str, float]], targets: list[str]) -> float:
    """NLL-minimising temperature, floored at 1 as in the paper (never sharpen)."""

    def nll(t: float) -> float:
        total = 0.0
        for probs, target in zip(prob_rows, targets):
            scaled = scale(probs, t)
            total -= math.log(max(scaled[target], 1e-300))
        return total

    grid = [1.0 + 0.05 * k for k in range(0, 1981)]  # 1.0 .. 100.0
    return min(grid, key=nll)


def scale(probs: dict[str, float], t: float) -> dict[str, float]:
    logs = {k: math.log(max(v, 1e-300)) / t for k, v in probs.items()}
    peak = max(logs.values())
    weights = {k: math.exp(v - peak) for k, v in logs.items()}
    total = sum(weights.values())
    return {k: w / total for k, w in weights.items()}


def brier(probs: dict[str, float], target: str) -> float:
    return sum((p - (1.0 if k == target else 0.0)) ** 2 for k, p in probs.items())


def _halves(rows: list[tuple[float, bool]]) -> tuple[float | None, float | None, int]:
    """Accuracy in the most and least confident halves (ties keep input order)."""

    ranked = sorted(rows, key=lambda r: -r[0])
    half = len(ranked) // 2
    top, bottom = ranked[:half], ranked[half:]
    acc = lambda part: sum(ok for _, ok in part) / len(part) if part else None
    return acc(top), acc(bottom), len(ranked)


def _score_readout(rows: list[dict[str, Any]], targets: dict[tuple, str]) -> dict[str, Any]:
    keyed = [(r, targets[(r["fixture_id"], r["index"])]) for r in rows]
    correct = [r["answer"] == t for r, t in keyed]
    top, bottom, n = _halves([(max(r["probs"].values()), ok) for (r, _), ok in zip(keyed, correct)])
    return {
        "n": n,
        "correct": sum(correct),
        "brier": sum(brier(r["probs"], t) for r, t in keyed) / n if n else None,
        "acc_confident_half": top,
        "acc_unconfident_half": bottom,
    }


def build_report(labels: dict[str, Any], arms: dict[str, Any]) -> dict[str, Any]:
    frozen_items = {f["fixture_id"]: f["items"] for f in arms["frozen"]["fixtures"]}
    label_rows = {(fid, item["index"]): item for fid, item in _labelled_items(labels)}
    report: dict[str, Any] = {"questions": {}, "items": [], "unassigned_g_nodes": []}

    # G: per repeat, per item answers.
    g_answers: dict[tuple, list[dict]] = {key: [] for key in label_rows}
    g_seconds: dict[str, list[float]] = {}
    for run in arms["generated"]:
        items = frozen_items[run["fixture_id"]]
        assigned, unassigned = assign_nodes(items, run["nodes"])
        g_seconds.setdefault(run["fixture_id"], []).append(run["seconds"])
        for node in unassigned:
            report["unassigned_g_nodes"].append({"repeat": run["repeat"],
                                                 "fixture_id": run["fixture_id"], "node": node})
        for index, nodes in enumerate(assigned):
            key = (run["fixture_id"], index)
            if key in g_answers:
                g_answers[key].append(generated_answers(nodes))

    readouts = {(r["order"], r["question"], r["fixture_id"], r["index"]): r for r in arms["readout"]}

    for question in ("q1", "q2"):
        keys = [k for k, item in label_rows.items() if item[question]]
        if question == "q1":
            targets = {k: label_rows[k]["q1"] for k in keys}
        else:
            targets = {k: Q2_IDS[label_rows[k]["q2"]] for k in keys}
        g_target = {k: label_rows[k][question] for k in keys}
        section: dict[str, Any] = {}
        for source in ("matcher", "all"):
            subset = [k for k in keys if source == "all" or label_rows[k]["source"] == source]
            if not subset:
                continue
            # G: accuracy per repeat; empirical distribution across repeats.
            per_repeat = [
                sum(g_answers[k][r][question] == g_target[k] for k in subset)
                for r in range(min(len(g_answers[k]) for k in subset))
            ]
            g_rows, g_brier = [], 0.0
            for k in subset:
                answers = [a[question] for a in g_answers[k]]
                dist = {a: answers.count(a) / len(answers) for a in set(answers)}
                dist.setdefault(g_target[k], 0.0)
                g_brier += brier(dist, g_target[k])
                modal = max(dist, key=dist.get)
                low = any(a["low"] for a in g_answers[k])
                g_rows.append(((dist[modal], 0 if low else 1), modal == g_target[k]))
            top, bottom, n = _halves([(conf[0] + 0.001 * conf[1], ok) for conf, ok in g_rows])
            arm_g = {
                "n": n, "correct_per_repeat": per_repeat, "brier_from_agreement": g_brier / n,
                "acc_confident_half": top, "acc_unconfident_half": bottom,
                "items_low_confidence": sum(1 for conf, _ in g_rows if conf[1] == 0),
            }
            fwd = [readouts[("forward", question, *k)] for k in subset]
            rev = [readouts[("reverse", question, *k)] for k in subset]
            arm_r = _score_readout(fwd, targets)
            arm_rp = _score_readout(rev, targets)
            flips = sum(f["answer"] != r["answer"] for f, r in zip(fwd, rev))
            # R-T: leave-one-out temperature on R's probabilities.
            temps, scaled_rows = [], []
            for i, row in enumerate(fwd):
                others = [r for j, r in enumerate(fwd) if j != i]
                t = fit_temperature([r["probs"] for r in others],
                                    [targets[(r["fixture_id"], r["index"])] for r in others])
                temps.append(t)
                scaled_rows.append({**row, "probs": scale(row["probs"], t)})
            arm_rt = _score_readout(scaled_rows, targets)
            arm_rt["temperature_all"] = fit_temperature(
                [r["probs"] for r in fwd], [targets[(r["fixture_id"], r["index"])] for r in fwd])
            arm_rt["temperature_loo_range"] = [min(temps), max(temps)]
            # Order-averaged probabilities (computed, no calls).
            averaged = [{**f, "probs": {k: (f["probs"][k] + r["probs"][k]) / 2 for k in f["probs"]}}
                        for f, r in zip(fwd, rev)]
            for row in averaged:
                row["answer"] = max(row["probs"], key=row["probs"].get)
            section[source] = {
                "G": arm_g, "R": arm_r, "R-perm": arm_rp, "R-T": arm_rt,
                "R-avg": _score_readout(averaged, targets),
                "order_flips": flips,
            }
        report["questions"][question] = section

    # Per-item listing (the D121 slice and every disagreement read from here).
    for key, item in label_rows.items():
        row = {
            "fixture_id": key[0], "index": key[1], "raw": item["raw"], "source": item["source"],
            "label_q1": item["q1"], "label_q2": item["q2"],
            "G_q1": [a["q1"] for a in g_answers[key]], "G_q2": [a["q2"] for a in g_answers[key]],
            "G_task_dated": [a["task_dated"] for a in g_answers[key]],
        }
        for question in ("q1", "q2"):
            for order in ("forward", "reverse"):
                r = readouts.get((order, question, *key))
                if r:
                    row[f"R_{question}_{order}"] = (r["answer"], round(r["probs"][r["answer"]], 3))
        report["items"].append(row)

    # Latency.
    r_by_fixture: dict[str, list[float]] = {}
    q_seconds: dict[str, list[float]] = {"q1": [], "q2": []}
    for r in arms["readout"]:
        if r["order"] == "forward":
            r_by_fixture.setdefault(r["fixture_id"], []).append(r["seconds"])
            q_seconds[r["question"]].append(r["seconds"])
    report["latency"] = {
        "readout_mean_seconds": {q: sum(v) / len(v) for q, v in q_seconds.items() if v},
        "per_fixture": {
            fid: {"readout_total": round(sum(v), 2),
                  "readout_calls": len(v),
                  "G_classify_mean": round(sum(g_seconds[fid]) / len(g_seconds[fid]), 2)}
            for fid, v in r_by_fixture.items()
        },
    }
    report["readout_missing_letters"] = sum(len(r["missing"]) for r in arms["readout"])
    report["readout_max_outside_mass"] = max(r["outside_mass"] for r in arms["readout"])
    return report


# ── CLI ────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gemma letter-readout probe (read-only)")
    parser.add_argument("command", choices=("freeze", "labels", "arms", "report"))
    parser.add_argument("--repeats", type=int, default=3)
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
    labels_path = args.out / "labels.json"
    arms_path = args.out / "arms.json"
    if args.command == "arms":
        labels = json.loads(labels_path.read_text())
        started = datetime.now().isoformat(timespec="seconds")
        readout_records = run_readout_arms(labels, fixtures)
        generated = run_generated_arm(frozen, fixtures, repeats=args.repeats)
        arms = {"started": started, "finished": datetime.now().isoformat(timespec="seconds"),
                "frozen": frozen, "readout": readout_records, "generated": generated}
        arms_path.write_text(json.dumps(arms, indent=1, ensure_ascii=False) + "\n")
        print(f"{len(readout_records)} readouts, {len(generated)} classify calls -> {arms_path}")
        return
    if args.command == "report":
        report = build_report(json.loads(labels_path.read_text()), json.loads(arms_path.read_text()))
        report_path = args.out / "report.json"
        report_path.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
        print(json.dumps({k: report[k] for k in report if k != "items"}, indent=1)[:20000])
        print(f"-> {report_path}")
        return
    hand_path = args.out / "hand-labels.json"
    hand = json.loads(hand_path.read_text())["labels"] if hand_path.exists() else []
    labels = label_frozen(frozen, fixtures, hand)
    labels_path.write_text(json.dumps(labels, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(labels["summary"], indent=1))
    if labels["unused_hand_labels"]:
        print("UNUSED hand labels:", *labels["unused_hand_labels"], sep="\n  ")
    print(f"-> {labels_path}")


if __name__ == "__main__":
    main()

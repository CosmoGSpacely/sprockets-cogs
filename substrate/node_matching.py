"""Pair a classified node with the raw capture item it came from.

Extracted from `substrate/time_context.py` in Stage 142 slice 4, where a third
call site appeared. Two copies were a duplication (finding 53); three is a
missing module.

The problem it solves is structural, not incidental. `classify_nodes` does not
emit one node per raw item - the named-person rule yields two, a multi-day
setting yields one per workday, and recurrence expansion multiplies further -
so `raw_nodes[i]` and `classified[i]` describe different things as soon as any
of those fire. Pairing by index moved a date onto an unrelated node (finding
42), and left every occurrence after the first without its time span (finding
80).
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

#: Words too common to be evidence of shared origin.
MATCH_STOPWORDS = {
    "a", "an", "and", "at", "for", "from", "in", "of", "on", "re", "the", "to",
    "with", "is", "it", "my", "need", "about", "up",
}

#: Below this, an overlap is coincidence rather than evidence of shared origin.
MATCH_MIN_SCORE = 0.15


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def match_words(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z0-9:]+", text.lower())
        if word not in MATCH_STOPWORDS
    }


def similarity(left: set[str], right: set[str]) -> float:
    """Jaccard overlap. 1.0 is identical, 0.0 is disjoint."""

    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def match_raw_index(
    node: Mapping[str, object],
    raw_nodes: Sequence[Mapping[str, object]],
) -> int | None:
    """Find the raw item a classified node came from, by content not position.

    Returns None when nothing matches well enough, or when the best two
    candidates tie - both mean "no evidence", and using the node's own text
    alone is safer than guessing between them.
    """

    node_words = match_words(
        f"{_string(node.get('title'))} {_string(node.get('item_text'))}"
    )
    if not node_words:
        return None

    scored: list[tuple[float, int]] = []
    for index, raw in enumerate(raw_nodes):
        raw_words = match_words(_string(raw.get("raw")))
        if not raw_words:
            continue
        score = similarity(node_words, raw_words)
        if score <= 0:
            continue
        scored.append((score, index))

    if not scored:
        return None
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    best_score, best_index = scored[0]
    if best_score < MATCH_MIN_SCORE:
        return None
    if len(scored) > 1 and scored[1][0] == best_score:
        return None
    return best_index


def raw_text_for(
    node: Mapping[str, object],
    raw_nodes: Sequence[Mapping[str, object]],
) -> str:
    """The raw text a node came from, or "" when it cannot be identified.

    Returning "" rather than falling back to a positional guess is the whole
    point: a caller that gets "" applies no raw-derived behaviour, which is
    correct. A caller that gets the wrong item's text applies the wrong
    behaviour confidently.
    """

    index = match_raw_index(node, raw_nodes)
    if index is None:
        return ""
    return _string(raw_nodes[index].get("raw"))

"""Deterministic segmentation of capture text into candidate items.

Stage 142 candidate 5 proposes that code, not a model, decides where one item
ends and the next begins. This module is that code. It answers exactly one
question - *how many items is this text, and what is each one's text* - and
answers nothing else. Typing, dating, and hierarchy stay downstream.

The case for it is Stage 141 finding 60: the extract call split "Check and
charge Dale battery" into two items because a prompt rule about counted repeats
was edited elsewhere. Segmentation of line-oriented input is not a language
judgement, and a rule that changes when an unrelated sentence is added to a
prompt is not a rule.

The case against it is the verb lexicon below. A deterministic clause splitter
needs to know what an imperative verb looks like, and there is no way to know
that without a word list. The list is the honest cost of this candidate: it
covers this project's captures, it will miss verbs nobody has written yet, and
missing one under-splits silently. That tradeoff is what Stage 142 slice 1
measures - it is not hidden here, and it is not solved here.

Because the lexicon has a floor, `segment_capture` reports whether it believes
the input is the kind of text it can segment. Unpunctuated dictation is not,
and the caller is expected to fall back to a model call rather than accept a
confident wrong answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Imperative verbs seen in this project's captures, plus close neighbours.
# Deliberately not a general English verb list: a large list splits more often,
# and over-splitting produces two errands the user must reconcile by hand,
# which is worse than one errand carrying a trailing clause.
IMPERATIVE_VERBS = frozenset(
    """
    add bring book buy call cancel charge check clean confirm cut deliver
    design drop email empty feed fill finish fix gas grab hang haul install
    load mail meet mount move mow need order pack paint patch pay pick print
    pull put reach read relocate remind remount remove renew repair replace
    return review run sand schedule seal send sharpen sign sort split stack
    start stop swap take tear text unload update visit wash water wire write
    """.split()
)

# Conjunctions that may begin a new clause. Ordered longest-first so that
# ", and" is consumed before the bare "and" inside it.
_CLAUSE_SPLIT_RE = re.compile(
    r"(?:\s*[,;]\s*(?:and\s+|then\s+)?|\s+and\s+then\s+|\s+and\s+|\s+then\s+)",
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_BULLET_RE = re.compile(r"^\s*(?:[-*•‣◦]|\d{1,2}[.)])\s+")

_HEADING_RE = re.compile(r"^(?P<text>[^:]{1,60}):\s*$")

_WORD_RE = re.compile(r"[A-Za-z0-9'/$-]+")

# Filler that marks transcribed speech rather than written capture.
_DISFLUENCY_RE = re.compile(
    r"\b(?:um+|uh+|erm|okay so|ok so|i mean|you know|like i said)\b", re.IGNORECASE
)

_TERMINAL_PUNCTUATION = frozenset(".!?")

# A clause below this many words is not independently actionable. This is what
# keeps "Check and charge Dale battery" whole: "Check" alone is a bare verb
# with no object, and an item consisting of one verb is not an errand.
MIN_CLAUSE_WORDS = 2

# Above this many words with no terminal punctuation and no line structure,
# the text is a run-on and the splitter declines. Calibrated against
# `stt-unpunctuated-run-on` (24 words) and `segmentation-single-errand`
# (19 words), which is a nineteen-to-twenty-four-word gap and therefore thin.
# The disfluency check is the load-bearing signal; this is the backstop.
RUN_ON_WORD_LIMIT = 22


@dataclass(frozen=True)
class Segment:
    """One candidate item, with the evidence for why it is one item."""

    raw: str
    scope: str = ""
    """Heading text governing this segment, or "" when none.

    Kept separate from `raw` so a caller can decide whether the heading is
    context for a human or text the model should see. `to_raw_nodes` folds it
    in, because downstream date resolution reads the raw string and a heading
    is frequently where the day lives.
    """

    rule: str = "line"
    """Which rule produced this segment: line, heading-scoped, sentence,
    or clause. Recorded so a wrong split can be traced to the rule that made
    it rather than reasoned about from the output."""

    source_line: int = 0


@dataclass(frozen=True)
class SegmentationResult:
    segments: list[Segment] = field(default_factory=list)
    structured: bool = True
    """Whether the input is the kind of text this module can segment.

    False means the caller should not use `segments` as the final answer.
    Segments are still returned - they are useful for inspection and as a
    degraded fallback - but the caller was warned.
    """

    declined_reason: str = ""

    def to_raw_nodes(self, processing_date: str = "") -> list[dict]:
        """Shape the segments like `extract_nodes` output, minus type_hint.

        No `type_hint` field is emitted: this module does not type items, and
        emitting an empty hint would let a downstream reader mistake "not
        computed" for "computed as nothing".

        **A heading is folded in only when it names a day.** The fold exists so
        `apply_runtime_date_context` can see "Saturday:" - that is the whole
        reason for it. Folding a non-date heading instead pays for itself
        twice: "Garage Work Project Tasks: Patch holes in rear wall" is echoed
        into `title` and `item_text`, inflating prompt *and* completion on
        every item under the heading. Stage 142 finding 74 measured that as
        part of what made candidate 5 the most expensive arm at 17.28s.

        `processing_date` is optional so callers that only want segmentation
        need not supply one; without it no heading is folded, since whether a
        heading names a day cannot be answered without knowing today.
        """

        from substrate.time_context import states_a_date

        nodes: list[dict] = []
        for segment in self.segments:
            fold = bool(
                segment.scope
                and processing_date
                and states_a_date(segment.scope, processing_date)
            )
            raw = f"{segment.scope}: {segment.raw}" if fold else segment.raw
            nodes.append({"raw": raw})
        return nodes


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _is_verb_initial(clause: str) -> bool:
    words = _words(clause)
    if not words:
        return False
    first = words[0].lower()
    if first in IMPERATIVE_VERBS:
        return True
    # "need to pick up ..." and "have to call ..." are imperative in effect.
    if first in {"need", "have", "gotta", "got"} and len(words) > 1:
        return True
    return False


def _split_clauses(text: str, line_index: int, scope: str) -> list[Segment]:
    """Split one line into independently actionable clauses.

    A boundary is accepted only when the following clause starts with a verb
    and both sides carry enough words to stand alone. Everything else stays
    joined, because under-splitting leaves one item a human can read and
    over-splitting invents an errand that was never captured.
    """

    parts = [part.strip() for part in _CLAUSE_SPLIT_RE.split(text)]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        return [Segment(raw=text.strip(), scope=scope, rule="line", source_line=line_index)]

    merged: list[str] = [parts[0]]
    for part in parts[1:]:
        previous = merged[-1]
        if (
            _is_verb_initial(part)
            and len(_words(part)) >= MIN_CLAUSE_WORDS
            and len(_words(previous)) >= MIN_CLAUSE_WORDS
        ):
            merged.append(part)
        else:
            # Rejoin with a comma: the original separator is not recoverable
            # from the split, and a comma reads correctly for the trailing
            # noun phrases and subordinate clauses this branch catches.
            merged[-1] = f"{previous}, {part}"

    if len(merged) == 1:
        return [Segment(raw=merged[0], scope=scope, rule="line", source_line=line_index)]
    return [
        Segment(raw=part, scope=scope, rule="clause", source_line=line_index)
        for part in merged
    ]


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]


def _looks_like_dictation(text: str) -> tuple[bool, str]:
    """Decide whether the clause splitter should decline this input."""

    if _DISFLUENCY_RE.search(text):
        return True, "speech disfluency markers present"
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        return False, ""
    if any(char in _TERMINAL_PUNCTUATION for char in text):
        return False, ""
    if len(_words(text)) > RUN_ON_WORD_LIMIT:
        return True, f"single unpunctuated line over {RUN_ON_WORD_LIMIT} words"
    return False, ""


def segment_capture(content: str) -> SegmentationResult:
    """Split capture text into candidate items without a model call.

    Applies, in order: bullet stripping, heading scoping, sentence splitting,
    then clause splitting. The order matters - a heading governs the lines
    under it, and a sentence boundary is a stronger signal than a comma.
    """

    if not content or not content.strip():
        return SegmentationResult(segments=[], structured=True)

    dictation, reason = _looks_like_dictation(content)

    segments: list[Segment] = []
    scope = ""
    raw_lines = content.splitlines()
    for line_index, line in enumerate(raw_lines):
        stripped = line.strip()
        if not stripped:
            continue

        bulleted = bool(_BULLET_RE.match(line))
        stripped = _BULLET_RE.sub("", line).strip()
        if not stripped:
            continue

        heading = _HEADING_RE.match(stripped)
        if heading and not bulleted and line_index + 1 < len(raw_lines):
            # A line that is nothing but "<text>:" is scope, not an errand.
            # Requiring an empty tail is what keeps "KOHLS: pick up order"
            # an item rather than a heading.
            scope = heading.group("text").strip()
            continue

        for sentence in _split_sentences(stripped):
            rule_scope = scope
            produced = _split_clauses(sentence, line_index, rule_scope)
            if len(_split_sentences(stripped)) > 1:
                produced = [
                    Segment(
                        raw=item.raw,
                        scope=item.scope,
                        rule="sentence" if item.rule == "line" else item.rule,
                        source_line=item.source_line,
                    )
                    for item in produced
                ]
            if scope:
                produced = [
                    Segment(
                        raw=item.raw,
                        scope=item.scope,
                        rule="heading-scoped" if item.rule == "line" else item.rule,
                        source_line=item.source_line,
                    )
                    for item in produced
                ]
            segments.extend(produced)

    return SegmentationResult(
        segments=segments,
        structured=not dictation,
        declined_reason=reason,
    )

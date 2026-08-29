# Capture Harness Fixtures

Each JSON file is one capture input with known-correct expected output, used by
`specialists/uniblab/capture_harness.py` to score any model/config combination
on the real `extract_nodes` / `classify_nodes` path.

Fixtures 01-09 are verbatim real captures taken from
`/home/cosmo/sc/archive/*.input`; the `source` field names the file. Fixtures
10-22 are composed, because the behaviors they grade - corrections, duplicate
suppression, year rollover, restraint, context crowding - either never occurred
in the archive or cannot be isolated from a real capture. Composed fixtures say
so in `source`.

## Scope: what this harness does not grade

The harness scores the two-call text chain and nothing else. Image inputs are
handled by `specialists/orbit/adapters/rich_inputs.py`, which classifies and
routes to review and never reaches `extract_nodes`, so a photo fixture here
would have nothing to grade. Grading the image path needs a separate harness at
the Orbit boundary, scoring routing decisions and OCR text quality; that is
Stage 140 work. Do not fake it with a text fixture containing "the text a photo
would have produced" - that grades nothing about the image path and silently
asserts an OCR quality nobody measured.

Speech-to-text is the opposite case and belongs here. All 68 archived captures
carrying a modality header say `modality: text`, but they were dictated, so STT
artifacts are the normal input rather than an edge case. Two classes, split
deliberately: correct-but-messy (`11-stt-unpunctuated-run-on`) where extraction
should be unaffected, and wrong (`12-stt-garbled-proper-noun`) where the right
answer is to preserve the garbled token verbatim at low confidence rather than
repair it or drop it.

## Fixtures written for a candidate design

`18-22` were added before Stage 142's call-architecture experiment, to make
candidates measurable that the existing set could not distinguish:
deterministic segmentation (18-20) and a conditional escalation path (21-22).

That is a real hazard. A fixture written to make a candidate measurable can end
up shaped by the candidate, and then the experiment grades the fixture author's
preference rather than the design. Three guards:

- They are written **from doctrine**, before any candidate runs, and their
  notes cite the rule they come from.
- **19 and 20 are a pair.** `segmentation-compound-line` must split on "and";
  `segmentation-single-errand` must not. No segmenter passes both by preferring
  one behavior, so neither fixture can be satisfied by a rule tuned to it.
- **No fixture may be adjusted because a candidate scores badly on it.** If a
  candidate fails one of these, that is the measurement working.

## Known-red fixtures

Some fixtures encode behavior the system does not have yet.
`13-correction-of-prior-capture` asserts that a mutation of existing graph state
routes to review; there is no mutation-intent detection today, so it is expected
to score red on arrival. This is deliberate. A red for a real unsupported
behavior is a truer baseline than a fixture set that only asks questions the
system can already answer. Do not soften one to raise the headline number.

Expected output is derived from the prompt doctrine in
`specialists/rosie/prompts.py`, not from what any model happened to produce.
When a model disagrees with a fixture, the fixture is the reference until
someone argues the doctrine is wrong.

## Shape

```json
{
  "fixture_id": "simple-appointment",
  "category": "simple|dense|multi-day|contact|edge|hard",
  "description": "one line",
  "source": "path or provenance",
  "content": "the capture text",
  "now": "2026-06-12T09:00:00",
  "context": "optional; defaults to the harness DEFAULT_CONTEXT",
  "expect_structural_guard": false,
  "expected": {
    "extract": {"item_count": 1, "type_hints": ["appointment"]},
    "nodes": [
      {"node_type": "cogs/daily", "must_include": ["yoga"], "date": "2026-06-13"}
    ],
    "allowed_extra": [
      {"node_type": "sprockets/entity", "must_include": ["farm"]}
    ]
  },
  "notes": "why this expectation is the correct one"
}
```

## Contested readings

Some inputs have more than one defensible answer. "Area: Farm. Goal: Fix
tractor." arguably should produce hierarchy nodes, and arguably should defer
them to review. Asserting one reading punishes the model for the other;
dropping the fixture biases the set toward easy cases.

`allowed_extra` is the answer: a node matching one of its entries is **neither
required nor counted against precision**. Each entry absorbs at most one node,
so duplicated output is still over-production. An `allowed_extra` entry can
never satisfy an `expected` node - permission is not credit.

Use it only where the alternative reading is genuinely defensible, never to
paper over a wrong answer. If a fixture needs many allowed extras to pass, the
fixture is wrong or the doctrine is unclear; fix that instead.

`parent_hint` is absent-vs-empty sensitive. Omitting the key leaves the field
ungraded. `"parent_hint": ""` asserts the node must carry **no** parent, which
is how a fixture states that borrowing a plausible parent is the failure being
watched for - a wrongly borrowed real parent is worse than an invented one,
because an invented parent is visibly wrong in review and a real one is not.
`confidence` works the same way: set it only where a specific confidence is the
behavior under test.

`now` is pinned per fixture so relative dates ("tomorrow", "next 3 Saturdays")
grade deterministically. Most fixtures use Friday 2026-06-12;
`15-date-year-rollover` uses Tuesday 2026-12-29 so its answers cross both a
month and a year boundary.

`must_include` terms are matched case-insensitively against `title` + `item_text`
combined. An empty list means only `node_type` and `date` are graded — used when
the source text contains a transcription error that would otherwise grade
speech-to-text rather than the behavior under test.

`expected.extract.item_count` is advisory and reported separately; the headline
score comes from the classified nodes, since that is what reaches the vault.

# Capture Harness Fixtures

Stage 138 fixture set. Each JSON file is one capture input with known-correct
expected output, used by `specialists/uniblab/capture_harness.py` to score any
model/config combination on the real `extract_nodes` / `classify_nodes` path.

Every fixture except `10-structural-label-pressure` is a verbatim real capture
taken from `/home/cosmo/sc/archive/*.input`; the `source` field names the file.

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

`now` is pinned per fixture so relative dates ("tomorrow", "next 3 Saturdays")
grade deterministically. All current fixtures use Friday 2026-06-12.

`must_include` terms are matched case-insensitively against `title` + `item_text`
combined. An empty list means only `node_type` and `date` are graded — used when
the source text contains a transcription error that would otherwise grade
speech-to-text rather than the behavior under test.

`expected.extract.item_count` is advisory and reported separately; the headline
score comes from the classified nodes, since that is what reaches the vault.

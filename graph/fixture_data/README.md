# Graph Contract Fixtures

These Stage 75 fixtures are small product-graph examples for the Phase 7.5
probe. They are not production persistence files.

Each fixture is meant to be readable by inspection and loadable by tests.

Fixture fields:

- `fixture_id`: stable fixture name.
- `validity`: `valid`, `invalid`, or `example`.
- `description`: human-facing purpose.
- `graph`: accepted product graph pieces, when present.
- `expected`: validation or routing expectation for later stages.
- `proposal` / `audit`: non-product-graph layer examples.

Stage 76 should use these fixtures to build contract validators without
inventing new graph assumptions.

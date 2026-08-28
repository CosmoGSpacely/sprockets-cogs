"""Load Stage 138 capture-harness fixtures.

Mirrors the `graph/fixtures.py` loader convention: fixtures are JSON on disk,
loaded into frozen dataclasses, so the fixture set is inspectable and diffable
without reading Python.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


FIXTURE_DIR = Path(__file__).parent / "fixture_data"

DEFAULT_CONTEXT = (
    "Already in today's note: (none)\n"
    "Known hierarchy parents: General, Farm, Sprockets-Cogs Builder\n"
)


@dataclass(frozen=True)
class ExpectedNode:
    """One node the classify call is expected to produce."""

    node_type: str
    must_include: tuple[str, ...] = ()
    date: str = ""
    parent_hint: str | None = None
    """Expected hierarchy parent. `None` does not grade the field at all;
    `""` asserts the node carries no parent, which is how a fixture states
    that inventing or borrowing a parent is the failure being watched for."""

    confidence: str = ""

    def matches(self, node: dict[str, Any]) -> bool:
        """True when an actual classified node satisfies this expectation."""

        if node.get("node_type") != self.node_type:
            return False
        if self.date and node.get("date") != self.date:
            return False
        if self.parent_hint is not None:
            if (node.get("parent_hint") or "") != self.parent_hint:
                return False
        if self.confidence and node.get("confidence") != self.confidence:
            return False
        haystack = " ".join(
            str(node.get(key, "")) for key in ("title", "item_text")
        ).lower()
        return all(term.lower() in haystack for term in self.must_include)


@dataclass(frozen=True)
class CaptureFixture:
    """One capture input with its known-correct expected output."""

    fixture_id: str
    content: str
    now: datetime
    category: str = "uncategorized"
    description: str = ""
    source: str = ""
    context: str = DEFAULT_CONTEXT
    expected_item_count: int | None = None
    expected_type_hints: tuple[str, ...] = ()
    expected_nodes: tuple[ExpectedNode, ...] = field(default_factory=tuple)
    allowed_extra: tuple[ExpectedNode, ...] = field(default_factory=tuple)
    """Nodes that are defensible but not required.

    Some inputs have more than one correct reading. "Area: Farm. Goal: Fix
    tractor." arguably should yield hierarchy nodes, and arguably should defer
    them to review. Asserting one reading punishes the model for the other;
    omitting the fixture biases the set toward easy cases. A node matching an
    `allowed_extra` entry is neither required nor counted against precision.
    """

    expect_structural_guard: bool = False
    notes: str = ""


def _expected_node(node: dict[str, Any]) -> ExpectedNode:
    """Build one ExpectedNode from fixture JSON.

    `parent_hint` is absent-vs-empty sensitive: a missing key leaves the field
    ungraded, an empty string asserts the node must carry no parent.
    """

    return ExpectedNode(
        node_type=node["node_type"],
        must_include=tuple(node.get("must_include", ())),
        date=node.get("date", ""),
        parent_hint=node.get("parent_hint"),
        confidence=node.get("confidence", ""),
    )


def fixture_paths(fixture_dir: Path = FIXTURE_DIR) -> list[Path]:
    return sorted(fixture_dir.glob("*.json"))


def load_capture_fixture(path: Path) -> CaptureFixture:
    """Load one fixture file."""

    data = json.loads(path.read_text())
    expected = data.get("expected", {})
    extract = expected.get("extract", {})
    return CaptureFixture(
        fixture_id=data["fixture_id"],
        content=data["content"],
        now=datetime.fromisoformat(data["now"]),
        category=data.get("category", "uncategorized"),
        description=data.get("description", ""),
        source=data.get("source", ""),
        context=data.get("context", DEFAULT_CONTEXT),
        expected_item_count=extract.get("item_count"),
        expected_type_hints=tuple(extract.get("type_hints", ())),
        expected_nodes=tuple(
            _expected_node(node) for node in expected.get("nodes", ())
        ),
        allowed_extra=tuple(
            _expected_node(node) for node in expected.get("allowed_extra", ())
        ),
        expect_structural_guard=bool(data.get("expect_structural_guard", False)),
        notes=data.get("notes", ""),
    )


def load_capture_fixtures(
    fixture_dir: Path = FIXTURE_DIR,
    *,
    only: Sequence[str] = (),
    categories: Sequence[str] = (),
) -> tuple[CaptureFixture, ...]:
    """Load the fixture set, optionally filtered by id or category."""

    fixtures = [load_capture_fixture(path) for path in fixture_paths(fixture_dir)]
    if only:
        wanted = set(only)
        fixtures = [item for item in fixtures if item.fixture_id in wanted]
    if categories:
        wanted_categories = set(categories)
        fixtures = [item for item in fixtures if item.category in wanted_categories]
    return tuple(fixtures)

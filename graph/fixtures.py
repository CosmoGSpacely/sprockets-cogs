"""Load Stage 75 graph contract fixtures."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graph.models import (
    Cog,
    Sprocket,
    SprocketCogBridgeEdge,
    SprocketHierarchyEdge,
)


FIXTURE_DIR = Path(__file__).parent / "fixture_data"


@dataclass(frozen=True)
class ProductGraphFixture:
    fixture_id: str
    validity: str
    data: dict[str, Any]
    sprockets: list[Sprocket]
    cogs: list[Cog]
    hierarchy_edges: list[SprocketHierarchyEdge]
    bridge_edges: list[SprocketCogBridgeEdge]


def fixture_paths(fixture_dir: Path = FIXTURE_DIR) -> list[Path]:
    return sorted(fixture_dir.glob("*.json"))


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def load_product_graph_fixture(path: Path) -> ProductGraphFixture:
    data = load_fixture(path)
    graph = data.get("graph", {})
    return ProductGraphFixture(
        fixture_id=data["fixture_id"],
        validity=data["validity"],
        data=data,
        sprockets=[Sprocket.model_validate(item) for item in graph.get("sprockets", [])],
        cogs=[Cog.model_validate(item) for item in graph.get("cogs", [])],
        hierarchy_edges=[
            SprocketHierarchyEdge.model_validate(item)
            for item in graph.get("hierarchy_edges", [])
        ],
        bridge_edges=[
            SprocketCogBridgeEdge.model_validate(item)
            for item in graph.get("bridge_edges", [])
        ],
    )

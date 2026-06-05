"""Lightweight product graph contract validators."""
from __future__ import annotations

from dataclasses import dataclass

from graph.fixtures import ProductGraphFixture
from graph.models import Cog, Sprocket, SprocketCogBridgeEdge, SprocketHierarchyEdge


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    subject_id: str = ""


@dataclass(frozen=True)
class ValidationResult:
    issues: tuple[ValidationIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)


def validate_fixture(fixture: ProductGraphFixture) -> ValidationResult:
    return validate_product_graph(
        sprockets=fixture.sprockets, cogs=fixture.cogs,
        hierarchy_edges=fixture.hierarchy_edges,
        bridge_edges=fixture.bridge_edges,
    )


def validate_product_graph(
    *,
    sprockets: list[Sprocket],
    cogs: list[Cog],
    hierarchy_edges: list[SprocketHierarchyEdge],
    bridge_edges: list[SprocketCogBridgeEdge],
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    sprocket_ids = {sprocket.id for sprocket in sprockets}
    cog_ids = {cog.id for cog in cogs}

    issues.extend(_validate_cog_primary_bridges(cogs, bridge_edges))
    issues.extend(_validate_bridge_targets(bridge_edges, sprocket_ids, cog_ids))
    issues.extend(_validate_hierarchy_targets(hierarchy_edges, sprocket_ids))
    issues.extend(_validate_current_locators(cogs))

    return ValidationResult(issues=tuple(issues))


def _validate_cog_primary_bridges(
    cogs: list[Cog],
    bridge_edges: list[SprocketCogBridgeEdge],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for cog in cogs:
        primary_count = sum(
            1 for edge in bridge_edges if edge.cog_id == cog.id and edge.role == "primary"
        )
        if primary_count == 0:
            issues.append(
                ValidationIssue(
                    code="cog_missing_primary_bridge",
                    message="Cog must have exactly one primary bridge.",
                    subject_id=cog.id,
                )
            )
        elif primary_count > 1:
            issues.append(
                ValidationIssue(
                    code="cog_multiple_primary_bridges",
                    message="Cog must not have more than one primary bridge.",
                    subject_id=cog.id,
                )
            )
    return issues


def _validate_bridge_targets(
    bridge_edges: list[SprocketCogBridgeEdge],
    sprocket_ids: set[str],
    cog_ids: set[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for edge in bridge_edges:
        if edge.cog_id not in cog_ids:
            issues.append(
                ValidationIssue(
                    code="bridge_unresolved_cog_target",
                    message="Bridge points to a Cog that is not in the product graph.",
                    subject_id=edge.edge_key,
                )
            )
        if edge.sprocket_id not in sprocket_ids:
            issues.append(
                ValidationIssue(
                    code="bridge_unresolved_sprocket_target",
                    message="Bridge points to a Sprocket that is not in the product graph.",
                    subject_id=edge.edge_key,
                )
            )
    return issues


def _validate_hierarchy_targets(
    hierarchy_edges: list[SprocketHierarchyEdge],
    sprocket_ids: set[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for edge in hierarchy_edges:
        if edge.parent_id not in sprocket_ids:
            issues.append(
                ValidationIssue(
                    code="hierarchy_unresolved_parent",
                    message="Hierarchy edge parent is not an accepted Sprocket.",
                    subject_id=edge.edge_key,
                )
            )
        if edge.child_id not in sprocket_ids:
            issues.append(
                ValidationIssue(
                    code="hierarchy_unresolved_child",
                    message="Hierarchy edge child is not an accepted Sprocket.",
                    subject_id=edge.edge_key,
                )
            )
    return issues


def _validate_current_locators(cogs: list[Cog]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for cog in cogs:
        if cog.current_locator is None:
            continue
        if not cog.current_locator.marker:
            issues.append(
                ValidationIssue(
                    code="cog_locator_missing_marker",
                    message="Current locator needs a marker for close, drop, or carry.",
                    subject_id=cog.id,
                )
            )
    return issues

"""Cogs specialist facade for Phase 4 orchestration.

Stage 39A keeps this boundary read-only. It delegates to the existing Cogs
modules so scripts and timers continue to own their current write paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import carry
import cogs_planning
import nightly
from vault import DEFAULT_DAILY_DIR


@dataclass(frozen=True)
class CogsSpecialistConfig:
    """Filesystem roots owned by the Cogs specialist."""

    cogs_dir: Path = DEFAULT_DAILY_DIR.parent
    daily_dir: Path = DEFAULT_DAILY_DIR


@dataclass(frozen=True)
class CogsCarryPreview:
    """Read-only carry preview result."""

    through_date: str
    destination_date: str
    candidate_count: int
    plan: dict[str, Any]
    preview: str


@dataclass(frozen=True)
class CogsNightlyPreview:
    """Read-only nightly carry preview result."""

    through_date: str | None
    destination_date: str | None
    plan: dict[str, Any]
    report: str


@dataclass(frozen=True)
class CogsPlanningPreview:
    """Read-only planning-note preview result."""

    value: str
    inventory: cogs_planning.CogsPlanningInventory
    create_plan: list[cogs_planning.PlanningCreatePlanItem]
    report: str


class CogsSpecialist:
    """Facade for Cogs carry, nightly, and planning responsibilities."""

    def __init__(self, config: CogsSpecialistConfig | None = None) -> None:
        self.config = config or CogsSpecialistConfig()

    def inventory(self, reference_date: str | None = None) -> cogs_planning.CogsPlanningInventory:
        """Inspect Cogs planning-note state without writing."""

        return cogs_planning.build_inventory(self.config.cogs_dir, reference_date)

    def format_inventory(self, reference_date: str | None = None) -> str:
        """Format a read-only planning inventory."""

        return cogs_planning.format_inventory(self.config.cogs_dir, reference_date)

    def carry_candidates(self, through_date: str | None = None) -> list[carry.CarryCandidate]:
        """Return open carry candidates without writing."""

        return carry.scan_daily_notes(self.config.daily_dir, through_date)

    def carry_preview(
        self,
        through_date: str,
        destination_date: str,
    ) -> CogsCarryPreview:
        """Preview an editable carry plan without writing."""

        candidates = self.carry_candidates(through_date)
        plan = carry.build_plan_document(candidates, destination_date)
        return CogsCarryPreview(
            through_date=through_date,
            destination_date=destination_date,
            candidate_count=len(candidates),
            plan=plan,
            preview=carry.preview_apply_plan_document(plan),
        )

    def nightly_preview(
        self,
        through_date: str | None = None,
        destination_date: str | None = None,
    ) -> CogsNightlyPreview:
        """Preview the nightly carry plan without writing."""

        plan = nightly.build_nightly_plan(
            daily_dir=self.config.daily_dir,
            through_date=through_date,
            destination_date=destination_date,
        )
        return CogsNightlyPreview(
            through_date=through_date,
            destination_date=destination_date,
            plan=plan,
            report=nightly.format_nightly_report(
                plan,
                daily_dir=self.config.daily_dir,
                through_date=through_date,
                destination_date=destination_date,
            ),
        )

    def planning_preview(self, value: str) -> CogsPlanningPreview:
        """Preview planning-note inventory and creates without writing."""

        inventory = self.inventory(value if len(value) == 10 else None)
        create_plan = cogs_planning.build_create_plan(self.config.cogs_dir, value)
        return CogsPlanningPreview(
            value=value,
            inventory=inventory,
            create_plan=create_plan,
            report=cogs_planning.format_create_plan(self.config.cogs_dir, value),
        )


def format_cogs_specialist_preview(preview: CogsCarryPreview | CogsNightlyPreview | CogsPlanningPreview) -> str:
    """Format a Cogs specialist preview for operator inspection."""

    if isinstance(preview, CogsCarryPreview):
        return "\n".join(
            [
                "Cogs specialist carry preview",
                f"- through: {preview.through_date}",
                f"- destination: {preview.destination_date}",
                f"- candidates: {preview.candidate_count}",
                "- writes: no",
                "",
                preview.preview,
            ]
        )
    if isinstance(preview, CogsNightlyPreview):
        return "\n".join(["Cogs specialist nightly preview", "- writes: no", "", preview.report])
    return "\n".join(
        [
            "Cogs specialist planning preview",
            f"- value: {preview.value}",
            f"- planned items: {len(preview.create_plan)}",
            "- writes: no",
            "",
            preview.report,
        ]
    )

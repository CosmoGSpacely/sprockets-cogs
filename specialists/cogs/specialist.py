"""Cogs specialist facade for Phase 4 orchestration.

Stage 39A keeps this boundary read-only. It delegates to the existing Cogs
modules so scripts and timers continue to own their current write paths.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import specialists.cogs.carry as carry
import specialists.cogs.planning as cogs_planning
import specialists.cogs.nightly as nightly
from specialists.astro.vault import DEFAULT_DAILY_DIR


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Cogs specialist preview.")
    parser.add_argument(
        "--cogs-dir",
        default=str(DEFAULT_DAILY_DIR.parent),
        help="Cogs root directory. Defaults to the real vault Cogs directory.",
    )
    parser.add_argument(
        "--daily-dir",
        default=None,
        help="Cogs daily-note directory. Defaults to COGS_DIR/daily.",
    )
    parser.add_argument(
        "--through",
        default=None,
        help="YYYY-MM-DD cutoff for carry/nightly previews.",
    )
    parser.add_argument(
        "--to",
        default=None,
        help="YYYY-MM-DD destination date for carry/nightly previews.",
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--inventory",
        action="store_true",
        help="Preview Cogs planning inventory without writing.",
    )
    mode.add_argument(
        "--carry-preview",
        action="store_true",
        help="Preview editable carry-plan actions without writing.",
    )
    mode.add_argument(
        "--nightly-preview",
        action="store_true",
        help="Preview nightly carry report without writing.",
    )
    mode.add_argument(
        "--planning-preview",
        metavar="YYYY-MM-DD|YYYY-MM",
        help="Preview planning-note creates without writing.",
    )
    return parser


def specialist_from_args(args: argparse.Namespace) -> CogsSpecialist:
    cogs_dir = Path(args.cogs_dir)
    daily_dir = Path(args.daily_dir) if args.daily_dir else cogs_dir / "daily"
    return CogsSpecialist(CogsSpecialistConfig(cogs_dir=cogs_dir, daily_dir=daily_dir))


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    specialist = specialist_from_args(args)

    if args.inventory:
        print(specialist.format_inventory(args.through))
        return
    if args.carry_preview:
        through = args.through or nightly.default_through_date()
        destination = args.to or nightly.default_destination_date()
        print(format_cogs_specialist_preview(specialist.carry_preview(through, destination)))
        return
    if args.nightly_preview:
        print(format_cogs_specialist_preview(specialist.nightly_preview(args.through, args.to)))
        return
    if args.planning_preview:
        print(format_cogs_specialist_preview(specialist.planning_preview(args.planning_preview)))
        return

    parser.error("select a Cogs specialist preview mode")


if __name__ == "__main__":
    main()

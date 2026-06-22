"""Cogs appearance-set computation for vault window surfaces."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from specialists.cogs.naming import monthly_path, nested_daily_path, weekly_path
from specialists.cogs.planning import five_wow_rows, forward_12_month_rows
from substrate.cog_appearance_registry import CogAppearance


def appearance_set_for_dated_cog(
    cog_id: str,
    date_iso: str,
    cogs_dir: Path,
    *,
    planning_anchor_month: str | None = None,
) -> list[CogAppearance]:
    """Return the rendered appearance set for a dated Cog.

    Stage 118 keeps window surfaces computed but not authoritative. The optional
    planning anchor tells Cogs which planning window is actually being rendered,
    instead of pretending every possible lookahead window is an appearance.
    """

    dt = datetime.strptime(date_iso, "%Y-%m-%d").date()
    iso_year, iso_week, _ = dt.isocalendar()
    actual_month = dt.strftime("%Y-%m")
    appearances = [
        CogAppearance(
            cog_id=cog_id,
            surface="day",
            period=date_iso,
            path=_vault_relative(cogs_dir, nested_daily_path(date_iso, cogs_dir)),
        ),
        CogAppearance(
            cog_id=cog_id,
            surface="week",
            period=f"{iso_year}-W{iso_week:02d}",
            path=_vault_relative(cogs_dir, weekly_path(date_iso, cogs_dir)),
        ),
        CogAppearance(
            cog_id=cog_id,
            surface="month",
            period=actual_month,
            path=_vault_relative(cogs_dir, monthly_path(date_iso, cogs_dir)),
        ),
    ]

    if planning_anchor_month and _date_in_5wow(date_iso, planning_anchor_month):
        appearances.append(
            CogAppearance(
                cog_id=cog_id,
                surface="5wow",
                period=planning_anchor_month,
                path=_vault_relative(cogs_dir, monthly_path(f"{planning_anchor_month}-01", cogs_dir)),
            )
        )
    if planning_anchor_month and _month_in_forward_12(actual_month, planning_anchor_month):
        appearances.append(
            CogAppearance(
                cog_id=cog_id,
                surface="forward12",
                period=planning_anchor_month,
                path=_vault_relative(cogs_dir, monthly_path(f"{planning_anchor_month}-01", cogs_dir)),
            )
        )

    return appearances


def _date_in_5wow(date_iso: str, anchor_month: str) -> bool:
    return any(row_date == date_iso for _, _, row_date in five_wow_rows(anchor_month))


def _month_in_forward_12(month: str, anchor_month: str) -> bool:
    return any(row_month == month for _, row_month in forward_12_month_rows(anchor_month))


def _vault_relative(cogs_dir: Path, path: Path) -> str:
    rel = path.relative_to(cogs_dir)
    return str(Path("Cogs") / rel)

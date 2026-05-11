"""Read-only Cogs planning-note and filename previews."""

from __future__ import annotations

import argparse
import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from cogs_naming import (
    annual_filename,
    build_daily_rename_plan,
    monthly_filename,
    planned_note_filenames,
    weekly_filename,
)
from vault import DEFAULT_DAILY_DIR


DEFAULT_COGS_DIR = DEFAULT_DAILY_DIR.parent
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
FULL_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True)
class CogsPlanningInventory:
    cogs_dir: Path
    reference_date: str
    daily_count: int
    weekly_count: int
    monthly_count: int
    annual_count: int
    daily_legacy_count: int
    daily_iso_count: int
    daily_invalid_count: int
    current_weekly_exists: bool
    current_monthly_exists: bool
    current_annual_exists: bool
    current_weekly_name: str
    current_monthly_name: str
    current_annual_name: str
    current_5wow_anchor: str


@dataclass(frozen=True)
class PlanningCreatePlanItem:
    kind: str
    path: Path
    status: str
    reason: str
    template: str


def _count_markdown_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.glob("*.md"))


def format_planning_names(date_iso: str) -> str:
    names = planned_note_filenames(date_iso)
    lines = [f"Planning note names for {date_iso}:"]
    lines.append(f"- daily: {names['daily']}")
    lines.append(f"- weekly: {names['weekly']}")
    lines.append(f"- monthly: {names['monthly']}")
    lines.append(f"- annual: {names['annual']}")
    lines.append(f"- 5WOW: monthly section anchor {names['five_wow_anchor']}")
    return "\n".join(lines)


def _existing_periodic_path(folder: Path, filename: str) -> Path | None:
    path = folder / filename
    return path if path.exists() else None


def build_inventory(cogs_dir: Path = DEFAULT_COGS_DIR, reference_date: str | None = None) -> CogsPlanningInventory:
    ref = reference_date or date.today().isoformat()
    names = planned_note_filenames(ref)
    daily_dir = cogs_dir / "daily"
    weekly_dir = cogs_dir / "weekly"
    monthly_dir = cogs_dir / "monthly"
    annual_dir = cogs_dir / "annual"

    rename_plan = build_daily_rename_plan(daily_dir)
    daily_legacy_count = sum(1 for item in rename_plan if item.status == "rename")
    daily_iso_count = sum(1 for item in rename_plan if item.status == "already-current")
    daily_invalid_count = sum(1 for item in rename_plan if item.status == "invalid")

    weekly_name = names["weekly"]
    monthly_name = names["monthly"]
    annual_name = names["annual"]

    return CogsPlanningInventory(
        cogs_dir=cogs_dir,
        reference_date=ref,
        daily_count=len(rename_plan),
        weekly_count=_count_markdown_files(weekly_dir),
        monthly_count=_count_markdown_files(monthly_dir),
        annual_count=_count_markdown_files(annual_dir),
        daily_legacy_count=daily_legacy_count,
        daily_iso_count=daily_iso_count,
        daily_invalid_count=daily_invalid_count,
        current_weekly_exists=_existing_periodic_path(weekly_dir, weekly_name) is not None,
        current_monthly_exists=_existing_periodic_path(monthly_dir, monthly_name) is not None,
        current_annual_exists=_existing_periodic_path(annual_dir, annual_name) is not None,
        current_weekly_name=weekly_name,
        current_monthly_name=monthly_name,
        current_annual_name=annual_name,
        current_5wow_anchor=names["five_wow_anchor"],
    )


def format_inventory(cogs_dir: Path = DEFAULT_COGS_DIR, reference_date: str | None = None) -> str:
    inventory = build_inventory(cogs_dir, reference_date)
    lines = [f"Cogs planning inventory for {inventory.cogs_dir}", f"Reference date: {inventory.reference_date}"]
    lines.append(
        "Daily notes: "
        f"{inventory.daily_count} total "
        f"({inventory.daily_legacy_count} legacy, "
        f"{inventory.daily_iso_count} ISO-first, "
        f"{inventory.daily_invalid_count} invalid)"
    )
    lines.append(f"Weekly notes: {inventory.weekly_count}")
    lines.append(f"Monthly notes: {inventory.monthly_count}")
    lines.append(f"Annual notes: {inventory.annual_count}")
    lines.append("Current planning notes:")
    lines.append(
        f"- weekly {inventory.current_weekly_name}: "
        f"{'exists' if inventory.current_weekly_exists else 'missing'}"
    )
    lines.append(
        f"- monthly {inventory.current_monthly_name}: "
        f"{'exists' if inventory.current_monthly_exists else 'missing'}"
    )
    lines.append(
        f"- annual {inventory.current_annual_name}: "
        f"{'exists' if inventory.current_annual_exists else 'missing'}"
    )
    lines.append(f"- 5WOW monthly anchor: {inventory.current_5wow_anchor}")
    return "\n".join(lines)


def format_daily_rename_plan(daily_dir: Path) -> str:
    plan = build_daily_rename_plan(daily_dir)
    if not plan:
        return f"No daily notes found in {daily_dir}."

    counts: dict[str, int] = {}
    for item in plan:
        counts[item.status] = counts.get(item.status, 0) + 1

    summary = ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))
    lines = [f"Daily rename plan for {daily_dir}", f"Summary: {summary}"]
    for item in plan:
        if item.status == "rename":
            lines.append(f"- rename {item.source_path.name} -> {item.target_path.name}")
        elif item.status == "already-current":
            lines.append(f"- keep   {item.source_path.name} ({item.reason})")
        elif item.status == "collision":
            lines.append(f"- block  {item.source_path.name} -> {item.target_path.name} ({item.reason})")
        else:
            lines.append(f"- skip   {item.source_path.name} ({item.reason})")
    return "\n".join(lines)


def parse_month(month: str) -> date:
    return datetime.strptime(month, "%Y-%m").date().replace(day=1)


def five_wow_grid(month: str) -> list[list[str]]:
    """Return a five-row Mon-Fri grid for the given YYYY-MM month."""
    first = parse_month(month)
    _, days_in_month = calendar.monthrange(first.year, first.month)
    rows = [["" for _ in WEEKDAYS] for _ in range(5)]
    row = 0
    for day_number in range(1, days_in_month + 1):
        day = date(first.year, first.month, day_number)
        weekday = day.weekday()
        if weekday >= 5:
            continue
        if day_number != 1 and weekday == 0 and any(rows[row]):
            row += 1
        rows[row][weekday] = f"{day_number:02d}"
    return rows


def format_month_preview(month: str) -> str:
    first = parse_month(month)
    date_iso = first.isoformat()
    monthly_name = monthly_filename(date_iso)
    weekly_name = weekly_filename(date_iso)
    annual_name = annual_filename(date_iso)
    lines = [f"Cogs month preview for {month}"]
    lines.append(f"- monthly note: {monthly_name}")
    lines.append(f"- annual note: {annual_name}")
    lines.append(f"- first ISO week: {weekly_name}")
    lines.append("- 5WOW section: monthly Mon-Fri grid")
    lines.append("")
    lines.append("| Week | Mon | Tue | Wed | Thu | Fri |")
    lines.append("|---|---|---|---|---|---|")
    for index, row in enumerate(five_wow_grid(month), start=1):
        cells = " | ".join(row)
        lines.append(f"| {index} | {cells} |")
    return "\n".join(lines)


def _frontmatter(node_type: str, period: str, date_value: str) -> str:
    return (
        "---\n"
        f"node_type: {node_type}\n"
        f"{period}: {date_value}\n"
        f"tags: [{node_type}]\n"
        "---\n"
    )


def _week_start(date_iso: str) -> date:
    dt = datetime.strptime(date_iso, "%Y-%m-%d").date()
    return dt - timedelta(days=dt.weekday())


def render_weekly_note_template(date_iso: str) -> str:
    start = _week_start(date_iso)
    iso_year, iso_week, _ = start.isocalendar()
    lines = [
        _frontmatter("cogs/weekly", "week", f"{iso_year}-W{iso_week:02d}"),
        f"# {iso_year}-W{iso_week:02d}",
        "",
        "## Carry In",
        "",
        "## Weekdays",
        "",
    ]
    for index, label in enumerate(FULL_WEEKDAYS):
        day = start + timedelta(days=index)
        lines.append(f"### {label} {day:%Y-%m-%d}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _five_wow_table(month: str) -> list[str]:
    lines = ["| Week | Mon | Tue | Wed | Thu | Fri |", "|---|---|---|---|---|---|"]
    for index, row in enumerate(five_wow_grid(month), start=1):
        cells = " | ".join(row)
        lines.append(f"| {index} | {cells} |")
    return lines


def render_monthly_note_template(month: str) -> str:
    first = parse_month(month)
    lines = [
        _frontmatter("cogs/monthly", "month", month),
        f"# {month}",
        "",
        "## 5WOW",
        "",
        *_five_wow_table(month),
        "",
        "## Carry In",
        "",
        "## Dates",
        "",
    ]
    _, days_in_month = calendar.monthrange(first.year, first.month)
    for day_number in range(1, days_in_month + 1):
        day = date(first.year, first.month, day_number)
        lines.append(f"### {day:%a %Y-%m-%d}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_annual_note_template(year: int) -> str:
    lines = [
        _frontmatter("cogs/annual", "year", str(year)),
        f"# {year}",
        "",
        "## Carry In",
        "",
        "## Months",
        "",
    ]
    for month_number in range(1, 13):
        lines.append(f"### {year}-{month_number:02d}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_template_preview(template: str, value: str) -> str:
    if template == "weekly":
        return render_weekly_note_template(value)
    if template == "monthly":
        return render_monthly_note_template(value)
    if template == "annual":
        year = int(value)
        return render_annual_note_template(year)
    raise ValueError(f"Unsupported template: {template!r}")


def _template_line_count(template: str) -> int:
    return len(template.splitlines())


def _plan_item(kind: str, path: Path, template: str) -> PlanningCreatePlanItem:
    if path.exists():
        return PlanningCreatePlanItem(kind, path, "exists", "target already exists", template)
    return PlanningCreatePlanItem(kind, path, "create", "missing planning note", template)


def build_create_plan(cogs_dir: Path, value: str) -> list[PlanningCreatePlanItem]:
    """Build a read-only planning-note creation plan.

    YYYY-MM-DD previews weekly, monthly, and annual notes for that date.
    YYYY-MM previews monthly and annual notes for that month.
    """
    monthly_dir = cogs_dir / "monthly"
    annual_dir = cogs_dir / "annual"
    if len(value) == 7:
        month_start = parse_month(value)
        month = value
        year = month_start.year
        return [
            _plan_item(
                "monthly",
                monthly_dir / monthly_filename(month_start.isoformat()),
                render_monthly_note_template(month),
            ),
            _plan_item("annual", annual_dir / annual_filename(month_start.isoformat()), render_annual_note_template(year)),
        ]

    date_value = datetime.strptime(value, "%Y-%m-%d").date()
    month = date_value.strftime("%Y-%m")
    weekly_dir = cogs_dir / "weekly"
    return [
        _plan_item("weekly", weekly_dir / weekly_filename(value), render_weekly_note_template(value)),
        _plan_item("monthly", monthly_dir / monthly_filename(value), render_monthly_note_template(month)),
        _plan_item("annual", annual_dir / annual_filename(value), render_annual_note_template(date_value.year)),
    ]


def format_create_plan(cogs_dir: Path = DEFAULT_COGS_DIR, value: str | None = None) -> str:
    if not value:
        value = date.today().isoformat()
    plan = build_create_plan(cogs_dir, value)
    counts: dict[str, int] = {}
    for item in plan:
        counts[item.status] = counts.get(item.status, 0) + 1
    summary = ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))
    lines = [f"Planning-note create preview for {value}", f"Cogs dir: {cogs_dir}", f"Summary: {summary}"]
    for item in plan:
        lines.append(
            f"- {item.status:<6} {item.kind:<7} {item.path} "
            f"({item.reason}; {len(item.template)} chars, {_template_line_count(item.template)} lines)"
        )
    lines.append("No files written.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--names",
        metavar="YYYY-MM-DD",
        help="Preview ISO-first daily/weekly/monthly/annual names for a date.",
    )
    parser.add_argument(
        "--daily-rename-plan",
        action="store_true",
        help="Preview legacy daily-note renames without writing.",
    )
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Inspect existing Cogs planning-note files without writing.",
    )
    parser.add_argument(
        "--month",
        metavar="YYYY-MM",
        help="Preview a monthly planning note and 5WOW section shape.",
    )
    parser.add_argument(
        "--template",
        choices=("weekly", "monthly", "annual"),
        help="Preview a full planning-note Markdown template without writing.",
    )
    parser.add_argument(
        "--preview-create",
        nargs="?",
        const="",
        metavar="YYYY-MM-DD|YYYY-MM",
        help="Preview planning-note files to create for a date or month without writing.",
    )
    parser.add_argument(
        "--for",
        dest="template_value",
        metavar="DATE",
        help="Template value: weekly YYYY-MM-DD, monthly YYYY-MM, annual YYYY.",
    )
    parser.add_argument(
        "--cogs-dir",
        default=str(DEFAULT_COGS_DIR),
        help="Cogs root directory. Defaults to the real vault Cogs directory.",
    )
    parser.add_argument(
        "--daily-dir",
        default=str(DEFAULT_DAILY_DIR),
        help="Cogs daily-note directory. Defaults to the real vault daily directory.",
    )
    args = parser.parse_args()

    if args.names:
        print(format_planning_names(args.names))
        return
    if args.daily_rename_plan:
        print(format_daily_rename_plan(Path(args.daily_dir)))
        return
    if args.inventory:
        print(format_inventory(Path(args.cogs_dir)))
        return
    if args.month:
        print(format_month_preview(args.month))
        return
    if args.template:
        if not args.template_value:
            parser.error("--template requires --for")
        print(format_template_preview(args.template, args.template_value), end="")
        return
    if args.preview_create is not None:
        print(format_create_plan(Path(args.cogs_dir), args.preview_create or None))
        return

    parser.error("choose --names, --daily-rename-plan, --inventory, --month, --template, or --preview-create")


if __name__ == "__main__":
    main()

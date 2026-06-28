"""Cogs planning-note previews and guarded creation helpers."""

from __future__ import annotations

import argparse
import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence

from specialists.cogs.naming import (
    annual_filename,
    annual_path,
    apply_cogs_directory_migration_plan,
    apply_daily_rename_plan,
    build_cogs_directory_migration_plan,
    build_daily_rename_plan,
    five_wow_path,
    forward12_path,
    monthly_filename,
    monthly_path,
    nested_daily_path,
    planned_note_filenames,
    weekly_filename,
    weekly_path,
)
from specialists.astro.vault import DEFAULT_COGS_DIR, DEFAULT_DAILY_DIR


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


@dataclass(frozen=True)
class PlanningRefreshPlanItem:
    kind: str
    path: Path
    status: str
    reason: str
    template: str = ""


def _count_markdown_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.glob("*.md"))


def _count_markdown_files_recursive(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.rglob("*.md"))


def format_planning_names(date_iso: str) -> str:
    names = planned_note_filenames(date_iso)
    lines = [f"Planning note names for {date_iso}:"]
    lines.append(f"- daily: {names['daily']}")
    lines.append(f"- weekly: {names['weekly']}")
    lines.append(f"- monthly: {names['monthly']}")
    lines.append(f"- 5WOW: {names['5wow']}")
    lines.append(f"- 12MF: {names['12mf']}")
    lines.append(f"- annual: {names['annual']}")
    return "\n".join(lines)


def build_inventory(cogs_dir: Path = DEFAULT_COGS_DIR, reference_date: str | None = None) -> CogsPlanningInventory:
    ref = reference_date or date.today().isoformat()
    names = planned_note_filenames(ref)
    daily_dir = cogs_dir

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
        weekly_count=sum(1 for _ in cogs_dir.rglob("????-W??.md")) if cogs_dir.exists() else 0,
        monthly_count=sum(1 for _ in cogs_dir.rglob("????-??.md")) if cogs_dir.exists() else 0,
        annual_count=sum(1 for _ in cogs_dir.glob("????.md")) if cogs_dir.exists() else 0,
        daily_legacy_count=daily_legacy_count,
        daily_iso_count=daily_iso_count,
        daily_invalid_count=daily_invalid_count,
        current_weekly_exists=weekly_path(ref, cogs_dir).exists(),
        current_monthly_exists=monthly_path(ref, cogs_dir).exists(),
        current_annual_exists=annual_path(ref, cogs_dir).exists(),
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


def apply_daily_renames(daily_dir: Path) -> str:
    """Apply reviewed daily renames and format one result per note."""
    applied = apply_daily_rename_plan(daily_dir)
    if not applied:
        return f"No daily notes found in {daily_dir}."

    counts = {
        "renamed": sum(1 for item in applied if item.status == "rename"),
        "already-current": sum(1 for item in applied if item.status == "already-current"),
    }
    summary = ", ".join(f"{status}: {count}" for status, count in counts.items() if count)
    lines = [f"Daily rename apply for {daily_dir}", f"Summary: {summary}"]
    for item in applied:
        if item.status == "rename":
            lines.append(f"- renamed {item.source_path.name} -> {item.target_path.name}")
        else:
            lines.append(f"- kept    {item.source_path.name} ({item.reason})")
    return "\n".join(lines)


def format_cogs_directory_migration_plan(cogs_dir: Path = DEFAULT_COGS_DIR) -> str:
    plan = build_cogs_directory_migration_plan(cogs_dir)
    if not plan:
        return f"No flat Cogs notes found in {cogs_dir}."
    counts: dict[str, int] = {}
    for item in plan:
        counts[item.status] = counts.get(item.status, 0) + 1
    summary = ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))
    lines = [f"Cogs directory migration plan for {cogs_dir}", f"Summary: {summary}"]
    for item in plan:
        rel_source = item.source_path.relative_to(cogs_dir)
        rel_target = item.target_path.relative_to(cogs_dir)
        lines.append(f"- {item.status:<15} {item.kind:<7} {rel_source} -> {rel_target} ({item.reason})")
    lines.append("No files written.")
    return "\n".join(lines)


def apply_cogs_directory_migration(cogs_dir: Path = DEFAULT_COGS_DIR) -> str:
    applied = apply_cogs_directory_migration_plan(cogs_dir)
    if not applied:
        return f"No flat Cogs notes found in {cogs_dir}."
    counts = {
        "moved": sum(1 for item in applied if item.status == "move"),
        "already-current": sum(1 for item in applied if item.status == "already-current"),
    }
    summary = ", ".join(f"{status}: {count}" for status, count in counts.items() if count)
    lines = [f"Cogs directory migration apply for {cogs_dir}", f"Summary: {summary}"]
    for item in applied:
        rel_source = item.source_path.relative_to(cogs_dir)
        rel_target = item.target_path.relative_to(cogs_dir)
        verb = "moved" if item.status == "move" else "kept"
        lines.append(f"- {verb:<5} {item.kind:<7} {rel_source} -> {rel_target}")
    return "\n".join(lines)


def parse_month(month: str) -> date:
    return datetime.strptime(month, "%Y-%m").date().replace(day=1)


def _five_wow_start(month: str) -> date:
    """Return the first Monday whose workweek has a weekday in the month."""
    first = parse_month(month)
    if first.weekday() < 5:
        return first - timedelta(days=first.weekday())
    return first + timedelta(days=7 - first.weekday())


def five_wow_grid(month: str) -> list[list[str]]:
    """Return the first five workweeks having weekdays in the named month."""
    start = _five_wow_start(month)
    rows: list[list[str]] = []
    for week in range(5):
        row: list[str] = []
        for weekday in range(5):
            day = start + timedelta(days=week * 7 + weekday)
            row.append(day.strftime("%m-%d"))
        rows.append(row)
    return rows


def calendar_grid(month: str) -> list[list[str]]:
    """Return a month-shaped seven-day calendar grid, Monday through Sunday."""
    first = parse_month(month)
    _, days_in_month = calendar.monthrange(first.year, first.month)
    rows: list[list[str]] = []
    row = ["" for _ in FULL_WEEKDAYS]
    for day_number in range(1, days_in_month + 1):
        day = date(first.year, first.month, day_number)
        weekday = day.weekday()
        row[weekday] = f"{day_number:02d}"
        if weekday == 6:
            rows.append(row)
            row = ["" for _ in FULL_WEEKDAYS]
    if any(row):
        rows.append(row)
    return rows


def calendar_grid_with_spillover(month: str) -> list[list[date]]:
    """Return full Mon-Sun calendar rows including prior/following month days."""
    first = parse_month(month)
    start = first - timedelta(days=first.weekday())
    rows: list[list[date]] = []
    current = start
    while True:
        row = [current + timedelta(days=offset) for offset in range(7)]
        rows.append(row)
        current = row[-1] + timedelta(days=1)
        if current.month != first.month and current > first:
            break
    return rows


def five_wow_rows(month: str) -> list[tuple[int, str, str]]:
    """Return vertical 5WOW weekday rows: window week, day label, ISO date."""
    rows: list[tuple[int, str, str]] = []
    start = _five_wow_start(month)
    for week in range(5):
        for weekday in range(5):
            day = start + timedelta(days=week * 7 + weekday)
            rows.append((week + 1, WEEKDAYS[weekday], day.isoformat()))
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
    lines.append("- calendar section: monthly Mon-Sun grid")
    lines.append("- 5WOW file: vertical weekday planning view")
    lines.append("- 12MF file: twelve-month forward look")
    lines.append("")
    lines.extend(_calendar_table(month))
    lines.append("")
    lines.extend(_five_wow_vertical_table(month))
    return "\n".join(lines)


def _calendar_table(month: str) -> list[str]:
    lines = ["| M | T | W | Th | F | S | Su |", "|---|---|---|---|---|---|---|"]
    for row in calendar_grid_with_spillover(month):
        cells = [f"{day.day:02d}<br><br>" for day in row]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _frontmatter(node_type: str, period: str, date_value: str) -> str:
    return (
        "---\n"
        f"node_type: {node_type}\n"
        f"{period}: {date_value}\n"
        f"tags: [{node_type}]\n"
        "---\n"
    )


def render_daily_note_template(date_iso: str) -> str:
    dt = datetime.strptime(date_iso, "%Y-%m-%d").date()
    return (
        _frontmatter("cogs/daily", "date", date_iso)
        + f"# {dt:%a %d %b %Y}\n\n"
        + "<!-- Cogs stay in likely day order: explicit times, then daypart/order hints. -->\n"
    )


def _week_start(date_iso: str) -> date:
    dt = datetime.strptime(date_iso, "%Y-%m-%d").date()
    return dt - timedelta(days=dt.weekday())


def render_weekly_note_template(date_iso: str) -> str:
    start = _week_start(date_iso)
    iso_year, iso_week, _ = start.isocalendar()
    lines = [
        _frontmatter("cogs/weekly", "week", f"{iso_year}-W{iso_week:02d}"),
        f"# Week {iso_week:02d} - {start:%b %Y}",
        "",
        "| Date | Setting | Cogs | Date |",
        "|---|---|---|---|",
    ]
    for index, label in enumerate(FULL_WEEKDAYS):
        day = start + timedelta(days=index)
        left_rail = f"{day.day:02d} {label}"
        lines.append(f"| {left_rail} |  | <br><br><br> | {day.day:02d} |")
    lines.extend(["", "## CARRY", ""])
    return "\n".join(lines).rstrip() + "\n"


def _five_wow_vertical_table(month: str) -> list[str]:
    lines = ["| Date | Setting | Cogs | Date |", "|---|---|---|---|"]
    for _, day_label, date_iso in five_wow_rows(month):
        day = datetime.strptime(date_iso, "%Y-%m-%d").date()
        left_rail = f"{day.day:02d} {day_label}"
        lines.append(f"| {left_rail} |  |  | {day.day:02d} |")
    return lines


def forward_12_month_rows(month: str) -> list[tuple[int, str]]:
    """Return annual 12MF buckets from January through December."""
    first = parse_month(month).replace(month=1)
    rows: list[tuple[int, str]] = []
    for offset in range(12):
        month_index = first.month - 1 + offset
        year = first.year + month_index // 12
        month_number = month_index % 12 + 1
        rows.append((offset + 1, f"{year}-{month_number:02d}"))
    return rows


def _forward_12_month_table(month: str) -> list[str]:
    lines = ["| + | Month | Cogs | Notes |", "|---|---|---|---|"]
    for offset, month_label in forward_12_month_rows(month):
        lines.append(f"| {offset} | {month_label} |  |  |")
    return lines


def render_monthly_note_template(month: str) -> str:
    lines = [
        _frontmatter("cogs/monthly", "month", month),
        f"# {month}",
        "",
        *_calendar_table(month),
        "",
        "## CARRY",
        "",
        "## KEY",
        "",
        "- `~~` setting span",
        "- `xx` unavailable/out",
        "- boxed date: important anchor",
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_five_wow_note_template(month: str) -> str:
    lines = [
        _frontmatter("cogs/5wow", "month", month),
        *_five_wow_vertical_table(month),
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_12mf_note_template(month: str) -> str:
    year = parse_month(month).year
    lines = [
        _frontmatter("cogs/12mf", "year", str(year)),
        f"# {year} 12MF",
        "",
        "<!-- Annual source surface for birthdays, anniversaries, and long-range anchors. -->",
        "",
        *_forward_12_month_table(month),
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_annual_note_template(year: int) -> str:
    lines = [
        _frontmatter("cogs/annual", "year", str(year)),
        f"# {year}",
        "",
        "## CARRY",
        "",
        "## Months",
        "",
    ]
    for month_number in range(1, 13):
        lines.append(f"### {year}-{month_number:02d}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_template_preview(template: str, value: str) -> str:
    if template == "daily":
        return render_daily_note_template(value)
    if template == "weekly":
        return render_weekly_note_template(value)
    if template == "monthly":
        return render_monthly_note_template(value)
    if template == "5wow":
        return render_five_wow_note_template(value)
    if template == "12mf":
        return render_12mf_note_template(value)
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
    if len(value) == 7:
        month_start = parse_month(value)
        month = value
        year = month_start.year
        return [
            _plan_item(
                "monthly",
                monthly_path(month_start.isoformat(), cogs_dir),
                render_monthly_note_template(month),
            ),
            _plan_item("5wow", five_wow_path(month_start.isoformat(), cogs_dir), render_five_wow_note_template(month)),
            _plan_item("12mf", forward12_path(month_start.isoformat(), cogs_dir), render_12mf_note_template(month)),
            _plan_item("annual", annual_path(month_start.isoformat(), cogs_dir), render_annual_note_template(year)),
        ]

    date_value = datetime.strptime(value, "%Y-%m-%d").date()
    month = date_value.strftime("%Y-%m")
    return [
        _plan_item("daily", nested_daily_path(value, cogs_dir), render_daily_note_template(value)),
        _plan_item("weekly", weekly_path(value, cogs_dir), render_weekly_note_template(value)),
        _plan_item("monthly", monthly_path(value, cogs_dir), render_monthly_note_template(month)),
        _plan_item("5wow", five_wow_path(value, cogs_dir), render_five_wow_note_template(month)),
        _plan_item("12mf", forward12_path(value, cogs_dir), render_12mf_note_template(month)),
        _plan_item("annual", annual_path(value, cogs_dir), render_annual_note_template(date_value.year)),
    ]


def filter_create_plan(
    plan: list[PlanningCreatePlanItem],
    kind: str,
) -> list[PlanningCreatePlanItem]:
    if kind == "all":
        return plan
    if kind not in {"daily", "weekly", "monthly", "5wow", "12mf", "annual"}:
        raise ValueError(f"Unsupported planning-note kind: {kind!r}")
    return [item for item in plan if item.kind == kind]


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


def create_planning_notes(
    cogs_dir: Path,
    value: str,
    kind: str = "all",
) -> list[str]:
    """Create missing planning notes from templates. Refuses to overwrite."""
    plan = filter_create_plan(build_create_plan(cogs_dir, value), kind)
    return _create_plan_items(plan)


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _has_task_lines(content: str) -> bool:
    return any(line.lstrip().startswith("- [") for line in content.splitlines())


def _old_weekly_is_empty(content: str) -> bool:
    if "node_type: cogs/weekly" not in content or "## Carry In" not in content or "## Weekdays" not in content:
        return False
    if _has_task_lines(content):
        return False
    between = content.split("## Carry In", 1)[1].split("## Weekdays", 1)[0]
    return not between.strip()


def _old_monthly_is_empty(content: str) -> bool:
    if "node_type: cogs/monthly" not in content or "## Calendar" not in content or "## 5WOW" not in content:
        return False
    if _has_task_lines(content):
        return False
    if "## Carry In" in content and "## Dates" in content:
        carry = content.split("## Carry In", 1)[1].split("## Dates", 1)[0]
        if carry.strip():
            return False
    for line in content.splitlines():
        if not line.startswith("|"):
            continue
        cells = _table_cells(line)
        if len(cells) == 5 and cells[0].isdigit() and len(cells[2]) == 10:
            if cells[3] or cells[4]:
                return False
    return True


def _calendar_monthly_is_empty(content: str) -> bool:
    """Recognize a generated calendar month with no marks or carried content."""
    has_header = "| M | T | W | Th | F | S | Su |" in content or "cogs-monthly-marker" in content
    if "node_type: cogs/monthly" not in content or not has_header:
        return False
    if _has_task_lines(content):
        return False
    if "## CARRY" in content and "## KEY" in content:
        carry = content.split("## CARRY", 1)[1].split("## KEY", 1)[0]
        if carry.strip():
            return False
    allowed_cell = re.compile(r"^(?:[A-Z][a-z]{2} )?\d{2}(?:<br>){1,2}$")
    rows = 0
    for line in content.splitlines():
        if not line.startswith("|"):
            continue
        cells = _table_cells(line)
        if len(cells) != 7 or cells[0] in {"M", "---"} or "cogs-monthly-marker" in cells[0]:
            continue
        rows += 1
        if any(not allowed_cell.fullmatch(cell) for cell in cells):
            return False
    return rows > 0


def _old_5wow_is_empty(content: str) -> bool:
    if "node_type: cogs/5wow" not in content or "| Week | Day | Date | Cogs | Notes |" not in content:
        return False
    if _has_task_lines(content):
        return False
    for line in content.splitlines():
        if not line.startswith("|"):
            continue
        cells = _table_cells(line)
        if len(cells) == 5 and cells[0].isdigit() and len(cells[2]) == 10:
            if cells[3] or cells[4]:
                return False
    return True


def _rail_5wow_is_empty(content: str) -> bool:
    """Recognize an empty Stage 134 rail surface, including the buggy link form."""
    has_header = "| Date | Setting | Cogs | Date |" in content or "cogs-5wow-marker" in content
    if "node_type: cogs/5wow" not in content or not has_header:
        return False
    if _has_task_lines(content):
        return False
    if "[[" in content:
        return True
    rows = 0
    for line in content.splitlines():
        if not line.startswith("|"):
            continue
        cells = _table_cells(line)
        if len(cells) != 4 or cells[0] in {"Date", "---"} or "cogs-5wow-marker" in cells[0]:
            continue
        rows += 1
        if cells[1] or cells[2]:
            return False
    return rows > 0


def _rail_weekly_is_empty(content: str) -> bool:
    """Recognize an empty generated Week rail, including the failed marker form."""
    has_header = "| Date | Setting | Cogs | Date |" in content or "cogs-weekly-marker" in content
    if "node_type: cogs/weekly" not in content or not has_header or _has_task_lines(content):
        return False
    rows = 0
    for line in content.splitlines():
        if not line.startswith("|"):
            continue
        cells = _table_cells(line)
        if len(cells) != 4 or cells[0] in {"Date", "---"} or "cogs-weekly-marker" in cells[0]:
            continue
        rows += 1
        if cells[1] or cells[2] not in {"", "<br><br>", "<br><br><br>"}:
            return False
    return rows > 0


def _old_rolling_12mf_is_empty(content: str) -> bool:
    if "node_type: cogs/12mf" not in content or "month:" not in content or "| + | Month | Cogs | Notes |" not in content:
        return False
    if _has_task_lines(content):
        return False
    for line in content.splitlines():
        if not line.startswith("|"):
            continue
        cells = _table_cells(line)
        if len(cells) == 4 and cells[0].isdigit() and len(cells[1]) == 7:
            if cells[2] or cells[3]:
                return False
    return True


def _refresh_status_for_existing(item: PlanningCreatePlanItem) -> PlanningRefreshPlanItem:
    if not item.path.exists():
        return PlanningRefreshPlanItem(item.kind, item.path, "missing", "target does not exist", item.template)
    content = item.path.read_text()
    if content == item.template:
        return PlanningRefreshPlanItem(item.kind, item.path, "preserve", "already uses current generated shape")
    refreshable = (
        (item.kind == "weekly" and (_old_weekly_is_empty(content) or _rail_weekly_is_empty(content)))
        or (item.kind == "monthly" and (_old_monthly_is_empty(content) or _calendar_monthly_is_empty(content)))
        or (item.kind == "5wow" and (_old_5wow_is_empty(content) or _rail_5wow_is_empty(content)))
        or (item.kind == "12mf" and _old_rolling_12mf_is_empty(content))
    )
    if refreshable:
        return PlanningRefreshPlanItem(item.kind, item.path, "refresh", "empty generated old-shape planning surface", item.template)
    return PlanningRefreshPlanItem(item.kind, item.path, "preserve", "not an empty generated old-shape planning surface")


def build_empty_surface_refresh_plan(
    cogs_dir: Path,
    reference_date: str | None = None,
    *,
    weekly_weeks: int = 12,
    month_count: int = 2,
) -> list[PlanningRefreshPlanItem]:
    """Build a guarded refresh plan for empty generated planning surfaces."""
    ref = datetime.strptime(reference_date or date.today().isoformat(), "%Y-%m-%d").date()
    by_path: dict[Path, PlanningRefreshPlanItem] = {}

    for offset in range(weekly_weeks + 1):
        day = ref + timedelta(days=offset * 7)
        item = _plan_item("weekly", weekly_path(day.isoformat(), cogs_dir), render_weekly_note_template(day.isoformat()))
        by_path[item.path] = _refresh_status_for_existing(item)

    for offset in range(month_count + 1):
        month_start = _add_months(ref.replace(day=1), offset)
        month = month_start.strftime("%Y-%m")
        month_iso = month_start.isoformat()
        for item in (
            _plan_item("monthly", monthly_path(month_iso, cogs_dir), render_monthly_note_template(month)),
            _plan_item("5wow", five_wow_path(month_iso, cogs_dir), render_five_wow_note_template(month)),
            _plan_item("12mf", forward12_path(month_iso, cogs_dir), render_12mf_note_template(month)),
        ):
            by_path[item.path] = _refresh_status_for_existing(item)

    for obsolete in sorted(cogs_dir.rglob("????-??-12MF.md")):
        if obsolete.name.endswith("-01-12MF.md"):
            continue
        content = obsolete.read_text()
        if _old_rolling_12mf_is_empty(content):
            by_path[obsolete] = PlanningRefreshPlanItem(
                "12mf",
                obsolete,
                "remove-obsolete",
                "empty rolling 12MF superseded by annual January 12MF",
            )
        else:
            by_path[obsolete] = PlanningRefreshPlanItem(
                "12mf",
                obsolete,
                "preserve",
                "obsolete rolling 12MF has content or unrecognized shape",
            )

    return sorted(by_path.values(), key=lambda item: (str(item.path), item.kind))


def format_empty_surface_refresh_plan(cogs_dir: Path = DEFAULT_COGS_DIR, reference_date: str | None = None) -> str:
    plan = build_empty_surface_refresh_plan(cogs_dir, reference_date)
    counts: dict[str, int] = {}
    for item in plan:
        counts[item.status] = counts.get(item.status, 0) + 1
    summary = ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))
    lines = [
        f"Empty planning-surface refresh preview for {reference_date or date.today().isoformat()}",
        f"Cogs dir: {cogs_dir}",
        f"Summary: {summary}",
    ]
    for item in plan:
        lines.append(f"- {item.status:<15} {item.kind:<7} {item.path} ({item.reason})")
    lines.append("No files written.")
    return "\n".join(lines)


def refresh_empty_planning_surfaces(cogs_dir: Path, reference_date: str | None = None) -> list[str]:
    """Refresh only empty generated old-shape planning surfaces."""
    results: list[str] = []
    for item in build_empty_surface_refresh_plan(cogs_dir, reference_date):
        if item.status == "refresh":
            item.path.write_text(item.template)
            results.append(f"refreshed {item.kind}: {item.path}")
        elif item.status == "remove-obsolete":
            item.path.unlink()
            results.append(f"removed obsolete {item.kind}: {item.path}")
        else:
            results.append(f"{item.status} {item.kind}: {item.path}")
    return results


def ensure_current_planning_notes(cogs_dir: Path, reference_date: str | None = None) -> list[str]:
    """Ensure weekly, monthly, and annual notes exist for the reference date."""
    ref = reference_date or date.today().isoformat()
    plan = [item for item in build_create_plan(cogs_dir, ref) if item.kind != "daily"]
    return _create_plan_items(plan)


def _add_months(dt: date, months: int) -> date:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _create_plan_items(plan: list[PlanningCreatePlanItem]) -> list[str]:
    results: list[str] = []
    for item in plan:
        if item.status == "exists":
            results.append(f"exists {item.kind}: {item.path}")
            continue
        item.path.parent.mkdir(parents=True, exist_ok=True)
        item.path.write_text(item.template)
        results.append(f"created {item.kind}: {item.path}")
    return results


def build_horizon_create_plan(
    cogs_dir: Path,
    reference_date: str | None = None,
    *,
    daily_days: int = 21,
    weekly_weeks: int = 12,
    month_count: int = 2,
) -> list[PlanningCreatePlanItem]:
    """Build the near-future vault horizon needed for manual carry."""
    ref = datetime.strptime(reference_date or date.today().isoformat(), "%Y-%m-%d").date()
    by_path: dict[Path, PlanningCreatePlanItem] = {}

    for offset in range(daily_days + 1):
        day = ref + timedelta(days=offset)
        item = _plan_item("daily", nested_daily_path(day.isoformat(), cogs_dir), render_daily_note_template(day.isoformat()))
        by_path[item.path] = item

    for offset in range(weekly_weeks + 1):
        day = ref + timedelta(days=offset * 7)
        item = _plan_item("weekly", weekly_path(day.isoformat(), cogs_dir), render_weekly_note_template(day.isoformat()))
        by_path[item.path] = item

    for offset in range(month_count + 1):
        month_start = _add_months(ref.replace(day=1), offset)
        month = month_start.strftime("%Y-%m")
        by_path[monthly_path(month_start.isoformat(), cogs_dir)] = _plan_item(
            "monthly",
            monthly_path(month_start.isoformat(), cogs_dir),
            render_monthly_note_template(month),
        )
        by_path[five_wow_path(month_start.isoformat(), cogs_dir)] = _plan_item(
            "5wow",
            five_wow_path(month_start.isoformat(), cogs_dir),
            render_five_wow_note_template(month),
        )
        by_path[forward12_path(month_start.isoformat(), cogs_dir)] = _plan_item(
            "12mf",
            forward12_path(month_start.isoformat(), cogs_dir),
            render_12mf_note_template(month),
        )

    next_year_start = date(ref.year + 1, 1, 1)
    by_path[forward12_path(next_year_start.isoformat(), cogs_dir)] = _plan_item(
        "12mf",
        forward12_path(next_year_start.isoformat(), cogs_dir),
        render_12mf_note_template(next_year_start.strftime("%Y-%m")),
    )

    for year in sorted({ref.year, _add_months(ref.replace(day=1), 11).year}):
        year_start = date(year, 1, 1)
        by_path[annual_path(year_start.isoformat(), cogs_dir)] = _plan_item(
            "annual",
            annual_path(year_start.isoformat(), cogs_dir),
            render_annual_note_template(year),
        )

    return sorted(by_path.values(), key=lambda item: (str(item.path), item.kind))


def ensure_planning_horizon(cogs_dir: Path, reference_date: str | None = None) -> list[str]:
    """Create the near-future vault horizon needed for manual carry."""
    return _create_plan_items(build_horizon_create_plan(cogs_dir, reference_date))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--names",
        metavar="YYYY-MM-DD",
        help="Preview ISO-first daily/weekly/monthly/annual names for a date. Read-only.",
    )
    parser.add_argument(
        "--daily-rename-plan",
        action="store_true",
        help="Preview legacy daily-note renames. Read-only; does not rename files.",
    )
    parser.add_argument(
        "--daily-rename-apply",
        action="store_true",
        help="Rename daily notes from a reviewed ISO-first plan. Refuses blocked items.",
    )
    parser.add_argument(
        "--directory-migration-plan",
        action="store_true",
        help="Preview flat-to-nested Cogs directory migration. Read-only.",
    )
    parser.add_argument(
        "--directory-migration-apply",
        action="store_true",
        help="Apply reviewed flat-to-nested Cogs directory migration. Refuses blocked items.",
    )
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Report existing Cogs planning-note files. Read-only.",
    )
    parser.add_argument(
        "--month",
        metavar="YYYY-MM",
        help="Preview monthly, 5WOW, and 12MF planning surface names. Read-only.",
    )
    parser.add_argument(
        "--template",
        choices=("daily", "weekly", "monthly", "5wow", "12mf", "annual"),
        help="Preview a full planning-note Markdown template. Read-only.",
    )
    parser.add_argument(
        "--preview-create",
        nargs="?",
        const="",
        metavar="YYYY-MM-DD|YYYY-MM",
        help="Preview planning-note files to create for a date or month. Read-only.",
    )
    parser.add_argument(
        "--create",
        metavar="YYYY-MM-DD|YYYY-MM",
        help="Create missing planning-note files for a date or month. Writes Cogs weekly/monthly/annual notes.",
    )
    parser.add_argument(
        "--ensure-current",
        action="store_true",
        help="Create missing weekly, monthly, and annual notes for today. Writes Cogs planning notes.",
    )
    parser.add_argument(
        "--ensure-horizon",
        action="store_true",
        help="Create near-future day/week/5WOW/month/12MF/year notes for manual carry landing surfaces.",
    )
    parser.add_argument(
        "--refresh-empty-surfaces-plan",
        action="store_true",
        help="Preview guarded refresh of empty old-shape planning surfaces. Read-only.",
    )
    parser.add_argument(
        "--refresh-empty-surfaces",
        action="store_true",
        help="Refresh only empty generated old-shape planning surfaces and remove empty obsolete rolling 12MF files.",
    )
    parser.add_argument(
        "--kind",
        choices=("daily", "weekly", "monthly", "5wow", "12mf", "annual", "all"),
        default="all",
        help="Limit --create to one planning-note kind. Defaults to all.",
    )
    parser.add_argument(
        "--for",
        dest="template_value",
        metavar="DATE",
        help="Template/reference value: daily/weekly YYYY-MM-DD, monthly/5WOW/12MF YYYY-MM, annual YYYY.",
    )
    parser.add_argument(
        "--cogs-dir",
        default=str(DEFAULT_COGS_DIR),
        help="Cogs root directory. Defaults to the real vault Cogs directory.",
    )
    parser.add_argument(
        "--daily-dir",
        default=str(DEFAULT_DAILY_DIR),
        help="Cogs daily-note directory/root. Defaults to the real vault Cogs root.",
    )
    args = parser.parse_args(argv)

    if args.names:
        print(format_planning_names(args.names))
        return
    if args.daily_rename_plan:
        print(format_daily_rename_plan(Path(args.daily_dir)))
        return
    if args.daily_rename_apply:
        print(apply_daily_renames(Path(args.daily_dir)))
        return
    if args.directory_migration_plan:
        print(format_cogs_directory_migration_plan(Path(args.cogs_dir)))
        return
    if args.directory_migration_apply:
        print(apply_cogs_directory_migration(Path(args.cogs_dir)))
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
    if args.create:
        print("\n".join(create_planning_notes(Path(args.cogs_dir), args.create, args.kind)))
        return
    if args.ensure_current:
        print("\n".join(ensure_current_planning_notes(Path(args.cogs_dir), args.template_value)))
        return
    if args.ensure_horizon:
        print("\n".join(ensure_planning_horizon(Path(args.cogs_dir), args.template_value)))
        return
    if args.refresh_empty_surfaces_plan:
        print(format_empty_surface_refresh_plan(Path(args.cogs_dir), args.template_value))
        return
    if args.refresh_empty_surfaces:
        print("\n".join(refresh_empty_planning_surfaces(Path(args.cogs_dir), args.template_value)))
        return

    parser.error(
        "choose --names, --daily-rename-plan, --daily-rename-apply, --inventory, --month, --template, "
        "--directory-migration-plan, --directory-migration-apply, --preview-create, --create, --ensure-current, "
        "--ensure-horizon, --refresh-empty-surfaces-plan, or --refresh-empty-surfaces"
    )


if __name__ == "__main__":
    main()

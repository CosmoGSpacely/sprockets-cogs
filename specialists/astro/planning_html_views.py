"""Generate complete HTML planning surfaces from canonical Cogs Markdown."""

from __future__ import annotations

import argparse
import calendar
import html
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence

from specialists.astro.vault import DEFAULT_COGS_DIR
from specialists.cogs.naming import resolve_existing_daily_path
from specialists.cogs.planning import calendar_grid_with_spillover, five_wow_rows


TASK_RE = re.compile(r"^\s*-\s+\[([ xX>\-])\]\s+(.+?)\s*$")
RULE = "border:0;border-bottom:1px solid var(--background-modifier-border);"
CELL = f"{RULE}padding:0.45rem 0.65rem;vertical-align:top;"
RAIL = f"{CELL}white-space:nowrap;color:var(--text-muted);"


@dataclass(frozen=True)
class PlanningHtmlView:
    kind: str
    filename: str
    content: str


def _frontmatter(kind: str, reference: str) -> str:
    return f"---\nreview_surface: {kind}\nreference: {reference}\n---\n\n"


def _daily_items(cogs_dir: Path, day: date) -> list[str]:
    path = resolve_existing_daily_path(day.isoformat(), cogs_dir)
    if path is None:
        return []
    items: list[str] = []
    for line in path.read_text().splitlines():
        match = TASK_RE.match(line)
        if match:
            items.append(match.group(2))
    return items


def _is_setting(item: str) -> bool:
    letters = "".join(character for character in item if character.isalpha())
    return bool(letters) and (
        letters.isupper()
        or item.casefold() in {"fullbloom", "out of office", "work from home", "wfh"}
    )


def _split_items(items: Sequence[str]) -> tuple[list[str], list[str]]:
    settings = [item for item in items if _is_setting(item)]
    cogs = [item for item in items if not _is_setting(item)]
    return settings, cogs


def _text_lines(items: Sequence[str], *, limit: int | None = None) -> str:
    selected = list(items if limit is None else items[:limit])
    return "<br>".join(html.escape(item) for item in selected)


def _table(rows: Sequence[Sequence[tuple[str, str]]], widths: Sequence[int]) -> str:
    lines = [
        '<table style="width:100%;border:0;border-collapse:collapse;table-layout:fixed;">',
        "  <colgroup>",
    ]
    lines.extend(f'    <col style="width:{width}%;">' for width in widths)
    lines.extend(["  </colgroup>", "  <tbody>"])
    for row in rows:
        lines.append("    <tr>")
        for value, style in row:
            lines.append(f'      <td style="{style}">{value}</td>')
        lines.append("    </tr>")
    lines.extend(["  </tbody>", "</table>"])
    return "\n".join(lines)


def _rail_row(day: date, cogs_dir: Path, *, min_height: str, compact: bool = False) -> list[tuple[str, str]]:
    settings, cogs = _split_items(_daily_items(cogs_dir, day))
    body_style = f"{CELL}min-height:{min_height};"
    if compact:
        body_style = CELL
    return [
        (f"{day.day:02d} {day:%a}", RAIL),
        (_text_lines(settings, limit=1), body_style),
        (_text_lines(cogs, limit=3 if not compact else 1), body_style),
        (f"{day.day:02d}", f"{RAIL}text-align:right;"),
    ]


def render_day_view(cogs_dir: Path, reference: date) -> str:
    settings, cogs = _split_items(_daily_items(cogs_dir, reference))
    lines = [
        _frontmatter("day", reference.isoformat()),
        f'<div style="font-size:1.4rem;font-weight:600;margin-bottom:0.8rem;">{reference:%a %d %b %Y}</div>',
    ]
    if settings:
        lines.append(
            '<div style="color:var(--text-muted);margin-bottom:0.8rem;">'
            + " · ".join(html.escape(item) for item in settings)
            + "</div>"
        )
    lines.append('<div style="display:grid;gap:0.55rem;">')
    for item in cogs:
        lines.append(
            f'  <div style="{RULE}padding:0.35rem 0;">{html.escape(item)}</div>'
        )
    if not cogs:
        lines.append('  <div style="color:var(--text-muted);">No Cogs</div>')
    lines.append("</div>")
    return "\n".join(lines).rstrip() + "\n"


def render_week_view(cogs_dir: Path, reference: date) -> str:
    start = reference - timedelta(days=reference.weekday())
    rows = [_rail_row(start + timedelta(days=offset), cogs_dir, min_height="4.8rem") for offset in range(7)]
    return _frontmatter("week", f"{start.isocalendar().year}-W{start.isocalendar().week:02d}") + _table(
        rows, (16, 24, 44, 16)
    ) + "\n\n## CARRY\n"


def render_five_wow_view(cogs_dir: Path, month: str) -> str:
    rows = []
    for _, _, date_iso in five_wow_rows(month):
        rows.append(_rail_row(datetime.strptime(date_iso, "%Y-%m-%d").date(), cogs_dir, min_height="2rem", compact=True))
    return _frontmatter("5wow", month) + _table(rows, (16, 28, 40, 16)) + "\n"


def render_month_view(cogs_dir: Path, month: str) -> str:
    weekday_style = f"{RULE}padding:0.35rem 0.45rem;font-weight:600;"
    lines = [
        _frontmatter("month", month),
        '<table style="width:100%;border:0;border-collapse:collapse;table-layout:fixed;">',
        "  <thead><tr>",
    ]
    lines.extend(f'    <th style="{weekday_style}">{label}</th>' for label in ("M", "T", "W", "Th", "F", "S", "Su"))
    lines.extend(["  </tr></thead>", "  <tbody>"])
    for week in calendar_grid_with_spillover(month):
        lines.append("    <tr>")
        for day in week:
            settings, cogs = _split_items(_daily_items(cogs_dir, day))
            marker = settings[0] if settings else (cogs[0] if cogs else "")
            lines.append(
                f'      <td style="{CELL}height:4.4rem;">'
                f'<div>{day.day:02d}</div>'
                f'<div style="color:var(--text-muted);font-size:0.85em;">{html.escape(marker)}</div>'
                "</td>"
            )
        lines.append("    </tr>")
    lines.extend(["  </tbody>", "</table>", "", "## CARRY", "", "## KEY", "", "- `~~` setting span", "- `xx` unavailable/out"])
    return "\n".join(lines).rstrip() + "\n"


def _add_months(first: date, offset: int) -> date:
    index = first.year * 12 + first.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def render_12mf_view(reference: date) -> str:
    first = reference.replace(day=1)
    rows: list[list[tuple[str, str]]] = []
    for offset in range(12):
        month = _add_months(first, offset)
        rows.append(
            [
                (f"+{offset}", RAIL),
                (f"{month:%b %Y}", CELL),
                ("", f"{CELL}min-height:2.4rem;"),
            ]
        )
    end = _add_months(first, 11)
    return _frontmatter("12mf", f"{first:%Y-%m}/{end:%Y-%m}") + _table(rows, (12, 28, 60)) + "\n"


def render_annual_view(year: int) -> str:
    rows: list[list[tuple[str, str]]] = []
    for quarter_start in range(1, 13, 3):
        row: list[tuple[str, str]] = []
        for month_number in range(quarter_start, quarter_start + 3):
            label = calendar.month_name[month_number]
            row.append(
                (
                    f'<div style="font-weight:600;">{label}</div><div style="min-height:4rem;"></div>',
                    CELL,
                )
            )
        rows.append(row)
    return _frontmatter("annual", str(year)) + _table(rows, (34, 33, 33)) + "\n\n## CARRY\n"


def build_planning_html_views(cogs_dir: Path, reference_date: str) -> tuple[PlanningHtmlView, ...]:
    reference = datetime.strptime(reference_date, "%Y-%m-%d").date()
    month = reference.strftime("%Y-%m")
    iso_year, iso_week, _ = reference.isocalendar()
    rolling_end = _add_months(reference.replace(day=1), 11)
    return (
        PlanningHtmlView("day", f"Day {reference}.md", render_day_view(cogs_dir, reference)),
        PlanningHtmlView("week", f"Week {iso_year}-W{iso_week:02d}.md", render_week_view(cogs_dir, reference)),
        PlanningHtmlView("5wow", f"5WOW {month}.md", render_five_wow_view(cogs_dir, month)),
        PlanningHtmlView("month", f"Month {month}.md", render_month_view(cogs_dir, month)),
        PlanningHtmlView(
            "12mf",
            f"12MF {month} to {rolling_end:%Y-%m}.md",
            render_12mf_view(reference),
        ),
        PlanningHtmlView("annual", f"Annual {reference.year}.md", render_annual_view(reference.year)),
    )


def write_planning_html_views(output_dir: Path, cogs_dir: Path, reference_date: str) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for view in build_planning_html_views(cogs_dir, reference_date):
        path = output_dir / view.filename
        path.write_text(view.content)
        paths.append(path)
    return paths


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cogs-dir", default=str(DEFAULT_COGS_DIR))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--for", dest="reference_date", default=date.today().isoformat())
    args = parser.parse_args(argv)
    for path in write_planning_html_views(Path(args.output_dir), Path(args.cogs_dir), args.reference_date):
        print(path)


if __name__ == "__main__":
    main()

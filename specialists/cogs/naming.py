"""Cogs date-based filenames and read-only migration planning."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


LEGACY_DAILY_FORMAT = "%a %d %b %Y"
ISO_DAILY_WITH_WEEKDAY_FORMAT = "%Y-%m-%d %a"
ISO_DAILY_FORMAT = "%Y-%m-%d"

DATE_FRONTMATTER_RE = re.compile(r"(?m)^date:\s*(?P<date>\d{4}-\d{2}-\d{2})\s*$")
ISO_DAILY_STEM_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})(?:\s+[A-Za-z]{3})?$")


@dataclass(frozen=True)
class DailyRenamePlanItem:
    """Read-only daily-note rename candidate."""

    date_iso: str
    source_path: Path
    target_path: Path
    status: str
    reason: str


@dataclass(frozen=True)
class CogsMovePlanItem:
    """Read-only Cogs directory migration candidate."""

    kind: str
    date_iso: str
    source_path: Path
    target_path: Path
    status: str
    reason: str


def parse_date_iso(date_iso: str) -> date:
    """Parse a YYYY-MM-DD date string."""
    return datetime.strptime(date_iso, "%Y-%m-%d").date()


def daily_heading(date_iso: str) -> str:
    return parse_date_iso(date_iso).strftime(LEGACY_DAILY_FORMAT)


def daily_filename(date_iso: str, style: str = "legacy") -> str:
    """Return a daily note filename for a supported naming style."""
    dt = parse_date_iso(date_iso)
    if style == "legacy":
        return f"{dt.strftime(LEGACY_DAILY_FORMAT)}.md"
    if style == "iso-weekday":
        return f"{dt.strftime(ISO_DAILY_WITH_WEEKDAY_FORMAT)}.md"
    if style == "iso":
        return f"{dt.strftime(ISO_DAILY_FORMAT)}.md"
    raise ValueError(f"Unsupported daily filename style: {style!r}")


def daily_path(date_iso: str, daily_dir: Path, style: str = "legacy") -> Path:
    return daily_dir / daily_filename(date_iso, style)


def _iso_parts(date_iso: str) -> tuple[str, str, str]:
    dt = parse_date_iso(date_iso)
    iso_year, iso_week, _ = dt.isocalendar()
    return str(iso_year), f"{dt.month:02d}", f"{iso_week:02d}"


def nested_daily_dir(date_iso: str, cogs_dir: Path) -> Path:
    iso_year, month, week = _iso_parts(date_iso)
    return cogs_dir / iso_year / month / week


def nested_daily_path(date_iso: str, cogs_dir: Path, style: str = "iso-weekday") -> Path:
    return nested_daily_dir(date_iso, cogs_dir) / daily_filename(date_iso, style)


def weekly_path(date_iso: str, cogs_dir: Path, style: str = "iso") -> Path:
    iso_year, month, _ = _iso_parts(date_iso)
    return cogs_dir / iso_year / month / weekly_filename(date_iso, style)


def monthly_path(date_iso: str, cogs_dir: Path, style: str = "iso") -> Path:
    return cogs_dir / f"{parse_date_iso(date_iso):%Y}" / monthly_filename(date_iso, style)


def annual_path(date_iso: str, cogs_dir: Path) -> Path:
    return cogs_dir / annual_filename(date_iso)


def _looks_like_cogs_root(path: Path) -> bool:
    return path.name == "Cogs" or any((path / child).exists() for child in ("daily", "weekly", "monthly", "annual"))


def daily_path_candidates(date_iso: str, daily_dir: Path) -> tuple[Path, ...]:
    """Return supported daily-note paths, newest naming first."""
    if _looks_like_cogs_root(daily_dir):
        return (
            nested_daily_path(date_iso, daily_dir, "iso-weekday"),
            nested_daily_path(date_iso, daily_dir, "iso"),
            daily_path(date_iso, daily_dir / "daily", "iso-weekday"),
            daily_path(date_iso, daily_dir / "daily", "iso"),
            daily_path(date_iso, daily_dir / "daily", "legacy"),
        )
    return (
        daily_path(date_iso, daily_dir, "iso-weekday"),
        daily_path(date_iso, daily_dir, "iso"),
        daily_path(date_iso, daily_dir, "legacy"),
    )


def resolve_existing_daily_path(date_iso: str, daily_dir: Path) -> Path | None:
    """Find an existing daily note using either ISO-first or legacy naming."""
    for path in daily_path_candidates(date_iso, daily_dir):
        if path.exists():
            return path
    return None


def preferred_daily_path(date_iso: str, daily_dir: Path, style: str = "legacy") -> Path:
    """Return an existing compatible path if present, otherwise the preferred path."""
    if _looks_like_cogs_root(daily_dir):
        return resolve_existing_daily_path(date_iso, daily_dir) or nested_daily_path(date_iso, daily_dir, "iso-weekday")
    return resolve_existing_daily_path(date_iso, daily_dir) or daily_path(date_iso, daily_dir, style)


def weekly_filename(date_iso: str, style: str = "iso") -> str:
    dt = parse_date_iso(date_iso)
    iso_year, iso_week, _ = dt.isocalendar()
    if style == "iso":
        return f"{iso_year}-W{iso_week:02d}.md"
    if style == "legacy":
        return f"Week {iso_week:02d} {iso_year}.md"
    raise ValueError(f"Unsupported weekly filename style: {style!r}")


def monthly_filename(date_iso: str, style: str = "iso") -> str:
    dt = parse_date_iso(date_iso)
    if style == "iso":
        return f"{dt:%Y-%m}.md"
    if style == "legacy":
        return f"{dt:%b %Y}.md"
    raise ValueError(f"Unsupported monthly filename style: {style!r}")


def annual_filename(date_iso: str) -> str:
    return f"{parse_date_iso(date_iso):%Y}.md"


def five_wow_anchor(date_iso: str) -> str:
    """Return the monthly 5WOW anchor for a date.

    5WOW is five weeks of weekdays: a month-shaped planning view that fits into
    a 5x5 Mon-Fri grid. Stage 26 treats it as a monthly view/section, not as a
    separate schema type.
    """
    return parse_date_iso(date_iso).strftime("%Y-%m")


def planned_note_filenames(date_iso: str) -> dict[str, str]:
    """Return ISO-first filenames/anchors for Stage 26 planning-note previews."""
    return {
        "daily": daily_filename(date_iso, "iso-weekday"),
        "weekly": weekly_filename(date_iso, "iso"),
        "monthly": monthly_filename(date_iso, "iso"),
        "annual": annual_filename(date_iso),
        "five_wow_anchor": five_wow_anchor(date_iso),
    }


def extract_daily_date(path: Path) -> str | None:
    """Infer a daily note date from frontmatter or supported filename styles."""
    try:
        text = path.read_text()
    except OSError:
        return None

    frontmatter_match = DATE_FRONTMATTER_RE.search(text)
    if frontmatter_match:
        return frontmatter_match.group("date")

    iso_match = ISO_DAILY_STEM_RE.match(path.stem)
    if iso_match:
        return iso_match.group("date")

    try:
        return datetime.strptime(path.stem, LEGACY_DAILY_FORMAT).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _extract_period_date(path: Path, *, kind: str) -> str | None:
    try:
        text = path.read_text()
    except OSError:
        return None
    if kind == "weekly":
        match = re.search(r"(?m)^week:\s*(?P<week>\d{4}-W\d{2})\s*$", text)
        if match:
            year, week = match.group("week").split("-W")
            return date.fromisocalendar(int(year), int(week), 1).isoformat()
        match = re.match(r"^(?P<year>\d{4})-W(?P<week>\d{2})$", path.stem)
        if match:
            return date.fromisocalendar(int(match.group("year")), int(match.group("week")), 1).isoformat()
    if kind == "monthly":
        match = re.search(r"(?m)^month:\s*(?P<month>\d{4}-\d{2})\s*$", text)
        month = match.group("month") if match else path.stem if re.match(r"^\d{4}-\d{2}$", path.stem) else ""
        if month:
            return f"{month}-01"
    if kind == "annual":
        match = re.search(r"(?m)^year:\s*(?P<year>\d{4})\s*$", text)
        year = match.group("year") if match else path.stem if re.match(r"^\d{4}$", path.stem) else ""
        if year:
            return f"{year}-01-01"
    return None


def _move_item(kind: str, source_path: Path, date_iso: str, target_path: Path) -> CogsMovePlanItem:
    if not date_iso:
        return CogsMovePlanItem(kind, "", source_path, source_path, "invalid", "could not infer period date")
    if source_path == target_path:
        status = "already-current"
        reason = "already in target structure"
    elif target_path.exists():
        status = "collision"
        reason = "target path already exists"
    else:
        status = "move"
        reason = "safe candidate"
    return CogsMovePlanItem(kind, date_iso, source_path, target_path, status, reason)


def build_cogs_directory_migration_plan(cogs_dir: Path) -> list[CogsMovePlanItem]:
    """Build a read-only plan to move flat Cogs notes into nested structure."""
    plan: list[CogsMovePlanItem] = []
    for source_path in sorted((cogs_dir / "daily").glob("*.md")):
        date_iso = extract_daily_date(source_path) or ""
        target = nested_daily_path(date_iso, cogs_dir, "iso-weekday") if date_iso else source_path
        plan.append(_move_item("daily", source_path, date_iso, target))
    for source_path in sorted((cogs_dir / "weekly").glob("*.md")):
        date_iso = _extract_period_date(source_path, kind="weekly") or ""
        target = weekly_path(date_iso, cogs_dir) if date_iso else source_path
        plan.append(_move_item("weekly", source_path, date_iso, target))
    for source_path in sorted((cogs_dir / "monthly").glob("*.md")):
        date_iso = _extract_period_date(source_path, kind="monthly") or ""
        target = monthly_path(date_iso, cogs_dir) if date_iso else source_path
        plan.append(_move_item("monthly", source_path, date_iso, target))
    for source_path in sorted((cogs_dir / "annual").glob("*.md")):
        date_iso = _extract_period_date(source_path, kind="annual") or ""
        target = annual_path(date_iso, cogs_dir) if date_iso else source_path
        plan.append(_move_item("annual", source_path, date_iso, target))
    target_counts: dict[Path, int] = {}
    for item in plan:
        if item.status == "move":
            target_counts[item.target_path] = target_counts.get(item.target_path, 0) + 1
    if not any(count > 1 for count in target_counts.values()):
        return plan
    checked: list[CogsMovePlanItem] = []
    for item in plan:
        if item.status == "move" and target_counts.get(item.target_path, 0) > 1:
            checked.append(
                CogsMovePlanItem(
                    item.kind,
                    item.date_iso,
                    item.source_path,
                    item.target_path,
                    "collision",
                    "multiple source files target the same nested path",
                )
            )
        else:
            checked.append(item)
    return checked


def apply_cogs_directory_migration_plan(cogs_dir: Path) -> list[CogsMovePlanItem]:
    """Apply a reviewed, collision-free Cogs directory migration plan."""
    plan = build_cogs_directory_migration_plan(cogs_dir)
    blocked = [item for item in plan if item.status not in {"move", "already-current"}]
    if blocked:
        reasons = "; ".join(f"{item.source_path}: {item.reason}" for item in blocked)
        raise ValueError(f"Cogs directory migration plan has blocked items: {reasons}")
    for item in plan:
        if item.status != "move":
            continue
        item.target_path.parent.mkdir(parents=True, exist_ok=True)
        item.source_path.rename(item.target_path)
    return plan


def build_daily_rename_plan(
    daily_dir: Path,
    target_style: str = "iso-weekday",
) -> list[DailyRenamePlanItem]:
    """Build a read-only old-path to ISO-first daily-note rename plan."""
    if target_style not in {"iso-weekday", "iso"}:
        raise ValueError("target_style must be 'iso-weekday' or 'iso'")
    if not daily_dir.exists():
        return []

    plan: list[DailyRenamePlanItem] = []
    if _looks_like_cogs_root(daily_dir):
        source_paths = sorted((daily_dir / "daily").glob("*.md")) + sorted(
            path for path in daily_dir.rglob("*.md")
            if ISO_DAILY_STEM_RE.match(path.stem)
        )
    else:
        source_paths = sorted(daily_dir.glob("*.md"))
    seen: set[Path] = set()
    for source_path in source_paths:
        if source_path in seen:
            continue
        seen.add(source_path)
        date_iso = extract_daily_date(source_path)
        if not date_iso:
            plan.append(
                DailyRenamePlanItem(
                    date_iso="",
                    source_path=source_path,
                    target_path=source_path,
                    status="invalid",
                    reason="could not infer YYYY-MM-DD date",
                )
            )
            continue

        if _looks_like_cogs_root(daily_dir):
            target_path = nested_daily_path(date_iso, daily_dir, target_style)
        else:
            target_path = daily_path(date_iso, daily_dir, target_style)
        if source_path == target_path:
            status = "already-current"
            reason = "already uses target naming style"
        elif target_path.exists():
            status = "collision"
            reason = "target path already exists"
        else:
            status = "rename"
            reason = "safe candidate"
        plan.append(
            DailyRenamePlanItem(
                date_iso=date_iso,
                source_path=source_path,
                target_path=target_path,
                status=status,
                reason=reason,
            )
        )
    return plan


def apply_daily_rename_plan(
    daily_dir: Path,
    target_style: str = "iso-weekday",
) -> list[DailyRenamePlanItem]:
    """Apply a collision-free daily rename plan one file at a time."""
    plan = build_daily_rename_plan(daily_dir, target_style)
    blocked = [item for item in plan if item.status not in {"rename", "already-current"}]
    if blocked:
        reasons = "; ".join(f"{item.source_path.name}: {item.reason}" for item in blocked)
        raise ValueError(f"Daily rename plan has blocked items: {reasons}")

    applied: list[DailyRenamePlanItem] = []
    for item in plan:
        if item.status == "already-current":
            applied.append(item)
            continue
        if item.target_path.exists():
            raise FileExistsError(f"Daily rename target already exists: {item.target_path}")
        item.source_path.rename(item.target_path)
        applied.append(item)
    return applied

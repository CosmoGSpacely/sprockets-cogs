"""Shared vault primitives for Cogs daily notes and carry workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from specialists.cogs.naming import monthly_path, preferred_daily_path, weekly_path


DEFAULT_VAULT_DIR = Path.home() / "vault"
DEFAULT_COGS_DIR = DEFAULT_VAULT_DIR / "Cogs"
DEFAULT_DAILY_DIR = DEFAULT_COGS_DIR

TASK_LINE_RE = re.compile(r"^(?P<indent>\s*)- \[(?P<state>[ x>\-])\] (?P<text>.*)$")


@dataclass(frozen=True)
class CogsBlock:
    """A top-level Cogs task and any indented child lines below it."""

    start_line: int
    end_line: int
    lines: tuple[str, ...]
    state: str
    item_text: str


@dataclass(frozen=True)
class CorrectionResult:
    """Result from a vault-facing Cogs locator correction."""

    status: str
    message: str
    source_path: Path | None = None
    target_path: Path | None = None


def daily_note_path(date_iso: str, daily_dir: Path = DEFAULT_DAILY_DIR) -> Path:
    return preferred_daily_path(date_iso, daily_dir, style="iso-weekday")


def ensure_daily_note(date_iso: str, daily_dir: Path = DEFAULT_DAILY_DIR) -> Path:
    path = daily_note_path(date_iso, daily_dir)
    if not path.exists():
        from specialists.cogs.planning import render_daily_note_template

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_daily_note_template(date_iso))
    return path


def append_cogs_item_text(
    date_iso: str,
    item_text: str,
    daily_dir: Path = DEFAULT_DAILY_DIR,
) -> bool:
    """Append an open Cogs item if no equivalent task state already exists."""
    note_path = ensure_daily_note(date_iso, daily_dir)
    existing = note_path.read_text()
    if any(f"{state} {item_text}" in existing for state in ["- [ ]", "- [x]", "- [>]", "- [-]"]):
        return False
    with note_path.open("a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(f"- [ ] {item_text}\n")
    return True


def append_cogs_block(
    date_iso: str,
    block_lines: tuple[str, ...] | list[str],
    daily_dir: Path = DEFAULT_DAILY_DIR,
) -> bool:
    """Append a full Cogs block, preserving indented detail lines."""

    if not block_lines:
        raise ValueError("block_lines cannot be empty")
    first_match = TASK_LINE_RE.match(block_lines[0])
    if not first_match:
        raise ValueError("first block line must be a Cogs task line")
    item_text = first_match.group("text").strip()
    note_path = ensure_daily_note(date_iso, daily_dir)
    existing = note_path.read_text()
    if any(f"{state} {item_text}" in existing for state in ["- [ ]", "- [x]", "- [>]", "- [-]"]):
        return False

    normalized = list(block_lines)
    normalized[0] = TASK_LINE_RE.sub(r"- [ ] \g<text>", normalized[0], count=1)
    with note_path.open("a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write("\n".join(normalized).rstrip() + "\n")
    return True


def append_weekly_carry_item_text(
    date_iso: str,
    item_text: str,
    cogs_dir: Path = DEFAULT_VAULT_DIR / "Cogs",
) -> bool:
    """Append an item to the CARRY block of the week containing date_iso."""

    from specialists.cogs.planning import render_weekly_note_template

    path = weekly_path(date_iso, cogs_dir)
    return _append_planning_carry_item(path, render_weekly_note_template(date_iso), item_text)


def append_monthly_carry_item_text(
    date_iso: str,
    item_text: str,
    cogs_dir: Path = DEFAULT_VAULT_DIR / "Cogs",
) -> bool:
    """Append an item to the CARRY block of the month containing date_iso."""

    from specialists.cogs.planning import render_monthly_note_template

    path = monthly_path(date_iso, cogs_dir)
    return _append_planning_carry_item(path, render_monthly_note_template(date_iso[:7]), item_text)


def _append_planning_carry_item(path: Path, template: str, item_text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(template)

    content = path.read_text()
    if any(f"{state} {item_text}" in content for state in ["- [ ]", "- [x]", "- [>]", "- [-]"]):
        return False

    heading = "## CARRY" if "## CARRY" in content or "## Carry In" not in content else "## Carry In"
    updated = _append_under_heading(content, heading, f"- [ ] {item_text}")
    path.write_text(updated)
    return True


def _append_under_heading(content: str, heading: str, line: str) -> str:
    lines = content.splitlines()
    try:
        heading_index = lines.index(heading)
    except ValueError:
        base = content.rstrip()
        return f"{base}\n\n{heading}\n{line}\n"

    insert_at = heading_index + 1
    if insert_at >= len(lines) or lines[insert_at] != "":
        lines.insert(insert_at, "")
        insert_at += 1
    while insert_at < len(lines) and lines[insert_at] == "":
        insert_at += 1
    lines.insert(insert_at, line)
    if insert_at + 1 >= len(lines) or lines[insert_at + 1] != "":
        lines.insert(insert_at + 1, "")
    return "\n".join(lines).rstrip() + "\n"


def parse_cogs_blocks(content: str, states: set[str] | None = None) -> list[CogsBlock]:
    """
    Parse top-level Cogs task blocks.
    A block starts at an unindented task line and includes following indented lines.
    """
    allowed = states or {" "}
    lines = content.splitlines()
    blocks: list[CogsBlock] = []
    i = 0
    while i < len(lines):
        match = TASK_LINE_RE.match(lines[i])
        if not match or match.group("indent") or match.group("state") not in allowed:
            i += 1
            continue

        start = i
        i += 1
        while i < len(lines):
            next_match = TASK_LINE_RE.match(lines[i])
            if next_match and not next_match.group("indent"):
                break
            if lines[i] and not lines[i].startswith((" ", "\t")):
                break
            i += 1

        block_lines = tuple(lines[start:i])
        blocks.append(
            CogsBlock(
                start_line=start,
                end_line=i - 1,
                lines=block_lines,
                state=match.group("state"),
                item_text=match.group("text").strip(),
            )
        )
    return blocks


def mark_block_state(content: str, block: CogsBlock, state: str) -> str:
    """Return content with the block's top-level task marker changed."""
    if state not in {" ", "x", ">", "-"}:
        raise ValueError(f"Unsupported Cogs task state: {state!r}")
    lines = content.splitlines()
    line = lines[block.start_line]
    lines[block.start_line] = TASK_LINE_RE.sub(f"- [{state}] " + r"\g<text>", line, count=1)
    trailing_newline = "\n" if content.endswith("\n") else ""
    return "\n".join(lines) + trailing_newline


def correct_cog_locator(
    query: str,
    destination_date: str,
    daily_dir: Path = DEFAULT_DAILY_DIR,
    *,
    replacement_text: str | None = None,
) -> CorrectionResult:
    """Move one clearly matched open Cog to a corrected daily locator."""

    matches = _find_open_blocks(query, daily_dir)
    if not matches:
        return CorrectionResult("review", f"no open Cog matched {query!r}")
    if len(matches) > 1:
        return CorrectionResult("review", f"{len(matches)} open Cogs matched {query!r}")

    source_path, block = matches[0]
    source_content = source_path.read_text()
    corrected_text = replacement_text or block.item_text
    corrected_lines = _replacement_block_lines(block, corrected_text)

    updated_source = _mark_block_corrected(source_content, block, destination_date)
    source_path.write_text(updated_source)
    appended = append_cogs_block(destination_date, corrected_lines, daily_dir)
    target_path = daily_note_path(destination_date, daily_dir)
    verb = "moved" if appended else "already present"
    return CorrectionResult(
        "corrected",
        f"{verb} {block.item_text!r} to {destination_date}",
        source_path=source_path,
        target_path=target_path,
    )


def replace_open_cog_text(
    query: str,
    replacement_text: str,
    daily_dir: Path = DEFAULT_DAILY_DIR,
) -> CorrectionResult:
    """Replace text in all clearly matched open or carried Cogs."""

    matches = _find_blocks(query, daily_dir, states={" ", ">"})
    if not matches:
        return CorrectionResult("review", f"no open Cog matched {query!r}")
    for source_path, block in matches:
        content = source_path.read_text()
        lines = content.splitlines()
        original = lines[block.start_line]
        state = block.state
        lines[block.start_line] = TASK_LINE_RE.sub(
            f"- [{state}] {replacement_text}",
            original,
            count=1,
        )
        note = f"  correction: replaced {query!r}"
        if note not in lines[block.start_line + 1:block.end_line + 2]:
            lines.insert(block.start_line + 1, note)
        trailing_newline = "\n" if content.endswith("\n") else ""
        source_path.write_text("\n".join(lines) + trailing_newline)
    return CorrectionResult("corrected", f"replaced {query!r} with {replacement_text!r} in {len(matches)} Cog(s)")


def mark_blocks_corrected_by_text(path: Path, item_text: str, reason: str) -> int:
    """Mark open blocks containing item_text as corrected/dropped."""

    if not path.exists():
        return 0
    content = path.read_text()
    blocks = [
        block
        for block in parse_cogs_blocks(content, states={" "})
        if item_text.lower() in block.item_text.lower()
    ]
    if not blocks:
        return 0
    lines = content.splitlines()
    offset = 0
    for block in blocks:
        line_index = block.start_line + offset
        lines[line_index] = TASK_LINE_RE.sub("- [-] " + r"\g<text>", lines[line_index], count=1)
        note = f"  correction: {reason}"
        lines.insert(line_index + 1, note)
        offset += 1
    trailing_newline = "\n" if content.endswith("\n") else ""
    path.write_text("\n".join(lines) + trailing_newline)
    return len(blocks)


def _find_open_blocks(query: str, daily_dir: Path) -> list[tuple[Path, CogsBlock]]:
    return _find_blocks(query, daily_dir, states={" "})


def _find_blocks(query: str, daily_dir: Path, *, states: set[str]) -> list[tuple[Path, CogsBlock]]:
    normalized = query.lower().strip()
    if not normalized or not daily_dir.exists():
        return []
    matches: list[tuple[Path, CogsBlock]] = []
    for path in sorted(daily_dir.rglob("*.md")):
        content = path.read_text()
        for block in parse_cogs_blocks(content, states=states):
            if normalized in block.item_text.lower():
                matches.append((path, block))
    return matches


def _replacement_block_lines(block: CogsBlock, replacement_text: str) -> tuple[str, ...]:
    lines = list(block.lines)
    lines[0] = TASK_LINE_RE.sub(f"- [ ] {replacement_text}", lines[0], count=1)
    return tuple(lines)


def _mark_block_corrected(content: str, block: CogsBlock, destination_date: str) -> str:
    marked = mark_block_state(content, block, ">")
    lines = marked.splitlines()
    note = f"  correction: moved to {destination_date}"
    insert_at = block.start_line + 1
    if note not in lines[insert_at:block.end_line + 2]:
        lines.insert(insert_at, note)
    trailing_newline = "\n" if marked.endswith("\n") else ""
    return "\n".join(lines) + trailing_newline

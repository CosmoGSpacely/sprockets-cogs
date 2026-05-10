"""Shared vault primitives for Cogs daily notes and carry workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_VAULT_DIR = Path.home() / "vault"
DEFAULT_DAILY_DIR = DEFAULT_VAULT_DIR / "Cogs" / "daily"

TASK_LINE_RE = re.compile(r"^(?P<indent>\s*)- \[(?P<state>[ x>\-])\] (?P<text>.*)$")


@dataclass(frozen=True)
class CogsBlock:
    """A top-level Cogs task and any indented child lines below it."""

    start_line: int
    end_line: int
    lines: tuple[str, ...]
    state: str
    item_text: str


def daily_note_path(date_iso: str, daily_dir: Path = DEFAULT_DAILY_DIR) -> Path:
    dt = datetime.strptime(date_iso, "%Y-%m-%d")
    heading = dt.strftime("%a %d %b %Y")
    return daily_dir / f"{heading}.md"


def ensure_daily_note(date_iso: str, daily_dir: Path = DEFAULT_DAILY_DIR) -> Path:
    path = daily_note_path(date_iso, daily_dir)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        dt = datetime.strptime(date_iso, "%Y-%m-%d")
        heading = dt.strftime("%a %d %b %Y")
        path.write_text(
            f"---\nnode_type: cogs/daily\ndate: {date_iso}\ntags: [cogs/daily]\n---\n\n"
            f"# {heading}\n\n"
        )
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
        f.write(f"- [ ] {item_text}\n")
    return True


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

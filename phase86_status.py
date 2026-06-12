"""Read-only Phase 8.6 promotion and deferred-work status.

Stage 98 gives Uniblab a small status surface for the active implementation
interruption. The builder repo remains the source of roadmap/stage truth; this
module only reads it and formats an operator report.
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path


BUILDER_ENV = "SPROCKETS_COGS_BUILDER_DIR"
PROMOTION_STAGE_MAP = {
    "1": "98",
    "2": "99",
    "3": "100",
    "4": "101",
    "5": "102",
    "5A": "102",
    "5B": "102",
    "6": "99",
    "7": "103",
    "8": "105",
    "9": "98",
    "10": "98",
    "11": "99",
    "12": "99",
    "13": "100",
    "14": "103",
    "15": "101",
    "16": "102",
    "17": "105",
    "18": "103",
    "19": "103",
    "20": "103",
    "21": "104",
    "22": "103",
}


@dataclass(frozen=True)
class Phase86Stage:
    number: str
    focus: str
    promotions: str


@dataclass(frozen=True)
class DeferredRow:
    deferred_id: str
    title: str
    disposition: str
    note: str

    @property
    def stage_home(self) -> str | None:
        text = f"{self.disposition} {self.note}"
        match = re.search(r"Stage\s+(\d+)", text)
        if match:
            return match.group(1)
        match = re.search(r"Promotion\s+(\d+[A-Z]?)", text)
        if not match:
            return None
        return PROMOTION_STAGE_MAP.get(match.group(1))

    @property
    def is_phase86_scheduled(self) -> bool:
        text = f"{self.disposition} {self.note}".lower()
        return "phase 8.6" in text or "stage 98" in text or "stage 99" in text or "stage 100" in text or "stage 101" in text or "stage 102" in text or "stage 103" in text or "stage 104" in text or "stage 105" in text

    @property
    def is_fired_trigger(self) -> bool:
        return "trigger fired" in f"{self.disposition} {self.note}".lower()

    @property
    def is_unscheduled(self) -> bool:
        text = f"{self.disposition} {self.note}".lower()
        if self.is_phase86_scheduled or self.is_fired_trigger:
            return False
        if "scheduled" in text or "promoted" in text or "built" in text:
            return False
        return "deferred" in text or "keep deferred" in text


@dataclass(frozen=True)
class Phase86Status:
    builder_dir: Path
    promoted_count: int | None
    stages: tuple[Phase86Stage, ...]
    deferred_rows: tuple[DeferredRow, ...]

    @property
    def phase86_scheduled_rows(self) -> tuple[DeferredRow, ...]:
        return tuple(row for row in self.deferred_rows if row.is_phase86_scheduled)

    @property
    def fired_trigger_rows(self) -> tuple[DeferredRow, ...]:
        return tuple(row for row in self.deferred_rows if row.is_fired_trigger)

    @property
    def unscheduled_rows(self) -> tuple[DeferredRow, ...]:
        return tuple(row for row in self.deferred_rows if row.is_unscheduled)


def default_builder_dir() -> Path:
    configured = os.environ.get(BUILDER_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parent.parent / "sprockets-cogs-builder"


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""


def parse_promoted_count(status_text: str) -> int | None:
    match = re.search(r"Behaviors promoted during Phase 8\.6[^:]*:\s*\*\*(\d+)\*\*", status_text)
    return int(match.group(1)) if match else None


def parse_stage_map(readme_text: str) -> tuple[Phase86Stage, ...]:
    stages: list[Phase86Stage] = []
    for line in readme_text.splitlines():
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        stages.append(Phase86Stage(number=parts[0], focus=parts[1], promotions=parts[2]))
    return tuple(stages)


def parse_deferred_rows(deferred_text: str) -> tuple[DeferredRow, ...]:
    rows: list[DeferredRow] = []
    for line in deferred_text.splitlines():
        if not line.startswith("| D"):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) < 4:
            continue
        rows.append(
            DeferredRow(
                deferred_id=parts[0],
                title=parts[1],
                disposition=parts[2],
                note=parts[3],
            )
        )
    return tuple(rows)


def build_phase86_status(builder_dir: Path | None = None) -> Phase86Status:
    root = builder_dir or default_builder_dir()
    phase_readme = root / "stages" / "phase-086-implementation-interruption-promotion" / "README.md"
    return Phase86Status(
        builder_dir=root,
        promoted_count=parse_promoted_count(_read(root / "STATUS.md")),
        stages=parse_stage_map(_read(phase_readme)),
        deferred_rows=parse_deferred_rows(_read(root / "DEFERRED.md")),
    )


def _format_rows(rows: tuple[DeferredRow, ...], *, include_stage: bool = False) -> list[str]:
    if not rows:
        return ["- none"]
    lines: list[str] = []
    for row in rows:
        stage = f" -> Stage {row.stage_home}" if include_stage and row.stage_home else ""
        lines.append(f"- {row.deferred_id}: {row.title}{stage}")
    return lines


def format_phase86_status(status: Phase86Status) -> str:
    promoted = str(status.promoted_count) if status.promoted_count is not None else "unknown"
    lines = [
        "Phase 8.6 promotion status",
        "",
        f"- builder: {status.builder_dir}",
        f"- live behaviors promoted: {promoted}",
        f"- active stage ledgers: {len(status.stages)}",
        f"- deferred rows tied to Phase 8.6: {len(status.phase86_scheduled_rows)}",
        f"- fired deferred triggers: {len(status.fired_trigger_rows)}",
        f"- unscheduled deferred rows: {len(status.unscheduled_rows)}",
        "",
        "Stage ledgers",
    ]
    if status.stages:
        lines.extend(f"- Stage {stage.number}: {stage.focus} (promotions {stage.promotions})" for stage in status.stages)
    else:
        lines.append("- none found")

    lines.extend(
        [
            "",
            "Fired deferred triggers",
            *_format_rows(status.fired_trigger_rows, include_stage=True),
            "",
            "Phase 8.6 deferred schedule",
            *_format_rows(status.phase86_scheduled_rows, include_stage=True),
            "",
            "Unscheduled deferred rows",
            *_format_rows(status.unscheduled_rows),
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Report Phase 8.6 promotion and deferred-work status.")
    parser.add_argument("--builder-dir", type=Path, default=None, help=f"Builder repo path. Defaults to ${BUILDER_ENV} or sibling repo.")
    args = parser.parse_args(argv)
    print(format_phase86_status(build_phase86_status(args.builder_dir)))


if __name__ == "__main__":
    main()

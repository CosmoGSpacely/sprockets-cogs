"""Preview SC operational backup scope.

Stage 63 starts with read-only inventory. Archive creation and restore are
separate slices so the backup policy is visible before any file is written.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Sequence

import agentic_loop


BackupRole = Literal["durable", "optional", "transient", "missing"]


@dataclass(frozen=True)
class BackupPathInventory:
    label: str
    path: Path
    role: BackupRole
    included_by_default: bool
    exists: bool
    file_count: int
    byte_count: int
    latest_mtime: float | None = None
    note: str = ""

    @property
    def latest_mtime_text(self) -> str:
        if self.latest_mtime is None:
            return "(none)"
        return datetime.fromtimestamp(self.latest_mtime).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ScBackupPreview:
    sc_root: Path
    include_input: bool
    paths: tuple[BackupPathInventory, ...]

    @property
    def included_paths(self) -> tuple[BackupPathInventory, ...]:
        return tuple(item for item in self.paths if item.included_by_default or (item.label == "input" and self.include_input))

    @property
    def excluded_paths(self) -> tuple[BackupPathInventory, ...]:
        included = set(self.included_paths)
        return tuple(item for item in self.paths if item not in included)

    @property
    def included_file_count(self) -> int:
        return sum(item.file_count for item in self.included_paths)

    @property
    def included_byte_count(self) -> int:
        return sum(item.byte_count for item in self.included_paths)

    @property
    def warnings(self) -> tuple[str, ...]:
        warnings: list[str] = []
        processing = next((item for item in self.paths if item.label == "processing"), None)
        if processing and processing.file_count:
            warnings.append(f"processing/ is non-empty ({processing.file_count} file(s)); it is excluded as transient")
        input_item = next((item for item in self.paths if item.label == "input"), None)
        if input_item and input_item.file_count and not self.include_input:
            warnings.append(f"input/ contains {input_item.file_count} file(s); pass --include-input to include for stuck-intake debugging")
        return tuple(warnings)


def _path_stats(path: Path) -> tuple[int, int, float | None]:
    if not path.exists():
        return (0, 0, None)
    if path.is_file():
        stat = path.stat()
        return (1, stat.st_size, stat.st_mtime)

    file_count = 0
    byte_count = 0
    latest_mtime: float | None = None
    for candidate in path.rglob("*"):
        if not candidate.is_file():
            continue
        stat = candidate.stat()
        file_count += 1
        byte_count += stat.st_size
        if latest_mtime is None or stat.st_mtime > latest_mtime:
            latest_mtime = stat.st_mtime
    return (file_count, byte_count, latest_mtime)


def _inventory_item(
    *,
    label: str,
    path: Path,
    role: BackupRole,
    included_by_default: bool,
    note: str,
) -> BackupPathInventory:
    file_count, byte_count, latest_mtime = _path_stats(path)
    return BackupPathInventory(
        label=label,
        path=path,
        role=role if path.exists() else "missing",
        included_by_default=included_by_default and path.exists(),
        exists=path.exists(),
        file_count=file_count,
        byte_count=byte_count,
        latest_mtime=latest_mtime,
        note=note,
    )


def build_backup_preview(
    sc_root: Path = agentic_loop.SC_ROOT,
    *,
    include_input: bool = False,
) -> ScBackupPreview:
    """Build the read-only SC backup preview."""

    sc_root = sc_root.expanduser()
    paths = (
        _inventory_item(
            label="archive",
            path=sc_root / "archive",
            role="durable",
            included_by_default=True,
            note="processed input history and audit trail",
        ),
        _inventory_item(
            label="output",
            path=sc_root / "output",
            role="durable",
            included_by_default=True,
            note="operator reports, packets, traces, and audits",
        ),
        _inventory_item(
            label="entity_state",
            path=sc_root / "entity_state.json",
            role="durable",
            included_by_default=True,
            note="hot contact/entity working memory",
        ),
        _inventory_item(
            label="state",
            path=sc_root / "state",
            role="durable",
            included_by_default=True,
            note="future grouped runtime state",
        ),
        _inventory_item(
            label="input",
            path=sc_root / "input",
            role="optional",
            included_by_default=False,
            note="pending intake; include only for stuck-intake debugging",
        ),
        _inventory_item(
            label="processing",
            path=sc_root / "processing",
            role="transient",
            included_by_default=False,
            note="service-owned in-flight work; excluded from backup",
        ),
    )
    return ScBackupPreview(sc_root=sc_root, include_input=include_input, paths=paths)


def _format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


def format_backup_preview(preview: ScBackupPreview) -> str:
    """Format a human-readable read-only backup preview."""

    lines = [
        "SC backup preview",
        "- writes: no",
        f"- sc root: {preview.sc_root}",
        f"- include input: {'yes' if preview.include_input else 'no'}",
        f"- included files: {preview.included_file_count}",
        f"- included size: {_format_bytes(preview.included_byte_count)}",
        "",
        "Included paths",
    ]
    for item in preview.included_paths:
        lines.append(
            f"- {item.label}: {item.path} ({item.file_count} file(s), {_format_bytes(item.byte_count)}, latest {item.latest_mtime_text})"
        )
        lines.append(f"  note: {item.note}")
    lines.extend(["", "Excluded paths"])
    for item in preview.excluded_paths:
        lines.append(
            f"- {item.label}: {item.path} role={item.role} ({item.file_count} file(s), {_format_bytes(item.byte_count)})"
        )
        lines.append(f"  note: {item.note}")
    if preview.warnings:
        lines.extend(["", "Warnings"])
        lines.extend(f"- {warning}" for warning in preview.warnings)
    return "\n".join(lines)


def preview_to_json(preview: ScBackupPreview) -> str:
    """Return a stable JSON representation for tests and future tooling."""

    return json.dumps(
        {
            "writes": "none",
            "sc_root": str(preview.sc_root),
            "include_input": preview.include_input,
            "included_file_count": preview.included_file_count,
            "included_byte_count": preview.included_byte_count,
            "warnings": list(preview.warnings),
            "paths": [
                {
                    "label": item.label,
                    "path": str(item.path),
                    "role": item.role,
                    "included": item in preview.included_paths,
                    "exists": item.exists,
                    "file_count": item.file_count,
                    "byte_count": item.byte_count,
                    "latest_mtime": item.latest_mtime_text,
                    "note": item.note,
                }
                for item in preview.paths
            ],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Preview SC operational backup scope.")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview backup scope without writing. This is currently the default and only mode.",
    )
    parser.add_argument(
        "--sc-root",
        type=Path,
        default=agentic_loop.SC_ROOT,
        help="SC runtime root to inspect; defaults to configured SPROCKETS_COGS_SC_ROOT.",
    )
    parser.add_argument(
        "--include-input",
        action="store_true",
        help="Include pending input/ files in preview scope for stuck-intake debugging.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    preview = build_backup_preview(args.sc_root, include_input=args.include_input)
    if args.json:
        print(preview_to_json(preview))
    else:
        print(format_backup_preview(preview))


if __name__ == "__main__":
    main()

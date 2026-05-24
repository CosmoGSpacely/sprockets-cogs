"""Manage SC operational backup scope.

Stage 63 keeps SC backups boring and explicit: preview/status are read-only,
and create writes a plain timestamped directory snapshot only when requested.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Sequence

import agentic_loop


BackupRole = Literal["durable", "optional", "transient", "missing"]
BACKUP_FORMAT = "sc-directory-snapshot-v1"


def default_backup_root() -> Path:
    """Return the default local backup directory."""

    return Path.home() / "sprockets-cogs" / "backups"


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


@dataclass(frozen=True)
class ScBackupCreateResult:
    backup_path: Path
    manifest_path: Path
    preview: ScBackupPreview


@dataclass(frozen=True)
class ScBackupStatus:
    backup_root: Path
    exists: bool
    snapshot_count: int
    latest_snapshot: Path | None

    @property
    def latest_snapshot_text(self) -> str:
        if self.latest_snapshot is None:
            return "(none)"
        return str(self.latest_snapshot)

    @property
    def latest_mtime_text(self) -> str:
        if self.latest_snapshot is None:
            return "(none)"
        return datetime.fromtimestamp(self.latest_snapshot.stat().st_mtime).isoformat(timespec="seconds")


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


def _snapshot_name(created_at: datetime | None = None) -> str:
    created_at = created_at or datetime.now()
    return f"sc-{created_at.strftime('%Y%m%d-%H%M%S')}"


def _collision_safe_snapshot_path(backup_root: Path, created_at: datetime | None = None) -> Path:
    base = backup_root / _snapshot_name(created_at)
    if not base.exists():
        return base
    for suffix in range(1, 100):
        candidate = backup_root / f"{base.name}-{suffix:02d}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"could not choose an unused backup path under {backup_root}")


def _relative_destination(label: str) -> Path:
    if label == "entity_state":
        return Path("entity_state.json")
    return Path(label)


def _manifest(preview: ScBackupPreview, backup_path: Path) -> dict[str, object]:
    return {
        "format": BACKUP_FORMAT,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "sc_root": str(preview.sc_root),
        "backup_path": str(backup_path),
        "include_input": preview.include_input,
        "included_file_count": preview.included_file_count,
        "included_byte_count": preview.included_byte_count,
        "paths": [
            {
                "label": item.label,
                "source": str(item.path),
                "destination": str(_relative_destination(item.label)),
                "role": item.role,
                "file_count": item.file_count,
                "byte_count": item.byte_count,
                "latest_mtime": item.latest_mtime_text,
                "note": item.note,
            }
            for item in preview.included_paths
        ],
    }


def create_backup_snapshot(
    sc_root: Path = agentic_loop.SC_ROOT,
    *,
    backup_root: Path | None = None,
    out: Path | None = None,
    include_input: bool = False,
    created_at: datetime | None = None,
) -> ScBackupCreateResult:
    """Create a plain directory snapshot of durable SC operational data."""

    backup_root = (backup_root or default_backup_root()).expanduser()
    backup_path = out.expanduser() if out is not None else _collision_safe_snapshot_path(backup_root, created_at)
    if backup_path.exists():
        raise FileExistsError(f"backup path already exists: {backup_path}")

    preview = build_backup_preview(sc_root, include_input=include_input)
    if not preview.included_paths:
        raise ValueError(f"no included SC backup paths exist under {preview.sc_root}")
    backup_path.mkdir(parents=True)
    for item in preview.included_paths:
        destination = backup_path / _relative_destination(item.label)
        if item.path.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.path, destination)
        elif item.path.is_dir():
            shutil.copytree(item.path, destination)

    manifest_path = backup_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest(preview, backup_path), indent=2, sort_keys=True), encoding="utf-8")
    return ScBackupCreateResult(backup_path=backup_path, manifest_path=manifest_path, preview=preview)


def build_backup_status(backup_root: Path | None = None) -> ScBackupStatus:
    """Return read-only backup status for Uniblab operational checks."""

    backup_root = (backup_root or default_backup_root()).expanduser()
    snapshots = (
        tuple(sorted((item for item in backup_root.glob("sc-*") if item.is_dir()), key=lambda item: item.name))
        if backup_root.exists()
        else ()
    )
    latest = snapshots[-1] if snapshots else None
    return ScBackupStatus(
        backup_root=backup_root,
        exists=backup_root.exists(),
        snapshot_count=len(snapshots),
        latest_snapshot=latest,
    )


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


def format_backup_create_result(result: ScBackupCreateResult) -> str:
    """Format a human-readable backup creation summary."""

    lines = [
        "SC backup create",
        "- writes: backup",
        f"- sc root: {result.preview.sc_root}",
        f"- backup path: {result.backup_path}",
        f"- manifest: {result.manifest_path}",
        f"- include input: {'yes' if result.preview.include_input else 'no'}",
        f"- copied files: {result.preview.included_file_count}",
        f"- copied size: {_format_bytes(result.preview.included_byte_count)}",
        "",
        "Copied paths",
    ]
    for item in result.preview.included_paths:
        lines.append(f"- {item.label}: {item.file_count} file(s), {_format_bytes(item.byte_count)}")
    if result.preview.warnings:
        lines.extend(["", "Warnings"])
        lines.extend(f"- {warning}" for warning in result.preview.warnings)
    return "\n".join(lines)


def create_result_to_json(result: ScBackupCreateResult) -> str:
    """Return a stable JSON representation of backup creation."""

    return json.dumps(
        {
            "writes": "backup",
            "format": BACKUP_FORMAT,
            "sc_root": str(result.preview.sc_root),
            "backup_path": str(result.backup_path),
            "manifest_path": str(result.manifest_path),
            "include_input": result.preview.include_input,
            "copied_file_count": result.preview.included_file_count,
            "copied_byte_count": result.preview.included_byte_count,
            "warnings": list(result.preview.warnings),
        },
        indent=2,
        sort_keys=True,
    )


def format_backup_status(status: ScBackupStatus) -> str:
    """Format read-only backup status."""

    return "\n".join(
        [
            "SC backup status",
            "- writes: no",
            f"- backup root: {status.backup_root}",
            f"- backup root exists: {'yes' if status.exists else 'no'}",
            f"- snapshots: {status.snapshot_count}",
            f"- latest snapshot: {status.latest_snapshot_text}",
            f"- latest snapshot modified: {status.latest_mtime_text}",
            "- create command: scripts/sc-backup --create",
        ]
    )


def status_to_json(status: ScBackupStatus) -> str:
    """Return a stable JSON representation of backup status."""

    return json.dumps(
        {
            "writes": "none",
            "backup_root": str(status.backup_root),
            "exists": status.exists,
            "snapshot_count": status.snapshot_count,
            "latest_snapshot": str(status.latest_snapshot) if status.latest_snapshot else None,
            "latest_mtime": status.latest_mtime_text,
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Preview, create, or inspect SC operational backups.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="Preview backup scope without writing. This is the default.")
    mode.add_argument("--create", action="store_true", help="Create a plain timestamped directory snapshot.")
    mode.add_argument("--status", action="store_true", help="Show read-only backup status.")
    parser.add_argument(
        "--sc-root",
        type=Path,
        default=agentic_loop.SC_ROOT,
        help="SC runtime root to inspect; defaults to configured SPROCKETS_COGS_SC_ROOT.",
    )
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=default_backup_root(),
        help="Root directory for default timestamped snapshots.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Explicit backup directory to create. Refuses to overwrite existing paths.",
    )
    parser.add_argument(
        "--include-input",
        action="store_true",
        help="Include pending input/ files for stuck-intake debugging.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    if args.status:
        status = build_backup_status(args.backup_root)
        print(status_to_json(status) if args.json else format_backup_status(status))
        return

    if args.create:
        try:
            result = create_backup_snapshot(
                args.sc_root,
                backup_root=args.backup_root,
                out=args.out,
                include_input=args.include_input,
            )
        except (FileExistsError, ValueError) as exc:
            parser.error(str(exc))
        print(create_result_to_json(result) if args.json else format_backup_create_result(result))
        return

    preview = build_backup_preview(args.sc_root, include_input=args.include_input)
    print(preview_to_json(preview) if args.json else format_backup_preview(preview))


if __name__ == "__main__":
    main()

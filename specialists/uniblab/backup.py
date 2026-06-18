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

import specialists.rosie.loop as agentic_loop


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


@dataclass(frozen=True)
class BackupContentCheck:
    label: str
    source: Path
    destination: Path
    exists: bool
    expected_file_count: int
    actual_file_count: int
    expected_byte_count: int
    actual_byte_count: int


@dataclass(frozen=True)
class ScBackupVerification:
    backup_path: Path
    manifest_path: Path
    manifest: dict[str, object] | None
    checks: tuple[BackupContentCheck, ...]
    issues: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class RestoreTargetPreview:
    label: str
    source: Path
    target: Path
    source_exists: bool
    target_exists: bool
    file_count: int
    byte_count: int


@dataclass(frozen=True)
class ScRestorePreview:
    backup_path: Path
    restore_to: Path
    verification: ScBackupVerification
    targets: tuple[RestoreTargetPreview, ...]

    @property
    def warnings(self) -> tuple[str, ...]:
        warnings = list(self.verification.issues)
        for target in self.targets:
            if target.target_exists:
                warnings.append(f"target exists and would not be overwritten by default: {target.target}")
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


def _read_manifest(backup_path: Path) -> tuple[dict[str, object] | None, tuple[str, ...]]:
    manifest_path = backup_path / "manifest.json"
    if not manifest_path.exists():
        return None, (f"missing manifest: {manifest_path}",)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, (f"invalid manifest JSON: {exc}",)
    if not isinstance(payload, dict):
        return None, ("manifest must be a JSON object",)
    issues: list[str] = []
    if payload.get("format") != BACKUP_FORMAT:
        issues.append(f"unsupported backup format: {payload.get('format')!r}")
    if not isinstance(payload.get("paths"), list):
        issues.append("manifest paths must be a list")
    return payload, tuple(issues)


def verify_backup_snapshot(backup_path: Path) -> ScBackupVerification:
    """Inspect a backup snapshot and compare contents with its manifest."""

    backup_path = backup_path.expanduser()
    manifest_path = backup_path / "manifest.json"
    issues: list[str] = []
    checks: list[BackupContentCheck] = []
    if not backup_path.exists():
        return ScBackupVerification(
            backup_path=backup_path,
            manifest_path=manifest_path,
            manifest=None,
            checks=(),
            issues=(f"backup path does not exist: {backup_path}",),
        )
    if not backup_path.is_dir():
        return ScBackupVerification(
            backup_path=backup_path,
            manifest_path=manifest_path,
            manifest=None,
            checks=(),
            issues=(f"backup path is not a directory snapshot: {backup_path}",),
        )

    manifest, manifest_issues = _read_manifest(backup_path)
    issues.extend(manifest_issues)
    if manifest is None:
        return ScBackupVerification(
            backup_path=backup_path,
            manifest_path=manifest_path,
            manifest=None,
            checks=(),
            issues=tuple(issues),
        )

    paths = manifest.get("paths", [])
    if isinstance(paths, list):
        for raw_path in paths:
            if not isinstance(raw_path, dict):
                issues.append("manifest path entries must be objects")
                continue
            label = str(raw_path.get("label", "(unknown)"))
            destination = Path(str(raw_path.get("destination", "")))
            if not str(destination):
                issues.append(f"{label}: missing destination")
                continue
            source = backup_path / destination
            actual_file_count, actual_byte_count, _latest_mtime = _path_stats(source)
            expected_file_count = int(raw_path.get("file_count", 0))
            expected_byte_count = int(raw_path.get("byte_count", 0))
            check = BackupContentCheck(
                label=label,
                source=source,
                destination=destination,
                exists=source.exists(),
                expected_file_count=expected_file_count,
                actual_file_count=actual_file_count,
                expected_byte_count=expected_byte_count,
                actual_byte_count=actual_byte_count,
            )
            checks.append(check)
            if not check.exists:
                issues.append(f"{label}: missing backup content at {source}")
            if actual_file_count != expected_file_count:
                issues.append(f"{label}: expected {expected_file_count} file(s), found {actual_file_count}")
            if actual_byte_count != expected_byte_count:
                issues.append(f"{label}: expected {_format_bytes(expected_byte_count)}, found {_format_bytes(actual_byte_count)}")

    return ScBackupVerification(
        backup_path=backup_path,
        manifest_path=manifest_path,
        manifest=manifest,
        checks=tuple(checks),
        issues=tuple(issues),
    )


def build_restore_preview(backup_path: Path, restore_to: Path) -> ScRestorePreview:
    """Preview restoring a backup into a chosen inspection directory."""

    backup_path = backup_path.expanduser()
    restore_to = restore_to.expanduser()
    verification = verify_backup_snapshot(backup_path)
    targets = tuple(
        RestoreTargetPreview(
            label=check.label,
            source=check.source,
            target=restore_to / check.destination,
            source_exists=check.exists,
            target_exists=(restore_to / check.destination).exists(),
            file_count=check.actual_file_count,
            byte_count=check.actual_byte_count,
        )
        for check in verification.checks
    )
    return ScRestorePreview(backup_path=backup_path, restore_to=restore_to, verification=verification, targets=targets)


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


def format_backup_verification(verification: ScBackupVerification) -> str:
    """Format read-only backup verification output."""

    lines = [
        "SC backup verify",
        "- writes: no",
        f"- backup path: {verification.backup_path}",
        f"- manifest: {verification.manifest_path}",
        f"- ok: {'yes' if verification.ok else 'no'}",
        f"- checked paths: {len(verification.checks)}",
        "",
        "Contents",
    ]
    if verification.checks:
        for check in verification.checks:
            lines.append(
                f"- {check.label}: {check.source} "
                f"({check.actual_file_count}/{check.expected_file_count} file(s), "
                f"{_format_bytes(check.actual_byte_count)}/{_format_bytes(check.expected_byte_count)})"
            )
    else:
        lines.append("- (none)")
    if verification.issues:
        lines.extend(["", "Issues"])
        lines.extend(f"- {issue}" for issue in verification.issues)
    return "\n".join(lines)


def verification_to_json(verification: ScBackupVerification) -> str:
    """Return a stable JSON representation of backup verification."""

    return json.dumps(
        {
            "writes": "none",
            "backup_path": str(verification.backup_path),
            "manifest_path": str(verification.manifest_path),
            "ok": verification.ok,
            "issues": list(verification.issues),
            "checks": [
                {
                    "label": check.label,
                    "source": str(check.source),
                    "destination": str(check.destination),
                    "exists": check.exists,
                    "expected_file_count": check.expected_file_count,
                    "actual_file_count": check.actual_file_count,
                    "expected_byte_count": check.expected_byte_count,
                    "actual_byte_count": check.actual_byte_count,
                }
                for check in verification.checks
            ],
        },
        indent=2,
        sort_keys=True,
    )


def format_restore_preview(preview: ScRestorePreview) -> str:
    """Format read-only restore preview output."""

    lines = [
        "SC backup restore preview",
        "- writes: no",
        f"- backup path: {preview.backup_path}",
        f"- restore to: {preview.restore_to}",
        f"- backup ok: {'yes' if preview.verification.ok else 'no'}",
        "",
        "Would copy",
    ]
    if preview.targets:
        for target in preview.targets:
            lines.append(
                f"- {target.label}: {target.source} -> {target.target} "
                f"({target.file_count} file(s), {_format_bytes(target.byte_count)})"
            )
    else:
        lines.append("- (none)")
    if preview.warnings:
        lines.extend(["", "Warnings"])
        lines.extend(f"- {warning}" for warning in preview.warnings)
    return "\n".join(lines)


def restore_preview_to_json(preview: ScRestorePreview) -> str:
    """Return a stable JSON representation of restore preview."""

    return json.dumps(
        {
            "writes": "none",
            "backup_path": str(preview.backup_path),
            "restore_to": str(preview.restore_to),
            "backup_ok": preview.verification.ok,
            "warnings": list(preview.warnings),
            "targets": [
                {
                    "label": target.label,
                    "source": str(target.source),
                    "target": str(target.target),
                    "source_exists": target.source_exists,
                    "target_exists": target.target_exists,
                    "file_count": target.file_count,
                    "byte_count": target.byte_count,
                }
                for target in preview.targets
            ],
        },
        indent=2,
        sort_keys=True,
    )


def _latest_or_requested_backup(parser: argparse.ArgumentParser, backup: Path | None, backup_root: Path) -> Path:
    if backup is not None:
        return backup
    status = build_backup_status(backup_root)
    if status.latest_snapshot is None:
        parser.error(f"no backup path supplied and no snapshots found under {backup_root}")
    return status.latest_snapshot


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Preview, create, or inspect SC operational backups.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="Preview backup scope without writing. This is the default.")
    mode.add_argument("--create", action="store_true", help="Create a plain timestamped directory snapshot.")
    mode.add_argument("--status", action="store_true", help="Show read-only backup status.")
    mode.add_argument("--verify", action="store_true", help="Verify a backup snapshot without writing.")
    mode.add_argument("--restore-preview", action="store_true", help="Preview restore into an inspection directory without writing.")
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
        "--backup",
        type=Path,
        help="Backup snapshot directory to verify or preview restore from. Defaults to latest snapshot.",
    )
    parser.add_argument(
        "--restore-to",
        type=Path,
        help="Inspection directory for restore preview. Required with --restore-preview.",
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

    if args.verify:
        backup_path = _latest_or_requested_backup(parser, args.backup, args.backup_root)
        verification = verify_backup_snapshot(backup_path)
        print(verification_to_json(verification) if args.json else format_backup_verification(verification))
        return

    if args.restore_preview:
        if args.restore_to is None:
            parser.error("--restore-preview requires --restore-to")
        backup_path = _latest_or_requested_backup(parser, args.backup, args.backup_root)
        preview = build_restore_preview(backup_path, args.restore_to)
        print(restore_preview_to_json(preview) if args.json else format_restore_preview(preview))
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

"""Read-only retention pressure report for Uniblab."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

import specialists.rosie.loop as agentic_loop
from specialists.uniblab.backup import _format_bytes, default_backup_root
from specialists.uniblab.vault_backup import DEFAULT_VAULT_BACKUP_ROOT


@dataclass(frozen=True)
class RetentionTarget:
    label: str
    path: Path
    exists: bool
    file_count: int
    byte_count: int
    oldest_mtime: float | None
    newest_mtime: float | None
    recommendation: str

    @property
    def oldest_text(self) -> str:
        if self.oldest_mtime is None:
            return "(none)"
        return datetime.fromtimestamp(self.oldest_mtime).isoformat(timespec="seconds")

    @property
    def newest_text(self) -> str:
        if self.newest_mtime is None:
            return "(none)"
        return datetime.fromtimestamp(self.newest_mtime).isoformat(timespec="seconds")


@dataclass(frozen=True)
class RetentionReport:
    targets: tuple[RetentionTarget, ...]

    @property
    def warnings(self) -> tuple[str, ...]:
        warnings: list[str] = []
        for target in self.targets:
            if target.byte_count >= 50 * 1024 * 1024:
                warnings.append(f"{target.label} is large ({_format_bytes(target.byte_count)})")
            if target.file_count >= 1000:
                warnings.append(f"{target.label} has many files ({target.file_count})")
        return tuple(warnings)


def _path_stats(path: Path) -> tuple[int, int, float | None, float | None]:
    if not path.exists():
        return (0, 0, None, None)
    paths = [path] if path.is_file() else [candidate for candidate in path.rglob("*") if candidate.is_file()]
    if not paths:
        return (0, 0, None, None)
    byte_count = 0
    oldest: float | None = None
    newest: float | None = None
    for candidate in paths:
        stat = candidate.stat()
        byte_count += stat.st_size
        oldest = stat.st_mtime if oldest is None else min(oldest, stat.st_mtime)
        newest = stat.st_mtime if newest is None else max(newest, stat.st_mtime)
    return (len(paths), byte_count, oldest, newest)


def _target(label: str, path: Path, recommendation: str) -> RetentionTarget:
    file_count, byte_count, oldest, newest = _path_stats(path)
    return RetentionTarget(
        label=label,
        path=path,
        exists=path.exists(),
        file_count=file_count,
        byte_count=byte_count,
        oldest_mtime=oldest,
        newest_mtime=newest,
        recommendation=recommendation,
    )


def build_retention_report(
    *,
    sc_root: Path = agentic_loop.SC_ROOT,
    runtime_backup_root: Path | None = None,
    vault_backup_root: Path = DEFAULT_VAULT_BACKUP_ROOT,
) -> RetentionReport:
    runtime_backup_root = runtime_backup_root or default_backup_root()
    output_dir = sc_root / "output"
    return RetentionReport(
        targets=(
            _target("runtime archive", sc_root / "archive", "keep as audit history; prune only by explicit policy"),
            _target("runtime output", output_dir, "review reports/traces before pruning"),
            _target(
                "memory traces",
                output_dir / agentic_loop.MEMORY_TRACE_FILENAME,
                "rotate when large; keep recent traces for debugging",
            ),
            _target("pending input", sc_root / "input", "operator should inspect old pending files"),
            _target("processing queue", sc_root / "processing", "should usually be empty"),
            _target("runtime backups", runtime_backup_root, "keep enough point-in-time snapshots to restore operations"),
            _target("vault backups", vault_backup_root, "separate from Syncthing; create before risky vault work"),
        )
    )


def format_retention_report(report: RetentionReport) -> str:
    lines = ["Retention status", "- writes: no"]
    for target in report.targets:
        lines.append(
            f"- {target.label}: exists={'yes' if target.exists else 'no'} "
            f"files={target.file_count} size={_format_bytes(target.byte_count)}"
        )
        lines.append(f"  path: {target.path}")
        lines.append(f"  oldest: {target.oldest_text} newest: {target.newest_text}")
        lines.append(f"  recommendation: {target.recommendation}")
    if report.warnings:
        lines.append("Warnings")
        lines.extend(f"- {warning}" for warning in report.warnings)
    return "\n".join(lines)


def report_to_json(report: RetentionReport) -> str:
    return json.dumps(
        {
            "writes": "none",
            "warnings": list(report.warnings),
            "targets": [
                {
                    "label": target.label,
                    "path": str(target.path),
                    "exists": target.exists,
                    "file_count": target.file_count,
                    "byte_count": target.byte_count,
                    "oldest": target.oldest_text,
                    "newest": target.newest_text,
                    "recommendation": target.recommendation,
                }
                for target in report.targets
            ],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sc-root", type=Path, default=agentic_loop.SC_ROOT)
    parser.add_argument("--runtime-backup-root", type=Path, default=default_backup_root())
    parser.add_argument("--vault-backup-root", type=Path, default=DEFAULT_VAULT_BACKUP_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_retention_report(
        sc_root=args.sc_root,
        runtime_backup_root=args.runtime_backup_root,
        vault_backup_root=args.vault_backup_root,
    )
    print(report_to_json(report) if args.json else format_retention_report(report))


if __name__ == "__main__":
    main()

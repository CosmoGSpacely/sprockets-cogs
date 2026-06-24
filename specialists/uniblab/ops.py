"""One-command operations floor summary for Uniblab."""

from __future__ import annotations

import argparse
import getpass
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from specialists.uniblab import backup, job_status, retention, vault_backup


MAIN_SERVICE = "sprockets-cogs.service"
TELEGRAM_SERVICE = "sprockets-cogs-telegram.service"
NIGHTLY_SERVICE = "sprockets-cogs-nightly.service"
NIGHTLY_TIMER = "sprockets-cogs-nightly.timer"
ENV_FILE = Path.home() / ".config" / "sprockets-cogs" / "env"


@dataclass(frozen=True)
class LingerStatus:
    checked: bool
    enabled: bool | None
    detail: str


@dataclass(frozen=True)
class OpsSummary:
    services: tuple[job_status.UnitStatus, ...]
    linger: LingerStatus
    env_file: Path
    env_exists: bool
    runtime_backup: backup.ScBackupStatus
    vault_preview: vault_backup.VaultBackupPreview
    retention_report: retention.RetentionReport


def build_linger_status() -> LingerStatus:
    command = ["loginctl", "show-user", getpass.getuser(), "--property=Linger", "--value"]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return LingerStatus(checked=False, enabled=None, detail=str(exc))
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"loginctl exited {completed.returncode}"
        return LingerStatus(checked=False, enabled=None, detail=detail)
    value = completed.stdout.strip().lower()
    if value in {"yes", "true", "1"}:
        return LingerStatus(checked=True, enabled=True, detail="enabled")
    if value in {"no", "false", "0"}:
        return LingerStatus(checked=True, enabled=False, detail="disabled")
    return LingerStatus(checked=True, enabled=None, detail=value or "unknown")


def build_ops_summary(env_file: Path = ENV_FILE) -> OpsSummary:
    return OpsSummary(
        services=(
            job_status.get_user_unit_status(MAIN_SERVICE),
            job_status.get_user_unit_status(TELEGRAM_SERVICE),
            job_status.get_user_unit_status(NIGHTLY_SERVICE),
            job_status.get_user_unit_status(NIGHTLY_TIMER),
        ),
        linger=build_linger_status(),
        env_file=env_file,
        env_exists=env_file.exists(),
        runtime_backup=backup.build_backup_status(),
        vault_preview=vault_backup.build_vault_backup_preview(),
        retention_report=retention.build_retention_report(),
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def format_ops_summary(summary: OpsSummary) -> str:
    lines = ["Operations floor", "- writes: no", "Services"]
    for unit in summary.services:
        if unit.error:
            lines.append(f"- {unit.name}: unavailable ({unit.error})")
            continue
        lines.append(
            f"- {unit.name}: installed={_yes_no(unit.exists)} "
            f"active={unit.active_state}/{unit.sub_state} enabled={unit.unit_file_state}"
        )
    lines.extend(
        [
            "User service posture",
            f"- linger checked: {_yes_no(summary.linger.checked)}",
            f"- linger enabled: {summary.linger.enabled if summary.linger.enabled is not None else 'unknown'}",
            f"- linger detail: {summary.linger.detail}",
            "Secrets/env",
            f"- env file: {summary.env_file}",
            f"- env file exists: {_yes_no(summary.env_exists)}",
            "- env values printed: no",
            "Backup posture",
            f"- runtime backup root: {summary.runtime_backup.backup_root}",
            f"- runtime snapshots: {summary.runtime_backup.snapshot_count}",
            f"- latest runtime snapshot: {summary.runtime_backup.latest_snapshot_text}",
            f"- vault backup root: {summary.vault_preview.backup_root}",
            f"- vault backup root exists: {_yes_no(summary.vault_preview.backup_root.exists())}",
            f"- vault backup preview files: {summary.vault_preview.included_file_count}",
            "Retention pressure",
        ]
    )
    if summary.retention_report.warnings:
        lines.extend(f"- warning: {warning}" for warning in summary.retention_report.warnings)
    else:
        lines.append("- warnings: none")
    lines.append("Next commands")
    lines.append("- scripts/sc vault-backup --preview")
    lines.append("- scripts/sc retention")
    lines.append("- scripts/sc status")
    return "\n".join(lines)


def summary_to_json(summary: OpsSummary) -> str:
    return json.dumps(
        {
            "writes": "none",
            "services": [
                {
                    "name": unit.name,
                    "exists": unit.exists,
                    "active_state": unit.active_state,
                    "sub_state": unit.sub_state,
                    "unit_file_state": unit.unit_file_state,
                    "error": unit.error,
                }
                for unit in summary.services
            ],
            "linger": {
                "checked": summary.linger.checked,
                "enabled": summary.linger.enabled,
                "detail": summary.linger.detail,
            },
            "env_file": str(summary.env_file),
            "env_exists": summary.env_exists,
            "runtime_backup_root": str(summary.runtime_backup.backup_root),
            "runtime_snapshot_count": summary.runtime_backup.snapshot_count,
            "vault_backup_root": str(summary.vault_preview.backup_root),
            "vault_preview_file_count": summary.vault_preview.included_file_count,
            "retention_warnings": list(summary.retention_report.warnings),
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    summary = build_ops_summary()
    print(summary_to_json(summary) if args.json else format_ops_summary(summary))


if __name__ == "__main__":
    main()

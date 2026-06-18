"""Read-only maintenance job status reporting.

Stage 27 starts with observation rather than scheduling. This module reports
whether expected user-level systemd units exist and points the operator toward
the dry-run and log commands for each maintenance job.
"""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class UnitStatus:
    name: str
    exists: bool
    load_state: str = "unknown"
    active_state: str = "unknown"
    sub_state: str = "unknown"
    unit_file_state: str = "unknown"
    result: str = "unknown"
    last_exit_status: str = "unknown"
    error: str | None = None


@dataclass(frozen=True)
class MaintenanceJob:
    name: str
    description: str
    service_unit: str
    timer_unit: str
    service_template: Path
    timer_template: Path
    report_command: tuple[str, ...]
    dry_run_command: tuple[str, ...]
    log_command: tuple[str, ...]


@dataclass(frozen=True)
class MaintenanceJobStatus:
    job: MaintenanceJob
    service: UnitStatus
    timer: UnitStatus


NIGHTLY_JOB = MaintenanceJob(
    name="nightly",
    description="Nightly Cogs carry safety net",
    service_unit="sprockets-cogs-nightly.service",
    timer_unit="sprockets-cogs-nightly.timer",
    service_template=PROJECT_ROOT / "systemd" / "user" / "sprockets-cogs-nightly.service",
    timer_template=PROJECT_ROOT / "systemd" / "user" / "sprockets-cogs-nightly.timer",
    report_command=("scripts/nightly", "--report"),
    dry_run_command=("scripts/nightly", "--dry-run"),
    log_command=("journalctl", "--user", "-u", "sprockets-cogs-nightly.service", "--since", "24 hours ago"),
)

KNOWN_JOBS = {
    NIGHTLY_JOB.name: NIGHTLY_JOB,
}


def parse_systemctl_show(output: str) -> dict[str, str]:
    """Parse simple key=value output from systemctl show."""
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def unit_status_from_show(name: str, values: dict[str, str]) -> UnitStatus:
    load_state = values.get("LoadState", "unknown") or "unknown"
    exists = load_state not in {"not-found", "masked", "unknown"}
    return UnitStatus(
        name=name,
        exists=exists,
        load_state=load_state,
        active_state=values.get("ActiveState", "unknown") or "unknown",
        sub_state=values.get("SubState", "unknown") or "unknown",
        unit_file_state=values.get("UnitFileState", "unknown") or "unknown",
        result=values.get("Result", "unknown") or "unknown",
        last_exit_status=values.get("ExecMainStatus", "unknown") or "unknown",
    )


def unavailable_unit_status(name: str, error: str) -> UnitStatus:
    return UnitStatus(name=name, exists=False, error=error)


def get_user_unit_status(name: str) -> UnitStatus:
    command = [
        "systemctl",
        "--user",
        "show",
        name,
        "--property=LoadState",
        "--property=ActiveState",
        "--property=SubState",
        "--property=UnitFileState",
        "--property=Result",
        "--property=ExecMainStatus",
        "--no-pager",
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        return unavailable_unit_status(name, str(exc))

    output = completed.stdout.strip()
    if not output:
        error = completed.stderr.strip() or f"systemctl exited {completed.returncode}"
        return unavailable_unit_status(name, error)
    return unit_status_from_show(name, parse_systemctl_show(output))


def build_job_status(job: MaintenanceJob) -> MaintenanceJobStatus:
    return MaintenanceJobStatus(
        job=job,
        service=get_user_unit_status(job.service_unit),
        timer=get_user_unit_status(job.timer_unit),
    )


def _format_command(command: tuple[str, ...]) -> str:
    return " ".join(command)


def _format_unit(unit: UnitStatus) -> list[str]:
    if unit.error:
        return [f"- {unit.name}: unavailable ({unit.error})"]

    installed = "yes" if unit.exists else "no"
    return [
        f"- {unit.name}: installed={installed}",
        f"  load={unit.load_state} active={unit.active_state}/{unit.sub_state}",
        f"  enabled={unit.unit_file_state} result={unit.result} exit={unit.last_exit_status}",
    ]


def format_job_status(status: MaintenanceJobStatus) -> str:
    lines = [
        f"{status.job.name}: {status.job.description}",
        "service:",
        *_format_unit(status.service),
        "timer:",
        *_format_unit(status.timer),
        f"service template: {status.job.service_template}",
        f"timer template: {status.job.timer_template}",
        f"report: {_format_command(status.job.report_command)}",
        f"dry run: {_format_command(status.job.dry_run_command)}",
        f"logs: {_format_command(status.job.log_command)}",
    ]
    if status.service.error or status.timer.error:
        lines.append(
            "next: user systemd status is unavailable from this process; inspect with systemctl --user from the host shell."
        )
    elif not status.timer.exists:
        lines.append("next: timer is not installed; keep using the dry-run command before enabling automation.")
    elif status.timer.active_state != "active":
        lines.append("next: timer exists but is not active; inspect status before relying on automation.")
    else:
        lines.append("next: timer is active; inspect logs after the next scheduled run.")
    return "\n".join(lines)


def format_all_statuses(statuses: list[MaintenanceJobStatus]) -> str:
    return "\n\n".join(format_job_status(status) for status in statuses)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Report read-only maintenance job status.")
    parser.add_argument(
        "job",
        nargs="?",
        choices=sorted(KNOWN_JOBS),
        help="Maintenance job to inspect. Defaults to all known jobs.",
    )
    args = parser.parse_args(argv)

    jobs = [KNOWN_JOBS[args.job]] if args.job else list(KNOWN_JOBS.values())
    print(format_all_statuses([build_job_status(job) for job in jobs]))


if __name__ == "__main__":
    main()

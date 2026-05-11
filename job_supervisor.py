"""Preview maintenance job supervision actions.

Stage 27D is deliberately preview-only: it shows where unit files would be
installed and which user-systemd commands would run, without copying files or
enabling timers.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from job_status import KNOWN_JOBS, MaintenanceJob


DEFAULT_USER_UNIT_DIR = Path.home() / ".config" / "systemd" / "user"


@dataclass(frozen=True)
class InstallPreview:
    job: MaintenanceJob
    user_unit_dir: Path
    service_target: Path
    timer_target: Path
    commands: tuple[tuple[str, ...], ...]


def build_install_preview(
    job: MaintenanceJob,
    user_unit_dir: Path = DEFAULT_USER_UNIT_DIR,
) -> InstallPreview:
    """Build a read-only install preview for a maintenance job."""
    return InstallPreview(
        job=job,
        user_unit_dir=user_unit_dir,
        service_target=user_unit_dir / job.service_unit,
        timer_target=user_unit_dir / job.timer_unit,
        commands=(
            ("mkdir", "-p", str(user_unit_dir)),
            ("cp", str(job.service_template), str(user_unit_dir / job.service_unit)),
            ("cp", str(job.timer_template), str(user_unit_dir / job.timer_unit)),
            ("systemctl", "--user", "daemon-reload"),
            ("systemctl", "--user", "enable", "--now", job.timer_unit),
            ("systemctl", "--user", "status", job.timer_unit),
        ),
    )


def _format_command(command: tuple[str, ...]) -> str:
    return " ".join(command)


def format_install_preview(preview: InstallPreview) -> str:
    """Format the exact install plan without performing it."""
    return "\n".join(
        [
            f"{preview.job.name}: install preview",
            "- writes: no",
            f"- user unit dir: {preview.user_unit_dir}",
            f"- service source: {preview.job.service_template}",
            f"- service target: {preview.service_target}",
            f"- timer source: {preview.job.timer_template}",
            f"- timer target: {preview.timer_target}",
            "commands to run later:",
            *[f"- {_format_command(command)}" for command in preview.commands],
            "next: run the report and dry-run before installing or enabling this timer.",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview maintenance job supervision actions.")
    parser.add_argument(
        "--preview-install",
        choices=sorted(KNOWN_JOBS),
        help="Show the install plan for a maintenance job without writing.",
    )
    parser.add_argument(
        "--user-unit-dir",
        default=str(DEFAULT_USER_UNIT_DIR),
        help="Target user systemd unit directory for previews.",
    )
    args = parser.parse_args()

    if not args.preview_install:
        parser.error("--preview-install is required for this preview-only slice")

    job = KNOWN_JOBS[args.preview_install]
    print(format_install_preview(build_install_preview(job, Path(args.user_unit_dir))))


if __name__ == "__main__":
    main()

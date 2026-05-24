"""Read-only system status surface for Sprockets-Cogs.

Stage 32 starts by composing existing status/report helpers. This module avoids
service changes, model inference calls, and vault writes.
"""
from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import agentic_loop
import cogs_planning
import embeddings
import job_status
import production_retrieval
import review
from retrieval_preview import format_status as format_retrieval_status
from specialists import SpecialistDefinition, iter_specialists

SERVICE_UNIT = "sprockets-cogs.service"
SERVICE_ENV_KEYS = (
    "SPROCKETS_COGS_MODEL",
    "SPROCKETS_COGS_MEMORY_RETRIEVAL",
    "SPROCKETS_COGS_MEMORY_CONTEXT",
    "SPROCKETS_COGS_MEMORY_RETRIEVER",
)


@dataclass(frozen=True)
class RuntimeStatus:
    model: str
    sc_root: Path
    input_dir: Path
    processing_dir: Path
    archive_dir: Path
    output_dir: Path
    vault_dir: Path
    embed_model: str
    embed_keep_alive: str
    embed_cache_path: Path


@dataclass(frozen=True)
class SystemStatus:
    runtime: RuntimeStatus
    service: "ServiceStatus"
    specialists: tuple[SpecialistDefinition, ...]
    directories: "DirectoryStatus"
    models: "ModelAvailabilityStatus"
    planning: "PlanningStatus"
    backup_sync: "BackupSyncStatus"
    review_report: dict
    retrieval_status: production_retrieval.ProductionRetrievalStatus
    jobs: tuple[job_status.MaintenanceJobStatus, ...]


@dataclass(frozen=True)
class ServiceStatus:
    unit: job_status.UnitStatus
    main_pid: int | None
    env: dict[str, str]
    env_error: str | None = None


@dataclass(frozen=True)
class DirectoryStatus:
    pending_inputs: int
    ignored_input_files: int
    processing_files: int
    archived_inputs: int
    output_files: int
    memory_trace_exists: bool
    oldest_pending_input: str | None = None
    oldest_ignored_input: str | None = None


@dataclass(frozen=True)
class ModelAvailabilityStatus:
    ollama_available: bool
    configured_model: str
    embedding_model: str
    installed_models: tuple[str, ...]
    error: str | None = None

    @property
    def configured_model_installed(self) -> bool:
        return _model_name_matches(self.configured_model, self.installed_models)

    @property
    def embedding_model_installed(self) -> bool:
        return _model_name_matches(self.embedding_model, self.installed_models)


@dataclass(frozen=True)
class PlanningStatus:
    cogs_dir: Path
    reference_date: str
    daily_count: int
    weekly_count: int
    monthly_count: int
    annual_count: int
    daily_legacy_count: int
    daily_iso_count: int
    daily_invalid_count: int
    current_weekly_name: str
    current_weekly_exists: bool
    current_monthly_name: str
    current_monthly_exists: bool
    current_annual_name: str
    current_annual_exists: bool
    current_5wow_anchor: str

    @property
    def current_planning_ready(self) -> bool:
        return (
            self.current_weekly_exists
            and self.current_monthly_exists
            and self.current_annual_exists
        )


@dataclass(frozen=True)
class BackupSyncStatus:
    vault_dir: Path
    sc_root: Path
    code_repo: Path
    vault_exists: bool
    sc_root_exists: bool
    code_repo_exists: bool
    timeshift_home_note: str
    syncthing_note: str
    github_note: str
    backup_gap: str


def _model_name_matches(model: str, installed_models: tuple[str, ...]) -> bool:
    candidates = {model}
    if ":" not in model:
        candidates.add(f"{model}:latest")
    return any(candidate in installed_models for candidate in candidates)


def build_runtime_status() -> RuntimeStatus:
    return RuntimeStatus(
        model=agentic_loop.MODEL,
        sc_root=agentic_loop.SC_ROOT,
        input_dir=agentic_loop.INPUT_DIR,
        processing_dir=agentic_loop.PROCESSING_DIR,
        archive_dir=agentic_loop.ARCHIVE_DIR,
        output_dir=agentic_loop.OUTPUT_DIR,
        vault_dir=agentic_loop.VAULT_DIR,
        embed_model=embeddings.EMBED_MODEL,
        embed_keep_alive=embeddings.EMBED_KEEP_ALIVE,
        embed_cache_path=embeddings.EMBED_CACHE_PATH,
    )


def parse_ollama_list(output: str) -> tuple[str, ...]:
    models: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("NAME"):
            continue
        name = stripped.split(maxsplit=1)[0]
        if name:
            models.append(name)
    return tuple(models)


def build_model_availability_status(runtime: RuntimeStatus) -> ModelAvailabilityStatus:
    command = ["ollama", "list"]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ModelAvailabilityStatus(
            ollama_available=False,
            configured_model=runtime.model,
            embedding_model=runtime.embed_model,
            installed_models=(),
            error=str(exc),
        )

    if completed.returncode != 0:
        error = completed.stderr.strip() or f"ollama list exited {completed.returncode}"
        return ModelAvailabilityStatus(
            ollama_available=False,
            configured_model=runtime.model,
            embedding_model=runtime.embed_model,
            installed_models=(),
            error=error,
        )

    return ModelAvailabilityStatus(
        ollama_available=True,
        configured_model=runtime.model,
        embedding_model=runtime.embed_model,
        installed_models=parse_ollama_list(completed.stdout),
    )


def build_planning_status(runtime: RuntimeStatus, reference_date: str | None = None) -> PlanningStatus:
    inventory = cogs_planning.build_inventory(runtime.vault_dir / "Cogs", reference_date)
    return PlanningStatus(
        cogs_dir=inventory.cogs_dir,
        reference_date=inventory.reference_date,
        daily_count=inventory.daily_count,
        weekly_count=inventory.weekly_count,
        monthly_count=inventory.monthly_count,
        annual_count=inventory.annual_count,
        daily_legacy_count=inventory.daily_legacy_count,
        daily_iso_count=inventory.daily_iso_count,
        daily_invalid_count=inventory.daily_invalid_count,
        current_weekly_name=inventory.current_weekly_name,
        current_weekly_exists=inventory.current_weekly_exists,
        current_monthly_name=inventory.current_monthly_name,
        current_monthly_exists=inventory.current_monthly_exists,
        current_annual_name=inventory.current_annual_name,
        current_annual_exists=inventory.current_annual_exists,
        current_5wow_anchor=inventory.current_5wow_anchor,
    )


def build_backup_sync_status(runtime: RuntimeStatus) -> BackupSyncStatus:
    code_repo = Path(__file__).resolve().parent
    return BackupSyncStatus(
        vault_dir=runtime.vault_dir,
        sc_root=runtime.sc_root,
        code_repo=code_repo,
        vault_exists=runtime.vault_dir.exists(),
        sc_root_exists=runtime.sc_root.exists(),
        code_repo_exists=(code_repo / ".git").exists(),
        timeshift_home_note="system snapshots only per project record; /home/cosmo/** is not treated as covered",
        syncthing_note="replication/sync only; not a point-in-time backup",
        github_note="protects committed repository history, not vault or runtime queue data",
        backup_gap="vault and SC runtime need point-in-time backup beyond Syncthing",
    )


def _count_files(path: Path, pattern: str = "*") -> int:
    if not path.exists():
        return 0
    return sum(1 for candidate in path.glob(pattern) if candidate.is_file())


def _oldest_file_name(path: Path, pattern: str = "*") -> str | None:
    if not path.exists():
        return None
    files = [candidate for candidate in path.glob(pattern) if candidate.is_file()]
    if not files:
        return None
    return min(files, key=lambda candidate: candidate.stat().st_mtime).name


def _ignored_input_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return [
        candidate
        for candidate in path.iterdir()
        if candidate.is_file() and candidate.suffix != ".input"
    ]


def _oldest_ignored_input(path: Path) -> str | None:
    files = _ignored_input_files(path)
    if not files:
        return None
    return min(files, key=lambda candidate: candidate.stat().st_mtime).name


def build_directory_status(runtime: RuntimeStatus) -> DirectoryStatus:
    memory_trace_path = runtime.output_dir / agentic_loop.MEMORY_TRACE_FILENAME
    return DirectoryStatus(
        pending_inputs=_count_files(runtime.input_dir, "*.input"),
        ignored_input_files=len(_ignored_input_files(runtime.input_dir)),
        processing_files=_count_files(runtime.processing_dir),
        archived_inputs=_count_files(runtime.archive_dir, "*.input"),
        output_files=_count_files(runtime.output_dir),
        memory_trace_exists=memory_trace_path.exists(),
        oldest_pending_input=_oldest_file_name(runtime.input_dir, "*.input"),
        oldest_ignored_input=_oldest_ignored_input(runtime.input_dir),
    )


def _service_unit_status_from_show(name: str, values: dict[str, str]) -> ServiceStatus:
    unit = job_status.unit_status_from_show(name, values)
    raw_pid = values.get("MainPID", "")
    try:
        main_pid = int(raw_pid)
    except ValueError:
        main_pid = None
    if main_pid == 0:
        main_pid = None
    return ServiceStatus(
        unit=unit,
        main_pid=main_pid,
        env={},
    )


def read_process_env(
    pid: int,
    keys: tuple[str, ...] = SERVICE_ENV_KEYS,
    proc_root: Path = Path("/proc"),
) -> tuple[dict[str, str], str | None]:
    path = proc_root / str(pid) / "environ"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {}, str(exc)

    wanted = set(keys)
    values: dict[str, str] = {}
    for chunk in raw.split(b"\0"):
        if not chunk or b"=" not in chunk:
            continue
        key_bytes, value_bytes = chunk.split(b"=", 1)
        key = key_bytes.decode(errors="replace")
        if key in wanted:
            values[key] = value_bytes.decode(errors="replace")
    return values, None


def build_service_status(name: str = SERVICE_UNIT) -> ServiceStatus:
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
        "--property=MainPID",
        "--no-pager",
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        return ServiceStatus(
            unit=job_status.unavailable_unit_status(name, str(exc)),
            main_pid=None,
            env={},
            env_error=str(exc),
        )

    output = completed.stdout.strip()
    if not output:
        error = completed.stderr.strip() or f"systemctl exited {completed.returncode}"
        return ServiceStatus(
            unit=job_status.unavailable_unit_status(name, error),
            main_pid=None,
            env={},
            env_error=error,
        )

    status = _service_unit_status_from_show(name, job_status.parse_systemctl_show(output))
    if status.main_pid is None:
        return status
    env, env_error = read_process_env(status.main_pid)
    return ServiceStatus(
        unit=status.unit,
        main_pid=status.main_pid,
        env=env,
        env_error=env_error,
    )


def build_system_status() -> SystemStatus:
    runtime = build_runtime_status()
    return SystemStatus(
        runtime=runtime,
        service=build_service_status(),
        specialists=tuple(iter_specialists()),
        directories=build_directory_status(runtime),
        models=build_model_availability_status(runtime),
        planning=build_planning_status(runtime),
        backup_sync=build_backup_sync_status(runtime),
        review_report=review.review_report(agentic_loop.REVIEW_DIR),
        retrieval_status=production_retrieval.production_retrieval_status(agentic_loop.VAULT_DIR),
        jobs=tuple(job_status.build_job_status(job) for job in job_status.KNOWN_JOBS.values()),
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _format_review_report(report: dict) -> list[str]:
    return [
        "Review queue",
        f"- total: {report['total']}",
        f"- parseable: {report['parseable']}",
        f"- unparseable: {report['unparseable']}",
    ]


def _format_runtime_status(status: RuntimeStatus) -> list[str]:
    cache_exists = status.embed_cache_path.exists()
    return [
        "Runtime",
        f"- model: {status.model}",
        f"- sc root: {status.sc_root}",
        f"- input: {status.input_dir}",
        f"- processing: {status.processing_dir}",
        f"- archive: {status.archive_dir}",
        f"- output: {status.output_dir}",
        f"- vault: {status.vault_dir}",
        f"- embedding model: {status.embed_model}",
        f"- embedding keep alive: {status.embed_keep_alive}",
        f"- embedding cache: {status.embed_cache_path}",
        f"- embedding cache exists: {_yes_no(cache_exists)}",
    ]


def _format_directory_status(status: DirectoryStatus) -> list[str]:
    lines = [
        "Runtime queues",
        f"- pending .input files: {status.pending_inputs}",
        f"- ignored non-.input files: {status.ignored_input_files}",
        f"- processing files: {status.processing_files}",
        f"- archived .input files: {status.archived_inputs}",
        f"- output files: {status.output_files}",
        f"- memory trace file exists: {_yes_no(status.memory_trace_exists)}",
    ]
    if status.oldest_pending_input:
        lines.append(f"- oldest pending input: {status.oldest_pending_input}")
    if status.oldest_ignored_input:
        lines.append(f"- oldest ignored input: {status.oldest_ignored_input}")
        lines.append("- intake note: Rosie only processes files ending in .input")
    return lines


def _format_model_status(status: ModelAvailabilityStatus) -> list[str]:
    lines = [
        "Models",
        f"- ollama available: {_yes_no(status.ollama_available)}",
        f"- configured model: {status.configured_model}",
        f"- configured model installed: {_yes_no(status.configured_model_installed)}",
        f"- embedding model: {status.embedding_model}",
        f"- embedding model installed: {_yes_no(status.embedding_model_installed)}",
        f"- installed model count: {len(status.installed_models)}",
    ]
    if status.error:
        lines.append(f"- ollama error: {status.error}")
    return lines


def _format_planning_status(status: PlanningStatus) -> list[str]:
    return [
        "Planning notes",
        f"- cogs dir: {status.cogs_dir}",
        f"- reference date: {status.reference_date}",
        f"- daily notes: {status.daily_count} total ({status.daily_legacy_count} legacy, {status.daily_iso_count} ISO-first, {status.daily_invalid_count} invalid)",
        f"- weekly notes: {status.weekly_count}",
        f"- monthly notes: {status.monthly_count}",
        f"- annual notes: {status.annual_count}",
        f"- current weekly {status.current_weekly_name}: {'exists' if status.current_weekly_exists else 'missing'}",
        f"- current monthly {status.current_monthly_name}: {'exists' if status.current_monthly_exists else 'missing'}",
        f"- current annual {status.current_annual_name}: {'exists' if status.current_annual_exists else 'missing'}",
        f"- current planning ready: {_yes_no(status.current_planning_ready)}",
        f"- 5WOW monthly anchor: {status.current_5wow_anchor}",
    ]


def _format_backup_sync_status(status: BackupSyncStatus) -> list[str]:
    return [
        "Backup and sync posture",
        f"- vault exists: {_yes_no(status.vault_exists)} ({status.vault_dir})",
        f"- sc root exists: {_yes_no(status.sc_root_exists)} ({status.sc_root})",
        f"- code repo exists: {_yes_no(status.code_repo_exists)} ({status.code_repo})",
        f"- Timeshift: {status.timeshift_home_note}",
        f"- Syncthing: {status.syncthing_note}",
        f"- GitHub: {status.github_note}",
        f"- gap: {status.backup_gap}",
    ]


def _format_service_status(status: ServiceStatus) -> list[str]:
    lines = ["Service"]
    lines.extend(job_status._format_unit(status.unit))
    lines.append(f"- main pid: {status.main_pid if status.main_pid is not None else 'unknown'}")
    if status.env_error:
        lines.append(f"- service env: unavailable ({status.env_error})")
    elif status.env:
        lines.append("- service env:")
        for key in SERVICE_ENV_KEYS:
            lines.append(f"  {key}: {status.env.get(key, '(unset)')}")
    else:
        lines.append("- service env: unavailable")
    return lines


def _format_specialist_status(specialists: tuple[SpecialistDefinition, ...]) -> list[str]:
    lines = ["Specialists"]
    for specialist in specialists:
        flags: list[str] = []
        if specialist.always_on:
            flags.append("always-on")
        if specialist.live_dispatch:
            flags.append("live-dispatch")
        flag_text = f" ({', '.join(flags)})" if flags else ""
        lines.append(
            f"- {specialist.display_name}: {specialist.role}; {specialist.runtime_form}{flag_text}"
        )
    if not any(specialist.live_dispatch for specialist in specialists):
        lines.append("- message bus: contract/rehearsal only, not live dispatch")
    return lines


def format_system_status(status: SystemStatus) -> str:
    sections = [
        "\n".join(["Sprockets-Cogs status", ""]),
        "\n".join(_format_runtime_status(status.runtime)),
        "\n".join(_format_service_status(status.service)),
        "\n".join(_format_specialist_status(status.specialists)),
        "\n".join(_format_directory_status(status.directories)),
        "\n".join(_format_model_status(status.models)),
        "\n".join(_format_planning_status(status.planning)),
        "\n".join(_format_backup_sync_status(status.backup_sync)),
        "\n".join(_format_review_report(status.review_report)),
        format_retrieval_status(status.retrieval_status),
        job_status.format_all_statuses(list(status.jobs)),
    ]
    return "\n\n".join(section for section in sections if section)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Report read-only Sprockets-Cogs system status.")
    parser.add_argument(
        "--show-env",
        action="store_true",
        help="Also print selected environment variable values.",
    )
    args = parser.parse_args(argv)

    print(format_system_status(build_system_status()))
    if args.show_env:
        print("\nEnvironment")
        for name in [
            "SPROCKETS_COGS_MODEL",
            "SPROCKETS_COGS_MEMORY_RETRIEVAL",
            "SPROCKETS_COGS_MEMORY_CONTEXT",
            "SPROCKETS_COGS_MEMORY_RETRIEVER",
            "SPROCKETS_COGS_EMBED_MODEL",
            "SPROCKETS_COGS_EMBED_KEEP_ALIVE",
            "SPROCKETS_COGS_EMBED_CACHE_PATH",
        ]:
            print(f"- {name}: {os.environ.get(name, '(unset)')}")


if __name__ == "__main__":
    main()

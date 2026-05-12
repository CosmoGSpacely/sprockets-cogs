"""Read-only system status surface for Sprockets-Cogs.

Stage 32 starts by composing existing status/report helpers. This module avoids
service changes, model calls, and vault writes.
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

import agentic_loop
import embeddings
import job_status
import production_retrieval
import review
from retrieval_preview import format_status as format_retrieval_status


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
    review_report: dict
    retrieval_status: production_retrieval.ProductionRetrievalStatus
    jobs: tuple[job_status.MaintenanceJobStatus, ...]


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


def build_system_status() -> SystemStatus:
    return SystemStatus(
        runtime=build_runtime_status(),
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


def format_system_status(status: SystemStatus) -> str:
    sections = [
        "\n".join(["Sprockets-Cogs status", ""]),
        "\n".join(_format_runtime_status(status.runtime)),
        "\n".join(_format_review_report(status.review_report)),
        format_retrieval_status(status.retrieval_status),
        job_status.format_all_statuses(list(status.jobs)),
    ]
    return "\n\n".join(section for section in sections if section)


def main() -> None:
    parser = argparse.ArgumentParser(description="Report read-only Sprockets-Cogs system status.")
    parser.add_argument(
        "--show-env",
        action="store_true",
        help="Also print selected environment variable values.",
    )
    args = parser.parse_args()

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

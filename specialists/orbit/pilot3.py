"""Pilot 3 source-loop helpers for Orbit and Telegram."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Sequence

import frontmatter

from specialists.adapters.source_surfaces import AdapterStatus, build_adapter_status, format_adapter_status
from specialists.adapters.telegram_polling import TelegramPollResult, format_poll_result, poll_telegram_once
from specialists.adapters.telegram_adapter import (
    DEFAULT_TELEGRAM_ENV_FILE,
    TELEGRAM_ALLOWED_CHATS_ENV,
    TELEGRAM_ALLOWED_USERS_ENV,
    TELEGRAM_TOKEN_ENV,
    merged_env_with_file,
    parse_id_list,
)


@dataclass(frozen=True)
class Pilot3Readiness:
    input_dir: Path
    archive_dir: Path
    review_dir: Path
    token_configured: bool
    allowed_users: int
    allowed_chats: int
    adapter_status: AdapterStatus
    review_items: int
    latest_telegram_archive: str


@dataclass(frozen=True)
class Pilot3TelegramRun:
    poll: TelegramPollResult
    archived: tuple[Path, ...]
    still_pending: tuple[Path, ...]
    timed_out: bool
    offset_path: Path | None = None
    saved_offset: int | None = None


DEFAULT_OFFSET_PATH = Path("/home/cosmo/sc/output/telegram-offset.json")


def load_telegram_offset(path: Path) -> int | None:
    """Return the persisted Telegram update offset, if present and valid."""

    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("offset")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def save_telegram_offset(path: Path, offset: int) -> None:
    """Persist the next Telegram update offset without exposing tokens."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(
        json.dumps({"offset": offset}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def _latest_telegram_archive(archive_dir: Path) -> str:
    if not archive_dir.exists():
        return ""
    candidates: list[Path] = []
    for path in archive_dir.glob("*.input"):
        try:
            post = frontmatter.load(path)
        except Exception:
            continue
        if post.get("source") == "telegram" or path.name.startswith("telegram-"):
            candidates.append(path)
    if not candidates:
        return ""
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    return latest.name


def build_readiness(
    *,
    input_dir: Path,
    archive_dir: Path,
    review_dir: Path,
    rejected_dir: Path | None = None,
    env_file: Path = DEFAULT_TELEGRAM_ENV_FILE,
) -> Pilot3Readiness:
    env = merged_env_with_file(env_file=env_file)
    users = parse_id_list(env.get(TELEGRAM_ALLOWED_USERS_ENV, ""))
    chats = parse_id_list(env.get(TELEGRAM_ALLOWED_CHATS_ENV, ""))
    review_items = len(tuple(review_dir.glob("*.md"))) if review_dir.exists() else 0
    return Pilot3Readiness(
        input_dir=input_dir,
        archive_dir=archive_dir,
        review_dir=review_dir,
        token_configured=bool(env.get(TELEGRAM_TOKEN_ENV, "").strip()),
        allowed_users=len(users),
        allowed_chats=len(chats),
        adapter_status=build_adapter_status(input_dir, rejected_dir),
        review_items=review_items,
        latest_telegram_archive=_latest_telegram_archive(archive_dir),
    )


def format_readiness(readiness: Pilot3Readiness) -> str:
    lines = [
        "Pilot 3 readiness",
        "- writes: no",
        "- primary input surface: Telegram through Orbit",
        f"- telegram token configured: {'yes' if readiness.token_configured else 'no'}",
        f"- allowed user ids configured: {readiness.allowed_users}",
        f"- allowed chat ids configured: {readiness.allowed_chats}",
        f"- review items: {readiness.review_items}",
        f"- latest telegram archive: {readiness.latest_telegram_archive or 'none'}",
        "",
        format_adapter_status(readiness.adapter_status),
    ]
    return "\n".join(lines)


def wait_for_telegram_processing(
    written_paths: Sequence[Path],
    *,
    archive_dir: Path,
    seconds: float,
    poll_interval: float = 0.5,
) -> tuple[tuple[Path, ...], tuple[Path, ...], bool]:
    if seconds <= 0 or not written_paths:
        return (), tuple(path for path in written_paths if path.exists()), False

    deadline = time.monotonic() + seconds
    archived: set[Path] = set()
    pending: set[Path] = set(written_paths)
    while time.monotonic() <= deadline:
        for path in written_paths:
            archive_path = archive_dir / path.name
            if archive_path.exists():
                archived.add(archive_path)
                pending.discard(path)
            elif not path.exists():
                pending.discard(path)
            else:
                pending.add(path)
        if not pending:
            return tuple(sorted(archived)), (), False
        time.sleep(poll_interval)
    return tuple(sorted(archived)), tuple(sorted(pending)), bool(pending)


def run_telegram_once(
    *,
    input_dir: Path,
    archive_dir: Path,
    processing_dir: Path | None = None,
    env_file: Path = DEFAULT_TELEGRAM_ENV_FILE,
    offset: int | None = None,
    offset_path: Path | None = DEFAULT_OFFSET_PATH,
    limit: int = 10,
    timeout: int = 0,
    wait_seconds: float = 0,
    opener=None,
) -> Pilot3TelegramRun:
    env = merged_env_with_file(env_file=env_file)
    token = env.get(TELEGRAM_TOKEN_ENV, "").strip()
    if not token:
        raise ValueError("telegram token is not configured")
    users = parse_id_list(env.get(TELEGRAM_ALLOWED_USERS_ENV, ""))
    chats = parse_id_list(env.get(TELEGRAM_ALLOWED_CHATS_ENV, ""))
    if not users and not chats:
        raise ValueError("telegram allowlist is not configured")
    kwargs = {}
    if opener is not None:
        kwargs["opener"] = opener
    effective_offset = offset
    if effective_offset is None and offset_path is not None:
        effective_offset = load_telegram_offset(offset_path)
    duplicate_dirs = [input_dir, archive_dir]
    if processing_dir is not None:
        duplicate_dirs.append(processing_dir)
    poll = poll_telegram_once(
        token=token,
        input_dir=input_dir,
        allowed_user_ids=users,
        allowed_chat_ids=chats,
        offset=effective_offset,
        limit=limit,
        timeout=timeout,
        duplicate_dirs=tuple(duplicate_dirs),
        **kwargs,
    )
    saved_offset = None
    if poll.next_offset is not None and offset_path is not None:
        save_telegram_offset(offset_path, poll.next_offset)
        saved_offset = poll.next_offset
    archived, pending, timed_out = wait_for_telegram_processing(
        [write.path for write in poll.written],
        archive_dir=archive_dir,
        seconds=wait_seconds,
    )
    return Pilot3TelegramRun(
        poll=poll,
        archived=archived,
        still_pending=pending,
        timed_out=timed_out,
        offset_path=offset_path,
        saved_offset=saved_offset,
    )


def run_telegram_watch(
    *,
    input_dir: Path,
    archive_dir: Path,
    processing_dir: Path | None = None,
    env_file: Path = DEFAULT_TELEGRAM_ENV_FILE,
    offset_path: Path | None = DEFAULT_OFFSET_PATH,
    limit: int = 10,
    timeout: int = 20,
    wait_seconds: float = 0,
    poll_interval: float = 1.0,
) -> None:
    """Run the foreground Pilot 3 Telegram loop until interrupted."""

    print("Pilot 3 Telegram watch")
    print("- primary input surface: Telegram through Orbit")
    print(f"- offset path: {offset_path if offset_path is not None else 'disabled'}")
    print("- stop: Ctrl-C")
    while True:
        run = run_telegram_once(
            input_dir=input_dir,
            archive_dir=archive_dir,
            processing_dir=processing_dir,
            env_file=env_file,
            offset_path=offset_path,
            limit=limit,
            timeout=timeout,
            wait_seconds=wait_seconds,
        )
        print(format_telegram_run(run), flush=True)
        time.sleep(poll_interval)


def format_telegram_run(run: Pilot3TelegramRun) -> str:
    lines = [
        "Pilot 3 Telegram run",
        "- primary input surface: Telegram through Orbit",
        "",
        format_poll_result(run.poll),
        "",
        f"- archived by Rosie: {len(run.archived)}",
        f"- still pending in input: {len(run.still_pending)}",
        f"- processing timed out: {'yes' if run.timed_out else 'no'}",
        f"- saved offset: {run.saved_offset if run.saved_offset is not None else 'none'}",
    ]
    if run.offset_path is not None:
        lines.append(f"- offset path: {run.offset_path}")
    for path in run.archived:
        lines.append(f"- archived: {path}")
    for path in run.still_pending:
        lines.append(f"- pending: {path}")
    if run.poll.fetched == 0 or run.poll.allowed == 0:
        lines.append("- pilot friction: no allowlisted Telegram text input was available")
    return "\n".join(lines)


def readiness_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Report Pilot 3 Telegram readiness.")
    parser.add_argument("--input-dir", type=Path, default=Path("/home/cosmo/sc/input"))
    parser.add_argument("--archive-dir", type=Path, default=Path("/home/cosmo/sc/archive"))
    parser.add_argument("--review-dir", type=Path, default=Path("/home/cosmo/vault/review"))
    parser.add_argument("--rejected-dir", type=Path, default=Path("/home/cosmo/sc/rejected"))
    parser.add_argument("--env-file", type=Path, default=DEFAULT_TELEGRAM_ENV_FILE)
    args = parser.parse_args(argv)
    print(format_readiness(build_readiness(
        input_dir=args.input_dir,
        archive_dir=args.archive_dir,
        review_dir=args.review_dir,
        rejected_dir=args.rejected_dir,
        env_file=args.env_file,
    )))


def telegram_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run one Pilot 3 Telegram poll and optionally wait for Rosie to archive written inputs.",
    )
    parser.add_argument("--input-dir", type=Path, default=Path("/home/cosmo/sc/input"))
    parser.add_argument("--processing-dir", type=Path, default=Path("/home/cosmo/sc/processing"))
    parser.add_argument("--archive-dir", type=Path, default=Path("/home/cosmo/sc/archive"))
    parser.add_argument("--env-file", type=Path, default=DEFAULT_TELEGRAM_ENV_FILE)
    parser.add_argument("--offset", type=int)
    parser.add_argument("--offset-path", type=Path, default=DEFAULT_OFFSET_PATH)
    parser.add_argument("--no-offset-state", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=0)
    parser.add_argument("--wait-seconds", type=float, default=0)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.timeout < 0:
        parser.error("--timeout cannot be negative")
    if args.wait_seconds < 0:
        parser.error("--wait-seconds cannot be negative")
    if args.poll_interval < 0:
        parser.error("--poll-interval cannot be negative")
    offset_path = None if args.no_offset_state else args.offset_path
    try:
        if args.watch:
            run_telegram_watch(
                input_dir=args.input_dir,
                archive_dir=args.archive_dir,
                processing_dir=args.processing_dir,
                env_file=args.env_file,
                offset_path=offset_path,
                limit=args.limit,
                timeout=args.timeout,
                wait_seconds=args.wait_seconds,
                poll_interval=args.poll_interval,
            )
            return
        run = run_telegram_once(
            input_dir=args.input_dir,
            archive_dir=args.archive_dir,
            processing_dir=args.processing_dir,
            env_file=args.env_file,
            offset=args.offset,
            offset_path=offset_path,
            limit=args.limit,
            timeout=args.timeout,
            wait_seconds=args.wait_seconds,
        )
    except Exception as exc:
        parser.error(str(exc))
    print(format_telegram_run(run))


if __name__ == "__main__":
    readiness_main()

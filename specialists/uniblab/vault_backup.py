"""Read-only vault backup preview for Uniblab."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

import specialists.rosie.loop as agentic_loop
from specialists.uniblab.backup import _format_bytes


DEFAULT_VAULT_BACKUP_ROOT = Path.home() / "sprockets-cogs" / "vault-backups"
EXCLUDED_NAMES = {
    ".git",
    ".obsidian",
    ".stfolder",
    ".trash",
    ".DS_Store",
    "node_modules",
}


@dataclass(frozen=True)
class VaultBackupItem:
    label: str
    path: Path
    included: bool
    exists: bool
    file_count: int
    byte_count: int
    note: str


@dataclass(frozen=True)
class VaultBackupPreview:
    vault_dir: Path
    backup_root: Path
    candidate_snapshot: Path
    items: tuple[VaultBackupItem, ...]

    @property
    def included_items(self) -> tuple[VaultBackupItem, ...]:
        return tuple(item for item in self.items if item.included)

    @property
    def excluded_items(self) -> tuple[VaultBackupItem, ...]:
        return tuple(item for item in self.items if not item.included)

    @property
    def included_file_count(self) -> int:
        return sum(item.file_count for item in self.included_items)

    @property
    def included_byte_count(self) -> int:
        return sum(item.byte_count for item in self.included_items)


def _path_stats(path: Path) -> tuple[int, int]:
    if not path.exists():
        return (0, 0)
    if path.is_file():
        return (1, path.stat().st_size)
    file_count = 0
    byte_count = 0
    for candidate in path.rglob("*"):
        if candidate.is_file():
            file_count += 1
            byte_count += candidate.stat().st_size
    return (file_count, byte_count)


def _snapshot_name(created_at: datetime | None = None) -> str:
    created_at = created_at or datetime.now()
    return f"vault-{created_at.strftime('%Y%m%d-%H%M%S')}"


def build_vault_backup_preview(
    vault_dir: Path = agentic_loop.VAULT_DIR,
    *,
    backup_root: Path = DEFAULT_VAULT_BACKUP_ROOT,
    created_at: datetime | None = None,
) -> VaultBackupPreview:
    vault_dir = vault_dir.expanduser()
    backup_root = backup_root.expanduser()
    candidate_snapshot = backup_root / _snapshot_name(created_at)
    items: list[VaultBackupItem] = []

    if not vault_dir.exists():
        return VaultBackupPreview(vault_dir, backup_root, candidate_snapshot, ())

    for path in sorted(vault_dir.iterdir(), key=lambda item: item.name.lower()):
        included = path.name not in EXCLUDED_NAMES
        file_count, byte_count = _path_stats(path)
        note = "vault content" if included else "excluded volatile/config/build path"
        items.append(
            VaultBackupItem(
                label=path.name,
                path=path,
                included=included,
                exists=path.exists(),
                file_count=file_count,
                byte_count=byte_count,
                note=note,
            )
        )

    return VaultBackupPreview(vault_dir, backup_root, candidate_snapshot, tuple(items))


def format_vault_backup_preview(preview: VaultBackupPreview) -> str:
    lines = [
        "Vault backup preview",
        "- writes: no",
        f"- vault: {preview.vault_dir}",
        f"- vault exists: {'yes' if preview.vault_dir.exists() else 'no'}",
        f"- backup root: {preview.backup_root}",
        f"- backup root exists: {'yes' if preview.backup_root.exists() else 'no'}",
        f"- candidate snapshot: {preview.candidate_snapshot}",
        "- Syncthing: sync only, not point-in-time backup",
        "- runtime backup: separate; use scripts/sc backup",
        f"- included files: {preview.included_file_count}",
        f"- included size: {_format_bytes(preview.included_byte_count)}",
        "",
        "Included vault paths",
    ]
    for item in preview.included_items:
        lines.append(f"- {item.label}: {item.file_count} file(s), {_format_bytes(item.byte_count)}")
    lines.append("")
    lines.append("Excluded vault paths")
    if not preview.excluded_items:
        lines.append("- (none)")
    for item in preview.excluded_items:
        lines.append(f"- {item.label}: {item.note}")
    return "\n".join(lines)


def preview_to_json(preview: VaultBackupPreview) -> str:
    return json.dumps(
        {
            "writes": "none",
            "vault_dir": str(preview.vault_dir),
            "vault_exists": preview.vault_dir.exists(),
            "backup_root": str(preview.backup_root),
            "backup_root_exists": preview.backup_root.exists(),
            "candidate_snapshot": str(preview.candidate_snapshot),
            "included_file_count": preview.included_file_count,
            "included_byte_count": preview.included_byte_count,
            "items": [
                {
                    "label": item.label,
                    "path": str(item.path),
                    "included": item.included,
                    "exists": item.exists,
                    "file_count": item.file_count,
                    "byte_count": item.byte_count,
                    "note": item.note,
                }
                for item in preview.items
            ],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help="Preview vault backup scope. This is the default behavior.")
    parser.add_argument("--vault-dir", type=Path, default=agentic_loop.VAULT_DIR)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_VAULT_BACKUP_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    preview = build_vault_backup_preview(args.vault_dir, backup_root=args.backup_root)
    print(preview_to_json(preview) if args.json else format_vault_backup_preview(preview))


if __name__ == "__main__":
    main()

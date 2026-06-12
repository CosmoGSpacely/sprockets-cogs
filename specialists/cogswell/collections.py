"""Deterministic Cogswell collection database and graph bridge."""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

from slug_utils import slugify


DEFAULT_DB_ENV = "SPROCKETS_COGS_COLLECTIONS_DB"
DEFAULT_VAULT_ENV = "SPROCKETS_COGS_VAULT_DIR"
VALID_STATUSES = {"missing", "have", "want_upgrade", "duplicate"}


TYPE_FIELDS: dict[str, tuple[str, ...]] = {
    "stamps": ("country", "year", "denomination", "series"),
    "coins": ("country", "year", "denomination", "mint"),
    "lbb": ("author", "year"),
}


COMMON_FIELDS = (
    "collection",
    "catalog_no",
    "title",
    "status",
    "condition",
    "location",
    "notes",
    "updated",
)


@dataclass(frozen=True)
class CollectionItem:
    id: int
    collection: str
    catalog_no: str
    title: str
    status: str
    condition: str | None = None
    location: str | None = None
    notes: str | None = None
    updated: str | None = None
    rendered_path: str | None = None
    extra: dict[str, Any] | None = None

    def slug(self) -> str:
        return slugify(f"{self.catalog_no} {self.title}", max_length=80)


def default_db_path() -> Path:
    configured = os.environ.get(DEFAULT_DB_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "sprockets-cogs" / "cogswell.sqlite3"


def default_vault_dir() -> Path:
    configured = os.environ.get(DEFAULT_VAULT_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "vault"


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def extension_table(collection: str) -> str:
    if collection not in TYPE_FIELDS:
        raise ValueError(f"unsupported collection type: {collection}")
    return f"collection_items_{collection}"


def init_db(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS collection_items (
                id INTEGER PRIMARY KEY,
                collection TEXT NOT NULL,
                catalog_no TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'missing',
                condition TEXT,
                location TEXT,
                notes TEXT,
                updated TEXT,
                rendered_path TEXT,
                UNIQUE(collection, catalog_no)
            )
            """
        )
        for collection, fields in TYPE_FIELDS.items():
            columns = ", ".join(f"{field} TEXT" for field in fields)
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {extension_table(collection)} (
                    item_id INTEGER PRIMARY KEY REFERENCES collection_items(id),
                    {columns}
                )
                """
            )


def _normalized_row(row: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized[key.strip().lower().replace(" ", "_")] = (value or "").strip()
    return normalized


def _require(row: dict[str, str], field: str) -> str:
    value = row.get(field, "").strip()
    if not value:
        raise ValueError(f"missing required CSV field: {field}")
    return value


def _valid_status(value: str) -> str:
    status = value or "missing"
    if status not in VALID_STATUSES:
        raise ValueError(f"unsupported collection status: {status}")
    return status


def import_csv(db_path: Path, csv_path: Path, *, collection: str | None = None) -> int:
    init_db(db_path)
    imported = 0
    with csv_path.open(newline="", encoding="utf-8") as handle, _connect(db_path) as conn:
        reader = csv.DictReader(handle)
        for raw in reader:
            row = _normalized_row(raw)
            row_collection = collection or _require(row, "collection")
            if row_collection not in TYPE_FIELDS:
                raise ValueError(f"unsupported collection type: {row_collection}")
            catalog_no = _require(row, "catalog_no")
            title = _require(row, "title")
            status = _valid_status(row.get("status", "missing"))
            updated = row.get("updated") or date.today().isoformat()

            cursor = conn.execute(
                """
                INSERT INTO collection_items (
                    collection, catalog_no, title, status, condition, location, notes, updated
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(collection, catalog_no) DO UPDATE SET
                    title=excluded.title,
                    status=excluded.status,
                    condition=excluded.condition,
                    location=excluded.location,
                    notes=excluded.notes,
                    updated=excluded.updated
                RETURNING id
                """,
                (
                    row_collection,
                    catalog_no,
                    title,
                    status,
                    row.get("condition") or None,
                    row.get("location") or None,
                    row.get("notes") or None,
                    updated,
                ),
            )
            item_id = int(cursor.fetchone()["id"])
            fields = TYPE_FIELDS[row_collection]
            values = [row.get(field) or None for field in fields]
            placeholders = ", ".join("?" for _ in fields)
            updates = ", ".join(f"{field}=excluded.{field}" for field in fields)
            conn.execute(
                f"""
                INSERT INTO {extension_table(row_collection)} (item_id, {", ".join(fields)})
                VALUES (?, {placeholders})
                ON CONFLICT(item_id) DO UPDATE SET {updates}
                """,
                (item_id, *values),
            )
            imported += 1
    return imported


def _row_to_item(row: sqlite3.Row) -> CollectionItem:
    extra = {
        key: row[key]
        for key in row.keys()
        if key not in {"id", *COMMON_FIELDS, "rendered_path"} and row[key] not in (None, "")
    }
    return CollectionItem(
        id=int(row["id"]),
        collection=row["collection"],
        catalog_no=row["catalog_no"],
        title=row["title"],
        status=row["status"],
        condition=row["condition"],
        location=row["location"],
        notes=row["notes"],
        updated=row["updated"],
        rendered_path=row["rendered_path"],
        extra=extra,
    )


def query_items(
    db_path: Path,
    *,
    collection: str | None = None,
    status: str | None = None,
    text: str | None = None,
    limit: int | None = None,
) -> tuple[CollectionItem, ...]:
    init_db(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if collection:
        clauses.append("i.collection = ?")
        params.append(collection)
    if status:
        clauses.append("i.status = ?")
        params.append(_valid_status(status))
    if text:
        clauses.append("(i.title LIKE ? OR i.catalog_no LIKE ? OR i.notes LIKE ?)")
        like = f"%{text}%"
        params.extend([like, like, like])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql_limit = "LIMIT ?" if limit else ""
    if limit:
        params.append(limit)

    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT i.*
            FROM collection_items i
            {where}
            ORDER BY i.collection, i.catalog_no
            {sql_limit}
            """,
            params,
        ).fetchall()
    return tuple(_row_to_item(row) for row in rows)


def get_item(
    db_path: Path,
    *,
    item_id: int | None = None,
    collection: str | None = None,
    catalog_no: str | None = None,
) -> CollectionItem:
    if item_id is None and not (collection and catalog_no):
        raise ValueError("provide --id or both --collection and --catalog-no")
    clauses = ["i.id = ?"] if item_id is not None else ["i.collection = ?", "i.catalog_no = ?"]
    params: list[Any] = [item_id] if item_id is not None else [collection, catalog_no]
    with _connect(db_path) as conn:
        row = conn.execute(
            f"SELECT i.* FROM collection_items i WHERE {' AND '.join(clauses)}",
            params,
        ).fetchone()
    if row is None:
        raise ValueError("collection item not found")
    return _row_to_item(row)


def rendered_path(vault_dir: Path, item: CollectionItem) -> Path:
    return vault_dir / "Sprockets" / "collections" / item.collection / f"{item.slug()}.md"


def _frontmatter_value(value: Any) -> str:
    if value is None:
        return '""'
    text = str(value).replace('"', '\\"')
    return f'"{text}"'


def _render_frontmatter(item: CollectionItem) -> str:
    fields: list[tuple[str, Any]] = [
        ("node_type", "sprockets/reference"),
        ("title", item.title),
        ("cogswell_id", item.id),
        ("collection", item.collection),
        ("catalog_no", item.catalog_no),
        ("collection_status", item.status),
        ("condition", item.condition),
        ("location", item.location),
        ("related_sprockets", []),
        ("tags", ["cogswell", f"collection/{item.collection}"]),
    ]
    if item.extra:
        fields.extend((key, value) for key, value in sorted(item.extra.items()))

    lines = ["---"]
    for key, value in fields:
        if isinstance(value, list):
            if value:
                lines.append(f"{key}:")
                lines.extend(f"  - {_frontmatter_value(item_value)}" for item_value in value)
            else:
                lines.append(f"{key}: []")
        else:
            lines.append(f"{key}: {_frontmatter_value(value)}")
    lines.append("---")
    return "\n".join(lines)


def _preserved_body(path: Path, title: str) -> str:
    if not path.exists():
        return f"\n# {title}\n\n"
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return text if text.startswith("\n") else f"\n{text}"
    end = text.find("\n---", 4)
    if end == -1:
        return f"\n# {title}\n\n"
    body_start = text.find("\n", end + 4)
    if body_start == -1:
        return f"\n# {title}\n\n"
    body = text[body_start + 1 :]
    return body if body.startswith("\n") else f"\n{body}"


def _item_with_extra(db_path: Path, item: CollectionItem) -> CollectionItem:
    fields = TYPE_FIELDS[item.collection]
    with _connect(db_path) as conn:
        row = conn.execute(
            f"SELECT {', '.join(fields)} FROM {extension_table(item.collection)} WHERE item_id = ?",
            (item.id,),
        ).fetchone()
    extra = {field: row[field] for field in fields if row and row[field] not in (None, "")}
    return CollectionItem(**{**item.__dict__, "extra": extra})


def sync_markdown(
    db_path: Path,
    vault_dir: Path,
    *,
    collection: str | None = None,
) -> tuple[Path, ...]:
    items = query_items(db_path, collection=collection)
    written: list[Path] = []
    with _connect(db_path) as conn:
        for item in items:
            full_item = _item_with_extra(db_path, item)
            path = rendered_path(vault_dir, full_item)
            path.parent.mkdir(parents=True, exist_ok=True)
            body = _preserved_body(path, full_item.title)
            path.write_text(f"{_render_frontmatter(full_item)}{body}", encoding="utf-8")
            conn.execute(
                "UPDATE collection_items SET rendered_path = ? WHERE id = ?",
                (str(path.relative_to(vault_dir)), full_item.id),
            )
            written.append(path)
    return tuple(written)


def _extract_frontmatter_field(path: Path, field: str) -> tuple[str, ...]:
    if not path.exists():
        return ()
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return ()
    end = text.find("\n---", 4)
    if end == -1:
        return ()
    lines = text[4:end].splitlines()
    values: list[str] = []
    in_field = False
    for line in lines:
        if line.startswith(f"{field}:"):
            in_field = True
            rest = line.split(":", 1)[1].strip()
            if rest and rest != "[]":
                values.append(rest.strip('"'))
            continue
        if in_field and line.startswith("  - "):
            values.append(line[4:].strip().strip('"'))
            continue
        if in_field and line and not line.startswith(" "):
            break
    return tuple(value for value in values if value)


def bridge_report(
    db_path: Path,
    vault_dir: Path,
    *,
    item_id: int | None = None,
    collection: str | None = None,
    catalog_no: str | None = None,
) -> str:
    item = get_item(db_path, item_id=item_id, collection=collection, catalog_no=catalog_no)
    path = vault_dir / item.rendered_path if item.rendered_path else rendered_path(vault_dir, item)
    related = _extract_frontmatter_field(path, "related_sprockets")
    unresolved = tuple(value for value in related if value.startswith("[[") and value.endswith("]]"))
    return "\n".join(
        [
            "Cogswell bridge inspection",
            f"- db: {db_path}",
            f"- id: {item.id}",
            f"- collection: {item.collection}",
            f"- catalog_no: {item.catalog_no}",
            f"- title: {item.title}",
            f"- status: {item.status}",
            f"- rendered_path: {path}",
            f"- rendered_exists: {'yes' if path.exists() else 'no'}",
            f"- related_sprockets: {', '.join(related) if related else 'none'}",
            f"- unresolved_links: {', '.join(unresolved) if unresolved else 'none'}",
            "- writes: no",
        ]
    )


def format_query(items: Iterable[CollectionItem], *, db_path: Path) -> str:
    rows = list(items)
    lines = [
        "Cogswell collection query",
        f"- db: {db_path}",
        f"- rows: {len(rows)}",
    ]
    for index, item in enumerate(rows, start=1):
        details = [item.collection, item.catalog_no, item.status, item.title]
        if item.condition:
            details.append(f"condition={item.condition}")
        if item.location:
            details.append(f"location={item.location}")
        lines.append(f"{index}. {' | '.join(details)}")
    return "\n".join(lines)


def _base_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description, add_help=False)
    parser.add_argument("--db", type=Path, default=default_db_path())
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    root = argparse.ArgumentParser(description="Cogswell collection database bridge.")
    subparsers = root.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", parents=[_base_parser("init")], add_help=False)
    init_parser.add_argument("--help", action="help", help=argparse.SUPPRESS)

    import_parser = subparsers.add_parser("import", parents=[_base_parser("import")], add_help=False)
    import_parser.add_argument("csv_path", type=Path)
    import_parser.add_argument("--type", dest="collection", choices=tuple(TYPE_FIELDS))
    import_parser.add_argument("--help", action="help", help=argparse.SUPPRESS)

    query_parser = subparsers.add_parser("query", parents=[_base_parser("query")], add_help=False)
    query_parser.add_argument("--collection", choices=tuple(TYPE_FIELDS))
    query_parser.add_argument("--status", choices=tuple(sorted(VALID_STATUSES)))
    query_parser.add_argument("--text")
    query_parser.add_argument("--limit", type=int)
    query_parser.add_argument("--help", action="help", help=argparse.SUPPRESS)

    sync_parser = subparsers.add_parser("sync", parents=[_base_parser("sync")], add_help=False)
    sync_parser.add_argument("--vault-dir", type=Path, default=default_vault_dir())
    sync_parser.add_argument("--collection", choices=tuple(TYPE_FIELDS))
    sync_parser.add_argument("--help", action="help", help=argparse.SUPPRESS)

    bridge_parser = subparsers.add_parser("bridge", parents=[_base_parser("bridge")], add_help=False)
    bridge_parser.add_argument("--vault-dir", type=Path, default=default_vault_dir())
    bridge_parser.add_argument("--id", dest="item_id", type=int)
    bridge_parser.add_argument("--collection", choices=tuple(TYPE_FIELDS))
    bridge_parser.add_argument("--catalog-no")
    bridge_parser.add_argument("--help", action="help", help=argparse.SUPPRESS)

    args = root.parse_args(argv)
    if args.command == "init":
        init_db(args.db)
        print(f"Cogswell database initialized: {args.db}")
    elif args.command == "import":
        count = import_csv(args.db, args.csv_path, collection=args.collection)
        print(f"Cogswell CSV import complete: {count} row(s)")
    elif args.command == "query":
        print(
            format_query(
                query_items(
                    args.db,
                    collection=args.collection,
                    status=args.status,
                    text=args.text,
                    limit=args.limit,
                ),
                db_path=args.db,
            )
        )
    elif args.command == "sync":
        paths = sync_markdown(args.db, args.vault_dir, collection=args.collection)
        print(f"Cogswell Markdown sync complete: {len(paths)} file(s)")
        for path in paths:
            print(f"- {path}")
    elif args.command == "bridge":
        print(
            bridge_report(
                args.db,
                args.vault_dir,
                item_id=args.item_id,
                collection=args.collection,
                catalog_no=args.catalog_no,
            )
        )


if __name__ == "__main__":
    main()

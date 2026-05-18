from pathlib import Path


def write_sprockets_node(
    vault: Path,
    folder: str,
    slug: str,
    metadata: str = "",
    body: str | None = None,
) -> Path:
    path = vault / "Sprockets" / folder / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    note_body = f"# {slug}" if body is None else body
    path.write_text(f"---\n{metadata}---\n\n{note_body}\n")
    return path

import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

import frontmatter
import ollama
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from prompts import (
    CLASSIFY_EXAMPLES, CLASSIFY_SCHEMA, CLASSIFY_SYSTEM,
    EXTRACT_EXAMPLES, EXTRACT_SCHEMA, EXTRACT_SYSTEM,
)

# ── Constants ──────────────────────────────────────────────────────────────────
MODEL = "qwen3.5:9b-32k-cosmo"

# ── Paths ─────────────────────────────────────────────────────────────────────
INPUT_DIR      = Path("/home/cosmo/sc/input")
PROCESSING_DIR = Path("/home/cosmo/sc/processing")
ARCHIVE_DIR    = Path("/home/cosmo/sc/archive")
OUTPUT_DIR     = Path("/home/cosmo/sc/output")
VAULT_DIR      = Path("/home/cosmo/vault")

DAILY_DIR      = VAULT_DIR / "Cogs" / "daily"
REVIEW_DIR     = VAULT_DIR / "review"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Abstracted seams (Phase 3 fills these in) ─────────────────────────────────

def build_context() -> str:
    """
    Phase 1: loads today's Cogs daily note.
    Phase 3: queries vector DB for semantically relevant nodes.
    """
    today = datetime.now().strftime("%a %d %b %Y")
    note_path = DAILY_DIR / f"{today}.md"
    if note_path.exists():
        return f"=== Today's Cogs Note ===\n{note_path.read_text()}"
    return "=== Today's Cogs Note ===\n(not yet created)"


def retrieve_relevant_nodes(query: str) -> list:
    """
    Phase 1: returns empty list.
    Phase 3: semantic search over vault embeddings.
    """
    return []


def write_node(node: dict) -> None:
    """
    Phase 1: writes Markdown file to vault.
    Phase 3: also upserts embedding to vector DB.
    """
    log.info("write_node() stub — node: %s", node)


def _create_daily_note(note_path: Path) -> None:
    today_iso = datetime.now().strftime("%Y-%m-%d")
    today_heading = datetime.now().strftime("%a %d %b %Y")
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    note_path.write_text(
        f"---\nnode_type: cogs/daily\ndate: {today_iso}\ntags: [cogs/daily]\n---\n\n# {today_heading}\n\n"
    )
    log.info("Created daily note: %s", note_path.name)


def send_response(session_id: str, text: str) -> None:
    """
    Phase 1: appends reflection line to today's Cogs daily note.
    Later: routes back to originating channel via source adapter.
    """
    today = datetime.now().strftime("%a %d %b %Y")
    note_path = DAILY_DIR / f"{today}.md"
    if not note_path.exists():
        _create_daily_note(note_path)
    timestamp = datetime.now().strftime("%H:%M")
    note_path.open("a").write(f"\n- [ ] [{timestamp}] agent: {text}\n")
    log.info("Reflection appended to %s", note_path.name)


# ── Pipeline steps ─────────────────────────────────────────────────────────────

def extract_nodes(content: str, context: str) -> list[dict]:
    """Qwen3 call 1: extract raw items from input text."""
    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM},
        *EXTRACT_EXAMPLES,
        {"role": "user", "content": f"Extract all items from this text:\n\n{content}"},
    ]
    response = ollama.chat(
        model=MODEL,
        messages=messages,
        format=EXTRACT_SCHEMA,
        options={"temperature": 0.1},
        think=False,
    )
    raw = response.message.content
    log.debug("extract_nodes raw: %s", raw)
    try:
        result = json.loads(raw)
        items = result.get("items", []) if isinstance(result, dict) else result
        log.info("Extracted %d item(s)", len(items))
        return items
    except json.JSONDecodeError as e:
        log.error("extract_nodes JSON parse failed: %s | raw: %s", e, raw)
        return []


def classify_nodes(raw_nodes: list[dict], context: str) -> list[dict]:
    """Qwen3 call 2: assign node_type, fields, and date to each extracted item."""
    if not raw_nodes:
        return []
    today = datetime.now().strftime("%Y-%m-%d (%A)")
    user_msg = (
        f"Today: {today}\n\n"
        f"Extracted:\n{json.dumps(raw_nodes, indent=2)}\n\n"
        f"Classify each item."
    )
    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM},
        *CLASSIFY_EXAMPLES,
        {"role": "user", "content": user_msg},
    ]
    response = ollama.chat(
        model=MODEL,
        messages=messages,
        format=CLASSIFY_SCHEMA,
        options={"temperature": 0.1},
        think=False,
    )
    raw = response.message.content
    log.debug("classify_nodes raw: %s", raw)
    try:
        result = json.loads(raw)
        nodes = result.get("nodes", []) if isinstance(result, dict) else result
        log.info("Classified %d node(s)", len(nodes))
        return nodes
    except json.JSONDecodeError as e:
        log.error("classify_nodes JSON parse failed: %s | raw: %s", e, raw)
        return []


def validate_output(nodes: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Validate against Pydantic models.
    Returns (valid_nodes, invalid_nodes). Stub — Stage 5 implements this.
    """
    log.info("validate_output() stub — all nodes valid")
    return nodes, []


def resolve_parents(nodes: list[dict]) -> list[dict]:
    """
    Phase 1: pass-through stub.
    Phase 2: networkx graph traversal.
    """
    return nodes


def append_reflection(session_id: str, nodes: list[dict]) -> None:
    summary = f"Processed {len(nodes)} node(s) from session {session_id}"
    if nodes:
        types = ", ".join(n.get("node_type", "unknown") for n in nodes)
        summary += f": {types}"
    send_response(session_id, summary)


def archive_input(processing_path: Path) -> None:
    dest = ARCHIVE_DIR / processing_path.name
    shutil.move(str(processing_path), dest)
    log.info("Archived → %s", dest)


# ── Main pipeline ──────────────────────────────────────────────────────────────

def process_input(file_path: Path) -> None:
    log.info("Processing: %s", file_path.name)
    processing_path = PROCESSING_DIR / file_path.name
    shutil.move(str(file_path), processing_path)

    try:
        post = frontmatter.load(str(processing_path))
        content = post.content
        session_id = post.get("session_id", processing_path.stem)

        context = build_context()
        raw_nodes = extract_nodes(content, context)
        classified = classify_nodes(raw_nodes, context)
        valid_nodes, invalid_nodes = validate_output(classified)
        resolved = resolve_parents(valid_nodes)

        for node in resolved:
            write_node(node)

        for node in invalid_nodes:
            log.warning("Invalid node → review/: %s", node)

        append_reflection(session_id, resolved)
        archive_input(processing_path)

    except Exception:
        log.exception("Failed to process %s — left in processing/ for inspection", file_path.name)


# ── Watchdog handler ───────────────────────────────────────────────────────────

class InputHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix == ".input":
            log.info("Detected: %s", path.name)
            time.sleep(0.5)
            process_input(path)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    log.info("Agentic loop starting. Watching: %s", INPUT_DIR)
    observer = Observer()
    observer.schedule(InputHandler(), str(INPUT_DIR), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutting down.")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()

import json
import logging
import re
import shutil
import time
import uuid as uuid_lib
from datetime import datetime, timedelta
from pathlib import Path

import frontmatter
import ollama
from jinja2 import Template
from pydantic import ValidationError
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from models import Confidence, NodeBase, validate_node
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

SPROCKETS_FOLDERS = {
    "sprockets/task":    VAULT_DIR / "Sprockets" / "tasks",
    "sprockets/contact": VAULT_DIR / "Sprockets" / "contacts",
    "sprockets/entity":  VAULT_DIR / "Sprockets" / "entities",
    "sprockets/note":    VAULT_DIR / "Sprockets" / "notes",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Node body template (Jinja2) ────────────────────────────────────────────────
# Body is empty for Phase 1. Stage 8 adds reflection; later stages add richer content.
_NODE_BODY = Template("")


# ── File I/O helpers ───────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """Return a filesystem-safe slug from a title."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60].strip("-")


def _ensure_daily_note(date_iso: str) -> Path:
    """Return the path to a Cogs daily note, creating it if absent."""
    dt      = datetime.strptime(date_iso, "%Y-%m-%d")
    heading = dt.strftime("%a %d %b %Y")
    path    = DAILY_DIR / f"{heading}.md"
    if not path.exists():
        DAILY_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\nnode_type: cogs/daily\ndate: {date_iso}\ntags: [cogs/daily]\n---\n\n"
            f"# {heading}\n\n"
        )
        log.info("Created daily note: %s", path.name)
    return path


def _append_cogs_item(node: NodeBase) -> None:
    """Append a Cogs daily item to the correct daily note."""
    note_path = _ensure_daily_note(node.date)
    existing = note_path.read_text()
    if any(f"{state} {node.item_text}" in existing
           for state in ["- [ ]", "- [x]", "- [>]", "- [-]"]):
        log.info("Cogs item already in %s, skipping: %s", note_path.name, node.item_text)
        return
    with note_path.open("a") as f:
	f.write(f"- [ ] {node.item_text}\n")
    log.info("Appended to %s: %s", note_path.name, node.item_text)


def _write_sprockets_node(node: NodeBase, folder: Path) -> None:
    """
    Write a Sprockets node as a Markdown file with YAML frontmatter.
    Skips silently if the file already exists (deduplication stub — Stage 11 hardens this).
    """
    folder.mkdir(parents=True, exist_ok=True)
    slug = _slugify(node.title)
    path = folder / f"{slug}.md"

    if path.exists():
        log.warning("Node file already exists, skipping: %s", path.name)
        return

    today = datetime.now().strftime("%Y-%m-%d")
    uid   = uuid_lib.uuid4().hex[:6]

    metadata: dict = {
        "node_type": node.node_type,
        "uuid":      uid,
        "title":     node.title,
        "tags":      [node.node_type],
        "created":   today,
        "updated":   today,
    }
    if hasattr(node, "status"):
        metadata["status"] = node.status

    body = _NODE_BODY.render(node=node)
    post = frontmatter.Post(body, **metadata)
    path.write_text(frontmatter.dumps(post))
    log.info("Wrote %s → %s", node.node_type, path.name)


# ── Abstracted seams (Phase 3 fills these in) ─────────────────────────────────


def _week_workdays(ref: datetime) -> str:
    monday = ref - timedelta(days=ref.weekday())
    return "  ".join(
        (monday + timedelta(days=i)).strftime("%a %Y-%m-%d") for i in range(5)
    )
def build_context() -> str:
    """
    Phase 1: loads today's Cogs daily note.
    Phase 3: queries vector DB for semantically relevant nodes.
    """
    today     = datetime.now().strftime("%a %d %b %Y")
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


def write_node(node: NodeBase) -> None:
    """
    Phase 1: appends Cogs items to daily notes; writes Sprockets nodes as vault files.
    Phase 3: also upserts embedding to vector DB.
    """
    if node.node_type == "cogs/daily":
        _append_cogs_item(node)
    elif node.node_type in SPROCKETS_FOLDERS:
        _write_sprockets_node(node, SPROCKETS_FOLDERS[node.node_type])
    else:
        log.warning("write_node: unhandled node_type %s", node.node_type)


def write_to_review(raw: dict, reason: str) -> None:
    """Write a node that failed validation or has low confidence to review/."""
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:18]
    slug = raw.get("node_type", "unknown").replace("/", "-")
    path = REVIEW_DIR / f"{ts}-{slug}.md"
    path.write_text(
        f"---\nnode_type: review\nreviewed: false\ncreated: {datetime.now().strftime('%Y-%m-%d')}\n---\n\n"
        f"**Reason:** {reason}\n\n"
        f"```json\n{json.dumps(raw, indent=2)}\n```\n"
    )
    log.warning("Routed to review/: %s — %s", path.name, reason)


def send_response(session_id: str, text: str) -> None:
    """
    Phase 1: appends reflection line to today's Cogs daily note.
    Later: routes back to originating channel via source adapter.
    """
    note_path = _ensure_daily_note(datetime.now().strftime("%Y-%m-%d"))
    timestamp = datetime.now().strftime("%H:%M")
    with note_path.open("a") as f:
	f.write(f"\n> [{timestamp}] agent: {text}\n")
    log.info("Reflection appended to %s", note_path.name)


# ── Pipeline steps ─────────────────────────────────────────────────────────────

def extract_nodes(content: str, context: str) -> list[dict]:
    """Qwen3 call 1: extract raw items from input text."""
    workdays = _week_workdays(datetime.now())
    extract_msg = (
        f"This week's workdays: {workdays}\n\n"
        f"Extract all items from this text:\n\n{content}"
    )
    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM},
        *EXTRACT_EXAMPLES,
        {"role": "user", "content": extract_msg},
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
        items  = result.get("items", []) if isinstance(result, dict) else result
        log.info("Extracted %d item(s)", len(items))
        return items
    except json.JSONDecodeError as e:
        log.error("extract_nodes JSON parse failed: %s | raw: %s", e, raw)
        return []


def classify_nodes(
    raw_nodes: list[dict],
    context: str,
    error_context: str = "",
    use_examples: bool = True,
) -> list[dict]:
    """Qwen3 call 2: assign node_type, fields, and date to each extracted item."""
    if not raw_nodes:
        return []
    today_dt = datetime.now()
    today    = today_dt.strftime("%Y-%m-%d (%A)")
    workdays = _week_workdays(today_dt)
    user_msg = (
        f"Today: {today}\n"
        f"This week's workdays: {workdays}\n\n"
        f"Extracted:\n{json.dumps(raw_nodes, indent=2)}\n\n"
    )
    if error_context:
        user_msg += f"Fix these issues from the previous attempt:\n{error_context}\n\n"
    user_msg += "Classify each item."

    examples = CLASSIFY_EXAMPLES if use_examples else []
    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM},
        *examples,
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
        nodes  = result.get("nodes", []) if isinstance(result, dict) else result
        log.info("Classified %d node(s)", len(nodes))
        return nodes
    except json.JSONDecodeError as e:
        log.error("classify_nodes JSON parse failed: %s | raw: %s", e, raw)
        return []


def _format_validation_error(node_type: str, exc: Exception) -> str:
    """Convert a Pydantic ValidationError into a clean, model-actionable string."""
    if isinstance(exc, ValidationError):
        missing = [str(err["loc"][0]) for err in exc.errors() if err.get("type") == "missing"]
        if missing:
            return (
                f"{node_type}: missing required field(s): {', '.join(missing)}. "
                f"Add {'them' if len(missing) > 1 else 'it'} from the original text."
            )
        return f"{node_type}: {exc.errors()[0]['msg']}"
    return f"{node_type}: {exc}"


InvalidTriple = tuple[int, dict, str]


def validate_output(nodes: list[dict]) -> tuple[list[NodeBase], list[InvalidTriple]]:
    """
    Validate each node against its Pydantic model.
    Returns (valid_nodes, invalid_triples) where each triple is (index, raw_dict, reason).
    Low-confidence nodes are invalid and route to review/ without retry.
    """
    valid:   list[NodeBase]      = []
    invalid: list[InvalidTriple] = []

    for i, raw in enumerate(nodes):
        try:
            node = validate_node(raw)
            if node.confidence == Confidence.LOW:
                invalid.append((i, raw, "confidence: low"))
            else:
                valid.append(node)
        except (ValueError, ValidationError) as e:
            reason = _format_validation_error(raw.get("node_type", "unknown"), e)
            invalid.append((i, raw, reason))

    log.info("Validation: %d valid, %d invalid", len(valid), len(invalid))
    return valid, invalid


def resolve_parents(nodes: list[NodeBase]) -> list[NodeBase]:
    """
    Phase 1: pass-through stub.
    Phase 2: networkx graph traversal.
    """
    return nodes


def append_reflection(session_id: str, nodes: list[NodeBase]) -> None:
    summary = f"Processed {len(nodes)} node(s) from session {session_id}"
    if nodes:
        summary += f": {', '.join(n.node_type for n in nodes)}"
    send_response(session_id, summary)


def archive_input(processing_path: Path) -> None:
    dest = ARCHIVE_DIR / processing_path.name
    shutil.move(str(processing_path), dest)
    log.info("Archived → %s", dest)



def ensure_cogs_companions(classified: list[dict]) -> list[dict]:
    """Guarantee every sprockets/task has a cogs/daily companion on the same date."""
    _stop = {"a", "the", "for", "to", "of", "and", "in", "by", "at", "on", "re"}

    def _words(s: str) -> set:
        return set(s.lower().split()) - _stop

    result = list(classified)
    cogs_by_date: dict[str, list[str]] = {}
    for n in classified:
        if n.get("node_type") == "cogs/daily":
            d = n.get("date", "")
            cogs_by_date.setdefault(d, []).append(n.get("item_text") or "")

    for node in classified:
        if node.get("node_type") != "sprockets/task":
            continue
        title = node.get("title", "")
        date  = node.get("date", "")
        if not date or not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
            log.warning("ensure_cogs_companions: task %r has invalid date %r, skipping companion", title, date)
            continue
        title_words = _words(title)
        existing = cogs_by_date.get(date, [])
        has_companion = any(
            title_words & _words(item)
            for item in existing
        )
        if not has_companion:
            companion = {
                "node_type":  "cogs/daily",
                "title":      title,
                "item_text":  title,
                "date":       date,
                "confidence": "high",
            }
            result.append(companion)
            cogs_by_date.setdefault(date, []).append(title)
            log.info("Auto-added cogs/daily for task: %s on %s", title, date)
    return result

# ── Main pipeline ──────────────────────────────────────────────────────────────

def process_input(file_path: Path) -> None:
    log.info("Processing: %s", file_path.name)
    processing_path = PROCESSING_DIR / file_path.name
    shutil.move(str(file_path), processing_path)

    try:
        post       = frontmatter.load(str(processing_path))
        content    = post.content
        session_id = post.get("session_id", processing_path.stem)

        context    = build_context()
        raw_nodes  = extract_nodes(content, context)
        classified = classify_nodes(raw_nodes, context)
        classified = ensure_cogs_companions(classified)

        valid_nodes, invalid_triples = validate_output(classified)

        direct_review = [(raw, reason) for _, raw, reason in invalid_triples
                         if "confidence: low" in reason]
        retry_triples = [(idx, raw, reason) for idx, raw, reason in invalid_triples
                         if "confidence: low" not in reason]

        for raw, reason in direct_review:
            write_to_review(raw, reason)

        if retry_triples:
            retry_raw     = [raw for _, raw, _ in retry_triples]
            error_context = "\n".join(f"- {reason}" for _, _, reason in retry_triples)
            log.info("Retrying classify for %d invalid node(s)", len(retry_triples))
            reclassified        = classify_nodes(retry_raw, context, error_context, use_examples=True)[:len(retry_triples)]
            valid_retry, failed = validate_output(reclassified)
            valid_nodes.extend(valid_retry)
            for _, raw, reason in failed:
                write_to_review(raw, f"retry failed: {reason}")

        resolved = resolve_parents(valid_nodes)
        seen: set = set()
        for node in resolved:
            key = (node.node_type, getattr(node, 'date', ''), getattr(node, 'item_text', ''), getattr(node, 'title', ''))
            if key in seen:
                log.warning('Duplicate node skipped: %s', key)
                continue
            seen.add(key)
            write_node(node)

        append_reflection(session_id, resolved)
        archive_input(processing_path)

    except Exception:
        log.exception(
            "Failed to process %s — left in processing/ for inspection",
            file_path.name,
        )


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

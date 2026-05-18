import json
import logging
import os
import re
import shutil
import time
import uuid as uuid_lib
from datetime import datetime
from pathlib import Path

import frontmatter
from rapidfuzz import fuzz
from jinja2 import Template
from pydantic import ValidationError
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import classifier_context
from entity_state import get_entities_by_tier, upsert_entity
from extractor_classifier import ExtractClassifier, ExtractClassifierConfig
import memory_guards
from memory_trace_log import append_memory_parent_trace
from models import Confidence, NodeBase, validate_node
from openai_fallback import (
    classify_nodes_with_openai_fallback,
    openai_fallback_enabled,
)
from slug_utils import slugify
from sprockets_specialist import SprocketsSpecialist, SprocketsSpecialistConfig
from vault_graph import (
    HIERARCHY_PARENT_NODE_TYPES,
    build_graph,
)
from vault import append_cogs_item_text, ensure_daily_note

# ── Constants ──────────────────────────────────────────────────────────────────
DEFAULT_MODEL = "qwen3.5:9b-32k-cosmo"
MODEL = os.environ.get("SPROCKETS_COGS_MODEL", DEFAULT_MODEL)

# ── Paths ─────────────────────────────────────────────────────────────────────
DEFAULT_SC_ROOT = Path.home() / "sc"
DEFAULT_VAULT_DIR = Path.home() / "vault"

SC_ROOT        = Path(os.environ.get("SPROCKETS_COGS_SC_ROOT", str(DEFAULT_SC_ROOT)))
INPUT_DIR      = Path(os.environ.get("SPROCKETS_COGS_INPUT_DIR", str(SC_ROOT / "input")))
PROCESSING_DIR = Path(os.environ.get("SPROCKETS_COGS_PROCESSING_DIR", str(SC_ROOT / "processing")))
ARCHIVE_DIR    = Path(os.environ.get("SPROCKETS_COGS_ARCHIVE_DIR", str(SC_ROOT / "archive")))
OUTPUT_DIR     = Path(os.environ.get("SPROCKETS_COGS_OUTPUT_DIR", str(SC_ROOT / "output")))
VAULT_DIR      = Path(os.environ.get("SPROCKETS_COGS_VAULT_DIR", str(DEFAULT_VAULT_DIR)))
MEMORY_TRACE_PATH_ENV = "SPROCKETS_COGS_MEMORY_TRACE_PATH"
MEMORY_TRACE_FILENAME = "memory-parent-traces.jsonl"

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

def _find_duplicate(title: str, folder: Path, threshold: int = 85) -> Path | None:
    """
    Return the path of an existing node whose slug fuzzy-matches title, or None.
    Compares slugified titles against existing file stems — no file reads needed.
    Threshold 85 catches typos and minor variations without false-positiving on
    legitimately different entities (e.g. 'Pinnacle Labs' vs 'Pinnacle CVS' → ~74%).
    """
    if not folder.exists():
        return None
    new_slug = slugify(title)
    for existing in folder.glob("*.md"):
        if fuzz.ratio(new_slug, existing.stem) >= threshold:
            return existing
    return None


def _ensure_daily_note(date_iso: str) -> Path:
    """Return the path to a Cogs daily note, creating it if absent."""
    path = ensure_daily_note(date_iso, DAILY_DIR)
    if path.exists():
        log.debug("Daily note ready: %s", path.name)
    return path


def _append_cogs_item(node: NodeBase) -> None:
    """Append a Cogs daily item to the correct daily note."""
    note_path = ensure_daily_note(node.date, DAILY_DIR)
    appended = append_cogs_item_text(node.date, node.item_text, DAILY_DIR)
    if not appended:
        log.info("Cogs item already in %s, skipping: %s", note_path.name, node.item_text)
        return
    log.info("Appended to %s: %s", note_path.name, node.item_text)


def _write_sprockets_node(node: NodeBase, folder: Path) -> None:
    """
    Write a Sprockets node as a Markdown file with YAML frontmatter.
    Skips silently if the file already exists (deduplication stub — Stage 11 hardens this).
    """
    folder.mkdir(parents=True, exist_ok=True)
    slug = slugify(node.title)
    path = folder / f"{slug}.md"

    duplicate = _find_duplicate(node.title, folder)
    if duplicate:
        log.info("Duplicate suppressed (fuzzy match → %s): %s", duplicate.name, node.title)
        return

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
    if getattr(node, "parent", ""):
        metadata["parent"] = node.parent

    body = _NODE_BODY.render(node=node)
    post = frontmatter.Post(body, **metadata)
    path.write_text(frontmatter.dumps(post))
    log.info("Wrote %s → %s", node.node_type, path.name)


# ── Abstracted seams (Phase 3 fills these in) ─────────────────────────────────


def _build_hierarchy_context(max_nodes: int = 30) -> list[str]:
    """
    Return compact area/goal/project labels for parent_hint selection.
    Reads frontmatter only through vault_graph; note bodies stay out of model context.
    """
    return _sprockets_specialist().hierarchy_context_lines(max_nodes)


def _sprockets_specialist() -> SprocketsSpecialist:
    """Return the Sprockets facade while preserving the local build_graph test seam."""

    return SprocketsSpecialist(
        SprocketsSpecialistConfig(
            vault_dir=VAULT_DIR,
            graph_builder=build_graph,
        )
    )


def build_context() -> str:
    """
    Phase 2: today's Cogs note items + hot entity hints (contacts/entities seen <=7 days).
    Avoids injecting raw Markdown prose into the classify call, which causes 9B model
    context contamination (model bleeds note content into structured output fields).
    Stage 10B: adds compact hierarchy titles from frontmatter only so parent_hint can
    target existing area/goal/project nodes without creating new hierarchy nodes.
    Phase 3: queries vector DB for semantically relevant nodes.
    """
    return classifier_context.build_base_context(
        DAILY_DIR,
        entity_provider=get_entities_by_tier,
        hierarchy_context_builder=_build_hierarchy_context,
    )


def build_context_for_input(input_text: str) -> str:
    """
    Build classifier context for a specific input.

    Stage 17 keeps retrieved memory behind SPROCKETS_COGS_MEMORY_CONTEXT so we
    can rehearse the prompt shape before enabling it in the service.
    """
    return classifier_context.build_input_context(
        input_text,
        base_context_builder=build_context,
        retrieval_provider=retrieve_relevant_nodes,
    )


def retrieve_relevant_nodes(query: str) -> list:
    """
    Phase 1: returns empty list.
    Phase 3: semantic search over vault embeddings.
    """
    from production_retrieval import memory_retrieval_enabled, retrieve_with_gated_memory

    if memory_retrieval_enabled():
        try:
            return list(retrieve_with_gated_memory(query, VAULT_DIR))
        except Exception as exc:
            log.warning("Memory retrieval disabled for this query after error: %s", exc)
    return []


def write_node(node: NodeBase) -> None:
    """
    Phase 2: appends Cogs items to daily notes; writes Sprockets nodes as vault files;
    upserts contacts and entities into entity state (JSON working memory).
    Phase 3: also upserts embedding to vector DB.
    """
    if node.node_type == "cogs/daily":
        _append_cogs_item(node)
    elif node.node_type in SPROCKETS_FOLDERS:
        _write_sprockets_node(node, SPROCKETS_FOLDERS[node.node_type])
    else:
        log.warning("write_node: unhandled node_type %s", node.node_type)
    upsert_entity(node)


def write_to_review(raw: dict, reason: str) -> None:
    """Write a node that failed validation or has low confidence to review/."""
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
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

def extract_nodes(content: str) -> list[dict]:
    """Qwen3 call 1: extract raw items from input text."""
    classifier = ExtractClassifier(ExtractClassifierConfig(model=MODEL))
    return classifier.extract_nodes(content)


def classify_nodes(
    raw_nodes: list[dict],
    context: str,
    error_context: str = "",
    use_examples: bool = True,
) -> list[dict]:
    """Qwen3 call 2: assign node_type, fields, and date to each extracted item."""
    classifier = ExtractClassifier(ExtractClassifierConfig(model=MODEL))
    return classifier.classify_nodes(
        raw_nodes,
        context,
        error_context=error_context,
        use_examples=use_examples,
    )


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
    Phase 2: for each Sprockets node with a parent_hint, fuzzy-match against the
    vault graph and set node.parent to [[slug]] if a match is found above threshold.
    Degrades gracefully — unmatched hints are silently dropped, node is written
    without a parent rather than with a phantom link.
    Phase 3: also walks vector DB for semantic parent candidates.
    """
    specialist = _sprockets_specialist()
    for node in nodes:
        if getattr(node, "parent", ""):
            continue
        hint = getattr(node, "parent_hint", "")
        if not hint:
            continue
        match = specialist.parent_match_preview(hint)
        if match.matched:
            slug = match.slug
            node.parent = f"[[{slug}]]"
            log.info("Parent resolved: %s → [[%s]]", node.title, slug)
        else:
            log.debug("Parent hint unresolved (no vault match): %r", hint)
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


def ensure_runtime_dirs() -> None:
    """Create operational directories needed by the file-processing loop."""
    for path in [INPUT_DIR, PROCESSING_DIR, ARCHIVE_DIR, OUTPUT_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def process_existing_inputs(input_dir: Path = INPUT_DIR) -> int:
    """
    Process .input files already present when the service starts.
    Watchdog only emits new filesystem events, so startup needs this explicit scan.
    """
    count = 0
    for path in sorted(input_dir.glob("*.input")):
        if not path.is_file():
            continue
        log.info("Startup scan found pending input: %s", path.name)
        process_input(path)
        count += 1
    if count:
        log.info("Startup scan processed %d pending input(s)", count)
    else:
        log.info("Startup scan found no pending inputs")
    return count



def ensure_cogs_companions(classified: list[dict]) -> list[dict]:
    """Guarantee every sprockets/task has a cogs/daily companion on the same date."""
    _stop = {"a", "the", "for", "to", "of", "and", "in", "by", "at", "on", "re"}

    def _words(s: str) -> set:
        return set(s.lower().split()) - _stop

    def _valid_date(date: str) -> bool:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            return False
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return False
        return True

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
        if not date:
            continue
        if not _valid_date(date):
            node.pop("date", None)
            log.warning("ensure_cogs_companions: task %r has invalid date, skipping companion", title)
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
                "confidence": node.get("confidence", "high"),
            }
            result.append(companion)
            cogs_by_date.setdefault(date, []).append(title)
            log.info("Auto-added cogs/daily for task: %s on %s", title, date)
    return result


def ensure_hierarchy_tasks(raw_nodes: list[dict], classified: list[dict]) -> list[dict]:
    """
    Guarantee project-scoped raw tasks become Sprockets tasks.
    The local model sometimes treats "Need to..." as a daily-only item. If the raw
    task names an existing area/goal/project title, preserve the structural task and
    let resolve_parents link it through the normal hierarchy-only path.
    """
    hierarchy_targets = _sprockets_specialist().hierarchy_titles()
    if not hierarchy_targets:
        return classified

    result = list(classified)
    existing_task_titles = [
        node.get("title", "").lower()
        for node in classified
        if node.get("node_type") == "sprockets/task"
    ]
    today = datetime.now().strftime("%Y-%m-%d")

    for raw in raw_nodes:
        if raw.get("type_hint") != "task":
            continue
        raw_text = raw.get("raw", "").strip()
        raw_lower = raw_text.lower()
        if not raw_text:
            continue
        if any(title and title in raw_lower for title in existing_task_titles):
            continue

        parent_title = next(
            (title for title in hierarchy_targets if title.lower() in raw_lower),
            "",
        )
        if not parent_title:
            continue

        title = re.sub(r"^(need to|remember to|todo:?)\s+", "", raw_text, flags=re.IGNORECASE).strip()
        title = title[:1].upper() + title[1:] if title else raw_text
        result.append({
            "node_type": "sprockets/task",
            "title": title,
            "item_text": title,
            "date": today,
            "status": "active",
            "confidence": "high",
            "parent_hint": parent_title,
        })
        existing_task_titles.append(title.lower())
        log.info("Auto-added hierarchy task for %s: %s", parent_title, title)

    return result


def apply_explicit_hierarchy_hints(raw_nodes: list[dict], classified: list[dict]) -> list[dict]:
    """
    Attach parent_hint to Sprockets tasks/notes when raw text names an existing
    hierarchy target exactly. This is intentionally exact-match only; fuzzy
    ambiguity is handled later by resolve_parents().
    """
    hierarchy_targets = _sprockets_specialist().hierarchy_titles()
    if not hierarchy_targets:
        return classified

    raw_text_by_type = {
        raw.get("type_hint"): raw.get("raw", "").lower()
        for raw in raw_nodes
    }
    result = list(classified)
    for node in result:
        if node.get("parent_hint"):
            continue
        if node.get("node_type") not in {"sprockets/task", "sprockets/note"}:
            continue
        type_hint = "note" if node.get("node_type") == "sprockets/note" else "task"
        raw_text = raw_text_by_type.get(type_hint, "")
        title_text = f"{node.get('title', '')} {node.get('item_text', '')}".lower()
        haystack = f"{raw_text} {title_text}"
        parent_title = next(
            (title for title in hierarchy_targets if title.lower() in haystack),
            "",
        )
        if parent_title:
            node["parent_hint"] = parent_title
            log.info("Applied hierarchy parent_hint for %s: %s", node.get("title", ""), parent_title)
    return result


def apply_memory_parent_hints(input_text: str, classified: list[dict]) -> list[dict]:
    """
    Attach a parent_hint from the top retrieved hierarchy node after classification.

    Stage 17 deliberately keeps retrieved memory out of the classifier prompt for
    now; the local model copied memory text into generated fields during live
    rehearsals. This guard uses retrieval as a structural hint only.
    """
    return apply_memory_parent_title(classified, memory_parent_title(input_text))


def memory_parent_title(input_text: str) -> str:
    """Return the top retrieved hierarchy title for an input, if one exists."""
    return memory_parent_trace(input_text).parent_title


def memory_parent_trace(input_text: str) -> memory_guards.MemoryParentTrace:
    """Return a compact trace of memory parent selection for an input."""
    return memory_guards.memory_parent_trace(
        retrieve_relevant_nodes(input_text),
        HIERARCHY_PARENT_NODE_TYPES,
    )


def log_memory_parent_trace(trace: memory_guards.MemoryParentTrace) -> None:
    """Log the memory parent decision without logging the raw input text."""
    if trace.selected:
        log.info(
            "Memory parent guard selected: parent=%r node_id=%s node_type=%s retrieved=%d",
            trace.parent_title,
            trace.parent_node_id,
            trace.parent_node_type,
            trace.retrieved_count,
        )
    elif trace.retrieved_count:
        log.info(
            "Memory parent guard skipped: reason=%s top_node_id=%s top_node_type=%s retrieved=%d",
            trace.reason,
            trace.top_node_id,
            trace.top_node_type,
            trace.retrieved_count,
        )
    else:
        log.debug("Memory parent guard skipped: %s", trace.reason)


def write_memory_parent_trace(trace: memory_guards.MemoryParentTrace) -> None:
    """Append the memory parent decision to the operational JSONL trace log."""
    path = memory_trace_path()
    if not path.parent.exists() or not os.access(path.parent, os.W_OK):
        log.debug("Memory parent trace path unavailable: %s", path)
        return
    try:
        append_memory_parent_trace(trace, path)
    except OSError as exc:
        log.warning("Memory parent trace write failed: %s", exc)


def memory_trace_path() -> Path:
    """Return the current memory trace JSONL path."""
    return Path(os.environ.get(
        MEMORY_TRACE_PATH_ENV,
        str(OUTPUT_DIR / MEMORY_TRACE_FILENAME),
    ))


def apply_memory_parent_title(classified: list[dict], parent_title: str) -> list[dict]:
    """Attach an already-selected memory parent title to suitable nodes."""
    before = [node.get("parent_hint", "") for node in classified]
    result = memory_guards.apply_memory_parent_title(classified, parent_title)
    after = [node.get("parent_hint", "") for node in result]
    for node, previous, current in zip(result, before, after):
        if current and current != previous:
            log.info("Applied memory parent_hint for %s: %s", node.get("title", ""), current)
    return result


def ensure_memory_hierarchy_tasks(
    raw_nodes: list[dict],
    classified: list[dict],
    parent_title: str,
) -> list[dict]:
    """
    Add a structural Sprockets task when memory identifies a parent project but
    the classifier only produced a daily item.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    result, added_titles = memory_guards.ensure_memory_hierarchy_tasks(
        raw_nodes,
        classified,
        parent_title,
        today,
    )
    for title in added_titles:
        log.info("Auto-added memory hierarchy task for %s: %s", parent_title, title)

    return result


def route_ambiguous_hierarchy_parent_hints_to_review(nodes: list[NodeBase]) -> list[NodeBase]:
    """
    Route valid nodes with ambiguous hierarchy parent_hint values to review/.
    Ambiguous is better than wrong: these nodes should wait for human choice
    instead of being written unlinked or attached to a guess.
    """
    specialist = _sprockets_specialist()

    keep: list[NodeBase] = []
    for node in nodes:
        hint = getattr(node, "parent_hint", "")
        if not hint or getattr(node, "parent", ""):
            keep.append(node)
            continue
        matches = specialist.ambiguous_parent_matches(hint)
        if not matches:
            keep.append(node)
            continue

        match_titles = ", ".join(title for _, title, _ in matches)
        write_to_review(
            node.model_dump(mode="json"),
            f"ambiguous hierarchy parent_hint: {hint!r} matched {match_titles}",
        )
        log.warning("Routed ambiguous hierarchy parent_hint to review: %s", hint)
    return keep


def route_openai_fallback_to_review(
    raw_nodes: list[dict],
    context: str,
    reason: str,
) -> bool:
    """Route OpenAI-rescued candidates to review/, never directly to the vault."""
    if not raw_nodes or not openai_fallback_enabled():
        return False
    try:
        candidates = classify_nodes_with_openai_fallback(raw_nodes, context, reason)
    except Exception:
        log.exception("OpenAI fallback failed")
        return False
    if not candidates:
        return False

    candidates = ensure_cogs_companions(candidates)
    valid, invalid = validate_output(candidates)
    for node in valid:
        write_to_review(
            node.model_dump(mode="json"),
            f"openai_fallback_candidate: {reason}",
        )
    for _, raw, invalid_reason in invalid:
        write_to_review(
            raw,
            f"openai_fallback_invalid: {reason}; {invalid_reason}",
        )
    return True

# ── Main pipeline ──────────────────────────────────────────────────────────────

def process_input(file_path: Path) -> None:
    log.info("Processing: %s", file_path.name)
    processing_path = PROCESSING_DIR / file_path.name
    shutil.move(str(file_path), processing_path)

    try:
        post       = frontmatter.load(str(processing_path))
        content    = post.content
        session_id = post.get("session_id", processing_path.stem)

        context    = build_context_for_input(content)
        raw_nodes  = extract_nodes(content)
        classified = classify_nodes(raw_nodes, context)
        classified = apply_explicit_hierarchy_hints(raw_nodes, classified)
        classified = ensure_hierarchy_tasks(raw_nodes, classified)
        memory_trace = memory_parent_trace(content)
        log_memory_parent_trace(memory_trace)
        write_memory_parent_trace(memory_trace)
        memory_parent = memory_trace.parent_title
        classified = ensure_memory_hierarchy_tasks(raw_nodes, classified, memory_parent)
        classified = apply_memory_parent_title(classified, memory_parent)
        classified = ensure_cogs_companions(classified)

        valid_nodes, invalid_triples = validate_output(classified)

        retry_triples = [(idx, raw, reason) for idx, raw, reason in invalid_triples
                         if "confidence: low" not in reason]

        for idx, raw, reason in invalid_triples:
            if "confidence: low" not in reason:
                continue
            fallback_raw = [raw_nodes[idx]] if idx < len(raw_nodes) else []
            if fallback_raw and not route_openai_fallback_to_review(fallback_raw, context, reason):
                write_to_review(raw, reason)

        if retry_triples:
            retry_raw     = [raw_nodes[idx] for idx, _, _ in retry_triples
                             if idx < len(raw_nodes)]
            error_context = "\n".join(f"- {reason}" for _, _, reason in retry_triples)
            log.info("Retrying classify for %d invalid node(s)", len(retry_triples))
            reclassified        = classify_nodes(retry_raw, context, error_context, use_examples=True)[:len(retry_triples)]
            valid_retry, failed = validate_output(reclassified)
            valid_nodes.extend(valid_retry)
            if failed and route_openai_fallback_to_review(retry_raw, context, error_context):
                log.info("Retry failures routed through OpenAI fallback candidates")
            else:
                for _, raw, reason in failed:
                    write_to_review(raw, f"retry failed: {reason}")

        valid_nodes = route_ambiguous_hierarchy_parent_hints_to_review(valid_nodes)
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
    ensure_runtime_dirs()
    observer = Observer()
    observer.schedule(InputHandler(), str(INPUT_DIR), recursive=False)
    observer.start()
    process_existing_inputs()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutting down.")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()

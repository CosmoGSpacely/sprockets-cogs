import json
import logging
import os
import re
import shutil
import time
import uuid as uuid_lib
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import frontmatter
from rapidfuzz import fuzz
from jinja2 import Template
from pydantic import ValidationError
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import specialists.rosie.classifier_context as classifier_context
from substrate.format import apply_cogs_item_format
from specialists.rudi.entity_state import get_entities_by_tier, upsert_entity
from specialists.rosie.extractor_classifier import ExtractClassifier, ExtractClassifierConfig
from specialists.rosie.pipeline import (
    CaptureState,
    PipelineStep,
    retry_steps,
    run_pipeline,
)
from graph.mutations import MutationCommand
from graph.proposals import ReviewProposal
from intents.models import (
    AuthorityAssessment,
    Confidence as IntentConfidence,
    IntentClass,
    IntentClassification,
    RequiredGuard,
    SuggestedRoute,
)
import specialists.rudi.memory_guards as memory_guards
from specialists.rudi.memory_trace_log import append_memory_parent_trace
from substrate.models import Confidence, NodeBase, validate_node
from substrate.node_normalization import normalize_raw_node
from specialists.rudi.openai_fallback import (
    classify_nodes_with_openai_fallback,
    openai_fallback_enabled,
)
from specialists.uniblab.friction import record_processing_failure
from specialists.rudi.response_routing import (
    ResponseContext,
    ResponseEnvelope,
    ResponseType,
    response_context_from_frontmatter,
)
from substrate.slug_utils import slugify
from specialists.sprockets.specialist import SprocketsSpecialist, SprocketsSpecialistConfig
import specialists.orbit.adapters.telegram_response as telegram_response
from substrate.node_matching import match_words, raw_text_for, similarity
from substrate.time_context import (
    apply_bounded_recurrence_context,
    apply_runtime_date_context,
    states_a_date,
)
from specialists.cogs.corrections import apply_correction_command, parse_correction_command
from specialists.sprockets.vault_graph import (
    HIERARCHY_PARENT_NODE_TYPES,
    build_graph,
)
from specialists.astro.vault import (
    append_cogs_item_text,
    append_monthly_carry_item_text,
    append_weekly_carry_item_text,
    ensure_daily_note,
)

# ── Constants ──────────────────────────────────────────────────────────────────
DEFAULT_MODEL = "gemma4:12b-16k-cosmo"
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
CORRECTION_AUDIT_FILENAME = "cogs-correction-audit.jsonl"
STRUCTURAL_GUARD_ENV = "SPROCKETS_COGS_STRUCTURAL_GUARD"
DEFAULT_TIMEZONE = "America/New_York"

DAILY_DIR      = VAULT_DIR / "Cogs"
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

_STRUCTURAL_LABEL_PATTERN = re.compile(
    r"\b(area|goal|project|task|subproject|sprocket|cog|bridge|parent|hierarchy)\s*:",
    re.IGNORECASE,
)
_STRUCTURAL_COMMAND_PATTERN = re.compile(
    r"\b(create|make|add|move|link|merge|split|rename|schedule|reparent)\b"
    r".*\b(area|goal|project|task|contact|entity|reference|sprocket|cog|bridge|parent|hierarchy)\b",
    re.IGNORECASE | re.DOTALL,
)
_STRUCTURAL_NODE_TYPES = {
    "graph/proposal",
    "review/proposal",
    "structural/proposal",
}
_STRUCTURAL_INTENT_VALUES = {
    "structural_proposal",
    "planning_update",
    "review_decision",
}
_ENTITY_AUTHORITY_NODE_TYPES = {
    "sprockets/entity",
}
_ADDRESS_PATTERN = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9 .'-]+"
    r"\b(?:st|street|ave|avenue|rd|road|dr|drive|ln|lane|blvd|boulevard|ct|court|way|pkwy|parkway)\b",
    re.IGNORECASE,
)
_RECURRENCE_PATTERN = re.compile(
    r"\b("
    r"every\s+(?:day|weekday|week|month|year|"
    r"mon(?:day)?s?|tue(?:s|sdays?)?|wed(?:nesday)?s?|thu(?:r|rs|rsday)?s?|"
    r"fri(?:day)?s?|sat(?:urday)?s?|sun(?:day)?s?)|"
    r"each\s+(?:day|weekday|week|month|year|"
    r"mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?)|"
    r"(?:daily|weekly|monthly|yearly|annually)|"
    r"(?:mon(?:day)?s|tue(?:s|sdays)|wed(?:nesday)?s|thu(?:r|rs|rsday)?s|"
    r"fri(?:day)?s|sat(?:urday)?s|sun(?:day)?s)"
    r")\b",
    re.IGNORECASE,
)


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
    horizon = getattr(node, "horizon", "day")
    cogs_dir = DAILY_DIR.parent if DAILY_DIR.name == "daily" else DAILY_DIR
    if horizon == "week":
        appended = append_weekly_carry_item_text(node.date, node.item_text, cogs_dir)
        if appended:
            log.info("Appended to weekly carry for %s: %s", node.date, node.item_text)
        else:
            log.info("Weekly carry item already present for %s, skipping: %s", node.date, node.item_text)
        return
    if horizon == "month":
        appended = append_monthly_carry_item_text(node.date, node.item_text, cogs_dir)
        if appended:
            log.info("Appended to monthly carry for %s: %s", node.date, node.item_text)
        else:
            log.info("Monthly carry item already present for %s, skipping: %s", node.date, node.item_text)
        return

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
    from specialists.rudi.production_retrieval import memory_retrieval_enabled, retrieve_with_gated_memory

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


def structural_guard_enabled() -> bool:
    """Return whether deterministic structural proposal routing is active."""

    value = os.environ.get(STRUCTURAL_GUARD_ENV, "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _node_text(node: dict) -> str:
    return " ".join(
        str(node.get(field, ""))
        for field in (
            "raw",
            "title",
            "item_text",
            "parent_hint",
            "operation",
            "intent_class",
            "action",
        )
    )


def _structural_guard_reasons(
    source_text: str,
    raw_nodes: list[dict],
    classified: list[dict],
) -> tuple[str, ...]:
    """Return deterministic reasons that require structural review."""

    reasons: list[str] = []
    combined_text = " ".join(
        [source_text]
        + [_node_text(node) for node in raw_nodes]
        + [_node_text(node) for node in classified]
    )
    if _STRUCTURAL_LABEL_PATTERN.search(combined_text):
        reasons.append("structural label syntax")
    if _STRUCTURAL_COMMAND_PATTERN.search(combined_text):
        reasons.append("graph mutation command language")

    for node in classified:
        node_type = str(node.get("node_type", "")).strip().lower()
        intent_class = str(node.get("intent_class", "")).strip().lower()
        operation = str(node.get("operation", "")).strip().lower()
        if node_type in _STRUCTURAL_NODE_TYPES:
            reasons.append(f"structural node_type: {node_type}")
        if intent_class in _STRUCTURAL_INTENT_VALUES:
            reasons.append(f"structural intent_class: {intent_class}")
        if operation in {"move", "link", "merge", "split", "rename", "reparent"}:
            reasons.append(f"non-allowlisted mutation operation: {operation}")

    return tuple(dict.fromkeys(reasons))


def _structural_review_proposal(
    source_text: str,
    raw_nodes: list[dict],
    classified: list[dict],
    reasons: tuple[str, ...],
    session_id: str,
) -> ReviewProposal:
    """Build a review-first proposal packet for guarded structural input."""

    proposal_id = f"structural-guard-{uuid_lib.uuid4().hex[:8]}"
    intent = IntentClassification(
        intent_class=IntentClass.STRUCTURAL_PROPOSAL,
        confidence=IntentConfidence.HIGH,
        authority=AuthorityAssessment(
            detected_authority_risks=reasons,
            required_guard=RequiredGuard.DETERMINISTIC_PACKET_REQUIRED,
            packet_required_suggestion=True,
        ),
        evidence=reasons,
        uncertainty=("requires human review before graph mutation",),
        suggested_route=(
            SuggestedRoute.ROSIE,
            SuggestedRoute.RUDI,
            SuggestedRoute.JANE,
            SuggestedRoute.VALIDATORS,
            SuggestedRoute.AUDIT,
        ),
    )
    command = MutationCommand(
        id=f"{proposal_id}-mutation",
        operation="create_sprocket_and_bridge",
        target_layer="product_graph",
        review_class="review_first",
        payload={
            "source_text": source_text,
            "raw_nodes": raw_nodes,
            "classified_nodes": classified,
            "intent": intent.to_dict(),
            "guard": RequiredGuard.DETERMINISTIC_PACKET_REQUIRED.value,
        },
        expected_current_state={
            "live_guard": STRUCTURAL_GUARD_ENV,
            "direct_write_allowed": False,
        },
    )
    return ReviewProposal(
        id=proposal_id,
        reason="deterministic structural guard requires review packet",
        display_text=source_text.strip()[:500] or "Structural proposal",
        mutation_command=command,
        source={
            "session_id": session_id,
            "guard_reasons": list(reasons),
        },
    )


def route_structural_guard_to_review(
    source_text: str,
    raw_nodes: list[dict],
    classified: list[dict],
    session_id: str,
) -> tuple[list[dict], bool]:
    """
    Route structural proposal language to review before ordinary validation.

    This is a deterministic substrate guard. It does not ask the model whether a
    review packet is required; it detects high-risk structural language and
    prevents direct writes.
    """

    if not structural_guard_enabled():
        return classified, False

    reasons = _structural_guard_reasons(source_text, raw_nodes, classified)
    if not reasons:
        return classified, False

    proposal = _structural_review_proposal(source_text, raw_nodes, classified, reasons, session_id)
    write_to_review(
        proposal.model_dump(mode="json", exclude_none=True),
        f"structural_guard_packet_required: {', '.join(reasons)}",
    )
    log.warning("Structural guard routed input to review: %s", ", ".join(reasons))
    return [], True


def needs_memory_parent_retrieval(raw_nodes: list[dict], classified: list[dict]) -> bool:
    """Return whether retrieved memory may be used as a structural parent hint."""

    for node in classified:
        if node.get("node_type") in {"sprockets/task", "sprockets/note"}:
            return True
        if str(node.get("intent_class", "")).strip().lower() in _STRUCTURAL_INTENT_VALUES:
            return True
        if str(node.get("operation", "")).strip().lower() in {"link", "reparent", "create_sprocket_and_bridge"}:
            return True
    return False


def memory_parent_trace_for_classification(
    input_text: str,
    raw_nodes: list[dict],
    classified: list[dict],
) -> memory_guards.MemoryParentTrace:
    """Use retrieved memory as parent evidence only for structural captures."""

    if not needs_memory_parent_retrieval(raw_nodes, classified):
        return memory_guards.MemoryParentTrace(retrieved_count=0)
    return memory_parent_trace(input_text)


def route_ordinary_entity_authority_to_review(
    raw_nodes: list[dict],
    classified: list[dict],
) -> list[dict]:
    """
    Route ordinary event-attached durable entity candidates to review.

    Cogs capture can mention places, addresses, or organizations without
    granting authority to create durable Sprockets vertices from that context.
    """

    has_cogs = any(node.get("node_type") == "cogs/daily" for node in classified)
    if not has_cogs:
        return classified

    raw_text = " ".join(str(raw.get("raw", "")) for raw in raw_nodes)
    result: list[dict] = []
    for node in classified:
        node_type = str(node.get("node_type", ""))
        node_text = _node_text(node)
        address_pressure = bool(_ADDRESS_PATTERN.search(f"{raw_text} {node_text}"))
        if node_type in _ENTITY_AUTHORITY_NODE_TYPES or (
            node_type == "sprockets/contact" and address_pressure
        ):
            write_to_review(
                node,
                "ordinary_entity_authority_guard: durable entity/contact creation requires review",
            )
            log.warning("Routed ordinary entity authority candidate to review: %s", node_text)
            continue
        result.append(node)
    return result


def route_recurrence_to_review(raw_nodes: list[dict], classified: list[dict]) -> list[dict]:
    """Route recurring Cogs candidates to review until recurrence has a contract."""

    result: list[dict] = []
    for index, node in enumerate(classified):
        if node.get("node_type") != "cogs/daily":
            result.append(node)
            continue
        if node.get("_bounded_recurrence"):
            result.append(node)
            continue
        texts = [
            str(raw_nodes[index].get("raw", "")) if index < len(raw_nodes) else "",
            _node_text(node),
        ]
        match = _RECURRENCE_PATTERN.search(" ".join(texts))
        if not match:
            result.append(node)
            continue
        write_to_review(
            node,
            f"recurrence_guard: recurring Cogs language {match.group(0)!r} requires review",
        )
        log.warning("Routed recurring Cogs candidate to review: %s", match.group(0))
    return result


def send_response(
    session_id: str,
    text: str,
    *,
    response_context: ResponseContext | None = None,
    response_type: ResponseType = ResponseType.PROCESSED,
) -> None:
    """
    Phase 1: appends reflection line to today's Cogs daily note.
    Later: routes back to originating channel via source adapter.
    """
    note_path = _ensure_daily_note(datetime.now().strftime("%Y-%m-%d"))
    timestamp = datetime.now().strftime("%H:%M")
    with note_path.open("a") as f:
        f.write(f"\n> [{timestamp}] agent: {text}\n")
    log.info("Reflection appended to %s", note_path.name)

    if response_context is None:
        return

    send_source_response(
        response_context=response_context,
        text=text,
        response_type=response_type,
    )


def send_source_response(
    *,
    response_context: ResponseContext,
    text: str,
    response_type: ResponseType = ResponseType.PROCESSED,
) -> None:
    """Send a conservative source response without adding another local note."""

    envelope = ResponseEnvelope(
        context=response_context,
        response_type=response_type,
        text=text,
    )
    route = telegram_response.route_response(envelope)
    if route.sink != "telegram" or not route.would_send:
        log.info("Source response stayed local: %s", route.reason)
        return

    env = telegram_response.merged_env_with_file()
    token = env.get(telegram_response.TELEGRAM_TOKEN_ENV, "").strip()
    if not token:
        log.warning("Telegram response skipped: token is not configured")
        return

    try:
        payload = telegram_response.send_telegram_response(envelope, token=token)
    except Exception as exc:
        log.warning("Telegram response failed: %s", exc)
        return

    message_id = ""
    result = payload.get("result", {})
    if isinstance(result, dict):
        message_id = str(result.get("message_id") or "")
    log.info("Telegram response sent: message_id=%s", message_id or "unknown")


# ── Pipeline steps ─────────────────────────────────────────────────────────────

def extract_nodes(content: str, now: datetime | None = None) -> list[dict]:
    """Qwen3 call 1: extract raw items from input text."""
    classifier = ExtractClassifier(ExtractClassifierConfig(model=MODEL))
    if now is None:
        return classifier.extract_nodes(content)
    return classifier.extract_nodes(content, now=now)


def classify_nodes(
    raw_nodes: list[dict],
    context: str,
    error_context: str = "",
    use_examples: bool = True,
    now: datetime | None = None,
) -> list[dict]:
    """Qwen3 call 2: assign node_type, fields, and date to each extracted item."""
    classifier = ExtractClassifier(ExtractClassifierConfig(model=MODEL))
    if now is None:
        return classifier.classify_nodes(
            raw_nodes,
            context,
            error_context=error_context,
            use_examples=use_examples,
        )
    return classifier.classify_nodes(
        raw_nodes,
        context,
        error_context=error_context,
        use_examples=use_examples,
        now=now,
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


def validate_output(
    nodes: list[dict],
    *,
    default_cogs_date: str | None = None,
    reject_non_default_cogs_date: bool = False,
) -> tuple[list[NodeBase], list[InvalidTriple]]:
    """
    Validate each node against its Pydantic model.
    Returns (valid_nodes, invalid_triples) where each triple is (index, raw_dict, reason).
    Low-confidence nodes are invalid and route to review/ without retry.
    """
    valid:   list[NodeBase]      = []
    invalid: list[InvalidTriple] = []

    for i, raw in enumerate(nodes):
        try:
            normalized = normalize_raw_node(
                raw,
                default_cogs_date=default_cogs_date,
                reject_non_default_cogs_date=reject_non_default_cogs_date,
            )
            node = validate_node(normalized)
            if node.confidence == Confidence.LOW:
                invalid.append((i, normalized, "confidence: low"))
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


def append_reflection(
    session_id: str,
    nodes: list[NodeBase],
    *,
    response_context: ResponseContext | None = None,
) -> None:
    summary = f"Processed {len(nodes)} node(s) from session {session_id}"
    if nodes:
        summary += f": {', '.join(n.node_type for n in nodes)}"
    send_response(session_id, summary, response_context=response_context)


def send_processed_ack(session_id: str, nodes: list[NodeBase], response_context: ResponseContext) -> None:
    """Send a compact source acknowledgement after a successful live pass."""

    count = len(nodes)
    text = f"Processed {count} item{'s' if count != 1 else ''}."
    send_source_response(response_context=response_context, text=text)


def archive_input(processing_path: Path) -> None:
    dest = collision_safe_archive_path(ARCHIVE_DIR / processing_path.name)
    shutil.move(str(processing_path), dest)
    log.info("Archived → %s", dest)


def collision_safe_archive_path(path: Path) -> Path:
    """Return an archive path that preserves existing input history."""

    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"could not find archive destination for: {path}")


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



#: How similar two Cogs item texts must be before one counts as the other's
#: companion. Stage 142 C9 / finding 36: the old test was "share any word",
#: which suppressed "Install ladder racks" because "Install bin shelves" had
#: already produced a companion. A ratio keeps near-duplicates suppressed and
#: lets genuinely different tasks through.
COMPANION_DUPLICATE_THRESHOLD = 0.6


def ensure_cogs_companions(
    raw_nodes: list[dict],
    classified: list[dict],
    processing_date: str,
) -> list[dict]:
    """Give a sprockets/task a cogs/daily companion when the capture named a day.

    Stage 142 C8, a product decision rather than an inferred one: spawning is a
    capture act **only when the source text states a day**. A standing task with
    no date waits for planning instead of being dumped onto today, which is what
    made `project-task-list` emit seven tasks and four spurious Cogs.

    The question is asked of the **raw text**, not the node's `date` field,
    because `normalize_raw_node` fills a missing date with the processing date -
    after which "stated" and "defaulted" cannot be told apart.
    """

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
        # C8: only when the capture actually named a day.
        raw_text = raw_text_for(node, raw_nodes)
        if not states_a_date(raw_text, processing_date):
            log.info(
                "ensure_cogs_companions: no day stated for task %r, "
                "leaving it for planning",
                title,
            )
            continue

        # C9: near-duplicate, not any-shared-word.
        title_words = match_words(title)
        existing = cogs_by_date.get(date, [])
        has_companion = any(
            similarity(title_words, match_words(item)) >= COMPANION_DUPLICATE_THRESHOLD
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
    default_cogs_date: str | None = None,
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

    candidates = ensure_cogs_companions(
        raw_nodes,
        candidates,
        default_cogs_date or datetime.now().strftime("%Y-%m-%d"),
    )
    valid, invalid = validate_output(
        candidates,
        default_cogs_date=default_cogs_date or datetime.now().strftime("%Y-%m-%d"),
        reject_non_default_cogs_date=True,
    )
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


def source_datetime_from_frontmatter(metadata: dict) -> datetime:
    """Return the source timestamp for an adapter input, falling back to now."""

    timestamp = ""
    direct = metadata.get("source_timestamp")
    if isinstance(direct, str):
        timestamp = direct
    nested = metadata.get("metadata")
    if not timestamp and isinstance(nested, dict):
        nested_timestamp = nested.get("source_timestamp")
        if isinstance(nested_timestamp, str):
            timestamp = nested_timestamp
        elif nested.get("telegram_message_date") is not None:
            try:
                timestamp = datetime.fromtimestamp(
                    int(str(nested["telegram_message_date"])),
                    tz=ZoneInfo("UTC"),
                ).isoformat()
            except (TypeError, ValueError, OSError):
                timestamp = ""

    if timestamp:
        normalized = timestamp.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE))
            return parsed.astimezone(ZoneInfo(DEFAULT_TIMEZONE))
        except ValueError:
            log.warning("Ignoring invalid source timestamp: %r", timestamp)

    return datetime.now()


def correction_audit_path() -> Path:
    """Return the current Cogs correction audit JSONL path."""

    return OUTPUT_DIR / CORRECTION_AUDIT_FILENAME


def write_correction_audit(
    *,
    session_id: str,
    source_text: str,
    correction_kind: str,
    status: str,
    message: str,
    source_date: str,
) -> None:
    """Append a compact audit record for correction command handling."""

    path = correction_audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "session_id": session_id,
        "source_date": source_date,
        "correction_kind": correction_kind,
        "status": status,
        "message": message,
        "source_text": source_text.strip(),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def handle_correction_input(
    *,
    content: str,
    source_date: str,
    session_id: str,
    response_context: ResponseContext,
) -> bool:
    """Apply a narrow correction/removal command before ordinary capture."""

    correction = parse_correction_command(content, source_date)
    if correction is None:
        return False
    result = apply_correction_command(correction, DAILY_DIR)
    write_correction_audit(
        session_id=session_id,
        source_text=content,
        correction_kind=correction.kind,
        status=result.status,
        message=result.message,
        source_date=source_date,
    )
    if result.status == "corrected":
        send_source_response(
            response_context=response_context,
            text=f"Corrected: {result.message}",
        )
        log.info("Correction applied: %s", result.message)
    else:
        write_to_review(
            {
                "node_type": "review/proposal",
                "title": "Cogs correction requires review",
                "item_text": content.strip(),
                "date": source_date,
                "confidence": "low",
            },
            f"correction_command_review: {result.message}",
        )
        send_source_response(
            response_context=response_context,
            text="Correction needs review.",
            response_type=ResponseType.REVIEW_REQUIRED,
        )
        log.warning("Correction routed to review: %s", result.message)
    return True

# ── Main pipeline ──────────────────────────────────────────────────────────────

# ── The declared post-classify pipeline (Stage 142 A1) ────────────────────────
#
# Each wrapper adapts one existing step to the uniform CaptureState signature.
# The wrappers add no logic: same functions, same arguments, same order. The
# thirteen names here are the same thirteen the drift guard checks.


def _step_runtime_date_context(state: CaptureState) -> None:
    state.classified, decisions = apply_runtime_date_context(
        state.raw_nodes, state.classified, state.source_date
    )
    for decision in decisions:
        log.info(
            "Runtime date context applied: node=%d phrase=%s date=%s -> %s",
            decision.index,
            decision.phrase,
            decision.original_date or "(missing)",
            decision.resolved_date,
        )


def _step_bounded_recurrence(state: CaptureState) -> None:
    state.classified, decisions = apply_bounded_recurrence_context(
        state.raw_nodes, state.classified, state.source_date
    )
    for decision in decisions:
        log.info(
            "Bounded recurrence expanded: node=%d occurrences=%d phrase=%r",
            decision.index,
            decision.occurrence_count,
            decision.phrase,
        )


def _step_cogs_item_format(state: CaptureState) -> None:
    state.classified, decisions = apply_cogs_item_format(
        state.raw_nodes, state.classified
    )
    for decision in decisions:
        log.info(
            "Cogs item format applied: node=%d reason=%s %r -> %r",
            decision.index,
            decision.reason,
            decision.original_text,
            decision.formatted_text,
        )


def _step_structural_guard(state: CaptureState) -> None:
    state.classified, routed = route_structural_guard_to_review(
        state.content, state.raw_nodes, state.classified, state.session_id
    )
    # The only step that ends a capture. The runner stops here and
    # process_input handles the reflection and archive.
    state.terminated = bool(routed)


def _step_ordinary_entity_authority(state: CaptureState) -> None:
    state.classified = route_ordinary_entity_authority_to_review(
        state.raw_nodes, state.classified
    )


def _step_recurrence_review(state: CaptureState) -> None:
    state.classified = route_recurrence_to_review(state.raw_nodes, state.classified)


def _step_explicit_hierarchy_hints(state: CaptureState) -> None:
    state.classified = apply_explicit_hierarchy_hints(state.raw_nodes, state.classified)


def _step_ensure_hierarchy_tasks(state: CaptureState) -> None:
    state.classified = ensure_hierarchy_tasks(state.raw_nodes, state.classified)


def _step_log_memory_parent_trace(state: CaptureState) -> None:
    # Computing the trace belongs to this step; the next one persists it.
    state.memory_trace = memory_parent_trace_for_classification(
        state.content, state.raw_nodes, state.classified
    )
    log_memory_parent_trace(state.memory_trace)
    state.memory_parent = state.memory_trace.parent_title


def _step_write_memory_parent_trace(state: CaptureState) -> None:
    write_memory_parent_trace(state.memory_trace)


def _step_ensure_memory_hierarchy_tasks(state: CaptureState) -> None:
    state.classified = ensure_memory_hierarchy_tasks(
        state.raw_nodes, state.classified, state.memory_parent
    )


def _step_apply_memory_parent_title(state: CaptureState) -> None:
    state.classified = apply_memory_parent_title(state.classified, state.memory_parent)


def _step_ensure_cogs_companions(state: CaptureState) -> None:
    state.classified = ensure_cogs_companions(
        state.raw_nodes, state.classified, state.source_date
    )


#: The capture pipeline. Order is behaviour - this is the same order the
#: inline chain ran, and `tests/test_stage_139_full_pipeline.py` fails if the
#: harness and this list disagree.
PIPELINE: tuple[PipelineStep, ...] = (
    PipelineStep("apply_runtime_date_context", "nodes", True, _step_runtime_date_context,
                 retry_note="re-runs: retried nodes carry unresolved dates"),
    PipelineStep("apply_bounded_recurrence_context", "nodes", True, _step_bounded_recurrence,
                 retry_note="re-runs: a retried recurrence still needs expanding"),
    PipelineStep("apply_cogs_item_format", "nodes", True, _step_cogs_item_format,
                 retry_note="re-runs: formatting applies to any node text"),
    PipelineStep("route_structural_guard_to_review", "capture", False, _step_structural_guard,
                 retry_note="whole-capture decision, already made"),
    PipelineStep("route_ordinary_entity_authority_to_review", "nodes", False,
                 _step_ordinary_entity_authority,
                 retry_note="omitted from retry - see RETRY_OMISSIONS"),
    PipelineStep("route_recurrence_to_review", "nodes", False, _step_recurrence_review,
                 retry_note="omitted from retry - see RETRY_OMISSIONS"),
    PipelineStep("apply_explicit_hierarchy_hints", "nodes", True, _step_explicit_hierarchy_hints,
                 retry_note="omitted from retry - see RETRY_OMISSIONS"),
    PipelineStep("ensure_hierarchy_tasks", "nodes", True, _step_ensure_hierarchy_tasks,
                 retry_note="omitted from retry - see RETRY_OMISSIONS"),
    PipelineStep("log_memory_parent_trace", "capture", False, _step_log_memory_parent_trace,
                 retry_note="capture-level tracing, emitted once"),
    PipelineStep("write_memory_parent_trace", "capture", False, _step_write_memory_parent_trace,
                 retry_note="capture-level tracing, written once"),
    PipelineStep("ensure_memory_hierarchy_tasks", "nodes", True,
                 _step_ensure_memory_hierarchy_tasks,
                 retry_note="omitted from retry - see RETRY_OMISSIONS"),
    PipelineStep("apply_memory_parent_title", "nodes", True, _step_apply_memory_parent_title,
                 retry_note="omitted from retry - see RETRY_OMISSIONS"),
    PipelineStep("ensure_cogs_companions", "nodes", True, _step_ensure_cogs_companions,
                 retry_note="omitted from retry - see RETRY_OMISSIONS"),
)


def process_input(file_path: Path) -> None:
    log.info("Processing: %s", file_path.name)
    processing_path = PROCESSING_DIR / file_path.name
    shutil.move(str(file_path), processing_path)

    try:
        post       = frontmatter.load(str(processing_path))
        content    = post.content
        session_id = post.get("session_id", processing_path.stem)
        response_context = response_context_from_frontmatter(
            post.metadata,
            fallback_session_id=session_id,
        )
        source_now = source_datetime_from_frontmatter(post.metadata)
        source_date = source_now.strftime("%Y-%m-%d")

        if handle_correction_input(
            content=content,
            source_date=source_date,
            session_id=session_id,
            response_context=response_context,
        ):
            archive_input(processing_path)
            return

        context    = build_context_for_input(content)
        raw_nodes  = extract_nodes(content, now=source_now)
        classified = classify_nodes(raw_nodes, context, now=source_now)

        state = run_pipeline(
            CaptureState(
                content=content,
                raw_nodes=raw_nodes,
                classified=classified,
                source_date=source_date,
                session_id=session_id,
            ),
            PIPELINE,
        )
        if state.terminated:
            append_reflection(session_id, [])
            archive_input(processing_path)
            return
        classified = state.classified

        valid_nodes, invalid_triples = validate_output(classified, default_cogs_date=source_date)

        retry_triples = [(idx, raw, reason) for idx, raw, reason in invalid_triples
                         if "confidence: low" not in reason]

        for idx, raw, reason in invalid_triples:
            if "confidence: low" not in reason:
                continue
            fallback_raw = [raw_nodes[idx]] if idx < len(raw_nodes) else []
            if fallback_raw and not route_openai_fallback_to_review(
                fallback_raw,
                context,
                reason,
                source_date,
            ):
                write_to_review(raw, reason)

        if retry_triples:
            retry_raw     = [raw_nodes[idx] for idx, _, _ in retry_triples
                             if idx < len(raw_nodes)]
            error_context = "\n".join(f"- {reason}" for _, _, reason in retry_triples)
            log.info("Retrying classify for %d invalid node(s)", len(retry_triples))
            reclassified        = classify_nodes(retry_raw, context, error_context, use_examples=True, now=source_now)[:len(retry_triples)]
            # Every node-scoped step, so a retried node gets the same
            # treatment as one that classified correctly first time. Slice 2b:
            # previously three of thirteen ran here, and the seven per-node
            # steps that did not are listed in `pipeline.RETRY_DEFECTS_FIXED`.
            # `memory_parent` is inherited rather than recomputed - the
            # capture-scoped step that derives it does not re-run, and a second
            # retrieval could return something different for no reason.
            retry_state = run_pipeline(
                CaptureState(
                    content=content,
                    raw_nodes=retry_raw,
                    classified=reclassified,
                    source_date=source_date,
                    session_id=session_id,
                    memory_parent=state.memory_parent,
                ),
                retry_steps(PIPELINE),
            )
            reclassified = retry_state.classified
            valid_retry, failed = validate_output(reclassified, default_cogs_date=source_date)
            valid_nodes.extend(valid_retry)
            if failed and route_openai_fallback_to_review(retry_raw, context, error_context, source_date):
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
        send_processed_ack(session_id, resolved, response_context)
        archive_input(processing_path)

    except Exception as exc:
        record_processing_failure(input_file=processing_path, error=exc)
        log.exception(
            "Failed to process %s — left in processing/ for inspection",
            file_path.name,
        )


# ── Watchdog handler ───────────────────────────────────────────────────────────

class InputHandler(FileSystemEventHandler):
    def _handle_input_path(self, path: Path) -> None:
        if path.suffix == ".input":
            log.info("Detected: %s", path.name)
            time.sleep(0.5)
            process_input(path)

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_input_path(Path(event.src_path))

    def on_moved(self, event):
        if event.is_directory:
            return
        self._handle_input_path(Path(event.dest_path))


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

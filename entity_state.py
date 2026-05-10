"""
entity_state.py — Persistent JSON working memory for known entities.

Tracks sprockets/contact and sprockets/entity nodes seen by the agentic loop.
Used by build_context() to surface hot entities to the classifier, and by
write_node() to keep state current on every vault write.

Tiers (by days since last_seen):
  hot  — <= 7 days   (included in classify context)
  warm — 8-30 days
  cold — > 30 days
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

SC_ROOT = Path(os.environ.get("SPROCKETS_COGS_SC_ROOT", str(Path.home() / "sc")))
STATE_PATH = Path(
    os.environ.get("SPROCKETS_COGS_ENTITY_STATE_PATH", str(SC_ROOT / "entity_state.json"))
)

TRACKABLE_TYPES = {"sprockets/contact", "sprockets/entity"}


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60].strip("-")


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def upsert_entity(node) -> None:
    """Update or insert an entity record when a node is written to vault."""
    if node.node_type not in TRACKABLE_TYPES:
        return
    state = load_state()
    slug = _slugify(node.title)
    today = datetime.now().strftime("%Y-%m-%d")
    existing = state.get(slug, {})
    state[slug] = {
        "title":     node.title,
        "node_type": node.node_type,
        "last_seen": today,
        "first_seen": existing.get("first_seen", today),
    }
    save_state(state)


def get_entities_by_tier(tier: str) -> list[dict]:
    """Return entity records filtered by tier: 'hot' (<=7d), 'warm' (8-30d), 'cold' (>30d)."""
    state = load_state()
    today = datetime.now().date()
    result = []
    for record in state.values():
        try:
            last_seen = datetime.strptime(record["last_seen"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        age = (today - last_seen).days
        if tier == "hot" and age <= 7:
            result.append(record)
        elif tier == "warm" and 8 <= age <= 30:
            result.append(record)
        elif tier == "cold" and age > 30:
            result.append(record)
    return result

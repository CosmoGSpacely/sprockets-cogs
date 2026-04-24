"""
Pydantic v2 node models for Sprockets and Cogs.
One model per node_type. validate_node() dispatches by node_type field.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator, model_validator

# Re-export ValidationError so callers only need to import from models
__all__ = [
    "Confidence", "NodeBase", "CogsDailyItem",
    "SprocketsTask", "SprocketsContact", "SprocketsEntity", "SprocketsNote",
    "validate_node", "ValidationError",
]


class Confidence(str, Enum):
    HIGH = "high"
    LOW  = "low"


class NodeBase(BaseModel):
    node_type:  str
    confidence: Confidence


# ── Cogs ───────────────────────────────────────────────────────────────────────

class CogsDailyItem(NodeBase):
    node_type: Literal["cogs/daily"]
    item_text:  str
    date:       str   # YYYY-MM-DD

    @field_validator("date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"date must be YYYY-MM-DD, got {v!r}")
        return v

    @field_validator("item_text")
    @classmethod
    def validate_item_text_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("item_text cannot be empty")
        return v.strip()


# ── Sprockets ──────────────────────────────────────────────────────────────────

class _SprocketsBase(NodeBase):
    """
    Base for all Sprockets nodes.
    Coerces item_text → title so the model's occasional wrong field name
    is fixed gracefully rather than rejected outright.
    """
    title: str

    @model_validator(mode="before")
    @classmethod
    def coerce_item_text_to_title(cls, data: dict) -> dict:
        if not data.get("title") and data.get("item_text"):
            data = {**data, "title": data["item_text"]}
        return data

    @field_validator("title")
    @classmethod
    def validate_title_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title cannot be empty")
        return v.strip()


class SprocketsTask(_SprocketsBase):
    node_type: Literal["sprockets/task"]
    status: Literal["active", "complete", "cancelled", "someday"] = "active"


class SprocketsContact(_SprocketsBase):
    node_type: Literal["sprockets/contact"]


class SprocketsEntity(_SprocketsBase):
    node_type: Literal["sprockets/entity"]


class SprocketsNote(_SprocketsBase):
    node_type: Literal["sprockets/note"]


# ── Dispatch ───────────────────────────────────────────────────────────────────

NODE_MODELS: dict[str, type[NodeBase]] = {
    "cogs/daily":        CogsDailyItem,
    "sprockets/task":    SprocketsTask,
    "sprockets/contact": SprocketsContact,
    "sprockets/entity":  SprocketsEntity,
    "sprockets/note":    SprocketsNote,
}


def validate_node(raw: dict) -> NodeBase:
    """
    Parse a raw dict into the correct node model by node_type.
    Raises ValueError for unknown node_type, ValidationError for bad fields.
    """
    node_type = raw.get("node_type", "")
    model_class = NODE_MODELS.get(node_type)
    if not model_class:
        raise ValueError(f"Unknown node_type: {node_type!r}")
    return model_class.model_validate(raw)

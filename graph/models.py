"""Minimal product graph models.

These models describe accepted graph facts. They intentionally do not replace
the root ``models.py`` classifier-output models used by the live pipeline.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


SprocketKind = Literal[
    "area",
    "goal",
    "project",
    "task",
    "contact",
    "organization",
    "place",
    "reference",
]
CogKind = Literal["action", "setting", "appointment"]
CogHorizon = Literal["year", "month", "5wow", "week", "day", "carry"]
BridgeRole = Literal["primary", "setting", "participant", "subject", "reference"]


class GraphModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def strip_text_fields(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class Sprocket(GraphModel):
    """Durable non-time-first product graph vertex."""

    id: str
    kind: SprocketKind
    text: str

    @field_validator("id", "text")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        if not value:
            raise ValueError("field cannot be empty")
        return value


class CogLocator(GraphModel):
    """Current rendered location for close, drop, or carry actions."""

    horizon: CogHorizon
    period: str
    path: str
    marker: str = ""
    revision: str = ""

    @field_validator("period", "path")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        if not value:
            raise ValueError("field cannot be empty")
        return value


class Cog(GraphModel):
    """Durable time-oriented product graph vertex."""

    id: str
    kind: CogKind
    text: str
    current_locator: CogLocator | None = None

    @field_validator("id", "text")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        if not value:
            raise ValueError("field cannot be empty")
        return value


class SprocketHierarchyEdge(GraphModel):
    """Structural Sprocket-to-Sprocket hierarchy edge."""

    parent_id: str
    child_id: str
    family: Literal["sprocket_hierarchy"] = "sprocket_hierarchy"

    @property
    def edge_key(self) -> str:
        return f"{self.parent_id}:{self.family}:{self.child_id}"

    @field_validator("parent_id", "child_id")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        if not value:
            raise ValueError("field cannot be empty")
        return value


class SprocketCogBridgeEdge(GraphModel):
    """Structural Sprocket-Cog bridge edge."""

    cog_id: str
    sprocket_id: str
    role: BridgeRole
    family: Literal["sprocket_cog_bridge"] = "sprocket_cog_bridge"

    @property
    def edge_key(self) -> str:
        return f"{self.cog_id}:{self.family}:{self.role}:{self.sprocket_id}"

    @field_validator("cog_id", "sprocket_id")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        if not value:
            raise ValueError("field cannot be empty")
        return value

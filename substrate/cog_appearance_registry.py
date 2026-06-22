"""Machine-readable registry for Cogs rendered on vault surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CogAppearanceSurface = Literal["day", "week", "month", "5wow", "forward12"]
CogAppearanceState = Literal["open", "done", "carried", "dropped", "review"]

REGISTRY_RELATIVE_PATH = Path(".graph") / "cog-appearances.json"


class CogAppearance(BaseModel):
    """One rendered vault footprint of one durable Cog."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cog_id: str
    surface: CogAppearanceSurface
    period: str
    path: str
    marker: str = "[ ]"
    state: CogAppearanceState = "open"

    @property
    def appearance_key(self) -> str:
        return f"{self.cog_id}:{self.surface}:{self.period}:{self.path}"

    @field_validator("cog_id", "period", "path", "marker")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field cannot be empty")
        return value


class CogAppearanceRegistry(BaseModel):
    """Versioned sidecar state for Cogs appearances."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    appearances: list[CogAppearance] = Field(default_factory=list)

    def upsert(self, appearance: CogAppearance) -> None:
        key = appearance.appearance_key
        self.appearances = [item for item in self.appearances if item.appearance_key != key]
        self.appearances.append(appearance)
        self.appearances.sort(key=lambda item: item.appearance_key)

    def by_cog(self, cog_id: str) -> list[CogAppearance]:
        return [item for item in self.appearances if item.cog_id == cog_id]

    def by_path(self, path: str) -> list[CogAppearance]:
        return [item for item in self.appearances if item.path == path]


def registry_path(vault_dir: Path) -> Path:
    """Return the hidden registry path for a vault."""

    return vault_dir / REGISTRY_RELATIVE_PATH


def load_registry(vault_dir: Path) -> CogAppearanceRegistry:
    """Load the appearance registry, returning an empty registry if absent."""

    path = registry_path(vault_dir)
    if not path.exists():
        return CogAppearanceRegistry()
    return CogAppearanceRegistry.model_validate_json(path.read_text(encoding="utf-8"))


def save_registry(vault_dir: Path, registry: CogAppearanceRegistry) -> Path:
    """Persist the appearance registry as stable, pretty JSON."""

    path = registry_path(vault_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = registry.model_dump(mode="json")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path

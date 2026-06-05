"""Mutation command scaffold for product graph changes."""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator


MutationOperation = Literal[
    "create_cog",
    "create_sprocket_and_bridge",
    "add_bridge",
    "carry_cog",
    "close_cog",
    "drop_cog",
    "write_render_marker",
]
MutationLayer = Literal["product_graph", "render"]
ReviewClass = Literal["automatic", "review_first", "never_direct"]


class MutationCommand(BaseModel):
    """Shared command shape for automatic and reviewed mutation paths."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    operation: MutationOperation
    target_layer: MutationLayer
    review_class: ReviewClass
    payload: dict[str, Any]
    expected_current_state: dict[str, Any] | None = None

    @field_validator("id")
    @classmethod
    def require_nonempty_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("id cannot be empty")
        return value

    @field_validator("payload")
    @classmethod
    def require_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("payload cannot be empty")
        return value

    def packet_json(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude_none=True), sort_keys=True)

    def packet_word_count(self) -> int:
        return len(self.packet_json().split())


def command_from_proposal_fixture(proposal_data: dict[str, Any]) -> MutationCommand:
    return MutationCommand.model_validate(proposal_data["proposal"]["mutation_command"])

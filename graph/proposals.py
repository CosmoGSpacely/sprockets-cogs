"""Proposal and audit layer models."""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from graph.mutations import MutationCommand


DecisionOutcome = Literal[
    "applied_automatic",
    "accepted",
    "rejected",
    "edited",
    "skipped",
]
Decider = Literal["substrate", "user", "jane", "rudi"]


class ReviewProposal(BaseModel):
    """Review-layer wrapper around a mutation command."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: Literal["review_proposal"] = "review_proposal"
    reason: str
    display_text: str
    mutation_command: MutationCommand
    source: dict[str, Any] | None = None
    confidence: float | None = None

    @field_validator("id", "reason", "display_text")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field cannot be empty")
        return value

    def packet_json(self) -> str:
        return json.dumps(self.model_dump(mode="json", exclude_none=True), sort_keys=True)

    def packet_word_count(self) -> int:
        return len(self.packet_json().split())


class AuditDecision(BaseModel):
    """Append-only decision evidence for automatic or reviewed mutations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: Literal["audit_decision"] = "audit_decision"
    mutation_id: str
    decision: DecisionOutcome
    decider: Decider
    reason: str
    timestamp: str
    proposal_id: str | None = None
    edits: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("id", "mutation_id", "reason", "timestamp")
    @classmethod
    def require_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field cannot be empty")
        return value


def proposal_from_fixture(fixture_data: dict[str, Any]) -> ReviewProposal:
    return ReviewProposal.model_validate(fixture_data["proposal"])


def audit_decisions_from_fixture(fixture_data: dict[str, Any]) -> list[AuditDecision]:
    return [AuditDecision.model_validate(item) for item in fixture_data["audit"]]

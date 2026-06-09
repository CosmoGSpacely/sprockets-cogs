"""Preview input intent models for Phase 8.5.

These models are substrate data, not routing logic or write authority.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, field
from enum import Enum
from typing import Any


class StringEnum(str, Enum):
    pass


class IntentClass(StringEnum):
    ORDINARY_CAPTURE = "ordinary_capture"
    STRUCTURAL_PROPOSAL = "structural_proposal"
    PLANNING_UPDATE = "planning_update"
    GRAPH_PROJECTION = "graph_projection"
    RICH_SOURCE_INGESTION = "rich_source_ingestion"
    REVIEW_DECISION = "review_decision"
    OPERATIONAL_COMMAND = "operational_command"


class SourceType(StringEnum):
    TEXT = "text"
    TELEGRAM = "telegram"
    CLI = "cli"
    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"
    SCREENSHOT = "screenshot"
    SCAN = "scan"
    FALLBACK_CLOUD = "fallback_cloud"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class SourceAuthority(StringEnum):
    USER = "user"
    LOCAL_MODEL = "local_model"
    FALLBACK_MODEL = "fallback_model"
    SYSTEM = "system"
    TEST = "test"
    UNKNOWN = "unknown"


class Confidence(StringEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCERTAIN = "uncertain"


class ContextScope(StringEnum):
    STABLE_DOCTRINE = "stable_doctrine"
    VOLATILE_RUNTIME = "volatile_runtime"
    VOLATILE_SOURCE = "volatile_source"
    FIXTURE = "fixture"


class RequiredGuard(StringEnum):
    NONE = "none"
    DETERMINISTIC_PACKET_REQUIRED = "deterministic_packet_required"
    RESOURCE_FIRST_REVIEW = "resource_first_review"
    TIME_ADAPTER_REQUIRED = "time_adapter_required"
    ALLOWLISTED_READ_ONLY_OPERATION = "allowlisted_read_only_operation"
    VALIDATED_ORDINARY_WRITE = "validated_ordinary_write"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SuggestedRoute(StringEnum):
    NONE = "none"
    ROSIE = "rosie"
    RUDI = "rudi"
    JANE = "jane"
    COGSWELL = "cogswell"
    UNIBLAB = "uniblab"
    COGS = "cogs"
    SPROCKETS = "sprockets"
    VALIDATORS = "validators"
    AUDIT = "audit"


def clean_text(value: str, name: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{name} cannot be empty")
    return value


def clean_items(values: tuple[str, ...] | list[str], name: str) -> tuple[str, ...]:
    cleaned = tuple(item.strip() for item in values)
    if any(not item for item in cleaned):
        raise ValueError(f"{name} cannot contain empty values")
    return cleaned


def strip_attrs(instance: Any, names: tuple[str, ...]) -> None:
    for name in names:
        object.__setattr__(instance, name, getattr(instance, name).strip())


def json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, tuple):
        return [json_value(item) for item in value]
    if isinstance(value, list):
        return [json_value(item) for item in value]
    return value


class JsonDataclass:
    def to_dict(self) -> dict[str, Any]:
        return json_value(self)


@dataclass(frozen=True)
class RuntimeTimeContext(JsonDataclass):
    local_date: str
    timezone: str
    local_time: str = ""
    generated_at: str = ""
    scope: ContextScope = ContextScope.VOLATILE_RUNTIME
    freshness: str = "fresh_per_input"

    def __post_init__(self) -> None:
        object.__setattr__(self, "local_date", clean_text(self.local_date, "local_date"))
        object.__setattr__(self, "timezone", clean_text(self.timezone, "timezone"))
        strip_attrs(self, ("local_time", "generated_at"))
        object.__setattr__(self, "freshness", clean_text(self.freshness, "freshness"))

@dataclass(frozen=True)
class SourceMetadata(JsonDataclass):
    source_type: SourceType
    source_authority: SourceAuthority
    locator: str = ""
    adapter: str = ""
    confidence: Confidence = Confidence.UNCERTAIN
    provider: str = ""
    model: str = ""
    provenance: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        strip_attrs(self, ("locator", "adapter", "provider", "model"))
        object.__setattr__(self, "provenance", clean_items(self.provenance, "provenance"))

@dataclass(frozen=True)
class AuthorityAssessment(JsonDataclass):
    detected_authority_risks: tuple[str, ...] = field(default_factory=tuple)
    model_authority_violation: bool = False
    required_guard: RequiredGuard = RequiredGuard.NONE
    packet_required_suggestion: bool = False

    def __post_init__(self) -> None:
        risks = clean_items(self.detected_authority_risks, "detected_authority_risks")
        object.__setattr__(self, "detected_authority_risks", risks)

@dataclass(frozen=True)
class NormalizedInput(JsonDataclass):
    input_id: str
    raw_text: str
    normalized_text: str
    source: SourceMetadata
    runtime_time: RuntimeTimeContext
    context_scope: ContextScope = ContextScope.VOLATILE_SOURCE
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_id", clean_text(self.input_id, "input_id"))
        object.__setattr__(self, "raw_text", clean_text(self.raw_text, "raw_text"))
        object.__setattr__(self, "normalized_text", clean_text(self.normalized_text, "normalized_text"))
        object.__setattr__(self, "notes", clean_items(self.notes, "notes"))

@dataclass(frozen=True)
class IntentClassification(JsonDataclass):
    intent_class: IntentClass
    confidence: Confidence
    authority: AuthorityAssessment
    evidence: tuple[str, ...] = field(default_factory=tuple)
    uncertainty: tuple[str, ...] = field(default_factory=tuple)
    suggested_route: tuple[SuggestedRoute, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", clean_items(self.evidence, "evidence"))
        object.__setattr__(self, "uncertainty", clean_items(self.uncertainty, "uncertainty"))

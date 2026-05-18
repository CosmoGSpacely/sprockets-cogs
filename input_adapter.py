"""Pure helpers for turning external inputs into Rosie `.input` files."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping

import frontmatter

from slug_utils import slugify


ADAPTER_CONTRACT_VERSION = "stage-53"
DEFAULT_MODALITY = "text"


@dataclass(frozen=True)
class InputAttachment:
    """Metadata for an external attachment referenced by an input adapter."""

    name: str
    media_type: str = ""
    path: str = ""
    url: str = ""
    text_excerpt: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("attachment name cannot be empty")
        if not any((self.path, self.url, self.text_excerpt)):
            raise ValueError("attachment must include path, url, or text_excerpt")

    def to_frontmatter(self) -> dict[str, str]:
        """Return a YAML-safe attachment mapping without empty fields."""

        values = {
            "name": self.name,
            "media_type": self.media_type,
            "path": self.path,
            "url": self.url,
            "text_excerpt": self.text_excerpt,
        }
        return {key: value for key, value in values.items() if value}


@dataclass(frozen=True)
class InputEnvelope:
    """Normalized external input before it is written as a `.input` file."""

    content: str
    source: str
    session_id: str = ""
    modality: str = DEFAULT_MODALITY
    source_id: str = ""
    idempotency_key: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    attachments: tuple[InputAttachment, ...] = ()

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("content cannot be empty")
        if not self.source.strip():
            raise ValueError("source cannot be empty")
        if not self.modality.strip():
            raise ValueError("modality cannot be empty")
        for key in self.metadata:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("metadata keys must be non-empty strings")


def stable_content_hash(content: str, length: int = 12) -> str:
    """Return a short stable hash for adapter filenames and idempotency."""

    normalized = content.strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:length]


def stable_input_key(envelope: InputEnvelope) -> str:
    """Return the stable identity component for an input envelope."""

    for value in (
        envelope.idempotency_key,
        envelope.source_id,
        envelope.session_id,
    ):
        if value.strip():
            return value.strip()
    return stable_content_hash(envelope.content)


def input_session_id(envelope: InputEnvelope) -> str:
    """Return the session id Rosie should see for this envelope."""

    if envelope.session_id.strip():
        return envelope.session_id.strip()
    return f"{slugify(envelope.source, max_length=24)}-{stable_content_hash(envelope.content)}"


def input_filename(envelope: InputEnvelope) -> str:
    """Return a deterministic `.input` filename for an envelope."""

    source = slugify(envelope.source, max_length=24) or "input"
    identity = slugify(stable_input_key(envelope), max_length=48) or stable_content_hash(
        envelope.content
    )
    return f"{source}-{identity}.input"


def input_frontmatter(envelope: InputEnvelope) -> dict[str, Any]:
    """Return frontmatter for an adapter-produced `.input` file."""

    values: dict[str, Any] = {
        "adapter_contract": ADAPTER_CONTRACT_VERSION,
        "source": envelope.source,
        "session_id": input_session_id(envelope),
        "modality": envelope.modality,
    }
    if envelope.source_id:
        values["source_id"] = envelope.source_id
    if envelope.idempotency_key:
        values["idempotency_key"] = envelope.idempotency_key
    if envelope.metadata:
        values["metadata"] = dict(envelope.metadata)
    if envelope.attachments:
        values["attachments"] = [
            attachment.to_frontmatter()
            for attachment in envelope.attachments
        ]
    return values


def render_input_file(envelope: InputEnvelope) -> str:
    """Render an envelope as the complete `.input` file content."""

    content = envelope.content.strip() + "\n"
    post = frontmatter.Post(content, **input_frontmatter(envelope))
    return frontmatter.dumps(post)


def preview_input_file(envelope: InputEnvelope) -> str:
    """Return a human-readable read-only preview of the adapter output."""

    rendered = render_input_file(envelope)
    return "\n".join(
        [
            "Input adapter preview",
            "- writes: no",
            f"- filename: {input_filename(envelope)}",
            f"- source: {envelope.source}",
            f"- session_id: {input_session_id(envelope)}",
            f"- modality: {envelope.modality}",
            "",
            rendered,
        ]
    )

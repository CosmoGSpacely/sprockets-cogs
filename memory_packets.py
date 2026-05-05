"""Read-only summarized memory packets for high-value vault nodes."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from retrieval_nodes import load_retrieval_nodes
from retrieval_strategies import node_slug, node_type_priority
from retrieval_types import RetrievalNode


DEFAULT_PACKET_NODE_TYPES = (
    "sprockets/area",
    "sprockets/goal",
    "sprockets/project",
)


@dataclass(frozen=True)
class MemoryPacket:
    """A compact, deterministic summary packet for one retrieval node."""

    node_id: str
    title: str
    node_type: str
    path: Path
    parent_slugs: tuple[str, ...]
    child_ids: tuple[str, ...]
    child_titles: tuple[str, ...]
    child_type_counts: tuple[tuple[str, int], ...]
    excerpt: str

    @property
    def packet_text(self) -> str:
        """Return compact text suitable for preview, embedding, or future prompts."""

        lines = [
            f"{self.title} [{self.node_type}]",
            f"id: {self.node_id}",
        ]
        if self.parent_slugs:
            lines.append(f"parents: {', '.join(self.parent_slugs)}")
        if self.child_type_counts:
            counts = ", ".join(
                f"{node_type}={count}" for node_type, count in self.child_type_counts
            )
            lines.append(f"children: {counts}")
        if self.child_titles:
            lines.append(f"child highlights: {'; '.join(self.child_titles)}")
        if self.excerpt:
            lines.append(f"excerpt: {self.excerpt}")
        return "\n".join(lines)


def build_memory_packets(
    nodes: Iterable[RetrievalNode],
    node_types: tuple[str, ...] = DEFAULT_PACKET_NODE_TYPES,
    child_limit: int = 8,
    excerpt_chars: int = 280,
) -> tuple[MemoryPacket, ...]:
    """Build deterministic summary packets from retrieval nodes without writing."""

    node_tuple = tuple(nodes)
    child_lookup = _children_by_parent_slug(node_tuple)
    packets = [
        memory_packet_for_node(
            node,
            child_lookup.get(node_slug(node), ()),
            child_limit=child_limit,
            excerpt_chars=excerpt_chars,
        )
        for node in node_tuple
        if node.node_type in node_types
    ]
    return tuple(sorted(packets, key=lambda packet: packet.node_id))


def memory_packet_for_node(
    node: RetrievalNode,
    children: Iterable[RetrievalNode] = (),
    child_limit: int = 8,
    excerpt_chars: int = 280,
) -> MemoryPacket:
    """Build one deterministic memory packet for a retrieval node."""

    child_tuple = tuple(
        sorted(children, key=lambda item: (node_type_priority(item), item.title.lower(), item.node_id))
    )
    child_counts = Counter(child.node_type for child in child_tuple)
    limited_children = child_tuple[:max(child_limit, 0)]
    return MemoryPacket(
        node_id=node.node_id,
        title=node.title,
        node_type=node.node_type,
        path=node.path,
        parent_slugs=node.parent_slugs,
        child_ids=tuple(child.node_id for child in limited_children),
        child_titles=tuple(child.title for child in limited_children),
        child_type_counts=tuple(sorted(child_counts.items())),
        excerpt=_compact_excerpt(node.text, excerpt_chars),
    )


def load_memory_packets(
    vault_dir: Path,
    node_types: tuple[str, ...] = DEFAULT_PACKET_NODE_TYPES,
    child_limit: int = 8,
    excerpt_chars: int = 280,
) -> tuple[MemoryPacket, ...]:
    """Load retrieval nodes from the vault and build read-only memory packets."""

    return build_memory_packets(
        load_retrieval_nodes(vault_dir),
        node_types=node_types,
        child_limit=child_limit,
        excerpt_chars=excerpt_chars,
    )


def format_memory_packet(packet: MemoryPacket) -> str:
    """Format one packet for terminal preview."""

    lines = [
        f"{packet.node_id} [{packet.node_type}] {packet.title}",
        f"- path: {packet.path}",
    ]
    if packet.parent_slugs:
        lines.append(f"- parents: {', '.join(packet.parent_slugs)}")
    if packet.child_type_counts:
        counts = ", ".join(
            f"{node_type}={count}" for node_type, count in packet.child_type_counts
        )
        lines.append(f"- child counts: {counts}")
    if packet.child_titles:
        lines.append("- child highlights:")
        lines.extend(f"  - {title}" for title in packet.child_titles)
    if packet.excerpt:
        lines.append(f"- excerpt: {packet.excerpt}")
    lines.append("- writes: none")
    return "\n".join(lines)


def format_memory_packet_inventory(packets: Iterable[MemoryPacket]) -> str:
    """Format a compact packet inventory for terminal preview."""

    packet_tuple = tuple(packets)
    lines = [
        "Sprockets-Cogs memory packets",
        f"- packets: {len(packet_tuple)}",
    ]
    counts = Counter(packet.node_type for packet in packet_tuple)
    if counts:
        lines.append(
            "- node types: "
            + ", ".join(f"{node_type}={count}" for node_type, count in sorted(counts.items()))
        )
    for packet in packet_tuple:
        lines.append(f"- {packet.node_id} [{packet.node_type}] {packet.title}")
    lines.append("- writes: none")
    return "\n".join(lines)


def _children_by_parent_slug(
    nodes: Iterable[RetrievalNode],
) -> dict[str, tuple[RetrievalNode, ...]]:
    children: dict[str, list[RetrievalNode]] = {}
    for node in nodes:
        for parent_slug in node.parent_slugs:
            children.setdefault(parent_slug, []).append(node)
    return {parent_slug: tuple(items) for parent_slug, items in children.items()}


def _compact_excerpt(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if limit < 1 or not normalized:
        return ""
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(limit - 3, 0)].rstrip() + "..."

"""Read-only CLI for Stage 22 summarized memory packets."""
from __future__ import annotations

import argparse
from pathlib import Path

from memory_packets import (
    DEFAULT_PACKET_NODE_TYPES,
    format_memory_packet,
    format_memory_packet_inventory,
    load_memory_packets,
)


DEFAULT_VAULT_DIR = Path("/home/cosmo/vault")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview deterministic memory packets without writing.",
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=DEFAULT_VAULT_DIR,
        help="Vault directory. Defaults to /home/cosmo/vault.",
    )
    parser.add_argument(
        "--node-type",
        action="append",
        choices=DEFAULT_PACKET_NODE_TYPES,
        help="Limit packets to a node type. Can be repeated.",
    )
    parser.add_argument(
        "--node-id",
        help="Show one packet by node ID.",
    )
    parser.add_argument(
        "--child-limit",
        type=int,
        default=8,
        help="Maximum child highlights to include per packet.",
    )
    parser.add_argument(
        "--excerpt-chars",
        type=int,
        default=280,
        help="Maximum source excerpt characters per packet.",
    )
    args = parser.parse_args()

    node_types = tuple(args.node_type) if args.node_type else DEFAULT_PACKET_NODE_TYPES
    packets = load_memory_packets(
        args.vault,
        node_types=node_types,
        child_limit=args.child_limit,
        excerpt_chars=args.excerpt_chars,
    )
    if args.node_id:
        packet = next((item for item in packets if item.node_id == args.node_id), None)
        if packet is None:
            raise SystemExit(f"memory packet not found: {args.node_id}")
        print(format_memory_packet(packet))
        return

    print(format_memory_packet_inventory(packets))


if __name__ == "__main__":
    main()

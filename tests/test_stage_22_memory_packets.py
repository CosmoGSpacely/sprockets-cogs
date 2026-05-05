import unittest
from pathlib import Path

from memory_packets import (
    build_memory_packets,
    format_memory_packet,
    format_memory_packet_inventory,
    memory_packet_for_node,
)
from retrieval_types import RetrievalNode


class Stage22MemoryPacketTests(unittest.TestCase):
    def test_build_memory_packets_summarizes_hierarchy_node_children(self):
        goal = RetrievalNode(
            node_id="goals/build-sprockets-cogs",
            title="Build Sprockets-Cogs",
            node_type="sprockets/goal",
            path=Path("goals/build-sprockets-cogs.md"),
            parent_slugs=("learn-agentic-ai",),
            text="Build the local-first personal operating system.",
        )
        project = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("projects/phase-3-memory-enhancement.md"),
            parent_slugs=("build-sprockets-cogs",),
            text="Improve retrieval and memory behavior.",
        )
        task = RetrievalNode(
            node_id="tasks/add-memory-packets",
            title="Add memory packets",
            node_type="sprockets/task",
            path=Path("tasks/add-memory-packets.md"),
            parent_slugs=("phase-3-memory-enhancement",),
        )

        packets = build_memory_packets((goal, project, task))
        by_id = {packet.node_id: packet for packet in packets}

        self.assertEqual(
            by_id["goals/build-sprockets-cogs"].child_ids,
            ("projects/phase-3-memory-enhancement",),
        )
        self.assertEqual(
            by_id["projects/phase-3-memory-enhancement"].child_ids,
            ("tasks/add-memory-packets",),
        )
        self.assertNotIn("tasks/add-memory-packets", by_id)

    def test_memory_packet_bounds_child_highlights_and_excerpt(self):
        project = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("projects/phase-3-memory-enhancement.md"),
            text="This is a deliberately long project note body for packet preview.",
        )
        children = (
            RetrievalNode(
                node_id="tasks/write-traces",
                title="Write traces",
                node_type="sprockets/task",
                path=Path("tasks/write-traces.md"),
            ),
            RetrievalNode(
                node_id="notes/memory-lessons",
                title="Memory lessons",
                node_type="sprockets/note",
                path=Path("notes/memory-lessons.md"),
            ),
        )

        packet = memory_packet_for_node(
            project,
            children,
            child_limit=1,
            excerpt_chars=18,
        )

        self.assertEqual(len(packet.child_titles), 1)
        self.assertEqual(packet.child_type_counts, (("sprockets/note", 1), ("sprockets/task", 1)))
        self.assertEqual(packet.excerpt, "This is a delib...")

    def test_format_memory_packet_inventory_is_read_only(self):
        packet = memory_packet_for_node(
            RetrievalNode(
                node_id="areas/learn-agentic-ai",
                title="Learn Agentic AI",
                node_type="sprockets/area",
                path=Path("areas/learn-agentic-ai.md"),
            )
        )

        inventory = format_memory_packet_inventory((packet,))
        detail = format_memory_packet(packet)

        self.assertIn("- packets: 1", inventory)
        self.assertIn("areas/learn-agentic-ai", inventory)
        self.assertIn("- writes: none", inventory)
        self.assertIn("- path: areas/learn-agentic-ai.md", detail)
        self.assertIn("- writes: none", detail)


if __name__ == "__main__":
    unittest.main()

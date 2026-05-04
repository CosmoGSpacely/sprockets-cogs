import unittest
from pathlib import Path

from memory_index import (
    MemoryNodeMetadata,
    MemoryQuery,
    MemoryRecord,
    RetrievalTrace,
    ScoredMemoryResult,
    VectorMetadata,
    should_reindex,
    vector_metadata_for,
)


class Stage17MemoryIndexTests(unittest.TestCase):
    def test_memory_node_metadata_captures_stable_node_identity(self):
        metadata = MemoryNodeMetadata(
            node_id="projects/phase-3-memory-enhancement",
            path=Path("Sprockets/projects/phase-3-memory-enhancement.md"),
            node_type="sprockets/project",
            title="Phase 3 - Memory Enhancement",
            parent_slugs=("build-sprockets-cogs",),
            source_mtime=1777741200.0,
            text_hash="abc123",
        )

        self.assertEqual(metadata.node_id, "projects/phase-3-memory-enhancement")
        self.assertEqual(metadata.parent_slugs, ("build-sprockets-cogs",))
        self.assertEqual(metadata.text_hash, "abc123")

    def test_memory_record_exposes_node_id_from_metadata(self):
        record = MemoryRecord(
            metadata=MemoryNodeMetadata(
                node_id="contacts/tom-reilly",
                path=Path("Sprockets/contacts/tom-reilly.md"),
                node_type="sprockets/contact",
                title="Tom Reilly",
            )
        )

        self.assertEqual(record.node_id, "contacts/tom-reilly")

    def test_vector_metadata_for_records_dimension_model_and_hash(self):
        metadata = vector_metadata_for("nomic-embed-text", "hash-1", [0.1, 0.2, 0.3])

        self.assertEqual(
            metadata,
            VectorMetadata(
                model="nomic-embed-text",
                dimension=3,
                text_hash="hash-1",
            ),
        )

    def test_should_reindex_new_or_unembedded_records(self):
        bare_record = MemoryRecord(
            metadata=MemoryNodeMetadata(
                node_id="notes/memory",
                path=Path("notes/memory.md"),
                node_type="sprockets/note",
                title="Memory",
            )
        )

        self.assertTrue(should_reindex(None, "nomic-embed-text", "hash-1"))
        self.assertTrue(should_reindex(bare_record, "nomic-embed-text", "hash-1"))

    def test_should_reindex_when_model_text_or_dimension_changes(self):
        record = MemoryRecord(
            metadata=MemoryNodeMetadata(
                node_id="notes/memory",
                path=Path("notes/memory.md"),
                node_type="sprockets/note",
                title="Memory",
                text_hash="hash-1",
            ),
            vector=(0.1, 0.2),
            vector_metadata=VectorMetadata(
                model="nomic-embed-text",
                dimension=2,
                text_hash="hash-1",
            ),
        )

        self.assertFalse(should_reindex(record, "nomic-embed-text", "hash-1"))
        self.assertTrue(should_reindex(record, "other-model", "hash-1"))
        self.assertTrue(should_reindex(record, "nomic-embed-text", "hash-2"))

        inconsistent_record = MemoryRecord(
            metadata=record.metadata,
            vector=(0.1,),
            vector_metadata=record.vector_metadata,
        )
        self.assertTrue(should_reindex(inconsistent_record, "nomic-embed-text", "hash-1"))

    def test_query_and_trace_hold_filters_and_ranked_results(self):
        query = MemoryQuery(
            text="Call Tom at GlobalTech",
            limit=3,
            node_types=("sprockets/contact", "sprockets/entity"),
            parent_slugs=("build-sprockets-cogs",),
        )
        record = MemoryRecord(
            metadata=MemoryNodeMetadata(
                node_id="contacts/tom-reilly",
                path=Path("contacts/tom-reilly.md"),
                node_type="sprockets/contact",
                title="Tom Reilly",
            )
        )
        result = ScoredMemoryResult(record=record, score=0.84, reasons=("name match",))
        trace = RetrievalTrace(
            query=query,
            retriever_name="test-memory-index",
            result_ids=(result.node_id,),
            filters_applied={"node_types": query.node_types},
            notes=("graph expansion skipped",),
        )

        self.assertEqual(query.limit, 3)
        self.assertEqual(result.node_id, "contacts/tom-reilly")
        self.assertEqual(result.reasons, ("name match",))
        self.assertEqual(trace.result_ids, ("contacts/tom-reilly",))
        self.assertEqual(trace.filters_applied["node_types"], query.node_types)


if __name__ == "__main__":
    unittest.main()

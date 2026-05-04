import unittest
from pathlib import Path

from memory_index import (
    InMemoryMemoryIndex,
    MemoryNodeMetadata,
    MemoryQuery,
    MemoryRecord,
    RetrievalTrace,
    ScoredMemoryResult,
    VectorMetadata,
    memory_record_from_retrieval_node,
    should_reindex,
    vector_metadata_for,
)
from retrieval_eval import RetrievalNode


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

    def test_memory_record_from_retrieval_node_preserves_index_metadata(self):
        node = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("Sprockets/projects/phase-3-memory-enhancement.md"),
            parent_slugs=("build-sprockets-cogs",),
            text="Evaluate retrieval quality before wiring production memory.",
        )

        record = memory_record_from_retrieval_node(node, source_mtime=1777741200.0)

        self.assertEqual(record.node_id, "projects/phase-3-memory-enhancement")
        self.assertEqual(
            record.metadata.path,
            Path("Sprockets/projects/phase-3-memory-enhancement.md"),
        )
        self.assertEqual(record.metadata.node_type, "sprockets/project")
        self.assertEqual(record.metadata.title, "Phase 3 - Memory Enhancement")
        self.assertEqual(record.metadata.parent_slugs, ("build-sprockets-cogs",))
        self.assertEqual(record.metadata.source_mtime, 1777741200.0)
        self.assertEqual(len(record.metadata.text_hash), 64)
        self.assertIsNone(record.vector)
        self.assertIsNone(record.vector_metadata)

    def test_memory_record_from_retrieval_node_reads_source_mtime_when_available(self):
        path = Path(__file__)
        node = RetrievalNode(
            node_id="notes/test-stage-17",
            title="Test Stage 17",
            node_type="sprockets/note",
            path=path,
        )

        record = memory_record_from_retrieval_node(node)

        self.assertEqual(record.metadata.source_mtime, path.stat().st_mtime)

    def test_in_memory_index_upserts_and_gets_records(self):
        index = InMemoryMemoryIndex()
        first = MemoryRecord(
            metadata=MemoryNodeMetadata(
                node_id="projects/phase-3-memory-enhancement",
                path=Path("projects/phase-3-memory-enhancement.md"),
                node_type="sprockets/project",
                title="Phase 3 - Memory Enhancement",
            )
        )
        replacement = MemoryRecord(
            metadata=MemoryNodeMetadata(
                node_id="projects/phase-3-memory-enhancement",
                path=Path("projects/phase-3-memory-enhancement.md"),
                node_type="sprockets/project",
                title="Phase 3 - Memory Index",
            )
        )

        index.upsert_nodes([first])
        index.upsert_nodes([replacement])

        self.assertEqual(index.get(first.node_id), replacement)

    def test_in_memory_index_deletes_records_missing_from_active_ids(self):
        keep = MemoryRecord(
            metadata=MemoryNodeMetadata(
                node_id="contacts/tom-reilly",
                path=Path("contacts/tom-reilly.md"),
                node_type="sprockets/contact",
                title="Tom Reilly",
            )
        )
        delete = MemoryRecord(
            metadata=MemoryNodeMetadata(
                node_id="contacts/sandra-cho",
                path=Path("contacts/sandra-cho.md"),
                node_type="sprockets/contact",
                title="Sandra Cho",
            )
        )
        index = InMemoryMemoryIndex([delete, keep])

        deleted = index.delete_missing_node_ids(["contacts/tom-reilly"])

        self.assertEqual(deleted, ("contacts/sandra-cho",))
        self.assertEqual(index.get("contacts/tom-reilly"), keep)
        self.assertIsNone(index.get("contacts/sandra-cho"))

    def test_in_memory_index_query_scores_and_filters_records(self):
        project = MemoryRecord(
            metadata=MemoryNodeMetadata(
                node_id="projects/phase-3-memory-enhancement",
                path=Path("projects/phase-3-memory-enhancement.md"),
                node_type="sprockets/project",
                title="Phase 3 - Memory Enhancement",
                parent_slugs=("build-sprockets-cogs",),
            )
        )
        note = MemoryRecord(
            metadata=MemoryNodeMetadata(
                node_id="notes/memory-index",
                path=Path("notes/memory-index.md"),
                node_type="sprockets/note",
                title="Memory Index Notes",
                parent_slugs=("build-sprockets-cogs",),
            )
        )
        contact = MemoryRecord(
            metadata=MemoryNodeMetadata(
                node_id="contacts/tom-reilly",
                path=Path("contacts/tom-reilly.md"),
                node_type="sprockets/contact",
                title="Tom Reilly",
            )
        )
        index = InMemoryMemoryIndex([contact, note, project])

        results = index.query(
            MemoryQuery(
                text="memory enhancement",
                limit=2,
                node_types=("sprockets/project", "sprockets/note"),
                parent_slugs=("build-sprockets-cogs",),
            )
        )

        self.assertEqual(
            [result.node_id for result in results],
            [
                "projects/phase-3-memory-enhancement",
                "notes/memory-index",
            ],
        )
        self.assertEqual(results[0].reasons, ("title", "node_id"))

    def test_in_memory_index_query_returns_empty_for_non_positive_limit(self):
        index = InMemoryMemoryIndex([
            MemoryRecord(
                metadata=MemoryNodeMetadata(
                    node_id="notes/memory",
                    path=Path("notes/memory.md"),
                    node_type="sprockets/note",
                    title="Memory",
                )
            )
        ])

        self.assertEqual(index.query(MemoryQuery(text="memory", limit=0)), ())


if __name__ == "__main__":
    unittest.main()

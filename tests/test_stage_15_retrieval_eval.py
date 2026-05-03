import tempfile
import unittest
from pathlib import Path

import agentic_loop
from retrieval_eval import (
    RetrievalCase,
    RetrievalNode,
    evaluate_retriever,
    lexical_retrieve,
    load_retrieval_nodes,
    stage_15_cases,
    stage_15_fixture_nodes,
)


def write_node(vault: Path, folder: str, slug: str, metadata: str = "", body: str = "") -> Path:
    path = vault / "Sprockets" / folder / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{metadata}---\n\n{body}\n")
    return path


class Stage15RetrievalEvalTests(unittest.TestCase):
    def test_evaluate_retriever_passes_when_expected_ids_are_returned(self):
        case = RetrievalCase(
            name="contact",
            query="Ask Jordan about the proposal.",
            expected_ids=frozenset({"contacts/jordan-mack"}),
            avoid_ids=frozenset({"contacts/jordan-lee"}),
        )

        result = evaluate_retriever([case], lambda _query: ["contacts/jordan-mack"])

        self.assertTrue(result.passed)
        self.assertEqual(result.passed_count, 1)
        self.assertEqual(result.total_count, 1)
        self.assertEqual(result.results[0].retrieved_ids, ("contacts/jordan-mack",))

    def test_evaluate_retriever_flags_missing_and_forbidden_ids(self):
        case = RetrievalCase(
            name="ambiguous-contact",
            query="Ask Jordan about the proposal.",
            expected_ids=frozenset({"contacts/jordan-mack"}),
            avoid_ids=frozenset({"contacts/jordan-lee"}),
        )

        result = evaluate_retriever([case], lambda _query: ["contacts/jordan-lee"])

        self.assertFalse(result.passed)
        self.assertEqual(result.results[0].missing_ids, frozenset({"contacts/jordan-mack"}))
        self.assertEqual(result.results[0].forbidden_ids, frozenset({"contacts/jordan-lee"}))

    def test_evaluate_retriever_accepts_retrieval_nodes_and_deduplicates_ids(self):
        case = RetrievalCase(
            name="node-object",
            query="Find Phase 3.",
            expected_ids=frozenset({"projects/phase-3-memory-enhancement"}),
        )
        node = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("phase-3-memory-enhancement.md"),
        )

        result = evaluate_retriever([case], lambda _query: [node, node])

        self.assertTrue(result.passed)
        self.assertEqual(result.results[0].retrieved_ids, ("projects/phase-3-memory-enhancement",))

    def test_stage_15_cases_cover_required_memory_risks(self):
        cases = stage_15_cases()
        categories = {case.category for case in cases}

        self.assertGreaterEqual(len(cases), 6)
        self.assertTrue(
            {
                "named_entity",
                "project_scope",
                "hierarchy",
                "recent_cogs",
                "semantic_gap",
                "staleness",
                "contamination",
            }.issubset(categories)
        )
        self.assertTrue(all(case.expected_ids for case in cases))
        self.assertTrue(any(case.avoid_ids for case in cases))

    def test_current_empty_retriever_is_a_recorded_baseline_miss(self):
        result = evaluate_retriever(stage_15_cases(), agentic_loop.retrieve_relevant_nodes)

        self.assertFalse(result.passed)
        self.assertEqual(result.passed_count, 0)
        self.assertEqual(result.total_count, len(stage_15_cases()))
        self.assertTrue(all(case_result.missing_ids for case_result in result.results))

    def test_load_retrieval_nodes_reads_fixture_vault_metadata_body_and_parent_slugs(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "goals",
                "build-sprockets-cogs",
                "node_type: sprockets/goal\n"
                "uuid: goal-1\n"
                "title: Build Sprockets-Cogs\n",
                "Goal reflection text.",
            )
            write_node(
                vault,
                "projects",
                "phase-3-memory-enhancement",
                "node_type: sprockets/project\n"
                "uuid: project-1\n"
                "title: Phase 3 - Memory Enhancement\n"
                "parent: [[build-sprockets-cogs]]\n",
                "Retrieval quality notes.",
            )

            nodes = load_retrieval_nodes(vault)

        by_id = {node.node_id: node for node in nodes}
        self.assertEqual(
            by_id["projects/phase-3-memory-enhancement"].title,
            "Phase 3 - Memory Enhancement",
        )
        self.assertEqual(
            by_id["projects/phase-3-memory-enhancement"].node_type,
            "sprockets/project",
        )
        self.assertEqual(
            by_id["projects/phase-3-memory-enhancement"].parent_slugs,
            ("build-sprockets-cogs",),
        )
        self.assertIn("Retrieval quality notes.", by_id["projects/phase-3-memory-enhancement"].text)

    def test_load_retrieval_nodes_includes_daily_notes_with_stable_date_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            daily = vault / "Cogs" / "daily" / "Sat 02 May 2026.md"
            daily.parent.mkdir(parents=True, exist_ok=True)
            daily.write_text("- [ ] Continue retrieval traces\n")

            nodes = load_retrieval_nodes(vault)

        by_id = {node.node_id: node for node in nodes}
        self.assertEqual(by_id["daily/2026-05-02"].title, "Sat 02 May 2026")
        self.assertEqual(by_id["daily/2026-05-02"].node_type, "cogs/daily")
        self.assertIn("retrieval traces", by_id["daily/2026-05-02"].text)

    def test_lexical_retriever_establishes_a_non_embedding_lower_bound(self):
        nodes = stage_15_fixture_nodes()
        result = evaluate_retriever(
            stage_15_cases(),
            lambda query: lexical_retrieve(query, nodes),
        )

        self.assertGreater(result.passed_count, 0)
        self.assertGreater(result.passed_count, evaluate_retriever(stage_15_cases(), lambda _query: []).passed_count)

    def test_lexical_retriever_can_recover_named_contact_without_ambiguous_contact(self):
        nodes = stage_15_fixture_nodes()

        result = evaluate_retriever(
            [case for case in stage_15_cases() if case.name == "named-contact-followup"],
            lambda query: lexical_retrieve(query, nodes),
        )

        self.assertTrue(result.passed)

    def test_lexical_retriever_exposes_remaining_stage_15_gaps(self):
        nodes = stage_15_fixture_nodes()
        result = evaluate_retriever(
            stage_15_cases(),
            lambda query: lexical_retrieve(query, nodes),
        )

        failed_categories = {
            case_result.case.category
            for case_result in result.results
            if not case_result.passed
        }
        self.assertIn("semantic_gap", failed_categories)


if __name__ == "__main__":
    unittest.main()

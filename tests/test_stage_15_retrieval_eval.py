import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agentic_loop
import retrieval_eval
from retrieval_eval import (
    RetrievalCase,
    RetrievalNode,
    evaluate_retriever,
    evaluate_target_presence,
    lexical_retrieve,
    load_retrieval_nodes,
    retrieval_node_counts,
    select_cases,
    stage_15_cases,
    stage_15_fixture_nodes,
    stage_15_real_vault_cases,
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

    def test_real_vault_cases_cover_required_memory_risks(self):
        cases = stage_15_real_vault_cases()
        categories = {case.category for case in cases}

        self.assertEqual(len(cases), len(stage_15_cases()))
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

    def test_select_cases_uses_real_vault_cases_for_lexical_vault_auto(self):
        self.assertEqual(select_cases("auto", "lexical-vault"), stage_15_real_vault_cases())
        self.assertEqual(select_cases("auto", "current"), stage_15_cases())
        self.assertEqual(select_cases("fixture", "lexical-vault"), stage_15_cases())
        self.assertEqual(select_cases("real-vault", "current"), stage_15_real_vault_cases())

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

    def test_retrieval_node_counts_summarizes_node_types(self):
        counts = retrieval_node_counts([
            RetrievalNode(
                node_id="projects/one",
                title="One",
                node_type="sprockets/project",
                path=Path("one.md"),
            ),
            RetrievalNode(
                node_id="daily/2026-05-02",
                title="Sat 02 May 2026",
                node_type="cogs/daily",
                path=Path("daily.md"),
            ),
            RetrievalNode(
                node_id="projects/two",
                title="Two",
                node_type="sprockets/project",
                path=Path("two.md"),
            ),
        ])

        self.assertEqual(counts, {"cogs/daily": 1, "sprockets/project": 2})

    def test_evaluate_target_presence_reports_missing_and_present_targets(self):
        case = RetrievalCase(
            name="targets",
            query="Find memory work.",
            expected_ids=frozenset({
                "projects/phase-3-memory-enhancement",
                "notes/openai-fallback-review-first",
            }),
            avoid_ids=frozenset({
                "projects/phase-2-hardening",
                "notes/anthropic-fallback-plan",
            }),
        )
        nodes = [
            RetrievalNode(
                node_id="projects/phase-3-memory-enhancement",
                title="Phase 3 - Memory Enhancement",
                node_type="sprockets/project",
                path=Path("phase-3-memory-enhancement.md"),
            ),
            RetrievalNode(
                node_id="projects/phase-2-hardening",
                title="Phase 2 - Hardening",
                node_type="sprockets/project",
                path=Path("phase-2-hardening.md"),
            ),
        ]

        status = evaluate_target_presence([case], nodes)[0]

        self.assertEqual(status.present_expected_ids, frozenset({"projects/phase-3-memory-enhancement"}))
        self.assertEqual(status.missing_expected_ids, frozenset({"notes/openai-fallback-review-first"}))
        self.assertEqual(status.present_avoid_ids, frozenset({"projects/phase-2-hardening"}))

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

    def test_cli_lexical_vault_mode_loads_nodes_from_configured_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "contacts",
                "jordan-mack",
                "node_type: sprockets/contact\n"
                "title: Jordan Mack\n",
                "Proposal follow-up contact for current product feedback.",
            )

            with patch("sys.argv", [
                "retrieval_eval",
                "--retriever",
                "lexical-vault",
                "--vault-dir",
                str(vault),
                "--list-nodes",
                "--show-targets",
            ]):
                with patch("builtins.print") as mock_print:
                    retrieval_eval.main()

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("- retriever: lexical-vault", printed)
        self.assertIn("- case-set: real-vault", printed)
        self.assertIn("- vault: ", printed)
        self.assertIn("- nodes: 1", printed)
        self.assertIn("- sprockets/contact: 1", printed)
        self.assertIn("Target inventory", printed)
        self.assertIn("contacts/tom-reilly", printed)


if __name__ == "__main__":
    unittest.main()

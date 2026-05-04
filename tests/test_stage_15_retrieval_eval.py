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
    expand_retrieval_neighbors,
    filter_by_query_intent,
    hybrid_retrieve,
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
        self.assertEqual(select_cases("auto", "embedding-vault"), stage_15_real_vault_cases())
        self.assertEqual(select_cases("auto", "hybrid-vault"), stage_15_real_vault_cases())
        self.assertEqual(select_cases("auto", "hybrid-graph-vault"), stage_15_real_vault_cases())
        self.assertEqual(select_cases("auto", "hybrid-graph-intent-vault"), stage_15_real_vault_cases())
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

    def test_hybrid_retriever_merges_lexical_and_embedding_results(self):
        memory = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("phase-3-memory-enhancement.md"),
            text="Memory retrieval and embeddings.",
        )
        production = RetrievalNode(
            node_id="projects/learn-how-to-bring-a-project-to-production",
            title="Learn how to bring a project to production",
            node_type="sprockets/project",
            path=Path("learn-how-to-bring-a-project-to-production.md"),
        )
        contact = RetrievalNode(
            node_id="contacts/tom-reilly",
            title="Tom Reilly",
            node_type="sprockets/contact",
            path=Path("tom-reilly.md"),
        )

        results = hybrid_retrieve(
            "memory retrieval beyond my laptop",
            (memory, production, contact),
            lambda _query: [production, contact],
            limit=3,
        )

        self.assertEqual([node.node_id for node in results], [
            "projects/learn-how-to-bring-a-project-to-production",
            "projects/phase-3-memory-enhancement",
            "contacts/tom-reilly",
        ])

    def test_hybrid_retriever_returns_empty_for_non_positive_limit(self):
        results = hybrid_retrieve("memory", (), lambda _query: [], limit=0)

        self.assertEqual(results, [])

    def test_expand_retrieval_neighbors_adds_parent_child_and_title_mentions(self):
        area = RetrievalNode(
            node_id="areas/learn-agentic-ai",
            title="Learn Agentic AI",
            node_type="sprockets/area",
            path=Path("learn-agentic-ai.md"),
        )
        goal = RetrievalNode(
            node_id="goals/build-sprockets-cogs",
            title="Build Sprockets-Cogs",
            node_type="sprockets/goal",
            path=Path("build-sprockets-cogs.md"),
            parent_slugs=("learn-agentic-ai",),
        )
        project = RetrievalNode(
            node_id="projects/phase-3-memory-enhancement",
            title="Phase 3 - Memory Enhancement",
            node_type="sprockets/project",
            path=Path("phase-3-memory-enhancement.md"),
            parent_slugs=("build-sprockets-cogs",),
        )
        task = RetrievalNode(
            node_id="tasks/call-tom-reilly-at-globaltech-about-the-invoice",
            title="Call Tom Reilly at GlobalTech about the invoice",
            node_type="sprockets/task",
            path=Path("call-tom-reilly-at-globaltech-about-the-invoice.md"),
        )
        contact = RetrievalNode(
            node_id="contacts/tom-reilly",
            title="Tom Reilly",
            node_type="sprockets/contact",
            path=Path("tom-reilly.md"),
        )
        entity = RetrievalNode(
            node_id="entities/globaltech",
            title="GlobalTech",
            node_type="sprockets/entity",
            path=Path("globaltech.md"),
        )

        expanded = expand_retrieval_neighbors(
            (task, project),
            (area, goal, project, task, contact, entity),
            limit=6,
        )

        self.assertEqual([node.node_id for node in expanded], [
            "tasks/call-tom-reilly-at-globaltech-about-the-invoice",
            "contacts/tom-reilly",
            "entities/globaltech",
            "projects/phase-3-memory-enhancement",
            "goals/build-sprockets-cogs",
        ])

    def test_hybrid_retriever_can_expand_graph_neighbors(self):
        task = RetrievalNode(
            node_id="tasks/call-tom-reilly-at-globaltech-about-the-invoice",
            title="Call Tom Reilly at GlobalTech about the invoice",
            node_type="sprockets/task",
            path=Path("call-tom-reilly-at-globaltech-about-the-invoice.md"),
        )
        contact = RetrievalNode(
            node_id="contacts/tom-reilly",
            title="Tom Reilly",
            node_type="sprockets/contact",
            path=Path("tom-reilly.md"),
        )
        entity = RetrievalNode(
            node_id="entities/globaltech",
            title="GlobalTech",
            node_type="sprockets/entity",
            path=Path("globaltech.md"),
        )

        results = hybrid_retrieve(
            "Tom invoice",
            (task, contact, entity),
            lambda _query: [task],
            expand_graph=True,
        )

        self.assertEqual([node.node_id for node in results], [
            "tasks/call-tom-reilly-at-globaltech-about-the-invoice",
            "contacts/tom-reilly",
            "entities/globaltech",
        ])

    def test_filter_by_query_intent_prefers_notes_for_reflection_queries(self):
        note = RetrievalNode(
            node_id="notes/reflection-on-phase-2---hierarchy",
            title="Reflection on Phase 2 - Hierarchy",
            node_type="sprockets/note",
            path=Path("reflection-on-phase-2---hierarchy.md"),
        )
        task = RetrievalNode(
            node_id="tasks/add-hierarchy-context-tests-for-phase-2---hardening",
            title="Add hierarchy context tests for Phase 2 - Hardening",
            node_type="sprockets/task",
            path=Path("add-hierarchy-context-tests-for-phase-2---hardening.md"),
        )
        project = RetrievalNode(
            node_id="projects/phase-2-hardening",
            title="Phase 2 - Hardening",
            node_type="sprockets/project",
            path=Path("phase-2-hardening.md"),
        )

        filtered = filter_by_query_intent(
            "Capture a reflection on Phase 2 hierarchy work.",
            (note, task, project),
        )

        self.assertEqual([node.node_id for node in filtered], [
            "notes/reflection-on-phase-2---hierarchy",
        ])

    def test_filter_by_query_intent_falls_back_when_no_preferred_type_exists(self):
        task = RetrievalNode(
            node_id="tasks/add-hierarchy-context-tests-for-phase-2---hardening",
            title="Add hierarchy context tests for Phase 2 - Hardening",
            node_type="sprockets/task",
            path=Path("add-hierarchy-context-tests-for-phase-2---hardening.md"),
        )

        filtered = filter_by_query_intent("Capture a reflection.", (task,))

        self.assertEqual(filtered, [task])

    def test_hybrid_retriever_can_apply_intent_filter_after_graph_expansion(self):
        note = RetrievalNode(
            node_id="notes/reflection-on-phase-2---hierarchy",
            title="Reflection on Phase 2 - Hierarchy",
            node_type="sprockets/note",
            path=Path("reflection-on-phase-2---hierarchy.md"),
        )
        task = RetrievalNode(
            node_id="tasks/add-hierarchy-context-tests-for-phase-2---hardening",
            title="Add hierarchy context tests for Phase 2 - Hardening",
            node_type="sprockets/task",
            path=Path("add-hierarchy-context-tests-for-phase-2---hardening.md"),
        )

        results = hybrid_retrieve(
            "Capture a reflection on Phase 2 hierarchy work.",
            (note, task),
            lambda _query: [task],
            expand_graph=True,
            apply_intent_filter=True,
        )

        self.assertEqual([node.node_id for node in results], [
            "notes/reflection-on-phase-2---hierarchy",
        ])

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

    def test_cli_embedding_vault_mode_uses_embedding_index_without_production_wiring(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "projects",
                "learn-how-to-bring-a-project-to-production",
                "node_type: sprockets/project\n"
                "title: Learn how to bring a project to production\n",
                "Deployment readiness notes.",
            )

            with patch("embeddings.build_embedding_index") as mock_build_index:
                with patch("embeddings.retrieve_by_embedding") as mock_retrieve_by_embedding:
                    mock_build_index.return_value = ("embedded-index",)
                    mock_retrieve_by_embedding.return_value = [
                        RetrievalNode(
                            node_id="projects/learn-how-to-bring-a-project-to-production",
                            title="Learn how to bring a project to production",
                            node_type="sprockets/project",
                            path=vault / "Sprockets" / "projects" / "learn-how-to-bring-a-project-to-production.md",
                        )
                    ]

                    with patch("sys.argv", [
                        "retrieval_eval",
                        "--retriever",
                        "embedding-vault",
                        "--vault-dir",
                        str(vault),
                        "--list-nodes",
                    ]):
                        with patch("builtins.print") as mock_print:
                            retrieval_eval.main()

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("- retriever: embedding-vault", printed)
        self.assertIn("- case-set: real-vault", printed)
        self.assertIn("- vault: ", printed)
        self.assertIn("- nodes: 1", printed)
        self.assertIn("- sprockets/project: 1", printed)
        mock_build_index.assert_called_once()
        self.assertTrue(mock_retrieve_by_embedding.called)

    def test_cli_hybrid_vault_mode_uses_embedding_index_and_hybrid_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "projects",
                "learn-how-to-bring-a-project-to-production",
                "node_type: sprockets/project\n"
                "title: Learn how to bring a project to production\n",
                "Deployment readiness notes.",
            )

            with patch("embeddings.build_embedding_index") as mock_build_index:
                with patch("embeddings.retrieve_by_embedding") as mock_retrieve_by_embedding:
                    mock_build_index.return_value = ("embedded-index",)
                    mock_retrieve_by_embedding.return_value = [
                        RetrievalNode(
                            node_id="projects/learn-how-to-bring-a-project-to-production",
                            title="Learn how to bring a project to production",
                            node_type="sprockets/project",
                            path=vault / "Sprockets" / "projects" / "learn-how-to-bring-a-project-to-production.md",
                        )
                    ]

                    with patch("sys.argv", [
                        "retrieval_eval",
                        "--retriever",
                        "hybrid-vault",
                        "--vault-dir",
                        str(vault),
                        "--list-nodes",
                    ]):
                        with patch("builtins.print") as mock_print:
                            retrieval_eval.main()

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("- retriever: hybrid-vault", printed)
        self.assertIn("- case-set: real-vault", printed)
        self.assertIn("- vault: ", printed)
        self.assertIn("- nodes: 1", printed)
        self.assertIn("- sprockets/project: 1", printed)
        mock_build_index.assert_called_once()
        self.assertTrue(mock_retrieve_by_embedding.called)

    def test_cli_hybrid_graph_vault_mode_uses_graph_expansion(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "tasks",
                "call-tom-reilly-at-globaltech-about-the-invoice",
                "node_type: sprockets/task\n"
                "title: Call Tom Reilly at GlobalTech about the invoice\n",
            )
            write_node(
                vault,
                "contacts",
                "tom-reilly",
                "node_type: sprockets/contact\n"
                "title: Tom Reilly\n",
            )
            write_node(
                vault,
                "entities",
                "globaltech",
                "node_type: sprockets/entity\n"
                "title: GlobalTech\n",
            )

            with patch("embeddings.build_embedding_index") as mock_build_index:
                with patch("embeddings.retrieve_by_embedding") as mock_retrieve_by_embedding:
                    mock_build_index.return_value = ("embedded-index",)
                    mock_retrieve_by_embedding.return_value = [
                        RetrievalNode(
                            node_id="tasks/call-tom-reilly-at-globaltech-about-the-invoice",
                            title="Call Tom Reilly at GlobalTech about the invoice",
                            node_type="sprockets/task",
                            path=vault / "Sprockets" / "tasks" / "call-tom-reilly-at-globaltech-about-the-invoice.md",
                        )
                    ]

                    with patch("sys.argv", [
                        "retrieval_eval",
                        "--retriever",
                        "hybrid-graph-vault",
                        "--vault-dir",
                        str(vault),
                        "--list-nodes",
                    ]):
                        with patch("builtins.print") as mock_print:
                            retrieval_eval.main()

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("- retriever: hybrid-graph-vault", printed)
        self.assertIn("- case-set: real-vault", printed)
        self.assertIn("- vault: ", printed)
        self.assertIn("- nodes: 3", printed)
        self.assertIn("- sprockets/contact: 1", printed)
        self.assertIn("- sprockets/entity: 1", printed)
        self.assertIn("- sprockets/task: 1", printed)
        mock_build_index.assert_called_once()
        self.assertTrue(mock_retrieve_by_embedding.called)

    def test_cli_hybrid_graph_intent_vault_mode_uses_intent_filtering(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "notes",
                "reflection-on-phase-2---hierarchy",
                "node_type: sprockets/note\n"
                "title: Reflection on Phase 2 - Hierarchy\n",
            )
            write_node(
                vault,
                "tasks",
                "add-hierarchy-context-tests-for-phase-2---hardening",
                "node_type: sprockets/task\n"
                "title: Add hierarchy context tests for Phase 2 - Hardening\n",
            )

            with patch("embeddings.build_embedding_index") as mock_build_index:
                with patch("embeddings.retrieve_by_embedding") as mock_retrieve_by_embedding:
                    mock_build_index.return_value = ("embedded-index",)
                    mock_retrieve_by_embedding.return_value = [
                        RetrievalNode(
                            node_id="tasks/add-hierarchy-context-tests-for-phase-2---hardening",
                            title="Add hierarchy context tests for Phase 2 - Hardening",
                            node_type="sprockets/task",
                            path=vault / "Sprockets" / "tasks" / "add-hierarchy-context-tests-for-phase-2---hardening.md",
                        )
                    ]

                    with patch("sys.argv", [
                        "retrieval_eval",
                        "--retriever",
                        "hybrid-graph-intent-vault",
                        "--vault-dir",
                        str(vault),
                        "--list-nodes",
                    ]):
                        with patch("builtins.print") as mock_print:
                            retrieval_eval.main()

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("- retriever: hybrid-graph-intent-vault", printed)
        self.assertIn("- case-set: real-vault", printed)
        self.assertIn("- vault: ", printed)
        self.assertIn("- nodes: 2", printed)
        self.assertIn("- sprockets/note: 1", printed)
        self.assertIn("- sprockets/task: 1", printed)
        mock_build_index.assert_called_once()
        self.assertTrue(mock_retrieve_by_embedding.called)


if __name__ == "__main__":
    unittest.main()

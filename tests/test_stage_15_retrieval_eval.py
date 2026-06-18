import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import specialists.rosie.loop as agentic_loop
import specialists.rudi.embeddings as embeddings
import specialists.rudi.retrieval_eval as retrieval_eval
from specialists.rudi.retrieval_eval import (
    RetrievalCase,
    RetrievalNode,
    SemanticQueryHint,
    build_experimental_retriever,
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
    stage_22_packet_vault_cases,
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
            query="Ask Alex about the proposal.",
            expected_ids=frozenset({"contacts/alex-rivera"}),
            avoid_ids=frozenset({"contacts/alex-lee"}),
        )

        result = evaluate_retriever([case], lambda _query: ["contacts/alex-rivera"])

        self.assertTrue(result.passed)
        self.assertEqual(result.passed_count, 1)
        self.assertEqual(result.total_count, 1)
        self.assertEqual(result.results[0].retrieved_ids, ("contacts/alex-rivera",))

    def test_evaluate_retriever_flags_missing_and_forbidden_ids(self):
        case = RetrievalCase(
            name="ambiguous-contact",
            query="Ask Alex about the proposal.",
            expected_ids=frozenset({"contacts/alex-rivera"}),
            avoid_ids=frozenset({"contacts/alex-lee"}),
        )

        result = evaluate_retriever([case], lambda _query: ["contacts/alex-lee"])

        self.assertFalse(result.passed)
        self.assertEqual(result.results[0].missing_ids, frozenset({"contacts/alex-rivera"}))
        self.assertEqual(result.results[0].forbidden_ids, frozenset({"contacts/alex-lee"}))

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

    def test_evaluate_retriever_accepts_retrieval_node_shaped_objects(self):
        class NodeLike:
            node_id = "projects/phase-3-memory-enhancement"

        case = RetrievalCase(
            name="node-like",
            query="Phase 3 memory",
            expected_ids=frozenset({"projects/phase-3-memory-enhancement"}),
        )

        result = evaluate_retriever([case], lambda _query: [NodeLike()])

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
        self.assertEqual(select_cases("auto", "memory-vault"), stage_15_real_vault_cases())
        self.assertEqual(select_cases("auto", "memory-embedding-vault"), stage_15_real_vault_cases())
        self.assertEqual(select_cases("auto", "memory-embedding-gated-vault"), stage_15_real_vault_cases())
        self.assertEqual(select_cases("auto", "memory-packet-embedding-gated-vault"), stage_15_real_vault_cases())
        self.assertEqual(select_cases("auto", "embedding-vault"), stage_15_real_vault_cases())
        self.assertEqual(select_cases("auto", "hybrid-vault"), stage_15_real_vault_cases())
        self.assertEqual(select_cases("auto", "hybrid-graph-vault"), stage_15_real_vault_cases())
        self.assertEqual(select_cases("auto", "hybrid-graph-intent-vault"), stage_15_real_vault_cases())
        self.assertEqual(select_cases("auto", "current"), stage_15_cases())
        self.assertEqual(select_cases("fixture", "lexical-vault"), stage_15_cases())
        self.assertEqual(select_cases("real-vault", "current"), stage_15_real_vault_cases())
        self.assertEqual(select_cases("packet-vault", "current"), stage_22_packet_vault_cases())

    def test_semantic_query_hints_expand_known_production_readiness_language(self):
        hints = retrieval_eval._semantic_query_hints(
            "What should I study so this can run beyond my laptop?"
        )

        self.assertEqual(
            hints,
            (
                SemanticQueryHint(
                    label="production readiness",
                    expansion_terms=(
                        "learn",
                        "bring",
                        "project",
                        "production",
                        "readiness",
                        "deployment",
                        "release",
                        "operations",
                        "service",
                        "monitoring",
                        "backups",
                    ),
                ),
            ),
        )
        self.assertIn("production readiness", hints[0].expansion_text)

    def test_semantic_query_hints_ignore_unknown_language(self):
        self.assertEqual(retrieval_eval._semantic_query_hints("What deserves attention next?"), ())

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
            node_id="contacts/taylor-reed",
            title="Taylor Reed",
            node_type="sprockets/contact",
            path=Path("taylor-reed.md"),
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
            "contacts/taylor-reed",
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
            node_id="tasks/call-taylor-reed-at-examplecorp-about-the-invoice",
            title="Call Taylor Reed at ExampleCorp about the invoice",
            node_type="sprockets/task",
            path=Path("call-taylor-reed-at-examplecorp-about-the-invoice.md"),
        )
        contact = RetrievalNode(
            node_id="contacts/taylor-reed",
            title="Taylor Reed",
            node_type="sprockets/contact",
            path=Path("taylor-reed.md"),
        )
        entity = RetrievalNode(
            node_id="entities/examplecorp",
            title="ExampleCorp",
            node_type="sprockets/entity",
            path=Path("examplecorp.md"),
        )

        expanded = expand_retrieval_neighbors(
            (task, project),
            (area, goal, project, task, contact, entity),
            limit=6,
        )

        self.assertEqual([node.node_id for node in expanded], [
            "tasks/call-taylor-reed-at-examplecorp-about-the-invoice",
            "contacts/taylor-reed",
            "entities/examplecorp",
            "projects/phase-3-memory-enhancement",
            "goals/build-sprockets-cogs",
        ])

    def test_hybrid_retriever_can_expand_graph_neighbors(self):
        task = RetrievalNode(
            node_id="tasks/call-taylor-reed-at-examplecorp-about-the-invoice",
            title="Call Taylor Reed at ExampleCorp about the invoice",
            node_type="sprockets/task",
            path=Path("call-taylor-reed-at-examplecorp-about-the-invoice.md"),
        )
        contact = RetrievalNode(
            node_id="contacts/taylor-reed",
            title="Taylor Reed",
            node_type="sprockets/contact",
            path=Path("taylor-reed.md"),
        )
        entity = RetrievalNode(
            node_id="entities/examplecorp",
            title="ExampleCorp",
            node_type="sprockets/entity",
            path=Path("examplecorp.md"),
        )

        results = hybrid_retrieve(
            "Taylor invoice",
            (task, contact, entity),
            lambda _query: [task],
            expand_graph=True,
        )

        self.assertEqual([node.node_id for node in results], [
            "tasks/call-taylor-reed-at-examplecorp-about-the-invoice",
            "contacts/taylor-reed",
            "entities/examplecorp",
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

    def test_filter_by_query_intent_prefers_daily_notes_for_recent_queries(self):
        daily = RetrievalNode(
            node_id="daily/2026-05-03",
            title="Sun 03 May 2026",
            node_type="cogs/daily",
            path=Path("Sun 03 May 2026.md"),
        )
        task = RetrievalNode(
            node_id="tasks/add-hierarchy-context-tests-for-phase-2---hardening",
            title="Add hierarchy context tests for Phase 2 - Hardening",
            node_type="sprockets/task",
            path=Path("add-hierarchy-context-tests-for-phase-2---hardening.md"),
        )

        filtered = filter_by_query_intent(
            "Continue the note from today about hierarchy context tests.",
            (task, daily),
        )

        self.assertEqual([node.node_id for node in filtered], ["daily/2026-05-03"])

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

    def test_build_experimental_retriever_builds_lexical_fixture_interface(self):
        retriever = build_experimental_retriever("lexical-fixture", Path("/unused"))

        results = list(retriever.retrieve("Ask Alex about the proposal follow-up."))

        self.assertEqual(retriever.name, "lexical-fixture")
        self.assertEqual(len(retriever.nodes), len(stage_15_fixture_nodes()))
        self.assertTrue(results)
        self.assertTrue(all(isinstance(node, RetrievalNode) for node in results))

    def test_build_experimental_retriever_builds_memory_fixture_interface(self):
        retriever = build_experimental_retriever("memory-fixture", Path("/unused"))

        results = list(retriever.retrieve("Phase 3 memory enhancement"))
        trace = retriever.trace("Phase 3 memory enhancement")

        self.assertEqual(retriever.name, "memory-fixture")
        self.assertEqual(len(retriever.nodes), len(stage_15_fixture_nodes()))
        self.assertEqual(results[0].node_id, "projects/phase-3-memory-enhancement")
        self.assertTrue(all(isinstance(node, RetrievalNode) for node in results))
        self.assertIsNotNone(trace)
        self.assertEqual(trace.retriever_name, "in-memory")
        self.assertEqual(trace.result_ids[0], "projects/phase-3-memory-enhancement")

    def test_memory_fixture_retriever_applies_intent_filters_with_fallback(self):
        retriever = build_experimental_retriever("memory-fixture", Path("/unused"))

        reflection_results = list(retriever.retrieve(
            "Capture an idea about a compact Dataview dashboard."
        ))
        fallback_results = list(retriever.retrieve(
            "Capture a reflection with no matching note tokens."
        ))
        daily_trace = retriever.trace("Continue the note from yesterday about retrieval traces.")

        self.assertEqual(reflection_results[0].node_id, "notes/dataview-dashboard")
        self.assertTrue(fallback_results)
        self.assertEqual(daily_trace.filters_applied["node_types"], ("cogs/daily",))
        self.assertIn("daily recency fallback", daily_trace.notes)

    def test_memory_fixture_retriever_falls_back_to_recent_daily_notes(self):
        retriever = build_experimental_retriever("memory-fixture", Path("/unused"))

        results = list(retriever.retrieve("Continue the note from today."))
        trace = retriever.trace("Continue the note from today.")

        self.assertEqual(results[0].node_id, "daily/2026-05-02")
        self.assertEqual(trace.confidence.level, "high")
        self.assertEqual(trace.confidence.action, "use")

    def test_memory_vault_recency_fallback_ignores_future_daily_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            future_date = date.today() + timedelta(days=2)
            current_date = date.today() - timedelta(days=1)
            future = vault / "Cogs" / "daily" / future_date.strftime("%a %d %b %Y.md")
            current = vault / "Cogs" / "daily" / current_date.strftime("%a %d %b %Y.md")
            future.parent.mkdir(parents=True, exist_ok=True)
            future.write_text("- [ ] Future note\n")
            current.write_text("- [ ] Current note\n")

            retriever = build_experimental_retriever("memory-vault", vault)
            results = list(retriever.retrieve("Continue the note from today."))

        self.assertEqual(results[0].node_id, f"daily/{current_date.isoformat()}")
        self.assertNotIn(f"daily/{future_date.isoformat()}", [node.node_id for node in results])

    def test_build_experimental_retriever_builds_memory_embedding_vault_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            production_path = write_node(
                vault,
                "projects",
                "learn-how-to-bring-a-project-to-production",
                "node_type: sprockets/project\n"
                "title: Learn how to bring a project to production\n",
            )
            laptop_path = write_node(
                vault,
                "notes",
                "laptop-setup",
                "node_type: sprockets/note\n"
                "title: Laptop setup\n",
            )
            production = RetrievalNode(
                node_id="projects/learn-how-to-bring-a-project-to-production",
                title="Learn how to bring a project to production",
                node_type="sprockets/project",
                path=production_path,
            )
            laptop = RetrievalNode(
                node_id="notes/laptop-setup",
                title="Laptop setup",
                node_type="sprockets/note",
                path=laptop_path,
            )

            with patch("specialists.rudi.embeddings.build_embedding_index") as mock_build_index:
                with patch("specialists.rudi.embeddings.embed_text") as mock_embed_text:
                    mock_build_index.return_value = (
                        embeddings.EmbeddedNode(node=production, vector=(1.0, 0.0)),
                        embeddings.EmbeddedNode(node=laptop, vector=(0.0, 1.0)),
                    )
                    mock_embed_text.return_value = [1.0, 0.0]

                    retriever = build_experimental_retriever(
                        "memory-embedding-vault",
                        vault,
                    )
                    results = list(retriever.retrieve("What should run beyond my laptop?"))
                    trace = retriever.trace("What should run beyond my laptop?")

        self.assertEqual(retriever.name, "memory-embedding-vault")
        self.assertEqual(results[0].node_id, "projects/learn-how-to-bring-a-project-to-production")
        self.assertEqual(trace.retriever_name, "in-memory")
        self.assertIn("projects/learn-how-to-bring-a-project-to-production", trace.result_ids)
        mock_build_index.assert_called_once()
        self.assertTrue(mock_embed_text.called)

    def test_memory_embedding_gated_vault_withholds_low_confidence_results_without_grounding(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            production_path = write_node(
                vault,
                "projects",
                "learn-how-to-bring-a-project-to-production",
                "node_type: sprockets/project\n"
                "title: Learn how to bring a project to production\n",
            )
            laptop_path = write_node(
                vault,
                "notes",
                "laptop-setup",
                "node_type: sprockets/note\n"
                "title: Laptop setup\n",
            )
            production = RetrievalNode(
                node_id="projects/learn-how-to-bring-a-project-to-production",
                title="Learn how to bring a project to production",
                node_type="sprockets/project",
                path=production_path,
            )
            laptop = RetrievalNode(
                node_id="notes/laptop-setup",
                title="Laptop setup",
                node_type="sprockets/note",
                path=laptop_path,
            )

            with patch("specialists.rudi.embeddings.build_embedding_index") as mock_build_index:
                with patch("specialists.rudi.embeddings.embed_text") as mock_embed_text:
                    mock_build_index.return_value = (
                        embeddings.EmbeddedNode(node=production, vector=(1.0, 0.0)),
                        embeddings.EmbeddedNode(node=laptop, vector=(0.99, 0.01)),
                    )
                    mock_embed_text.return_value = [1.0, 0.0]

                    retriever = build_experimental_retriever(
                        "memory-embedding-gated-vault",
                        vault,
                    )
                    results = list(retriever.retrieve("What deserves attention next?"))
                    trace = retriever.trace("What deserves attention next?")

        self.assertEqual(retriever.name, "memory-embedding-gated-vault")
        self.assertEqual(results, [])
        self.assertEqual(trace.result_ids, ())
        self.assertEqual(trace.confidence.action, "review")
        self.assertIn("confidence gate withheld low-confidence results", trace.notes)
        mock_build_index.assert_called_once()
        self.assertTrue(mock_embed_text.called)

    def test_memory_embedding_gated_vault_grounds_production_readiness_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            production_path = write_node(
                vault,
                "projects",
                "learn-how-to-bring-a-project-to-production",
                "node_type: sprockets/project\n"
                "title: Learn how to bring a project to production\n",
            )
            laptop_path = write_node(
                vault,
                "notes",
                "laptop-setup",
                "node_type: sprockets/note\n"
                "title: Laptop setup\n",
            )
            production = RetrievalNode(
                node_id="projects/learn-how-to-bring-a-project-to-production",
                title="Learn how to bring a project to production",
                node_type="sprockets/project",
                path=production_path,
            )
            laptop = RetrievalNode(
                node_id="notes/laptop-setup",
                title="Laptop setup",
                node_type="sprockets/note",
                path=laptop_path,
            )

            with patch("specialists.rudi.embeddings.build_embedding_index") as mock_build_index:
                with patch("specialists.rudi.embeddings.embed_text") as mock_embed_text:
                    mock_build_index.return_value = (
                        embeddings.EmbeddedNode(node=production, vector=(0.99, 0.01)),
                        embeddings.EmbeddedNode(node=laptop, vector=(1.0, 0.0)),
                    )
                    mock_embed_text.return_value = [1.0, 0.0]

                    retriever = build_experimental_retriever(
                        "memory-embedding-gated-vault",
                        vault,
                    )
                    results = list(retriever.retrieve("What should run beyond my laptop?"))
                    trace = retriever.trace("What should run beyond my laptop?")

        self.assertEqual(results[0].node_id, "projects/learn-how-to-bring-a-project-to-production")
        self.assertEqual(trace.result_ids[0], "projects/learn-how-to-bring-a-project-to-production")
        self.assertEqual(trace.confidence.action, "use")
        self.assertIn("semantic hint applied: production readiness", trace.notes)
        self.assertNotIn("confidence gate withheld low-confidence results", trace.notes)
        mock_build_index.assert_called_once()
        self.assertTrue(mock_embed_text.called)

    def test_memory_packet_embedding_gated_vault_adds_packet_nodes_without_production_wiring(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "goals",
                "build-sprockets-cogs",
                "node_type: sprockets/goal\n"
                "title: Build Sprockets-Cogs\n",
            )
            write_node(
                vault,
                "projects",
                "phase-3-memory-enhancement",
                "node_type: sprockets/project\n"
                "title: Phase 3 - Memory Enhancement\n"
                "parent: [[build-sprockets-cogs]]\n",
                "Improve retrieval and memory behavior.",
            )
            daily = vault / "Cogs" / "daily" / "Mon 04 May 2026.md"
            daily.parent.mkdir(parents=True, exist_ok=True)
            daily.write_text("- [ ] Review memory packet indexing\n")

            with patch("specialists.rudi.embeddings.build_embedding_index") as mock_build_index:
                mock_build_index.return_value = ()

                retriever = build_experimental_retriever(
                    "memory-packet-embedding-gated-vault",
                    vault,
                )

        node_ids = {node.node_id for node in retriever.nodes}
        self.assertEqual(retriever.name, "memory-packet-embedding-gated-vault")
        self.assertIn("projects/phase-3-memory-enhancement", node_ids)
        self.assertIn("packets/projects/phase-3-memory-enhancement", node_ids)
        self.assertIn("packets/memory/recent-cogs", node_ids)
        self.assertTrue(any(node.node_type == "memory/packet" for node in retriever.nodes))
        mock_build_index.assert_called_once()

    def test_build_experimental_retriever_builds_hybrid_graph_intent_interface(self):
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

            with patch("specialists.rudi.embeddings.build_embedding_index") as mock_build_index:
                with patch("specialists.rudi.embeddings.retrieve_by_embedding") as mock_retrieve_by_embedding:
                    mock_build_index.return_value = ("embedded-index",)
                    mock_retrieve_by_embedding.return_value = [
                        RetrievalNode(
                            node_id="tasks/add-hierarchy-context-tests-for-phase-2---hardening",
                            title="Add hierarchy context tests for Phase 2 - Hardening",
                            node_type="sprockets/task",
                            path=vault / "Sprockets" / "tasks" / "add-hierarchy-context-tests-for-phase-2---hardening.md",
                        )
                    ]

                    retriever = build_experimental_retriever(
                        "hybrid-graph-intent-vault",
                        vault,
                    )
                    results = list(retriever.retrieve(
                        "Capture a reflection on Phase 2 hierarchy work."
                    ))

        self.assertEqual(retriever.name, "hybrid-graph-intent-vault")
        self.assertEqual(len(retriever.nodes), 2)
        self.assertEqual([node.node_id for node in results], [
            "notes/reflection-on-phase-2---hierarchy",
        ])
        mock_build_index.assert_called_once()
        self.assertTrue(mock_retrieve_by_embedding.called)

    def test_build_experimental_retriever_rejects_unknown_name(self):
        with self.assertRaisesRegex(ValueError, "unknown retriever"):
            build_experimental_retriever("not-a-retriever", Path("/unused"))

    def test_cli_lexical_vault_mode_loads_nodes_from_configured_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "contacts",
                "alex-rivera",
                "node_type: sprockets/contact\n"
                "title: Alex Rivera\n",
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
        self.assertIn("contacts/taylor-reed", printed)

    def test_cli_memory_vault_mode_uses_memory_index_without_production_wiring(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "projects",
                "phase-3-memory-enhancement",
                "node_type: sprockets/project\n"
                "title: Phase 3 - Memory Enhancement\n",
                "Evaluate retrieval quality before production wiring.",
            )

            with patch("sys.argv", [
                "retrieval_eval",
                "--retriever",
                "memory-vault",
                "--vault-dir",
                str(vault),
                "--list-nodes",
            ]):
                with patch("builtins.print") as mock_print:
                    retrieval_eval.main()

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("- retriever: memory-vault", printed)
        self.assertIn("- case-set: real-vault", printed)
        self.assertIn("- vault: ", printed)
        self.assertIn("- nodes: 1", printed)
        self.assertIn("- sprockets/project: 1", printed)

    def test_cli_memory_vault_mode_can_show_query_traces(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_node(
                vault,
                "projects",
                "phase-3-memory-enhancement",
                "node_type: sprockets/project\n"
                "title: Phase 3 - Memory Enhancement\n",
                "Evaluate retrieval quality before production wiring.",
            )

            with patch("sys.argv", [
                "retrieval_eval",
                "--retriever",
                "memory-vault",
                "--vault-dir",
                str(vault),
                "--case-set",
                "fixture",
                "--show-traces",
            ]):
                with patch("builtins.print") as mock_print:
                    retrieval_eval.main()

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("- trace retriever: in-memory", printed)
        self.assertIn("- trace notes: records scanned: 1", printed)
        self.assertIn("candidates scored:", printed)
        self.assertIn("- trace results:", printed)
        self.assertIn("score=", printed)
        self.assertIn("reasons=", printed)

    def test_cli_memory_embedding_vault_mode_uses_cached_embeddings_without_production_wiring(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            production_path = write_node(
                vault,
                "projects",
                "learn-how-to-bring-a-project-to-production",
                "node_type: sprockets/project\n"
                "title: Learn how to bring a project to production\n",
            )
            production = RetrievalNode(
                node_id="projects/learn-how-to-bring-a-project-to-production",
                title="Learn how to bring a project to production",
                node_type="sprockets/project",
                path=production_path,
            )

            with patch("specialists.rudi.embeddings.build_embedding_index") as mock_build_index:
                with patch("specialists.rudi.embeddings.embed_text") as mock_embed_text:
                    mock_build_index.return_value = (
                        embeddings.EmbeddedNode(node=production, vector=(1.0, 0.0)),
                    )
                    mock_embed_text.return_value = [1.0, 0.0]

                    with patch("sys.argv", [
                        "retrieval_eval",
                        "--retriever",
                        "memory-embedding-vault",
                        "--vault-dir",
                        str(vault),
                        "--list-nodes",
                        "--show-traces",
                    ]):
                        with patch("builtins.print") as mock_print:
                            retrieval_eval.main()

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("- retriever: memory-embedding-vault", printed)
        self.assertIn("- case-set: real-vault", printed)
        self.assertIn("- vault: ", printed)
        self.assertIn("- nodes: 1", printed)
        self.assertIn("- trace retriever: in-memory", printed)
        self.assertIn("- trace results:", printed)
        self.assertIn("parts=title=", printed)
        self.assertIn("vector=", printed)
        self.assertIn("- trace quality:", printed)
        self.assertIn("- trace confidence:", printed)
        self.assertIn("Confidence summary", printed)
        self.assertIn("- low/review:", printed)
        mock_build_index.assert_called_once()
        self.assertTrue(mock_embed_text.called)

    def test_cli_non_memory_retriever_reports_unavailable_traces(self):
        with patch("sys.argv", [
            "retrieval_eval",
            "--retriever",
            "lexical-fixture",
            "--show-traces",
        ]):
            with patch("builtins.print") as mock_print:
                retrieval_eval.main()

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("- trace: unavailable", printed)

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

            with patch("specialists.rudi.embeddings.build_embedding_index") as mock_build_index:
                with patch("specialists.rudi.embeddings.retrieve_by_embedding") as mock_retrieve_by_embedding:
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

            with patch("specialists.rudi.embeddings.build_embedding_index") as mock_build_index:
                with patch("specialists.rudi.embeddings.retrieve_by_embedding") as mock_retrieve_by_embedding:
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
                "call-taylor-reed-at-examplecorp-about-the-invoice",
                "node_type: sprockets/task\n"
                "title: Call Taylor Reed at ExampleCorp about the invoice\n",
            )
            write_node(
                vault,
                "contacts",
                "taylor-reed",
                "node_type: sprockets/contact\n"
                "title: Taylor Reed\n",
            )
            write_node(
                vault,
                "entities",
                "examplecorp",
                "node_type: sprockets/entity\n"
                "title: ExampleCorp\n",
            )

            with patch("specialists.rudi.embeddings.build_embedding_index") as mock_build_index:
                with patch("specialists.rudi.embeddings.retrieve_by_embedding") as mock_retrieve_by_embedding:
                    mock_build_index.return_value = ("embedded-index",)
                    mock_retrieve_by_embedding.return_value = [
                        RetrievalNode(
                            node_id="tasks/call-taylor-reed-at-examplecorp-about-the-invoice",
                            title="Call Taylor Reed at ExampleCorp about the invoice",
                            node_type="sprockets/task",
                            path=vault / "Sprockets" / "tasks" / "call-taylor-reed-at-examplecorp-about-the-invoice.md",
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

            with patch("specialists.rudi.embeddings.build_embedding_index") as mock_build_index:
                with patch("specialists.rudi.embeddings.retrieve_by_embedding") as mock_retrieve_by_embedding:
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

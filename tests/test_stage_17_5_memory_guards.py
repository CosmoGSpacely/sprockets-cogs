import unittest
from pathlib import Path

import memory_guards
from retrieval_types import RetrievalNode


class Stage175MemoryGuardTests(unittest.TestCase):
    def test_top_hierarchy_parent_title_uses_first_hierarchy_node(self):
        project = RetrievalNode(
            node_id="projects/production",
            title="Learn how to bring a project to production",
            node_type="sprockets/project",
            path=Path("production.md"),
        )

        title = memory_guards.top_hierarchy_parent_title(
            (project,),
            {"sprockets/area", "sprockets/goal", "sprockets/project"},
        )

        self.assertEqual(title, "Learn how to bring a project to production")

    def test_memory_parent_trace_records_selected_parent(self):
        project = RetrievalNode(
            node_id="projects/production",
            title="Learn how to bring a project to production",
            node_type="sprockets/project",
            path=Path("production.md"),
        )
        note = RetrievalNode(
            node_id="notes/production",
            title="Production note",
            node_type="sprockets/note",
            path=Path("production-note.md"),
        )

        trace = memory_guards.memory_parent_trace(
            (project, note),
            {"sprockets/area", "sprockets/goal", "sprockets/project"},
        )

        self.assertTrue(trace.selected)
        self.assertEqual(trace.retrieved_count, 2)
        self.assertEqual(trace.top_node_id, "projects/production")
        self.assertEqual(trace.top_node_type, "sprockets/project")
        self.assertEqual(trace.top_title, "Learn how to bring a project to production")
        self.assertEqual(trace.parent_node_id, "projects/production")
        self.assertEqual(trace.parent_node_type, "sprockets/project")
        self.assertEqual(trace.parent_title, "Learn how to bring a project to production")
        self.assertEqual(trace.reason, "top retrieval result is a hierarchy parent")

    def test_top_hierarchy_parent_title_ignores_non_hierarchy_node(self):
        contact = RetrievalNode(
            node_id="contacts/tom-reilly",
            title="Tom Reilly",
            node_type="sprockets/contact",
            path=Path("tom-reilly.md"),
        )

        title = memory_guards.top_hierarchy_parent_title(
            (contact,),
            {"sprockets/area", "sprockets/goal", "sprockets/project"},
        )

        self.assertEqual(title, "")

    def test_memory_parent_trace_selects_first_hierarchy_after_non_hierarchy_top(self):
        contact = RetrievalNode(
            node_id="contacts/tom-reilly",
            title="Tom Reilly",
            node_type="sprockets/contact",
            path=Path("tom-reilly.md"),
        )
        project = RetrievalNode(
            node_id="projects/production",
            title="Production",
            node_type="sprockets/project",
            path=Path("production.md"),
        )

        trace = memory_guards.memory_parent_trace(
            (contact, project),
            {"sprockets/area", "sprockets/goal", "sprockets/project"},
        )

        self.assertTrue(trace.selected)
        self.assertEqual(trace.retrieved_count, 2)
        self.assertEqual(trace.top_node_id, "contacts/tom-reilly")
        self.assertEqual(trace.top_node_type, "sprockets/contact")
        self.assertEqual(trace.parent_node_id, "projects/production")
        self.assertEqual(trace.parent_node_type, "sprockets/project")
        self.assertEqual(trace.parent_title, "Production")
        self.assertEqual(trace.reason, "first hierarchy result selected after non-hierarchy result")

    def test_memory_parent_trace_records_no_hierarchy_result(self):
        contact = RetrievalNode(
            node_id="contacts/tom-reilly",
            title="Tom Reilly",
            node_type="sprockets/contact",
            path=Path("tom-reilly.md"),
        )

        trace = memory_guards.memory_parent_trace(
            (contact,),
            {"sprockets/area", "sprockets/goal", "sprockets/project"},
        )

        self.assertFalse(trace.selected)
        self.assertEqual(trace.retrieved_count, 1)
        self.assertEqual(trace.top_node_id, "contacts/tom-reilly")
        self.assertEqual(trace.parent_title, "")
        self.assertEqual(trace.reason, "no hierarchy parent in retrieved nodes")

    def test_memory_parent_trace_records_empty_retrieval(self):
        trace = memory_guards.memory_parent_trace(
            (),
            {"sprockets/area", "sprockets/goal", "sprockets/project"},
        )

        self.assertFalse(trace.selected)
        self.assertEqual(trace.retrieved_count, 0)
        self.assertEqual(trace.reason, "no retrieved nodes")

    def test_apply_memory_parent_title_preserves_existing_hints_and_daily_items(self):
        classified = [
            {
                "node_type": "sprockets/task",
                "title": "Draft checklist",
                "confidence": "high",
            },
            {
                "node_type": "sprockets/note",
                "title": "Existing note",
                "parent_hint": "Phase 3",
                "confidence": "high",
            },
            {
                "node_type": "cogs/daily",
                "item_text": "Draft checklist",
                "date": "2026-05-04",
                "confidence": "high",
            },
        ]

        result = memory_guards.apply_memory_parent_title(classified, "Production")

        self.assertEqual(result[0]["parent_hint"], "Production")
        self.assertEqual(result[1]["parent_hint"], "Phase 3")
        self.assertNotIn("parent_hint", result[2])

    def test_ensure_memory_hierarchy_tasks_adds_missing_task_and_reports_title(self):
        raw_nodes = [
            {
                "raw": "Need to draft a deployment checklist.",
                "type_hint": "task",
            }
        ]
        classified = [
            {
                "node_type": "cogs/daily",
                "item_text": "Draft a deployment checklist",
                "date": "2026-05-04",
                "confidence": "high",
            }
        ]

        result, added_titles = memory_guards.ensure_memory_hierarchy_tasks(
            raw_nodes,
            classified,
            "Production",
            "2026-05-04",
        )

        self.assertEqual(added_titles, ("Draft a deployment checklist.",))
        self.assertEqual(result[1]["node_type"], "sprockets/task")
        self.assertEqual(result[1]["parent_hint"], "Production")

    def test_ensure_memory_hierarchy_tasks_preserves_existing_task(self):
        raw_nodes = [
            {
                "raw": "Need to draft a deployment checklist",
                "type_hint": "task",
            }
        ]
        classified = [
            {
                "node_type": "sprockets/task",
                "title": "Draft a deployment checklist",
                "confidence": "high",
            }
        ]

        result, added_titles = memory_guards.ensure_memory_hierarchy_tasks(
            raw_nodes,
            classified,
            "Production",
            "2026-05-04",
        )

        self.assertEqual(result, classified)
        self.assertEqual(added_titles, ())


if __name__ == "__main__":
    unittest.main()

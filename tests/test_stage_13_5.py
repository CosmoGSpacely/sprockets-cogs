import json
import importlib
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import specialists.rosie.loop as agentic_loop
import specialists.rudi.entity_state as entity_state
import specialists.rudi.fallback_eval as fallback_eval
import specialists.rudi.openai_fallback as openai_fallback
import specialists.jane.review as review
from substrate.models import validate_node


class Stage135HardeningTests(unittest.TestCase):
    def test_agentic_loop_paths_can_be_configured_from_environment(self):
        original_env = os.environ.copy()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                os.environ["SPROCKETS_COGS_SC_ROOT"] = str(root / "sc")
                os.environ["SPROCKETS_COGS_VAULT_DIR"] = str(root / "vault")
                reloaded = importlib.reload(agentic_loop)

                self.assertEqual(reloaded.INPUT_DIR, root / "sc" / "input")
                self.assertEqual(reloaded.PROCESSING_DIR, root / "sc" / "processing")
                self.assertEqual(reloaded.ARCHIVE_DIR, root / "sc" / "archive")
                self.assertEqual(reloaded.OUTPUT_DIR, root / "sc" / "output")
                self.assertEqual(reloaded.VAULT_DIR, root / "vault")
                self.assertEqual(reloaded.DAILY_DIR, root / "vault" / "Cogs")
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(agentic_loop)

    def test_entity_state_path_can_be_configured_from_environment(self):
        original_env = os.environ.copy()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                state_path = Path(tmp) / "state.json"
                os.environ["SPROCKETS_COGS_ENTITY_STATE_PATH"] = str(state_path)
                reloaded = importlib.reload(entity_state)

                self.assertEqual(reloaded.STATE_PATH, state_path)
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(entity_state)

    def test_process_existing_inputs_processes_sorted_input_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp)
            (input_dir / "b.input").write_text("b")
            (input_dir / "a.input").write_text("a")
            (input_dir / "ignore.txt").write_text("nope")

            processed = []

            def fake_process(path):
                processed.append(path.name)

            with patch.object(agentic_loop, "process_input", side_effect=fake_process):
                count = agentic_loop.process_existing_inputs(input_dir)

            self.assertEqual(count, 2)
            self.assertEqual(processed, ["a.input", "b.input"])

    def test_input_handler_processes_moved_input_files(self):
        class Event:
            is_directory = False
            src_path = "/tmp/.adapter.input.tmp"
            dest_path = "/tmp/adapter.input"

        processed = []

        def fake_process(path):
            processed.append(Path(path).name)

        with (
            patch.object(agentic_loop, "process_input", side_effect=fake_process),
            patch.object(agentic_loop.time, "sleep"),
        ):
            agentic_loop.InputHandler().on_moved(Event())

        self.assertEqual(processed, ["adapter.input"])

    def test_ensure_runtime_dirs_creates_operational_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {
                "INPUT_DIR": root / "input",
                "PROCESSING_DIR": root / "processing",
                "ARCHIVE_DIR": root / "archive",
                "OUTPUT_DIR": root / "output",
            }

            patches = [
                patch.object(agentic_loop, name, path)
                for name, path in paths.items()
            ]
            for active_patch in patches:
                active_patch.start()
            try:
                agentic_loop.ensure_runtime_dirs()
            finally:
                for active_patch in reversed(patches):
                    active_patch.stop()

            for path in paths.values():
                self.assertTrue(path.is_dir())

    def test_validate_output_separates_valid_low_confidence_and_invalid(self):
        raw_nodes = [
            {
                "node_type": "cogs/daily",
                "item_text": "DENTIST 8am",
                "date": "2026-05-02",
                "confidence": "high",
            },
            {
                "node_type": "sprockets/contact",
                "title": "Alex Rivera",
                "confidence": "low",
            },
            {
                "node_type": "unknown/type",
                "title": "Mystery",
                "confidence": "high",
            },
        ]

        valid, invalid = agentic_loop.validate_output(raw_nodes)

        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0].node_type, "cogs/daily")
        self.assertEqual(len(invalid), 2)
        self.assertEqual(invalid[0][2], "confidence: low")
        self.assertIn("Unknown node_type", invalid[1][2])

    def test_ensure_cogs_companions_adds_missing_daily_for_task(self):
        classified = [
            {
                "node_type": "sprockets/task",
                "title": "Send proposal to Alex",
                "date": "2026-05-04",
                "status": "active",
                "confidence": "high",
            }
        ]

        result = agentic_loop.ensure_cogs_companions(classified)

        self.assertEqual(len(result), 2)
        companion = result[1]
        self.assertEqual(companion["node_type"], "cogs/daily")
        self.assertEqual(companion["item_text"], "Send proposal to Alex")
        self.assertEqual(companion["date"], "2026-05-04")

    def test_ensure_cogs_companions_strips_invalid_task_date(self):
        classified = [
            {
                "node_type": "sprockets/task",
                "title": "Review memory context",
                "date": "2026-05-04Already in today's note: Call Alex",
                "status": "active",
                "confidence": "high",
            }
        ]

        result = agentic_loop.ensure_cogs_companions(classified)

        self.assertEqual(len(result), 1)
        self.assertNotIn("date", result[0])

    def test_openai_fallback_routes_valid_candidates_to_review(self):
        raw_nodes = [{"raw": "call Alex", "type_hint": "task"}]
        candidates = [
            {
                "node_type": "sprockets/task",
                "title": "Call Alex",
                "date": "2026-05-02",
                "status": "active",
                "confidence": "high",
            }
        ]
        written = []

        with patch.object(agentic_loop, "openai_fallback_enabled", return_value=True), \
             patch.object(agentic_loop, "classify_nodes_with_openai_fallback", return_value=candidates), \
             patch.object(agentic_loop, "write_to_review", side_effect=lambda raw, reason: written.append((raw, reason))):
            routed = agentic_loop.route_openai_fallback_to_review(
                raw_nodes,
                "Already in today's note: (none)",
                "confidence: low",
            )

        self.assertTrue(routed)
        self.assertEqual(len(written), 2)
        self.assertEqual(written[0][0]["node_type"], "sprockets/task")
        self.assertEqual(written[0][1], "openai_fallback_candidate: confidence: low")
        self.assertEqual(written[1][0]["node_type"], "cogs/daily")

    def test_openai_fallback_schema_is_strict_responses_api_shape(self):
        schema = openai_fallback._openai_classify_schema()
        node_schema = schema["properties"]["nodes"]["items"]

        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(node_schema["additionalProperties"])
        self.assertEqual(set(node_schema["required"]), set(node_schema["properties"]))
        self.assertIn("status", node_schema["required"])
        self.assertIn("parent_hint", node_schema["required"])

    def test_openai_fallback_user_message_marks_candidates_for_review(self):
        message = openai_fallback._fallback_user_message(
            [{"raw": "Call Alex", "type_hint": "task"}],
            "Already in today's note: (none)",
            "confidence: low",
        )

        self.assertIn("Reason: confidence: low", message)
        self.assertIn("review candidate", message)
        self.assertIn("never leave item_text empty", message)
        self.assertIn("Call Alex", message)

    def test_openai_fallback_normalizes_daily_item_text_from_title(self):
        nodes = openai_fallback._normalize_fallback_nodes([
            {
                "node_type": "cogs/daily",
                "title": "WFH",
                "item_text": "",
                "date": "2026-05-04",
                "status": "active",
                "confidence": "high",
                "parent_hint": "",
            }
        ])

        self.assertEqual(nodes[0]["item_text"], "WFH")

    def test_openai_fallback_response_text_raises_on_refusal(self):
        class Content:
            refusal = "Cannot comply"
            text = ""

        class Item:
            content = [Content()]

        class Response:
            output_text = ""
            output = [Item()]

        with self.assertRaisesRegex(ValueError, "OpenAI fallback refused"):
            openai_fallback._response_text(Response())

    def test_openai_error_summary_includes_quota_code_without_traceback_noise(self):
        class QuotaError(Exception):
            status_code = 429
            body = {
                "error": {
                    "message": "You exceeded your current quota",
                    "type": "insufficient_quota",
                    "code": "insufficient_quota",
                }
            }

        summary = openai_fallback._openai_error_summary(QuotaError("nope"))

        self.assertIn("429", summary)
        self.assertIn("insufficient_quota", summary)
        self.assertIn("You exceeded your current quota", summary)

    def test_fallback_eval_scores_expected_candidates(self):
        case = fallback_eval.CASES[2]
        candidates = [
            {
                "node_type": "sprockets/note",
                "title": "Review-first fallback",
                "item_text": "review-first fallback keeps the vault safer",
                "date": "2026-05-03",
                "status": "active",
                "confidence": "high",
                "parent_hint": "Phase 2 - Hardening",
            }
        ]

        passed, issues = fallback_eval._score_case(case, candidates)

        self.assertTrue(passed)
        self.assertEqual(issues, [])

    def test_fallback_eval_flags_missing_task_companion(self):
        case = fallback_eval.CASES[0]
        candidates = [
            {
                "node_type": "sprockets/task",
                "title": "Call Alex",
                "item_text": "Call Alex",
                "date": "2026-05-07",
                "status": "active",
                "confidence": "high",
                "parent_hint": "",
            }
        ]

        passed, issues = fallback_eval._score_case(case, candidates)

        self.assertFalse(passed)
        self.assertIn("sprockets/task candidate missing cogs/daily companion", issues)

    def test_fallback_eval_selects_named_case(self):
        selected = fallback_eval._select_cases("specific-two-day-setting")

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].name, "specific-two-day-setting")

    def test_fallback_eval_rejects_unknown_case(self):
        with self.assertRaises(SystemExit):
            fallback_eval._select_cases("not-a-case")

    def test_fallback_eval_result_summarizes_valid_candidates(self):
        case = fallback_eval.CASES[0]
        candidates = [
            {
                "node_type": "sprockets/task",
                "title": "Call Alex",
                "item_text": "Call Alex",
                "date": "2026-05-07",
                "status": "active",
                "confidence": "high",
                "parent_hint": "",
            },
            {
                "node_type": "cogs/daily",
                "title": "Call Alex",
                "item_text": "Call Alex",
                "date": "2026-05-07",
                "status": "active",
                "confidence": "high",
                "parent_hint": "",
            },
        ]

        result = fallback_eval._evaluate_case(case, candidates)

        self.assertEqual(result.case_name, "relative-date-task")
        self.assertEqual(result.candidate_count, 2)
        self.assertEqual(result.valid_count, 2)
        self.assertTrue(result.passed)

    def test_fallback_eval_does_not_duplicate_validation_issues(self):
        case = fallback_eval.CASES[1]
        candidates = [
            {
                "node_type": "cogs/daily",
                "title": "WFH",
                "item_text": "",
                "date": "2026-05-04",
                "status": "active",
                "confidence": "high",
                "parent_hint": "",
            }
        ]

        result = fallback_eval._evaluate_case(case, candidates)

        self.assertEqual(
            len([issue for issue in result.issues if "item_text cannot be empty" in issue]),
            1,
        )

    def test_fallback_eval_prints_promotion_criteria(self):
        stream = StringIO()

        with redirect_stdout(stream):
            fallback_eval.print_promotion_criteria()

        output = stream.getvalue()
        self.assertIn("Fallback promotion criteria", output)
        self.assertIn("review-first", output)
        self.assertIn("direct vault writes stay disabled", output)

    def test_openai_fallback_skips_when_disabled(self):
        with patch.object(agentic_loop, "openai_fallback_enabled", return_value=False), \
             patch.object(agentic_loop, "classify_nodes_with_openai_fallback") as fallback:
            routed = agentic_loop.route_openai_fallback_to_review(
                [{"raw": "call Alex", "type_hint": "task"}],
                "",
                "retry failed",
            )

        self.assertFalse(routed)
        fallback.assert_not_called()

    def test_process_input_routes_low_confidence_through_fallback_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            processing_dir = root / "processing"
            archive_dir = root / "archive"
            review_dir = root / "review"
            daily_dir = root / "daily"
            input_dir.mkdir()
            input_path = input_dir / "low.input"
            input_path.write_text("---\nsession_id: low-test\n---\n\nCall Alex.\n")

            raw_nodes = [{"raw": "Call Alex", "type_hint": "task"}]
            low_classified = [
                {
                    "node_type": "sprockets/task",
                    "title": "Call Alex",
                    "date": "2026-05-02",
                    "status": "active",
                    "confidence": "low",
                }
            ]
            fallback_classified = [
                {
                    "node_type": "sprockets/task",
                    "title": "Call Alex",
                    "date": "2026-05-02",
                    "status": "active",
                    "confidence": "high",
                }
            ]

            with patch.object(agentic_loop, "INPUT_DIR", input_dir), \
                 patch.object(agentic_loop, "PROCESSING_DIR", processing_dir), \
                 patch.object(agentic_loop, "ARCHIVE_DIR", archive_dir), \
                 patch.object(agentic_loop, "REVIEW_DIR", review_dir), \
                 patch.object(agentic_loop, "DAILY_DIR", daily_dir), \
                 patch.object(agentic_loop, "extract_nodes", return_value=raw_nodes), \
                 patch.object(agentic_loop, "classify_nodes", return_value=low_classified), \
                 patch.object(agentic_loop, "openai_fallback_enabled", return_value=True), \
                 patch.object(agentic_loop, "classify_nodes_with_openai_fallback", return_value=fallback_classified):
                agentic_loop.ensure_runtime_dirs()
                agentic_loop.process_input(input_path)

            review_files = sorted(review_dir.glob("*.md"))
            self.assertEqual(len(review_files), 2)
            review_text = "\n".join(path.read_text() for path in review_files)
            self.assertIn("openai_fallback_candidate: confidence: low", review_text)
            self.assertIn('"node_type": "sprockets/task"', review_text)
            self.assertIn('"node_type": "cogs/daily"', review_text)
            self.assertTrue((archive_dir / "low.input").exists())
            daily_files = list(daily_dir.glob("*.md"))
            self.assertEqual(len(daily_files), 1)
            self.assertIn("Processed 0 node(s)", daily_files[0].read_text())

    def test_find_duplicate_uses_fuzzy_slug_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "call-frank.md").write_text("---\n---\n")

            duplicate = agentic_loop._find_duplicate("Call Frank!", folder)

            self.assertIsNotNone(duplicate)
            self.assertEqual(duplicate.name, "call-frank.md")

    def test_write_to_review_writes_reason_and_raw_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            raw = {
                "node_type": "sprockets/task",
                "title": "Ambiguous task",
                "confidence": "low",
            }

            with patch.object(agentic_loop, "REVIEW_DIR", review_dir):
                agentic_loop.write_to_review(raw, "confidence: low")

            files = list(review_dir.glob("*.md"))
            self.assertEqual(len(files), 1)
            content = files[0].read_text()
            self.assertIn("**Reason:** confidence: low", content)
            self.assertIn(json.dumps(raw, indent=2), content)

    def test_write_to_review_avoids_same_second_filename_collisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            raw = {
                "node_type": "cogs/daily",
                "item_text": "Call Alex",
                "date": "2026-05-02",
                "confidence": "low",
            }

            with patch.object(agentic_loop, "REVIEW_DIR", review_dir):
                agentic_loop.write_to_review(raw, "one")
                agentic_loop.write_to_review(raw, "two")

            self.assertEqual(len(list(review_dir.glob("*.md"))), 2)

    def test_list_pending_summarizes_review_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            raw = {
                "node_type": "sprockets/task",
                "title": "Ambiguous task",
                "item_text": "Ambiguous task",
                "date": "2026-05-02",
                "confidence": "low",
            }
            (review_dir / "pending.md").write_text(
                "---\nnode_type: review\nreviewed: false\n---\n\n"
                "**Reason:** confidence: low\n\n"
                f"```json\n{json.dumps(raw, indent=2)}\n```\n"
            )

            items = review.list_pending(review_dir)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["file"], "pending.md")
            self.assertEqual(items[0]["reason"], "confidence: low")
            self.assertEqual(items[0]["source"], "local low confidence")
            self.assertEqual(items[0]["node_type"], "sprockets/task")
            self.assertEqual(items[0]["title"], "Ambiguous task")
            self.assertTrue(items[0]["parseable"])

    def test_list_pending_identifies_openai_fallback_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            raw = {
                "node_type": "sprockets/task",
                "title": "Call Alex",
                "item_text": "Call Alex",
                "date": "2026-05-02",
                "confidence": "high",
            }
            (review_dir / "openai.md").write_text(
                "---\nnode_type: review\nreviewed: false\n---\n\n"
                "**Reason:** openai_fallback_candidate: confidence: low\n\n"
                f"```json\n{json.dumps(raw, indent=2)}\n```\n"
            )

            items = review.list_pending(review_dir)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["source"], "openai fallback candidate")

    def test_list_pending_maps_known_review_reason_sources(self):
        cases = [
            ("openai_fallback_invalid: retry failed", "openai fallback invalid"),
            ("ambiguous hierarchy parent_hint: 'Phase 2' matched A, B", "hierarchy ambiguity"),
            ("retry failed: cogs/daily: date must be YYYY-MM-DD", "local retry failure"),
            ("confidence: low", "local low confidence"),
            ("manual inspection requested", "local review"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            raw = {
                "node_type": "sprockets/task",
                "title": "Review source taxonomy",
                "item_text": "Review source taxonomy",
                "date": "",
                "confidence": "low",
            }
            for index, (reason, _) in enumerate(cases):
                (review_dir / f"pending-{index}.md").write_text(
                    "---\nnode_type: review\nreviewed: false\n---\n\n"
                    f"**Reason:** {reason}\n\n"
                    f"```json\n{json.dumps(raw, indent=2)}\n```\n"
                )

            items = review.list_pending(review_dir)

            self.assertEqual(len(items), len(cases))
            sources_by_reason = {item["reason"]: item["source"] for item in items}
            for reason, source in cases:
                with self.subTest(reason=reason):
                    self.assertEqual(sources_by_reason[reason], source)

    def test_review_report_summarizes_queue_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            valid_task = {
                "node_type": "sprockets/task",
                "title": "Review report task",
                "item_text": "Review report task",
                "date": "2026-05-02",
                "confidence": "low",
            }
            valid_note = {
                "node_type": "sprockets/note",
                "title": "Review report note",
                "body": "Review report note",
                "confidence": "high",
            }
            (review_dir / "task.md").write_text(
                "---\nnode_type: review\nreviewed: false\n---\n\n"
                "**Reason:** confidence: low\n\n"
                f"```json\n{json.dumps(valid_task, indent=2)}\n```\n"
            )
            (review_dir / "note.md").write_text(
                "---\nnode_type: review\nreviewed: false\n---\n\n"
                "**Reason:** openai_fallback_candidate: confidence: low\n\n"
                f"```json\n{json.dumps(valid_note, indent=2)}\n```\n"
            )
            (review_dir / "broken.md").write_text(
                "---\nnode_type: review\nreviewed: false\n---\n\n"
                "**Reason:** retry failed\n\n"
                "```json\nnot json\n```\n"
            )

            report = review.review_report(review_dir)

            self.assertEqual(report["total"], 3)
            self.assertEqual(report["parseable"], 2)
            self.assertEqual(report["unparseable"], 1)
            self.assertEqual(report["by_source"]["local low confidence"], 1)
            self.assertEqual(report["by_source"]["openai fallback candidate"], 1)
            self.assertEqual(report["by_source"]["local retry failure"], 1)
            self.assertEqual(report["by_node_type"]["sprockets/task"], 1)
            self.assertEqual(report["by_node_type"]["sprockets/note"], 1)
            self.assertEqual(report["by_node_type"]["?"], 1)
            self.assertEqual(report["by_confidence"]["low"], 1)
            self.assertEqual(report["by_confidence"]["high"], 1)
            self.assertEqual(report["by_confidence"]["?"], 1)
            self.assertEqual(report["by_reason"]["confidence: low"], 1)
            self.assertEqual(report["by_reason"]["openai_fallback_candidate: confidence: low"], 1)
            self.assertEqual(report["by_reason"]["retry failed"], 1)

    def test_review_packet_preview_formats_markdown_without_full_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            raw = {
                "node_type": "sprockets/task",
                "title": "Review markdown packet",
                "item_text": "Review markdown packet",
                "date": "2026-05-02",
                "confidence": "low",
            }
            (review_dir / "pending.md").write_text(
                "---\nnode_type: review\nreviewed: false\n---\n\n"
                "**Reason:** confidence: low\n\n"
                f"```json\n{json.dumps(raw, indent=2)}\n```\n"
            )

            packet = review.review_packet_markdown(review_dir)

            self.assertTrue(packet.startswith("---\ntype: review-packet\npacket_schema: jane-vault-action-v1\n"))
            self.assertIn("status: pending", packet)
            self.assertIn("item_count: 1", packet)
            self.assertIn("queue_fingerprint:", packet)
            self.assertIn("review_files:\n  - pending.md", packet)
            self.assertIn("# Sprockets-Cogs Review Packet", packet)
            self.assertIn("Vault action surface", packet)
            self.assertIn("- Total: 1", packet)
            self.assertIn("| File | Source | Type | Confidence | Date | Title | Reason |", packet)
            self.assertIn("| pending.md | local low confidence | sprockets/task | low | 2026-05-02 | Review markdown packet | confidence: low |", packet)
            self.assertIn("## Vault Decision Surface", packet)
            self.assertIn("## Proposed Changes", packet)
            self.assertIn("### `pending.md`", packet)
            self.assertIn("- Proposed node: `sprockets/task`", packet)
            self.assertIn("- Item text: Review markdown packet", packet)
            self.assertNotIn(str(review_dir), packet)
            self.assertNotIn("```json", packet)

    def test_review_packet_preview_handles_empty_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            packet = review.review_packet_markdown(Path(tmp))

            self.assertIn("item_count: 0", packet)
            self.assertIn("- Total: 0", packet)
            self.assertIn("No pending review items.", packet)

    def test_list_pending_marks_unparseable_review_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)
            (review_dir / "broken.md").write_text(
                "---\nnode_type: review\nreviewed: false\n---\n\n"
                "**Reason:** retry failed\n\n"
                "```json\nnot json\n```\n"
            )

            items = review.list_pending(review_dir)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["file"], "broken.md")
            self.assertEqual(items[0]["reason"], "retry failed")
            self.assertFalse(items[0]["parseable"])

    def test_entity_state_tracks_hot_contact(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "entity_state.json"
            node = validate_node({
                "node_type": "sprockets/contact",
                "title": "Alex Rivera",
                "confidence": "high",
            })

            with patch.object(entity_state, "STATE_PATH", state_path):
                entity_state.upsert_entity(node)
                hot = entity_state.get_entities_by_tier("hot")

            self.assertEqual(len(hot), 1)
            self.assertEqual(hot[0]["title"], "Alex Rivera")
            self.assertEqual(hot[0]["node_type"], "sprockets/contact")


if __name__ == "__main__":
    unittest.main()

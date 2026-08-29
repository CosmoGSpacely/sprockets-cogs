import json
import unittest

from intents.models import (
    AuthorityAssessment,
    Confidence,
    ContextScope,
    IntentClass,
    IntentClassification,
    NormalizedInput,
    RequiredGuard,
    RuntimeTimeContext,
    SourceAuthority,
    SourceMetadata,
    SourceType,
    SuggestedRoute,
)


class Stage92IntentModelTests(unittest.TestCase):
    def test_stage_81_intent_taxonomy_is_encoded(self):
        self.assertEqual(
            {item.value for item in IntentClass},
            {
                "ordinary_capture",
                "structural_proposal",
                "planning_update",
                "graph_projection",
                "rich_source_ingestion",
                "review_decision",
                "operational_command",
            },
        )

    def test_runtime_time_context_is_volatile_and_json_friendly(self):
        context = RuntimeTimeContext(
            local_date="2026-06-09",
            local_time="09:15",
            timezone="America/New_York",
            generated_at="2026-06-09T09:15:00-04:00",
        )

        serialized = context.to_dict()

        self.assertEqual(serialized["scope"], "volatile_runtime")
        self.assertEqual(serialized["timezone"], "America/New_York")
        json.dumps(serialized)

    def test_source_metadata_preserves_rich_source_and_model_provenance(self):
        source = SourceMetadata(
            source_type=SourceType.IMAGE,
            source_authority=SourceAuthority.LOCAL_MODEL,
            locator="vault://resources/tractor-tire-photo.jpg",
            adapter="cogswell-preview",
            confidence=Confidence.MEDIUM,
            provider="ollama",
            model="gemma4:12b-16k-cosmo",
            provenance=("direct image probe",),
        )

        serialized = source.to_dict()

        self.assertEqual(serialized["source_type"], "image")
        self.assertEqual(serialized["source_authority"], "local_model")
        self.assertEqual(serialized["provenance"], ["direct image probe"])
        json.dumps(serialized)

    def test_authority_assessment_separates_detected_risk_from_model_violation(self):
        authority = AuthorityAssessment(
            detected_authority_risks=("durable hierarchy creation",),
            model_authority_violation=False,
            required_guard=RequiredGuard.DETERMINISTIC_PACKET_REQUIRED,
            packet_required_suggestion=True,
        )

        serialized = authority.to_dict()

        self.assertEqual(serialized["detected_authority_risks"], ["durable hierarchy creation"])
        self.assertFalse(serialized["model_authority_violation"])
        self.assertEqual(serialized["required_guard"], "deterministic_packet_required")
        self.assertTrue(serialized["packet_required_suggestion"])

    def test_normalized_input_and_classification_represent_stage_87_concepts(self):
        source = SourceMetadata(
            source_type=SourceType.TEXT,
            source_authority=SourceAuthority.USER,
            locator="synthetic://stage87/fx87-004",
            adapter="manual",
            confidence=Confidence.HIGH,
            provenance=("Stage 87 accepted fixture",),
        )
        runtime_time = RuntimeTimeContext(
            local_date="2026-06-09",
            timezone="America/New_York",
            scope=ContextScope.FIXTURE,
            freshness="synthetic_fixture",
        )
        normalized = NormalizedInput(
            input_id="FX87-004",
            raw_text="Area: Learning agentic AI. Goal: Build Sprockets-Cogs.",
            normalized_text="Area/goal/task structural proposal from Stage 64 regression.",
            source=source,
            runtime_time=runtime_time,
            context_scope=ContextScope.VOLATILE_SOURCE,
            notes=("primary regression fixture",),
        )
        classification = IntentClassification(
            intent_class=IntentClass.STRUCTURAL_PROPOSAL,
            confidence=Confidence.HIGH,
            authority=AuthorityAssessment(
                detected_authority_risks=("task flattening risk",),
                required_guard=RequiredGuard.DETERMINISTIC_PACKET_REQUIRED,
                packet_required_suggestion=True,
            ),
            evidence=("area/goal language",),
            uncertainty=("requires review-first graph interpretation",),
            suggested_route=(
                SuggestedRoute.ROSIE,
                SuggestedRoute.RUDI,
                SuggestedRoute.JANE,
                SuggestedRoute.VALIDATORS,
                SuggestedRoute.AUDIT,
            ),
        )

        self.assertEqual(normalized.to_dict()["input_id"], "FX87-004")
        self.assertEqual(classification.to_dict()["intent_class"], "structural_proposal")
        self.assertEqual(classification.to_dict()["suggested_route"][1], "rudi")

    def test_empty_required_text_is_rejected(self):
        with self.assertRaises(ValueError):
            RuntimeTimeContext(local_date=" ", timezone="America/New_York")

        with self.assertRaises(ValueError):
            NormalizedInput(
                input_id="FX87-empty",
                raw_text=" ",
                normalized_text="empty",
                source=SourceMetadata(SourceType.TEXT, SourceAuthority.TEST),
                runtime_time=RuntimeTimeContext("2026-06-09", "America/New_York"),
            )


if __name__ == "__main__":
    unittest.main()

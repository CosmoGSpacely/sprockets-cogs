import unittest

from pydantic import ValidationError

from graph.fixtures import fixture_paths, load_fixture
from graph.proposals import (
    AuditDecision,
    ReviewProposal,
    audit_decisions_from_fixture,
    proposal_from_fixture,
)


class Stage78ProposalAuditModelTests(unittest.TestCase):
    def test_review_proposal_fixture_wraps_mutation_command(self):
        fixture = next(
            load_fixture(path)
            for path in fixture_paths()
            if load_fixture(path)["fixture_id"] == "proposal_mutation_command"
        )

        proposal = proposal_from_fixture(fixture)

        self.assertEqual(proposal.kind, "review_proposal")
        self.assertEqual(
            proposal.mutation_command.operation,
            "create_sprocket_and_bridge",
        )
        self.assertLess(proposal.packet_word_count(), 800)

    def test_audit_fixture_loads_automatic_and_reviewed_decisions(self):
        fixture = next(
            load_fixture(path)
            for path in fixture_paths()
            if load_fixture(path)["fixture_id"] == "audit_examples"
        )

        decisions = audit_decisions_from_fixture(fixture)

        self.assertEqual(decisions[0].decision, "applied_automatic")
        self.assertEqual(decisions[0].decider, "substrate")
        self.assertEqual(decisions[1].decision, "accepted")
        self.assertEqual(decisions[1].proposal_id, "proposal-create-tom-contact")

    def test_rejected_and_edited_decisions_are_supported(self):
        rejected = AuditDecision(
            id="audit-reject-ambiguous-target",
            mutation_id="mutation-create-tom-contact-and-bridge",
            proposal_id="proposal-create-tom-contact",
            decision="rejected",
            decider="user",
            reason="Tom was the wrong contact target.",
            timestamp="2026-06-05T07:45:00-04:00",
        )
        edited = AuditDecision(
            id="audit-edit-target",
            mutation_id="mutation-create-tom-contact-and-bridge",
            proposal_id="proposal-create-tom-contact",
            decision="edited",
            decider="user",
            reason="Changed Tom to Thomas Rivera.",
            timestamp="2026-06-05T07:46:00-04:00",
            edits=[{"field": "payload.sprocket.text", "to": "Thomas Rivera"}],
        )

        self.assertEqual(rejected.decision, "rejected")
        self.assertEqual(edited.edits[0]["to"], "Thomas Rivera")

    def test_proposals_and_audits_reject_empty_required_fields(self):
        with self.assertRaises(ValidationError):
            ReviewProposal(
                id="",
                reason="missing id",
                display_text="Create contact",
                mutation_command={
                    "id": "mutation",
                    "operation": "add_bridge",
                    "target_layer": "product_graph",
                    "review_class": "review_first",
                    "payload": {"bridge": "example"},
                },
            )

        with self.assertRaises(ValidationError):
            AuditDecision(
                id="audit-empty",
                mutation_id="",
                decision="accepted",
                decider="user",
                reason="empty mutation id",
                timestamp="2026-06-05T07:47:00-04:00",
            )


if __name__ == "__main__":
    unittest.main()

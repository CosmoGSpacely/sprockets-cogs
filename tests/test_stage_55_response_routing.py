import unittest

import response_routing


class Stage55ResponseRoutingTests(unittest.TestCase):
    def test_context_from_frontmatter_extracts_adapter_metadata(self):
        context = response_routing.response_context_from_frontmatter(
            {
                "source": "telegram",
                "session_id": "telegram-chat-888",
                "source_id": "chat-888-message-42",
                "idempotency_key": "telegram:888:42",
                "metadata": {
                    "telegram_chat_id": "888",
                    "telegram_message_id": "42",
                },
            },
            fallback_session_id="fallback",
        )

        self.assertEqual(context.source, "telegram")
        self.assertEqual(context.session_id, "telegram-chat-888")
        self.assertEqual(context.source_id, "chat-888-message-42")
        self.assertEqual(context.metadata["telegram_chat_id"], "888")

    def test_context_defaults_to_local_source(self):
        context = response_routing.response_context_from_frontmatter(
            {},
            fallback_session_id="local-session",
        )

        self.assertEqual(context.source, "local")
        self.assertEqual(context.session_id, "local-session")

    def test_telegram_acknowledgement_would_send_to_chat(self):
        context = response_routing.ResponseContext(
            source="telegram",
            session_id="telegram-chat-888",
            metadata={"telegram_chat_id": "888"},
        )
        envelope = response_routing.ResponseEnvelope(
            context=context,
            response_type=response_routing.ResponseType.ACKNOWLEDGEMENT,
            text="Queued.",
        )

        route = response_routing.route_response(envelope)

        self.assertEqual(route.sink, "telegram")
        self.assertTrue(route.would_send)
        self.assertEqual(route.target, "888")

    def test_review_required_stays_local_even_for_telegram(self):
        context = response_routing.ResponseContext(
            source="telegram",
            session_id="telegram-chat-888",
            metadata={"telegram_chat_id": "888"},
        )
        envelope = response_routing.ResponseEnvelope(
            context=context,
            response_type=response_routing.ResponseType.REVIEW_REQUIRED,
            text="Needs review.",
        )

        route = response_routing.route_response(envelope)

        self.assertEqual(route.sink, "local")
        self.assertFalse(route.would_send)
        self.assertIn("review-first", route.reason)

    def test_missing_telegram_chat_id_stays_local(self):
        envelope = response_routing.ResponseEnvelope(
            context=response_routing.ResponseContext(
                source="telegram",
                session_id="telegram-chat-missing",
            ),
            response_type=response_routing.ResponseType.PROCESSED,
            text="Processed.",
        )

        route = response_routing.route_response(envelope)

        self.assertEqual(route.sink, "local")
        self.assertFalse(route.would_send)
        self.assertIn("missing chat id", route.reason)

    def test_preview_is_read_only_and_names_target(self):
        context = response_routing.ResponseContext(
            source="telegram",
            session_id="telegram-chat-888",
            metadata={"telegram_chat_id": "888"},
        )
        envelope = response_routing.ResponseEnvelope(
            context=context,
            response_type=response_routing.ResponseType.PROCESSED,
            text="Processed 1 node.",
        )

        preview = response_routing.format_response_preview(envelope)

        self.assertIn("Response route preview", preview)
        self.assertIn("- writes: no", preview)
        self.assertIn("- sink: telegram", preview)
        self.assertIn("- would_send: yes", preview)
        self.assertIn("- target: 888", preview)
        self.assertIn("Processed 1 node.", preview)


if __name__ == "__main__":
    unittest.main()

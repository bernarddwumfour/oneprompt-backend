import json
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.accounts.tests.factories import UserFactory
from apps.conversations.models import Message
from apps.conversations.tests.factories import ConversationFactory
from apps.credits.models import CreditWallet
from apps.credits.services.ledger_service import promotional_credit
from apps.providers.models import CapabilityRoute
from common.jwt import encode_access_token


class SendMessageViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = UserFactory()
        self.wallet = CreditWallet.objects.create(user=self.user, currency="USD")
        promotional_credit(
            wallet=self.wallet, amount=Decimal("5.00"), idempotency_key="fund", reference={}
        )
        self.conversation = ConversationFactory(user=self.user)
        self.token = encode_access_token(self.user)

        sleep_patcher = patch("apps.providers.stub_provider.time.sleep")
        sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    def _post_message(self, prompt="Hello", **headers):
        return self.client.post(
            f"/api/v1/conversations/{self.conversation.id}/messages",
            data=json.dumps({"prompt": prompt}),
            content_type="application/json",
            **headers,
        )

    def test_send_message_returns_a_well_formed_event_stream(self):
        response = self._post_message(HTTP_AUTHORIZATION=f"Bearer {self.token}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get("Content-Type"), "text/event-stream")

        content = b"".join(response.streaming_content).decode()
        self.assertIn("event: start", content)
        self.assertIn("event: chunk", content)
        self.assertIn("event: done", content)

    def test_send_message_requires_authentication(self):
        response = self._post_message()
        self.assertEqual(response.status_code, 401)

    def test_send_message_rejects_another_users_conversation(self):
        other_token = encode_access_token(UserFactory())
        response = self._post_message(HTTP_AUTHORIZATION=f"Bearer {other_token}")
        self.assertEqual(response.status_code, 404)

    def test_send_message_rejects_empty_prompt(self):
        response = self._post_message(prompt="   ", HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(response.status_code, 422)

    def test_send_message_can_stream_up_to_three_models_for_one_user_message(self):
        CapabilityRoute.objects.filter(
            slug__in=["fast", "deepseek-flash"]
        ).update(is_active=True)
        response = self.client.post(
            f"/api/v1/conversations/{self.conversation.id}/messages",
            data=json.dumps(
                {
                    "prompt": "@Fast @DeepSeek Compare these approaches",
                    "model_prompt": "Compare these approaches",
                    "capabilities": ["fast", "deepseek-flash"],
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content).decode()
        self.assertIn("event: batch_start", content)
        self.assertEqual(content.count("event: done"), 2)
        self.assertIn("event: complete", content)
        self.assertEqual(
            Message.objects.filter(
                conversation=self.conversation,
                role="user",
            ).count(),
            1,
        )
        self.assertEqual(
            Message.objects.filter(
                conversation=self.conversation,
                role="assistant",
            ).count(),
            2,
        )

    def test_send_message_rejects_more_than_three_models(self):
        response = self.client.post(
            f"/api/v1/conversations/{self.conversation.id}/messages",
            data=json.dumps(
                {
                    "prompt": "Compare this",
                    "capabilities": ["one", "two", "three", "four"],
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 422)

from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.accounts.tests.factories import UserFactory
from apps.conversations.models import Message, ModelInvocation
from apps.conversations.services.chat_service import send_message
from apps.conversations.tests.factories import ConversationFactory
from apps.credits.models import CreditWallet
from apps.credits.services.ledger_service import promotional_credit
from apps.providers.models import CapabilityRoute


class ChatServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = UserFactory()
        self.wallet = CreditWallet.objects.create(user=self.user, currency="USD")
        self.conversation = ConversationFactory(user=self.user)
        CapabilityRoute.objects.filter(slug="fast").update(is_active=True)

        sleep_patcher = patch("apps.providers.stub_provider.time.sleep")
        sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    def _fund(self, amount="5.00", key="fund"):
        promotional_credit(
            wallet=self.wallet, amount=Decimal(amount), idempotency_key=key, reference={}
        )

    def test_happy_path_charges_wallet_and_resolves_reservation(self):
        self._fund()

        gen = send_message(
            conversation=self.conversation,
            user=self.user,
            prompt="Hello there",
            capability="fast",
        )
        events = list(gen)
        event_types = [e[0] for e in events]

        self.assertEqual(event_types[0], "batch_start")
        self.assertIn("done", event_types)
        self.assertEqual(event_types[-1], "complete")

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.reserved, Decimal("0.00"))
        self.assertLess(self.wallet.balance, Decimal("5.00"))

        invocation = ModelInvocation.objects.get(conversation=self.conversation)
        self.assertEqual(invocation.status, "succeeded")
        self.assertIsNotNone(invocation.capture_entry)
        self.assertEqual(
            Message.objects.filter(conversation=self.conversation, role="assistant").count(), 1
        )

    def test_insufficient_balance_raises_before_creating_any_rows(self):
        # Wallet has zero balance — no funding.
        with self.assertRaises(ValueError):
            send_message(
                conversation=self.conversation,
                user=self.user,
                prompt="Hello",
                capability="fast",
            )

        self.assertEqual(ModelInvocation.objects.filter(conversation=self.conversation).count(), 0)
        self.assertEqual(Message.objects.filter(conversation=self.conversation).count(), 0)

    def test_unknown_capability_raises_immediately(self):
        self._fund()
        with self.assertRaises(ValueError):
            send_message(
                conversation=self.conversation,
                user=self.user,
                prompt="hi",
                capability="does-not-exist",
            )

    def test_cancellation_releases_credits_and_marks_invocation_cancelled(self):
        self._fund()

        gen = send_message(
            conversation=self.conversation,
            user=self.user,
            prompt="Hello there, how are you today?",
            capability="fast",
        )
        start_event = next(gen)
        self.assertEqual(start_event[0], "batch_start")
        invocation_id = start_event[1]["invocations"][0]["invocation_id"]

        next(gen)  # consume one chunk before cancelling
        cache.set(f"cancel:{invocation_id}", True, timeout=60)
        remaining_events = [e[0] for e in gen]
        self.assertIn("cancelled", remaining_events)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("5.00"))
        self.assertEqual(self.wallet.reserved, Decimal("0.00"))

        invocation = ModelInvocation.objects.get(id=invocation_id)
        self.assertEqual(invocation.status, "cancelled")
        self.assertEqual(
            Message.objects.filter(conversation=self.conversation, role="assistant").count(), 0
        )

    def test_free_route_works_with_zero_balance_and_creates_no_ledger_entries(self):
        gen = send_message(
            conversation=self.conversation,
            user=self.user,
            prompt="Hello for free",
            capability="oneprompt-free",
        )
        events = list(gen)

        self.assertIn("done", [event[0] for event in events])
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))
        self.assertEqual(self.wallet.reserved, Decimal("0.00"))

        invocation = ModelInvocation.objects.get(conversation=self.conversation)
        self.assertEqual(invocation.credits_estimated, Decimal("0.00"))
        self.assertEqual(invocation.credits_charged, Decimal("0.00"))
        self.assertIsNone(invocation.reservation_entry)
        self.assertIsNone(invocation.capture_entry)

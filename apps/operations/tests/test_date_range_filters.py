from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.conversations.models import Conversation, ModelInvocation
from apps.conversations.tests.factories import ConversationFactory
from apps.credits.models import CreditLedgerEntry
from apps.credits.tests.factories import CreditWalletFactory
from apps.support.models import SupportTicket
from common.jwt import encode_access_token


def _js_iso(dt):
    # Mirrors JS `Date.prototype.toISOString()` — always a "Z" suffix, never
    # a "+00:00" offset (which needs URL-encoding to survive Django's
    # QueryDict parsing, which treats a literal "+" as a space).
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class InvocationListViewDateRangeFilterTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(is_staff=True)
        self.admin_token = encode_access_token(self.admin)
        self.user = UserFactory()
        conversation = ConversationFactory(user=self.user)

        now = timezone.now()
        self.old = ModelInvocation.objects.create(
            conversation=conversation, capability="fast", status="succeeded",
        )
        ModelInvocation.objects.filter(id=self.old.id).update(
            created_at=now - timezone.timedelta(days=10)
        )
        self.recent = ModelInvocation.objects.create(
            conversation=conversation, capability="fast", status="succeeded",
        )
        ModelInvocation.objects.filter(id=self.recent.id).update(created_at=now)

    def test_created_at_range_filters_invocations(self):
        from_iso = _js_iso(timezone.now() - timezone.timedelta(days=1))
        response = self.client.get(
            f"/api/v1/operations/invocations?created_at=from={from_iso}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(response.status_code, 200)
        ids = {i["id"] for i in response.json()["data"]["invocations"]}
        self.assertIn(str(self.recent.id), ids)
        self.assertNotIn(str(self.old.id), ids)


class LedgerListViewDateRangeFilterTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(is_staff=True)
        self.admin_token = encode_access_token(self.admin)
        self.user = UserFactory()
        wallet = CreditWalletFactory(user=self.user, currency="GHS")

        now = timezone.now()
        self.old = CreditLedgerEntry.objects.create(
            wallet=wallet, entry_type="usage_capture", amount=Decimal("5.00"),
            idempotency_key="old-entry",
        )
        CreditLedgerEntry.objects.filter(id=self.old.id).update(
            created_at=now - timezone.timedelta(days=10)
        )
        self.recent = CreditLedgerEntry.objects.create(
            wallet=wallet, entry_type="usage_capture", amount=Decimal("3.00"),
            idempotency_key="recent-entry",
        )
        CreditLedgerEntry.objects.filter(id=self.recent.id).update(created_at=now)

    def test_created_at_range_filters_ledger_entries(self):
        from_iso = _js_iso(timezone.now() - timezone.timedelta(days=1))
        response = self.client.get(
            f"/api/v1/operations/ledger?created_at=from={from_iso}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(response.status_code, 200)
        ids = {e["id"] for e in response.json()["data"]["entries"]}
        self.assertIn(str(self.recent.id), ids)
        self.assertNotIn(str(self.old.id), ids)


class SupportTicketListViewDateRangeFilterTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(is_staff=True)
        self.admin_token = encode_access_token(self.admin)
        self.user = UserFactory()

        now = timezone.now()
        self.old = SupportTicket.objects.create(user=self.user, subject="Old ticket")
        SupportTicket.objects.filter(id=self.old.id).update(
            updated_at=now - timezone.timedelta(days=10)
        )
        self.recent = SupportTicket.objects.create(user=self.user, subject="Recent ticket")
        SupportTicket.objects.filter(id=self.recent.id).update(updated_at=now)

    def test_updated_at_range_filters_tickets(self):
        from_iso = _js_iso(timezone.now() - timezone.timedelta(days=1))
        response = self.client.get(
            f"/api/v1/operations/support/tickets?updated_at=from={from_iso}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(response.status_code, 200)
        ids = {t["id"] for t in response.json()["data"]["tickets"]}
        self.assertIn(str(self.recent.id), ids)
        self.assertNotIn(str(self.old.id), ids)


class ConversationListViewDateRangeFilterTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(is_staff=True)
        self.admin_token = encode_access_token(self.admin)
        self.user = UserFactory()

        now = timezone.now()
        self.old = ConversationFactory(user=self.user, title="Old conversation")
        Conversation.objects.filter(id=self.old.id).update(
            updated_at=now - timezone.timedelta(days=10)
        )
        self.recent = ConversationFactory(user=self.user, title="Recent conversation")
        Conversation.objects.filter(id=self.recent.id).update(updated_at=now)

    def test_updated_at_range_filters_conversations(self):
        from_iso = _js_iso(timezone.now() - timezone.timedelta(days=1))
        response = self.client.get(
            f"/api/v1/operations/conversations?updated_at=from={from_iso}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(response.status_code, 200)
        ids = {c["id"] for c in response.json()["data"]["conversations"]}
        self.assertIn(str(self.recent.id), ids)
        self.assertNotIn(str(self.old.id), ids)


class CustomerListViewDateJoinedRangeFilterTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(is_staff=True, email="admin2@example.com")
        self.admin_token = encode_access_token(self.admin)

        now = timezone.now()
        self.old = UserFactory(email="old-customer@example.com")
        type(self.old).objects.filter(id=self.old.id).update(
            date_joined=now - timezone.timedelta(days=10)
        )
        self.recent = UserFactory(email="recent-customer@example.com")
        type(self.recent).objects.filter(id=self.recent.id).update(date_joined=now)

    def test_date_joined_range_filters_customers(self):
        from_iso = _js_iso(timezone.now() - timezone.timedelta(days=1))
        response = self.client.get(
            f"/api/v1/operations/customers?date_joined=from={from_iso}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(response.status_code, 200)
        ids = {c["id"] for c in response.json()["data"]["customers"]}
        self.assertIn(str(self.recent.id), ids)
        self.assertNotIn(str(self.old.id), ids)

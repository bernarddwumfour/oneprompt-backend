from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.billing.models import Purchase
from apps.billing.tests.factories import CreditPackFactory
from apps.conversations.models import ModelInvocation
from apps.conversations.tests.factories import ConversationFactory, MessageFactory
from apps.credits.models import CreditLedgerEntry
from apps.credits.tests.factories import CreditWalletFactory
from common.jwt import encode_access_token


class AnalyticsTrendsViewTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(email="admin@example.com", is_staff=True)
        self.user = UserFactory(email="user@example.com")
        self.admin_token = encode_access_token(self.admin)
        self.user_token = encode_access_token(self.user)

        self.wallet = CreditWalletFactory(user=self.user, currency="GHS")
        self.pack = CreditPackFactory(currency="GHS")

    def _trends(self, token, **params):
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return self.client.get(
            f"/api/v1/operations/analytics/trends?{query}",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_requires_admin(self):
        self.assertEqual(self._trends(self.user_token, currency="GHS", days=30).status_code, 403)
        self.assertEqual(self._trends(self.admin_token, currency="GHS", days=30).status_code, 200)

    def test_days_must_be_a_valid_integer_in_range(self):
        self.assertEqual(self._trends(self.admin_token, currency="GHS", days="abc").status_code, 400)
        self.assertEqual(self._trends(self.admin_token, currency="GHS", days=9999).status_code, 400)
        self.assertEqual(self._trends(self.admin_token, currency="GHS", days=0).status_code, 400)
        self.assertEqual(self._trends(self.admin_token, currency="GHS", days=30).status_code, 200)

    def test_revenue_bucketed_by_day_and_summed(self):
        from datetime import timedelta

        today = timezone.now()
        yesterday = today - timedelta(days=1)

        p1 = Purchase.objects.create(
            user=self.user, credit_pack=self.pack, reference="ref-day1",
            status="success", currency="GHS", amount_minor_units=1000,
            amount_credits=self.pack.amount_credits,
        )
        Purchase.objects.filter(id=p1.id).update(created_at=today)

        p2 = Purchase.objects.create(
            user=self.user, credit_pack=self.pack, reference="ref-day2",
            status="success", currency="GHS", amount_minor_units=2500,
            amount_credits=self.pack.amount_credits,
        )
        Purchase.objects.filter(id=p2.id).update(created_at=yesterday)

        # A failed purchase must not be counted as revenue.
        p3 = Purchase.objects.create(
            user=self.user, credit_pack=self.pack, reference="ref-failed",
            status="failed", currency="GHS", amount_minor_units=5000,
            amount_credits=self.pack.amount_credits,
        )

        revenue = self._trends(self.admin_token, currency="GHS", days=30).json()["data"]["revenue"]
        self.assertEqual(len(revenue), 2)
        self.assertEqual(sum(row["value"] for row in revenue), 3500)

    def test_usage_trend_only_counts_usage_capture_entries(self):
        CreditLedgerEntry.objects.create(
            wallet=self.wallet, entry_type="usage_capture", amount=Decimal("5.00"),
            idempotency_key="usage-1",
        )
        CreditLedgerEntry.objects.create(
            wallet=self.wallet, entry_type="usage_capture", amount=Decimal("3.00"),
            idempotency_key="usage-2",
        )
        # A purchase credit should not be counted as "usage".
        CreditLedgerEntry.objects.create(
            wallet=self.wallet, entry_type="purchase_credit", amount=Decimal("100.00"),
            idempotency_key="purchase-1",
        )
        usage = self._trends(self.admin_token, currency="GHS", days=30).json()["data"]["usage"]
        total = sum(Decimal(str(row["value"])) for row in usage)
        self.assertEqual(total, Decimal("8.00"))

    def test_active_users_trend_counts_distinct_users_not_messages(self):
        conversation = ConversationFactory(user=self.user)
        MessageFactory(conversation=conversation, role="user", content="hi")
        MessageFactory(conversation=conversation, role="user", content="hi again")

        active_users = self._trends(self.admin_token, currency="GHS", days=30).json()["data"]["active_users"]
        self.assertEqual(sum(row["value"] for row in active_users), 1)


class AnalyticsProviderComparisonViewTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(email="admin@example.com", is_staff=True)
        self.admin_token = encode_access_token(self.admin)
        self.user = UserFactory(email="user@example.com")
        CreditWalletFactory(user=self.user, currency="GHS")
        self.conversation = ConversationFactory(user=self.user)

    def test_groups_by_capability_and_sums_correctly(self):
        ModelInvocation.objects.create(
            conversation=self.conversation, capability="fast", status="succeeded",
            credits_charged=Decimal("1.00"), provider_cost_usd=Decimal("0.001"),
            completed_at=timezone.now(),
        )
        ModelInvocation.objects.create(
            conversation=self.conversation, capability="fast", status="succeeded",
            credits_charged=Decimal("2.00"), provider_cost_usd=Decimal("0.002"),
            completed_at=timezone.now(),
        )
        ModelInvocation.objects.create(
            conversation=self.conversation, capability="deepseek-flash", status="succeeded",
            credits_charged=Decimal("5.00"), provider_cost_usd=Decimal("0.01"),
            completed_at=timezone.now(),
        )
        # A failed invocation should not appear in the comparison.
        ModelInvocation.objects.create(
            conversation=self.conversation, capability="fast", status="failed",
            completed_at=timezone.now(),
        )

        response = self.client.get(
            "/api/v1/operations/analytics/providers?currency=GHS&period=month",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        rows = {r["capability"]: r for r in response.json()["data"]["providers"]}
        self.assertEqual(rows["fast"]["invocation_count"], 2)
        self.assertEqual(Decimal(rows["fast"]["credits_charged"]), Decimal("3.00"))
        self.assertEqual(rows["deepseek-flash"]["invocation_count"], 1)

    def test_requires_admin(self):
        user_token = encode_access_token(self.user)
        response = self.client.get(
            "/api/v1/operations/analytics/providers?currency=GHS&period=month",
            HTTP_AUTHORIZATION=f"Bearer {user_token}",
        )
        self.assertEqual(response.status_code, 403)

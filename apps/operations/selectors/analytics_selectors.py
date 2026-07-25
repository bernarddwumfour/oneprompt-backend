"""Analytics selectors — trend data and provider comparison."""

from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.billing.models import Purchase
from apps.credits.models import CreditLedgerEntry, CreditWallet
from apps.conversations.models import Message, ModelInvocation


def get_revenue_trend(*, currency: str, days: int = 30):
    """Day-bucketed successful purchase revenue."""
    cutoff = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    return (
        Purchase.objects.filter(
            currency=currency.upper(), status="success", created_at__gte=cutoff
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(value=Sum("amount_minor_units"))
        .order_by("day")
    )


def get_usage_trend(*, currency: str, days: int = 30):
    """Day-bucketed credit consumption for wallets of a given currency."""
    cutoff = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    wallet_ids = CreditWallet.objects.filter(currency=currency.upper()).values_list("id", flat=True)
    return (
        CreditLedgerEntry.objects.filter(
            wallet_id__in=wallet_ids,
            entry_type="usage_capture",
            created_at__gte=cutoff,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(value=Sum("amount"))
        .order_by("day")
    )


def get_active_users_trend(*, days: int = 30):
    """Day-bucketed distinct active users (sent at least one message)."""
    cutoff = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    return (
        Message.objects.filter(role="user", created_at__gte=cutoff)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(value=Count("conversation__user", distinct=True))
        .order_by("day")
    )


def get_provider_comparison(*, currency: str, period: str = "month"):
    """Breakdown table: group by capability for a currency + period."""
    from apps.operations.selectors.operations_selectors import _period_filter

    qs = _period_filter(
        ModelInvocation.objects.filter(
            conversation__user__wallet__currency=currency.upper(),
            status="succeeded",
        ),
        "completed_at",
        period,
    )
    return (
        qs.values("capability")
        .annotate(
            invocation_count=Count("id"),
            credits_charged=Sum("credits_charged"),
            provider_cost_usd=Sum("provider_cost_usd"),
        )
        .order_by("-invocation_count")
    )

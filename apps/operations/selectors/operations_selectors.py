"""Admin operations selectors — read-only aggregate queries.

Per plan 0003: metrics are reported per wallet currency, not blended.
"""

from datetime import datetime, timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import Purchase
from apps.credits.models import CreditLedgerEntry, CreditWallet
from apps.conversations.models import Conversation, ModelInvocation


def _period_filter(qs, date_field: str, period: str):
    """Apply a period filter to *qs* on *date_field*."""
    now = timezone.now()
    if period == "today":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        cutoff = now - timedelta(days=7)
    elif period == "month":
        cutoff = now - timedelta(days=30)
    else:
        cutoff = now - timedelta(days=30)
    return qs.filter(**{f"{date_field}__gte": cutoff})


def get_overview(*, currency: str, period: str = "month") -> dict:
    """Return commercial overview metrics for *currency*.

    All monetary amounts are in minor units (kobo/pesewas) for purchases
    and credit units for ledger entries.
    """
    # Revenue: successful purchases in this currency
    purchases = Purchase.objects.filter(
        currency=currency.upper(), status="success"
    )
    purchases = _period_filter(purchases, "created_at", period)
    revenue = purchases.aggregate(total=Sum("amount_minor_units"))["total"] or 0

    active_paying_users = (
        purchases.values("user").distinct().count()
    )

    # Credits sold (purchase + promotional)
    wallets = CreditWallet.objects.filter(currency=currency.upper())
    wallet_ids = list(wallets.values_list("id", flat=True))

    ledger_qs = CreditLedgerEntry.objects.filter(wallet_id__in=wallet_ids)
    ledger_qs = _period_filter(ledger_qs, "created_at", period)

    credits_sold = (
        ledger_qs.filter(
            entry_type__in=["purchase_credit", "promotional_credit"]
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    credits_consumed = (
        ledger_qs.filter(entry_type="usage_capture").aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )
    refund_amount = (
        ledger_qs.filter(entry_type="refund").aggregate(total=Sum("amount"))["total"]
        or 0
    )
    refund_count = ledger_qs.filter(entry_type="refund").count()

    # Provider cost (USD) — invocations by wallets of this currency
    provider_cost_usd = (
        ModelInvocation.objects.filter(
            conversation__user__wallet__currency=currency.upper(),
            status="succeeded",
            provider_cost_usd__isnull=False,
        )
    )
    provider_cost_usd = _period_filter(provider_cost_usd, "completed_at", period)
    provider_cost_usd = (
        provider_cost_usd.aggregate(total=Sum("provider_cost_usd"))["total"] or 0
    )

    # Payment failures
    failed_purchases = Purchase.objects.filter(
        currency=currency.upper(), status="failed"
    )
    failed_purchases = _period_filter(failed_purchases, "created_at", period)
    payment_failure_count = failed_purchases.count()

    return {
        "currency": currency.upper(),
        "period": period,
        "revenue_minor_units": revenue,
        "active_paying_users": active_paying_users,
        "credits_sold": str(credits_sold),
        "credits_consumed": str(credits_consumed),
        "provider_cost_usd": str(provider_cost_usd),
        "refund_count": refund_count,
        "refund_amount": str(refund_amount),
        "payment_failure_count": payment_failure_count,
    }


def search_customers(*, search: str = "", page: int = 1, limit: int = 20) -> dict:
    """Paginated customer search by email or full_name."""
    qs = User.objects.all()
    if search:
        qs = qs.filter(
            Q(email__icontains=search) | Q(full_name__icontains=search)
        )
    qs = qs.order_by("-date_joined")

    total = qs.count()
    offset = (page - 1) * limit
    users = qs[offset : offset + limit]

    return {
        "customers": [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "country": u.country,
                "is_email_verified": u.is_email_verified,
                "is_staff": u.is_staff,
                "date_joined": u.date_joined.isoformat(),
                "wallet": _wallet_summary(u),
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


def get_customer_detail(user: User) -> dict:
    """Full customer detail — user, wallet, ledger, purchases."""
    from apps.billing.selectors.purchase_selectors import get_purchase_for_user
    from apps.billing.schemas.purchase_schemas import serialize_purchase
    from apps.credits.schemas.wallet_schemas import (
        serialize_ledger_entry,
        serialize_wallet,
    )
    from apps.credits.selectors.wallet_selectors import (
        get_wallet_for_user,
        get_wallet_ledger,
    )

    wallet = get_wallet_for_user(user)
    wallet_data = serialize_wallet(wallet) if wallet else None

    ledger_entries = []
    if wallet:
        results, _ = get_wallet_ledger(wallet, page=1, limit=50)
        ledger_entries = [serialize_ledger_entry(e) for e in results]

    purchases = list(
        Purchase.objects.filter(user=user).select_related("credit_pack", "payment")[
            :20
        ]
    )

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "country": user.country,
            "is_email_verified": user.is_email_verified,
            "is_staff": user.is_staff,
            "date_joined": user.date_joined.isoformat(),
        },
        "wallet": wallet_data,
        "ledger_entries": ledger_entries,
        "purchases": [serialize_purchase(p) for p in purchases],
    }


def list_invocations(*, status: str = "", capability: str = "", page: int = 1, limit: int = 20) -> dict:
    """Admin invocation listing with aggregate stats."""
    from django.db.models import Avg, Count, F, Q
    from django.utils import timezone

    qs = ModelInvocation.objects.select_related(
        "conversation__user"
    ).order_by("-created_at")

    if status:
        qs = qs.filter(status=status)
    if capability:
        qs = qs.filter(capability=capability)

    total = qs.count()
    offset = (page - 1) * limit
    invocations = qs[offset : offset + limit]

    # Aggregates for today
    today_qs = ModelInvocation.objects.filter(
        created_at__date=timezone.now().date()
    )
    today_total = today_qs.count()
    today_success = today_qs.filter(status="succeeded").count()
    success_rate = (today_success / today_total * 100) if today_total > 0 else 0
    avg_latency = (
        today_qs.filter(
            completed_at__isnull=False, created_at__isnull=False
        ).aggregate(
            avg=Avg(F("completed_at") - F("created_at"))
        )["avg"]
    )
    avg_latency_seconds = (
        avg_latency.total_seconds() if avg_latency else None
    )

    return {
        "invocations": [
            {
                "id": str(inv.id),
                "user_email": inv.conversation.user.email,
                "capability": inv.capability,
                "status": inv.status,
                "input_tokens": inv.input_tokens,
                "output_tokens": inv.output_tokens,
                "credits_charged": str(inv.credits_charged) if inv.credits_charged else None,
                "provider_cost_usd": str(inv.provider_cost_usd) if inv.provider_cost_usd else None,
                "error_message": inv.error_message,
                "created_at": inv.created_at.isoformat(),
                "completed_at": inv.completed_at.isoformat() if inv.completed_at else None,
                "latency_seconds": (
                    (inv.completed_at - inv.created_at).total_seconds()
                    if inv.completed_at and inv.created_at
                    else None
                ),
            }
            for inv in invocations
        ],
        "total": total,
        "page": page,
        "limit": limit,
        "stats": {
            "today_total": today_total,
            "success_rate": round(success_rate, 1),
            "avg_latency_seconds": (
                round(avg_latency_seconds, 2) if avg_latency_seconds else None
            ),
        },
    }


def list_ledger_entries(
    *, entry_type: str = "", currency: str = "", page: int = 1, limit: int = 20
) -> dict:
    """Global ledger entry listing."""
    qs = CreditLedgerEntry.objects.select_related(
        "wallet__user"
    ).order_by("-created_at")

    if entry_type:
        qs = qs.filter(entry_type=entry_type)
    if currency:
        qs = qs.filter(wallet__currency=currency.upper())

    total = qs.count()
    offset = (page - 1) * limit
    entries = qs[offset : offset + limit]

    return {
        "entries": [
            {
                "id": str(e.id),
                "user_id": str(e.wallet.user.id),
                "user_email": e.wallet.user.email,
                "entry_type": e.entry_type,
                "amount": str(e.amount),
                "currency": e.wallet.currency,
                "reference": e.reference,
                "reason": e.reason,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


def list_purchases(
    *, status: str = "", currency: str = "", page: int = 1, limit: int = 20
) -> dict:
    """Global purchase listing."""
    qs = Purchase.objects.select_related(
        "user", "credit_pack", "payment"
    ).order_by("-created_at")

    if status:
        qs = qs.filter(status=status)
    if currency:
        qs = qs.filter(currency=currency.upper())

    total = qs.count()
    offset = (page - 1) * limit
    purchases = qs[offset : offset + limit]

    return {
        "purchases": [
            {
                "id": str(p.id),
                "reference": p.reference,
                "user_email": p.user.email,
                "credit_pack_label": p.credit_pack.label,
                "status": p.status,
                "currency": p.currency,
                "amount_minor_units": p.amount_minor_units,
                "amount_credits": str(p.credit_pack.amount_credits),
                "refunded_at": p.refunded_at.isoformat() if p.refunded_at else None,
                "created_at": p.created_at.isoformat(),
            }
            for p in purchases
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


def list_conversations(
    *, user_email: str = "", page: int = 1, limit: int = 20
) -> dict:
    """Admin conversation listing with message count."""
    from django.db.models import Count, Q

    qs = Conversation.objects.select_related("user").annotate(
        message_count=Count("messages")
    ).order_by("-updated_at")

    if user_email:
        qs = qs.filter(user__email__icontains=user_email)

    total = qs.count()
    offset = (page - 1) * limit
    conversations = qs[offset : offset + limit]

    return {
        "conversations": [
            {
                "id": str(c.id),
                "user_email": c.user.email,
                "title": c.title,
                "message_count": c.message_count,
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat(),
            }
            for c in conversations
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


def _wallet_summary(user: User) -> dict | None:
    try:
        w = user.wallet
        return {
            "id": str(w.id),
            "currency": w.currency,
            "balance": str(w.balance),
            "available": str(w.available),
        }
    except Exception:
        return None

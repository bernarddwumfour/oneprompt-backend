"""Read-only purchase queries."""

from typing import Optional

from apps.billing.models import CreditPack, Purchase


def list_active_credit_packs():
    return CreditPack.objects.filter(is_active=True).order_by("sort_order")


def get_purchase_for_user(purchase_id: str, user) -> Optional[Purchase]:
    try:
        return Purchase.objects.select_related("credit_pack", "payment").get(
            id=purchase_id, user=user
        )
    except Purchase.DoesNotExist:
        return None

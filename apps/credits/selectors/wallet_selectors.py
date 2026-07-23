"""
Read-only wallet queries.
"""

from typing import Optional

from django.core.paginator import Paginator

from apps.credits.models import CreditLedgerEntry, CreditWallet


def get_wallet_for_user(user) -> Optional[CreditWallet]:
    """Return the user's wallet or None."""
    try:
        return CreditWallet.objects.select_related("user").get(user=user)
    except CreditWallet.DoesNotExist:
        return None


def get_wallet_ledger(
    wallet: CreditWallet,
    page: int = 1,
    limit: int = 20,
    entry_type: str = "",
):
    """Paginated ledger entries for *wallet*."""
    qs = CreditLedgerEntry.objects.filter(wallet=wallet)
    if entry_type:
        qs = qs.filter(entry_type=entry_type)
    paginator = Paginator(qs, limit)
    return paginator.get_page(page), paginator.count

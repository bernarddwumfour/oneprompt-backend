"""Wallet serialization."""

from apps.credits.models import CreditLedgerEntry, CreditWallet


def serialize_wallet(wallet: CreditWallet) -> dict:
    return {
        "id": str(wallet.id),
        "currency": wallet.currency,
        "balance": str(wallet.balance),
        "reserved": str(wallet.reserved),
        "available": str(wallet.available),
    }


def serialize_ledger_entry(entry: CreditLedgerEntry) -> dict:
    return {
        "id": str(entry.id),
        "entry_type": entry.entry_type,
        "amount": str(entry.amount),
        "reference": entry.reference,
        "reason": entry.reason,
        "created_at": entry.created_at.isoformat(),
    }

"""Billing serialization."""

from apps.billing.models import CreditPack, Purchase


def serialize_credit_pack(pack: CreditPack) -> dict:
    return {
        "id": str(pack.id),
        "label": pack.label,
        "currency": pack.currency,
        "amount_credits": str(pack.amount_credits),
        "price_minor_units": pack.price_minor_units,
        "is_active": pack.is_active,
        "sort_order": pack.sort_order,
    }


def serialize_purchase(purchase: Purchase) -> dict:
    return {
        "id": str(purchase.id),
        "reference": purchase.reference,
        "status": purchase.status,
        "currency": purchase.currency,
        "amount_minor_units": purchase.amount_minor_units,
        "credit_pack": {
            "label": purchase.credit_pack.label,
            "amount_credits": str(purchase.credit_pack.amount_credits),
        },
        "refunded_at": purchase.refunded_at.isoformat() if purchase.refunded_at else None,
        "created_at": purchase.created_at.isoformat(),
        "confirmed_at": purchase.confirmed_at.isoformat() if purchase.confirmed_at else None,
    }

"""Operations schemas — validation."""


class ValidationError(ValueError):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__("Validation failed")


def validate_correction(data: dict) -> dict:
    errors = {}

    try:
        from decimal import Decimal

        amount = Decimal(str(data.get("amount", 0)))
        if amount <= 0:
            errors["amount"] = "Amount must be positive."
    except Exception:
        errors["amount"] = "Invalid amount."

    direction = (data.get("direction") or "").strip().lower()
    if direction not in ("credit", "debit"):
        errors["direction"] = "Direction must be 'credit' or 'debit'."

    reason = (data.get("reason") or "").strip()
    if not reason:
        errors["reason"] = "A reason is required for administrative corrections."

    if errors:
        raise ValidationError(errors)

    idempotency_key = (data.get("idempotency_key") or "").strip() or None

    return {
        "amount": amount,
        "direction": direction,
        "reason": reason,
        "idempotency_key": idempotency_key,
    }

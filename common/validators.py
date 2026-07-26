"""Shared bulk-action input validation — reusable across all admin sections.

Per plan 0008: one validator, one contract. Every bulk endpoint uses the same
``action`` + ``ids`` shape so the frontend doesn't need per-section variants.
"""


def validate_bulk_action(data: dict, valid_actions: list[str]) -> tuple[dict, dict]:
    """Validate a bulk-action request body.

    Returns a ``(cleaned, errors)`` tuple — exactly one will be non-empty.

    *data* is the already-parsed JSON body (``json.loads(request.body)``).
    *valid_actions* is the whitelist of allowed ``action`` values for this
    endpoint, e.g. ``["activate", "deactivate"]``.
    """
    errors: dict = {}

    action = data.get("action")
    if not action or action not in valid_actions:
        errors["action"] = f"Must be one of: {', '.join(valid_actions)}."

    ids = data.get("ids")
    if not isinstance(ids, list) or not ids:
        errors["ids"] = "Must be a non-empty list of IDs."

    if errors:
        return {}, errors

    return {"action": action, "ids": ids}, {}

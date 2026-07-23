"""
Read-only user queries. No mutations, no business logic.
"""

from typing import Optional

from apps.accounts.models import User


def get_user_by_id(user_id: str) -> Optional[User]:
    """Return the user with the given UUID pk, or None."""
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return None


def get_user_by_email(email: str) -> Optional[User]:
    """Return the user with the given email, or None."""
    try:
        return User.objects.get(email=email.lower().strip())
    except User.DoesNotExist:
        return None

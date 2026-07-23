"""Bootstrap admin account — created once from env credentials.

Per plan 0003: whenever the project is set up fresh (i.e. `migrate` runs
against a database that doesn't have this admin yet), ensure an admin
account exists using DJANGO_ADMIN_EMAIL/PASSWORD from the environment.
Never overwrites an existing account — this only fills in a missing one.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def ensure_default_admin(sender, using, **kwargs):
    email = (settings.DJANGO_ADMIN_EMAIL or "").strip().lower()
    password = settings.DJANGO_ADMIN_PASSWORD or ""

    if not email or not password:
        # Not configured — nothing to do. Don't create an admin with a
        # blank/unusable password.
        return

    from apps.accounts.models import User
    from apps.accounts.services.auth_service import _currency_for_country
    from apps.credits.models import CreditWallet

    if User.objects.using(using).filter(email=email).exists():
        logger.info("Bootstrap admin %s already exists — leaving it alone.", email)
        return

    country = (settings.DJANGO_ADMIN_COUNTRY or "GH").upper()
    admin = User.objects.db_manager(using).create_user(
        email=email,
        password=password,
        username=email,
        full_name=settings.DJANGO_ADMIN_FULL_NAME,
        country=country,
        is_email_verified=True,
        is_staff=True,
        is_superuser=True,
    )

    CreditWallet.objects.using(using).get_or_create(
        user=admin,
        defaults={"currency": _currency_for_country(country)},
    )

    logger.info("Bootstrap admin created from DJANGO_ADMIN_EMAIL: %s", email)

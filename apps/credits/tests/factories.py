from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.credits.models import CreditWallet


class CreditWalletFactory(DjangoModelFactory):
    class Meta:
        model = CreditWallet

    user = factory.SubFactory(UserFactory)
    currency = "USD"
    balance = Decimal("0")
    reserved = Decimal("0")

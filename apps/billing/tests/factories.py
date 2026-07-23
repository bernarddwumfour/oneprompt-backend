from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.billing.models import CreditPack


class CreditPackFactory(DjangoModelFactory):
    class Meta:
        model = CreditPack

    label = factory.Sequence(lambda n: f"Pack {n}")
    currency = "GHS"
    amount_credits = Decimal("50.00")
    price_minor_units = 1000
    is_active = True

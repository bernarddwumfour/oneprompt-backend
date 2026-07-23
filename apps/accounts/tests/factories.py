import factory
from factory.django import DjangoModelFactory

from apps.accounts.models import User


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    username = factory.LazyAttribute(lambda o: o.email)
    full_name = factory.Faker("name")
    country = "GH"
    password = factory.PostGenerationMethodCall("set_password", "testpass123")

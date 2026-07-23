import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.conversations.models import Conversation, Message


class ConversationFactory(DjangoModelFactory):
    class Meta:
        model = Conversation

    user = factory.SubFactory(UserFactory)
    title = "Test conversation"


class MessageFactory(DjangoModelFactory):
    class Meta:
        model = Message

    conversation = factory.SubFactory(ConversationFactory)
    role = "user"
    content = "Hello"

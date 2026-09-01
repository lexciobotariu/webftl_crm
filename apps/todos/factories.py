import factory

from apps.accounts.factories import UserFactory
from apps.clients.factories import ClientFactory
from apps.todos.models import Todo


class TodoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Todo

    owner = factory.SubFactory(UserFactory)
    client = None
    title = factory.Faker('sentence', nb_words=5)
    description = factory.Faker('paragraph')
    due_date = factory.Faker('date_object')
    is_completed = False
    completed_at = None


class ClientTodoFactory(TodoFactory):
    """Factory for creating todos associated with a client."""
    client = factory.SubFactory(ClientFactory)

import pytest

from apps.clients.factories import ClientFactory
from apps.projects.factories import ProjectFactory


@pytest.mark.django_db
class TestClientModel:
    def test_create_client(self):
        client = ClientFactory()
        assert client.name is not None
        assert client.pk is not None

    def test_client_str(self):
        client = ClientFactory(name='Acme Corp')
        assert str(client) == 'Acme Corp'

    def test_project_count_property(self):
        client = ClientFactory()
        assert client.project_count == 0
        ProjectFactory(client=client)
        ProjectFactory(client=client)
        assert client.project_count == 2

    def test_client_ordering(self):
        ClientFactory(name='Zebra Corp')
        ClientFactory(name='Alpha Inc')
        from apps.clients.models import Client
        clients = list(Client.objects.all())
        assert clients[0].name == 'Alpha Inc'
        assert clients[1].name == 'Zebra Corp'

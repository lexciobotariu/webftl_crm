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

    def test_blank_billing_name_and_email_use_contact(self):
        client = ClientFactory(
            name='Acme Corp',
            email='acme@client.com',
            billing_name='',
            billing_email='',
        )
        assert client.bill_to_name == 'Acme Corp'
        assert client.bill_to_email == 'acme@client.com'
        assert client.billing_name == ''
        assert client.billing_email == ''

    def test_set_billing_name_and_email_override_contact(self):
        client = ClientFactory(
            name='Acme Corp',
            email='acme@client.com',
            billing_name='Acme Billing LLC',
            billing_email='billing@acme.com',
        )
        assert client.bill_to_name == 'Acme Billing LLC'
        assert client.bill_to_email == 'billing@acme.com'

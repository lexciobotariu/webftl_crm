import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_client_todos_say_they_are_private(client):
    from apps.accounts.factories import AdminUserFactory
    from apps.clients.factories import ClientFactory

    admin = AdminUserFactory()
    owner = ClientFactory()
    client.force_login(admin)
    html = client.get(reverse('client_detail_todos', args=[owner.pk])).content.decode()
    assert 'Only you see these' in html
    assert 'Only you see these' not in client.get(reverse('my_tasks')).content.decode()

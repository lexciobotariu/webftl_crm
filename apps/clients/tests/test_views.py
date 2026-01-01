import pytest
from django.urls import reverse
from apps.accounts.factories import UserFactory, AdminUserFactory
from apps.clients.factories import ClientFactory


@pytest.mark.django_db
class TestClientList:
    def test_client_list_requires_login(self, client):
        response = client.get(reverse('client_list'))
        assert response.status_code == 302

    def test_client_list_shows_clients(self, client):
        user = UserFactory()
        client.force_login(user)
        ClientFactory(name='Test Client')
        response = client.get(reverse('client_list'))
        assert response.status_code == 200
        assert 'Test Client' in response.content.decode()

    def test_client_list_pagination(self, client):
        user = UserFactory()
        for i in range(25):
            ClientFactory(name=f'Client {i}')
        client.force_login(user)
        response = client.get(reverse('client_list'))
        assert response.context['page_obj'].has_next()


@pytest.mark.django_db
class TestClientCreate:
    def test_client_create_requires_login(self, client):
        response = client.post(reverse('client_create'), {'name': 'New Client'})
        assert response.status_code == 302

    def test_client_create_requires_admin(self, client):
        """Non-admin users cannot create clients."""
        user = UserFactory()
        client.force_login(user)
        response = client.post(reverse('client_create'), {'name': 'New Client'})
        assert response.status_code == 403

    def test_client_create_with_valid_data(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('client_create'), {
            'name': 'New Client',
            'email': 'new@client.com',
            'phone': '555-1234',
            'address': '123 Main St',
            'notes': 'Important client',
        })
        assert response.status_code == 302
        from apps.clients.models import Client
        assert Client.objects.filter(name='New Client').exists()

    def test_client_create_with_invalid_data(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('client_create'), {
            'name': '',
        })
        assert response.status_code == 200
        from apps.clients.models import Client
        assert Client.objects.count() == 0


@pytest.mark.django_db
class TestClientDetail:
    def test_client_detail_shows_info(self, client):
        user = UserFactory()
        test_client = ClientFactory(name='Detail Client', email='detail@test.com')
        client.force_login(user)
        response = client.get(reverse('client_detail', args=[test_client.pk]))
        assert response.status_code == 200
        assert 'Detail Client' in response.content.decode()

    def test_client_detail_404_for_nonexistent(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('client_detail', args=[99999]))
        assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.security
class TestClientDelete:
    def test_delete_requires_admin(self, client):
        user = UserFactory(role='member')
        test_client = ClientFactory()
        client.force_login(user)
        response = client.post(reverse('client_delete', args=[test_client.pk]))
        assert response.status_code == 403

    def test_admin_can_delete(self, client):
        admin = AdminUserFactory()
        test_client = ClientFactory()
        client.force_login(admin)
        response = client.post(reverse('client_delete', args=[test_client.pk]))
        assert response.status_code == 302
        from apps.clients.models import Client
        assert not Client.objects.filter(pk=test_client.pk).exists()

    def test_delete_requires_post(self, client):
        admin = AdminUserFactory()
        test_client = ClientFactory()
        client.force_login(admin)
        response = client.get(reverse('client_delete', args=[test_client.pk]))
        assert response.status_code == 405


@pytest.mark.django_db
class TestClientDetailTabs:
    def test_client_detail_default_tab_is_profile(self, client):
        """GET /clients/<pk>/ should set active_tab to 'profile'"""
        user = UserFactory()
        client_obj = ClientFactory()
        client.force_login(user)
        response = client.get(reverse('client_detail', args=[client_obj.pk]))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'profile'

    def test_client_detail_projects_tab(self, client):
        """GET /clients/<pk>/projects/ should set active_tab to 'projects'"""
        user = UserFactory()
        client_obj = ClientFactory()
        client.force_login(user)
        response = client.get(reverse('client_detail_projects', args=[client_obj.pk]))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'projects'

    def test_client_detail_todos_tab(self, client):
        """GET /clients/<pk>/todos/ should set active_tab to 'todos'"""
        user = UserFactory()
        client_obj = ClientFactory()
        client.force_login(user)
        response = client.get(reverse('client_detail_todos', args=[client_obj.pk]))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'todos'

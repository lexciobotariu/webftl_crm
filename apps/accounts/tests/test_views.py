import pytest
from django.urls import reverse
from apps.accounts.factories import UserFactory, AdminUserFactory


@pytest.mark.django_db
class TestDashboard:
    def test_dashboard_requires_login(self, client):
        response = client.get(reverse('dashboard'))
        assert response.status_code == 302
        assert '/accounts/login/' in response.url

    def test_dashboard_accessible_when_logged_in(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert response.status_code == 200

    def test_dashboard_shows_stats(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert 'client_count' in response.context
        assert 'project_count' in response.context
        assert 'my_task_count' in response.context


@pytest.mark.django_db
class TestTeamList:
    def test_team_list_requires_admin(self, client):
        user = UserFactory(role='member')
        client.force_login(user)
        response = client.get(reverse('team_list'))
        assert response.status_code == 403

    def test_team_list_accessible_by_admin(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert response.status_code == 200

    def test_team_list_pagination(self, client):
        admin = AdminUserFactory()
        for _ in range(25):
            UserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert response.context['page_obj'].has_next()


@pytest.mark.django_db
@pytest.mark.security
class TestToggleRole:
    def test_toggle_role_requires_admin(self, client):
        user = UserFactory(role='member')
        target = UserFactory(role='member')
        client.force_login(user)
        response = client.post(reverse('toggle_role', args=[target.pk]))
        assert response.status_code == 403

    def test_toggle_role_works_for_admin(self, client):
        admin = AdminUserFactory()
        target = UserFactory(role='member')
        client.force_login(admin)
        response = client.post(reverse('toggle_role', args=[target.pk]))
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.role == 'admin'

    def test_admin_cannot_toggle_own_role(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('toggle_role', args=[admin.pk]))
        admin.refresh_from_db()
        assert admin.role == 'admin'

    def test_toggle_role_requires_post(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.get(reverse('toggle_role', args=[target.pk]))
        assert response.status_code == 405

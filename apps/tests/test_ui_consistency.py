"""
Tests to verify UI/UX consistency across the application.
These tests check templates and responses for consistent patterns.
"""
import pytest
from django.urls import reverse
from apps.accounts.factories import UserFactory, AdminUserFactory
from apps.clients.factories import ClientFactory
from apps.projects.factories import ProjectFactory, ProjectMemberFactory


@pytest.mark.django_db
class TestPageHeaders:
    """All list pages should have consistent compact headers."""

    def test_dashboard_has_compact_header(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        content = response.content.decode()
        # Dashboard uses compact header styling with text-sm font-medium
        assert 'text-sm font-medium' in content  # Compact title style
        assert 'Dashboard' in content

    def test_client_list_has_compact_header(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('client_list'))
        content = response.content.decode()
        assert 'Clients' in content
        assert 'total_count' in response.context or 'clients' in response.context

    def test_project_list_has_compact_header(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('project_list'))
        content = response.content.decode()
        assert 'Projects' in content

    def test_team_list_has_compact_header(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        content = response.content.decode()
        assert 'Team' in content


@pytest.mark.django_db
class TestPagination:
    """All list pages should support pagination consistently."""

    def test_client_list_pagination_context(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('client_list'))
        assert 'page_obj' in response.context

    def test_project_list_pagination_context(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('project_list'))
        assert 'page_obj' in response.context

    def test_my_tasks_pagination_context(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('my_tasks'))
        assert 'page_obj' in response.context

    def test_team_list_pagination_context(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert 'page_obj' in response.context


@pytest.mark.django_db
class TestHTMXSupport:
    """Views with HTMX support should respond correctly."""

    def test_project_board_htmx(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.get(
            reverse('project_board', args=[project.pk]),
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200
        # Should return partial, not full page
        content = response.content.decode()
        assert '<!DOCTYPE' not in content

    def test_task_create_htmx(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')
        client.force_login(user)
        response = client.get(
            reverse('task_create', args=[project.pk]),
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200
        # Should return slide-over content
        content = response.content.decode()
        assert 'slide-over' in content.lower() or 'New Task' in content

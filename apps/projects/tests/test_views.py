import pytest
import json
from django.urls import reverse
from apps.accounts.factories import UserFactory, AdminUserFactory
from apps.projects.factories import ProjectFactory, ProjectMemberFactory
from apps.clients.factories import ClientFactory


@pytest.mark.django_db
class TestProjectList:
    def test_project_list_requires_login(self, client):
        response = client.get(reverse('project_list'))
        assert response.status_code == 302

    def test_project_list_shows_projects_for_admin(self, client):
        """Admins can see all projects."""
        admin = AdminUserFactory()
        ProjectFactory(name='Test Project')
        client.force_login(admin)
        response = client.get(reverse('project_list'))
        assert response.status_code == 200
        assert 'Test Project' in response.content.decode()

    def test_project_list_shows_only_member_projects(self, client):
        """Non-admin users only see projects they're members of."""
        user = UserFactory()
        project1 = ProjectFactory(name='My Project')
        project2 = ProjectFactory(name='Other Project')
        ProjectMemberFactory(project=project1, user=user, role='viewer')
        # user is NOT a member of project2
        client.force_login(user)
        response = client.get(reverse('project_list'))
        assert response.status_code == 200
        assert 'My Project' in response.content.decode()
        assert 'Other Project' not in response.content.decode()

    def test_project_list_filter_by_client(self, client):
        admin = AdminUserFactory()
        client1 = ClientFactory(name='Client A')
        client2 = ClientFactory(name='Client B')
        ProjectFactory(name='Project A', client=client1)
        ProjectFactory(name='Project B', client=client2)
        client.force_login(admin)
        response = client.get(reverse('project_list') + f'?client={client1.pk}')
        assert 'Project A' in response.content.decode()
        assert 'Project B' not in response.content.decode()


@pytest.mark.django_db
class TestProjectBoard:
    def test_project_board_shows_kanban(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.get(reverse('project_board', args=[project.pk]))
        assert response.status_code == 200

    def test_project_board_htmx_returns_partial(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.get(
            reverse('project_board', args=[project.pk]),
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200

    def test_project_board_denied_without_membership(self, client):
        """Users without membership cannot access project board."""
        user = UserFactory()
        project = ProjectFactory()
        # No membership created
        client.force_login(user)
        response = client.get(reverse('project_board', args=[project.pk]))
        assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.security
class TestProjectDelete:
    def test_delete_requires_admin(self, client):
        user = UserFactory(role='member')
        project = ProjectFactory()
        client.force_login(user)
        response = client.post(reverse('project_delete', args=[project.pk]))
        assert response.status_code == 403

    def test_admin_can_delete(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory()
        pk = project.pk
        client.force_login(admin)
        response = client.post(reverse('project_delete', args=[pk]))
        assert response.status_code == 302
        from apps.projects.models import Project
        assert not Project.objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestStatusManagement:
    def test_create_status_requires_manager(self, client):
        """Only managers can create statuses."""
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.post(
            reverse('status_create', args=[project.pk]),
            {'name': 'New Status'}
        )
        assert response.status_code == 403

    def test_create_status_with_manager_role(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='manager')
        initial_count = project.statuses.count()
        client.force_login(user)
        response = client.post(
            reverse('status_create', args=[project.pk]),
            {'name': 'New Status'}
        )
        assert response.status_code == 200
        assert project.statuses.count() == initial_count + 1

    def test_delete_empty_status(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='manager')
        status = project.statuses.first()
        client.force_login(user)
        response = client.post(
            reverse('status_delete', args=[project.pk, status.pk])
        )
        assert response.status_code == 200

    def test_cannot_delete_status_with_tasks(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='manager')
        status = project.statuses.first()
        from apps.tasks.factories import TaskFactory
        TaskFactory(project=project, status=status)
        client.force_login(user)
        response = client.post(
            reverse('status_delete', args=[project.pk, status.pk])
        )
        assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.race
class TestReorderStatuses:
    def test_reorder_statuses(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='manager')
        statuses = list(project.statuses.all())
        new_order = [s.pk for s in reversed(statuses)]
        client.force_login(user)
        response = client.post(
            reverse('reorder_statuses', args=[project.pk]),
            json.dumps({'order': new_order}),
            content_type='application/json'
        )
        assert response.status_code == 204
        reordered = list(project.statuses.all())
        assert reordered[0].pk == new_order[0]


@pytest.mark.django_db
class TestProjectDetail:
    def test_project_detail_requires_login(self, client):
        project = ProjectFactory()
        response = client.get(reverse('project_detail', args=[project.pk]))
        assert response.status_code == 302

    def test_project_detail_shows_project_info(self, client):
        user = UserFactory()
        project = ProjectFactory(name='Test Project', description='Test description')
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.get(reverse('project_detail', args=[project.pk]))
        assert response.status_code == 200
        assert 'Test Project' in response.content.decode()

    def test_project_detail_denied_without_membership(self, client):
        user = UserFactory()
        project = ProjectFactory()
        client.force_login(user)
        response = client.get(reverse('project_detail', args=[project.pk]))
        assert response.status_code == 403

    def test_project_detail_shows_task_count(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        from apps.tasks.factories import TaskFactory
        status = project.statuses.first()
        TaskFactory(project=project, status=status)
        TaskFactory(project=project, status=status)
        client.force_login(user)
        response = client.get(reverse('project_detail', args=[project.pk]))
        assert response.status_code == 200
        content = response.content.decode()
        # Should show task count in stats
        assert '2' in content

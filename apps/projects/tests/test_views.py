import pytest
import json
from django.urls import reverse
from apps.accounts.factories import UserFactory, AdminUserFactory
from apps.projects.factories import ProjectFactory, ProjectMemberFactory
from apps.clients.factories import ClientFactory
from apps.accounts.permissions import PermissionPreset


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
class TestProjectDetailTabs:
    def test_project_detail_default_tab_is_overview(self, client):
        """GET /projects/<pk>/detail/ should set active_tab to 'overview'"""
        user = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(user)

        response = client.get(reverse('project_detail', args=[project.pk]))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'overview'

    def test_project_detail_tasks_tab(self, client):
        """GET /projects/<pk>/detail/tasks/ should set active_tab to 'tasks'"""
        user = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(user)

        response = client.get(reverse('project_detail_tasks', args=[project.pk]))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'tasks'


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


@pytest.mark.django_db
class TestBoardVisibility:
    def test_board_hides_invisible_statuses(self, client):
        """Statuses with visible_on_board=False should not appear on the board."""
        user = AdminUserFactory()
        project = ProjectFactory()
        hidden_status = project.statuses.filter(name='Done').first()
        hidden_status.visible_on_board = False
        hidden_status.save()
        client.force_login(user)
        response = client.get(reverse('project_board', args=[project.pk]))
        content = response.content.decode()
        assert 'Done' not in content
        # Other statuses still visible
        assert 'Backlog' in content
        assert 'In Progress' in content

    def test_board_shows_hidden_task_count(self, client):
        """Board should show count of tasks in hidden statuses."""
        user = AdminUserFactory()
        project = ProjectFactory()
        hidden_status = project.statuses.filter(name='Done').first()
        hidden_status.visible_on_board = False
        hidden_status.save()
        from apps.tasks.factories import TaskFactory
        TaskFactory(project=project, status=hidden_status)
        TaskFactory(project=project, status=hidden_status)
        client.force_login(user)
        response = client.get(reverse('project_board', args=[project.pk]))
        assert response.context['hidden_task_count'] == 2

    def test_board_no_hidden_badge_when_zero(self, client):
        """No hidden task count in context when all statuses are visible."""
        user = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(user)
        response = client.get(reverse('project_board', args=[project.pk]))
        assert response.context['hidden_task_count'] == 0

    def test_toggle_visibility_requires_manager(self, client):
        """Only managers can toggle status visibility."""
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        status = project.statuses.first()
        client.force_login(user)
        response = client.post(
            reverse('status_toggle_visibility', args=[project.pk, status.pk])
        )
        assert response.status_code == 403

    def test_toggle_visibility_hides_status(self, client):
        """POSTing to toggle endpoint should flip visible_on_board."""
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='manager')
        status = project.statuses.first()
        assert status.visible_on_board is True
        client.force_login(user)
        response = client.post(
            reverse('status_toggle_visibility', args=[project.pk, status.pk])
        )
        assert response.status_code == 200
        status.refresh_from_db()
        assert status.visible_on_board is False

    def test_toggle_visibility_shows_status(self, client):
        """Toggling a hidden status makes it visible again."""
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='manager')
        status = project.statuses.first()
        status.visible_on_board = False
        status.save()
        client.force_login(user)
        response = client.post(
            reverse('status_toggle_visibility', args=[project.pk, status.pk])
        )
        assert response.status_code == 200
        status.refresh_from_db()
        assert status.visible_on_board is True

    def test_task_status_dropdown_shows_all_statuses(self, client):
        """The status dropdown on task detail should show all statuses including hidden ones."""
        user = AdminUserFactory()
        project = ProjectFactory()
        hidden_status = project.statuses.filter(name='Done').first()
        hidden_status.visible_on_board = False
        hidden_status.save()
        from apps.tasks.factories import TaskFactory
        task = TaskFactory(project=project, status=project.statuses.first())
        client.force_login(user)
        response = client.get(reverse('task_detail', args=[task.pk]))
        content = response.content.decode()
        # All statuses should appear in the dropdown
        assert 'Done' in content

    def test_task_create_defaults_to_first_visible_status(self, client):
        """When creating a task without specifying a status, use first visible status."""
        user = AdminUserFactory()
        project = ProjectFactory()
        # Hide the first status (Backlog, order=0)
        first_status = project.statuses.order_by('order').first()
        first_status.visible_on_board = False
        first_status.save()
        second_status = project.statuses.filter(visible_on_board=True).order_by('order').first()
        client.force_login(user)
        response = client.post(
            reverse('task_create', args=[project.pk]),
            {'title': 'Test Task', 'description': ''},
        )
        from apps.tasks.models import Task
        task = Task.objects.get(title='Test Task')
        assert task.status == second_status


@pytest.mark.django_db
class TestClientNameVisibility:
    def test_project_list_shows_client_link_for_admin(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(admin)
        response = client.get(reverse('project_list'))
        content = response.content.decode()
        assert f'/clients/{project.client.pk}/' in content

    def test_project_list_hides_client_link_for_developer(self, client):
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.get(reverse('project_list'))
        content = response.content.decode()
        assert project.client.name in content
        assert f'/clients/{project.client.pk}/' not in content

    def test_project_list_hides_client_filter_for_developer(self, client):
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.get(reverse('project_list'))
        content = response.content.decode()
        assert 'All Clients' not in content

    def test_project_detail_shows_client_breadcrumb_link_for_admin(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(admin)
        response = client.get(reverse('project_detail', args=[project.pk]))
        content = response.content.decode()
        assert f'/clients/{project.client.pk}/' in content

    def test_project_detail_hides_client_breadcrumb_link_for_developer(self, client):
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.get(reverse('project_detail', args=[project.pk]))
        content = response.content.decode()
        assert project.client.name in content
        assert f'/clients/{project.client.pk}/' not in content

    def test_project_board_hides_client_link_for_developer(self, client):
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.get(reverse('project_board', args=[project.pk]))
        content = response.content.decode()
        assert project.client.name in content
        assert f'/clients/{project.client.pk}/' not in content

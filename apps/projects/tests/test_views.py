import json

import pytest
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.projects.factories import ProjectAccessFactory, ProjectFactory


def _with_edit_own(user):
    preset = PermissionPreset.objects.create(
        name=f'EditOwn{user.pk}',
        access_projects=True,
        projects_edit_own=True,
        access_tasks=True,
    )
    user.permission_preset = preset
    user.save(update_fields=['permission_preset'])
    return user


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
        ProjectFactory(name='Other Project')
        ProjectAccessFactory(project=project1, user=user)
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
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)
        response = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=board')
        assert response.status_code == 200

    def test_project_board_htmx_request_gets_the_full_page(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)
        response = client.get(
            reverse('project_tasks', args=[project.pk]) + '?layout=board',
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200

    def test_project_board_denied_without_membership(self, client):
        """Users without membership cannot access project board."""
        user = UserFactory()
        project = ProjectFactory()
        # No membership created
        client.force_login(user)
        response = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=board')
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

    def test_admin_can_delete_project_that_has_tasks(self, client):
        """Task.status must not block a delete that also removes the statuses.

        With on_delete=PROTECT this raised ProtectedError (500); RESTRICT allows
        the delete because the referenced statuses go in the same cascade.
        """
        from apps.projects.models import Project
        from apps.tasks.factories import TaskFactory
        from apps.tasks.models import Task

        admin = AdminUserFactory()
        project = ProjectFactory()
        TaskFactory(project=project, status=project.statuses.first())
        client.force_login(admin)

        response = client.post(reverse('project_delete', args=[project.pk]))

        assert response.status_code == 302
        assert not Project.objects.filter(pk=project.pk).exists()
        assert not Task.objects.filter(project_id=project.pk).exists()


@pytest.mark.django_db
class TestStatusManagement:
    def test_create_status_requires_manager(self, client):
        """Only managers can create statuses."""
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)
        response = client.post(
            reverse('status_create', args=[project.pk]),
            {'name': 'New Status'}
        )
        assert response.status_code == 403

    def test_create_status_with_manager_role(self, client):
        user = _with_edit_own(UserFactory())
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        initial_count = project.statuses.count()
        client.force_login(user)
        response = client.post(
            reverse('status_create', args=[project.pk]),
            {'name': 'New Status'}
        )
        assert response.status_code == 200
        assert project.statuses.count() == initial_count + 1

    def test_delete_empty_status(self, client):
        user = _with_edit_own(UserFactory())
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        status = project.statuses.first()
        client.force_login(user)
        response = client.post(
            reverse('status_delete', args=[project.pk, status.pk])
        )
        assert response.status_code == 200

    def test_cannot_delete_status_with_tasks(self, client):
        user = _with_edit_own(UserFactory())
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
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
        user = _with_edit_own(UserFactory())
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
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
        """GET /projects/<pk>/overview/ should set active_tab to 'overview'"""
        user = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(user)

        response = client.get(reverse('project_detail', args=[project.pk]))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'overview'

    def test_tasks_url_is_the_full_width_tasks_page(self, client):
        """GET /projects/<pk>/tasks/ is the Tasks page, not a project detail tab."""
        user = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(user)

        response = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=list')
        assert response.status_code == 200
        assert 'tasks/view/project_tasks.html' in [t.name for t in response.templates]

    def test_bare_project_url_redirects_to_overview(self, client):
        """GET /projects/<pk>/ should redirect to the overview tab"""
        user = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(user)

        response = client.get(f'/projects/{project.pk}/')
        assert response.status_code == 302
        assert response['Location'] == reverse('project_detail', args=[project.pk])


@pytest.mark.django_db
class TestProjectDetail:
    def test_project_detail_requires_login(self, client):
        project = ProjectFactory()
        response = client.get(reverse('project_detail', args=[project.pk]))
        assert response.status_code == 302

    def test_project_detail_shows_project_info(self, client):
        user = UserFactory()
        project = ProjectFactory(name='Test Project', description='Test description')
        ProjectAccessFactory(project=project, user=user)
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
        ProjectAccessFactory(project=project, user=user)
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
        response = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=board')
        # The filter menu still lists every status; the board columns do not.
        columns = [status.name for status in response.context['visible_statuses']]
        assert 'Done' not in columns
        assert 'Backlog' in columns
        assert 'In Progress' in columns

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
        response = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=board')
        assert response.context['hidden_task_count'] == 2

    def test_board_no_hidden_badge_when_zero(self, client):
        """No hidden task count in context when all statuses are visible."""
        user = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(user)
        response = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=board')
        assert response.context['hidden_task_count'] == 0

    def test_toggle_visibility_requires_manager(self, client):
        """Only managers can toggle status visibility."""
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        status = project.statuses.first()
        client.force_login(user)
        response = client.post(
            reverse('status_toggle_visibility', args=[project.pk, status.pk])
        )
        assert response.status_code == 403

    def test_toggle_visibility_hides_status(self, client):
        """POSTing to toggle endpoint should flip visible_on_board."""
        user = _with_edit_own(UserFactory())
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
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
        user = _with_edit_own(UserFactory())
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
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
        assert response.status_code in (200, 302)
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
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)
        response = client.get(reverse('project_list'))
        content = response.content.decode()
        assert project.client.name in content
        assert f'/clients/{project.client.pk}/' not in content

    def test_project_list_ignores_client_query_without_access(self, client):
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        client_a = ClientFactory(name='Hidden Filter A')
        client_b = ClientFactory(name='Hidden Filter B')
        project_a = ProjectFactory(name='Visible A', client=client_a)
        project_b = ProjectFactory(name='Visible B', client=client_b)
        ProjectAccessFactory(project=project_a, user=user)
        ProjectAccessFactory(project=project_b, user=user)
        client.force_login(user)

        response = client.get(reverse('project_list'), {'client': client_a.pk})
        content = response.content.decode()

        assert 'Visible A' in content
        assert 'Visible B' in content
        assert project_a.client.name in content
        assert f'/clients/{client_a.pk}/' not in content
        assert 'All Clients' not in content

    def test_project_list_hides_add_for_non_admin(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)
        content = client.get(reverse('project_list')).content.decode()
        assert 'Add Project' not in content
        assert reverse('project_create') not in content

    def test_project_list_hides_client_filter_for_developer(self, client):
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
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
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)
        response = client.get(reverse('project_detail', args=[project.pk]))
        content = response.content.decode()
        assert project.client.name in content
        assert f'/clients/{project.client.pk}/' not in content

    def test_project_board_hides_client_link_for_developer(self, client):
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)
        response = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=board')
        content = response.content.decode()
        assert project.client.name in content
        assert f'/clients/{project.client.pk}/' not in content


@pytest.mark.django_db
class TestProjectDeleteButton:
    def test_manager_does_not_see_delete(self, client):
        user = _with_edit_own(UserFactory())
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)
        content = client.get(reverse('project_settings', args=[project.pk])).content.decode()
        assert 'Delete Project' not in content
        assert reverse('project_delete', args=[project.pk]) not in content

    def test_admin_sees_delete(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(admin)
        content = client.get(reverse('project_settings', args=[project.pk])).content.decode()
        assert 'Delete Project' in content
        assert reverse('project_delete', args=[project.pk]) in content


@pytest.mark.django_db
class TestStatusSetCategory:
    def _post(self, client, project, status, category):
        return client.post(
            reverse('status_set_category', args=[project.pk, status.pk]),
            {'category': category},
        )

    def test_requires_manager(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        status = project.statuses.get(name='To Do')
        client.force_login(user)
        assert self._post(client, project, status, 'started').status_code == 403
        status.refresh_from_db()
        assert status.category == 'unstarted'

    def test_sets_category(self, client):
        user = _with_edit_own(UserFactory())
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        status = project.statuses.get(name='To Do')
        client.force_login(user)
        response = self._post(client, project, status, 'canceled')
        assert response.status_code == 200
        status.refresh_from_db()
        assert status.category == 'canceled'

    def test_rejects_unknown_category(self, client):
        user = _with_edit_own(UserFactory())
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        status = project.statuses.get(name='To Do')
        client.force_login(user)
        assert self._post(client, project, status, 'bogus').status_code == 400
        status.refresh_from_db()
        assert status.category == 'unstarted'

    def test_status_of_another_project_is_404(self, client):
        user = _with_edit_own(UserFactory())
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        other = ProjectFactory().statuses.first()
        client.force_login(user)
        assert self._post(client, project, other, 'started').status_code == 404

    def test_settings_page_renders_category_select(self, client):
        user = _with_edit_own(UserFactory())
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)
        html = client.get(reverse('project_settings', args=[project.pk])).content.decode()
        assert 'name="category"' in html

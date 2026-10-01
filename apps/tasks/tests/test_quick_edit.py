import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.tasks.factories import TaskFactory
from apps.tasks.models import Task, TaskActivity, editable_scope


def _user(name, **overrides):
    fields = {
        'access_dashboard': True,
        'access_projects': True,
        'access_tasks': True,
        'tasks_view_all': False,
        'tasks_create': False,
        'tasks_edit_own': False,
        'tasks_edit_all': False,
    }
    fields.update(overrides)
    return UserFactory(permission_preset=PermissionPreset.objects.create(name=name, **fields))


def _menu(client, task, field):
    return client.get(reverse('task_quick_menu', args=[task.pk, field]))


def _checked(content):
    return content.count('aria-checked="true"')


@pytest.mark.django_db
class TestQuickMenu:
    def test_status_options_check_the_current_status(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        current = project.statuses.get(name='In Progress')
        task = TaskFactory(project=project, status=current)
        client.force_login(user)

        response = _menu(client, task, 'status')

        assert response.status_code == 200
        content = response.content.decode()
        for status in project.statuses.all():
            assert f'data-value="{status.pk}"' in content
        assert _checked(content) == 1
        assert content.index(f'data-value="{current.pk}"') < content.index('aria-checked="true"')

    def test_assignee_options_list_unassigned_and_the_team(self, client):
        user = UserFactory(name='Ada Lovelace')
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        task = TaskFactory(project=project, assignee=user)
        UserFactory(name='Zed Outsider')
        client.force_login(user)

        content = _menu(client, task, 'assignee').content.decode()

        assert 'Unassigned' in content
        assert 'Ada Lovelace' in content
        assert 'Zed Outsider' not in content
        assert _checked(content) == 1

    def test_unassigned_task_checks_unassigned(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        task = TaskFactory(project=project, assignee=None)
        client.force_login(user)

        content = _menu(client, task, 'assignee').content.decode()

        assert _checked(content) == 1
        assert content.index('data-value=""') < content.index('aria-checked="true"') < content.index('data-value="', content.index('data-value=""') + 1)

    def test_unknown_field_is_not_found(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        task = TaskFactory(project=project)
        client.force_login(user)

        assert _menu(client, task, 'priority').status_code == 404
        assert _menu(client, task, 'title').status_code == 404

    def test_someone_who_may_only_view_cannot_open_it(self, client):
        viewer = _user('Viewer', tasks_view_all=True)
        task = TaskFactory()
        client.force_login(viewer)

        assert _menu(client, task, 'status').status_code == 403

    def test_someone_without_access_cannot_open_it(self, client):
        stranger = UserFactory()
        task = TaskFactory()
        client.force_login(stranger)

        assert _menu(client, task, 'assignee').status_code == 403

    def test_cost_does_not_grow_with_the_team(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        task = TaskFactory(project=project)
        client.force_login(user)

        def queries():
            with CaptureQueriesContext(connection) as ctx:
                assert _menu(client, task, 'assignee').status_code == 200
            return len(ctx)

        before = queries()
        for _ in range(5):
            ProjectAccessFactory(project=project, user=UserFactory())
        assert queries() == before


@pytest.mark.django_db
class TestPriorityUpdate:
    def _setup(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        task = TaskFactory(project=project, priority='low')
        client.force_login(user)
        return task

    def test_valid_priority_is_saved(self, client):
        task = self._setup(client)
        response = client.post(reverse('task_update_priority', args=[task.pk]), {'priority': 'urgent'})
        assert response.status_code == 200
        task.refresh_from_db()
        assert task.priority == 'urgent'

    def test_empty_priority_clears_it(self, client):
        task = self._setup(client)
        client.post(reverse('task_update_priority', args=[task.pk]), {'priority': ''})
        task.refresh_from_db()
        assert task.priority == ''

    def test_invalid_priority_is_rejected(self, client):
        task = self._setup(client)
        response = client.post(
            reverse('task_update_priority', args=[task.pk]), {'priority': 'whenever'}
        )
        assert response.status_code == 400
        task.refresh_from_db()
        assert task.priority == 'low'


@pytest.mark.django_db
class TestStatusUpdate:
    def test_choosing_the_current_status_changes_nothing(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        status = project.statuses.get(name='Backlog')
        first = TaskFactory(project=project, status=status, order=0)
        last = TaskFactory(project=project, status=status, order=1)
        client.force_login(user)
        TaskActivity.objects.all().delete()

        response = client.post(
            reverse('task_update_status', args=[first.pk]), {'status_id': status.pk}
        )

        assert response.status_code == 200
        assert 'HX-Trigger' not in response
        first.refresh_from_db()
        last.refresh_from_db()
        assert (first.order, last.order) == (0, 1)
        assert not TaskActivity.objects.exists()

    def test_choosing_the_current_status_still_needs_edit_rights(self, client):
        viewer = _user('Viewer', tasks_view_all=True)
        task = TaskFactory()
        client.force_login(viewer)

        response = client.post(
            reverse('task_update_status', args=[task.pk]), {'status_id': task.status_id}
        )

        assert response.status_code == 403


@pytest.mark.django_db
class TestEditableScope:
    def test_admin_may_edit_everywhere(self):
        assert editable_scope(AdminUserFactory()) == (True, frozenset())

    def test_edit_all_may_edit_everywhere(self):
        user = _user('EditAll', tasks_view_all=True, tasks_edit_all=True)
        assert editable_scope(user) == (True, frozenset())

    def test_no_edit_flag_edits_nowhere(self):
        user = _user('ViewOnly', tasks_view_all=True)
        assert editable_scope(user) == (False, frozenset())

    def test_edit_own_without_view_all_needs_no_query(self, django_assert_num_queries):
        user = _user('EditOwn', tasks_edit_own=True)
        with django_assert_num_queries(0):
            assert editable_scope(user) == (True, frozenset())

    def test_edit_own_with_view_all_is_limited_to_access_rows(self):
        user = _user('EditOwnViewAll', tasks_edit_own=True, tasks_view_all=True)
        mine = ProjectFactory()
        ProjectAccessFactory(project=mine, user=user)
        ProjectFactory()
        assert editable_scope(user) == (False, frozenset({mine.pk}))


@pytest.mark.django_db
class TestTriggersOnPages:
    def test_project_page_shows_triggers_and_one_menu_to_an_editor(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        TaskFactory.create_batch(3, project=project)
        client.force_login(user)

        content = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=list').content.decode()

        assert content.count('data-quick="priority"') == 3
        assert content.count('data-quick="status"') == 3
        assert content.count('data-quick="assignee"') == 3
        assert content.count('id="task-quick-menu"') == 1
        assert content.count('data-task-row') == 3

    def test_board_cards_get_priority_and_assignee_but_no_status_trigger(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        TaskFactory.create_batch(2, project=project)
        client.force_login(user)

        content = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=board').content.decode()

        assert content.count('data-quick="priority"') == 2
        assert content.count('data-quick="assignee"') == 2
        assert 'data-quick="status"' not in content

    def test_a_viewer_gets_plain_icons_and_no_menu(self, client):
        viewer = _user('Viewer', tasks_view_all=True)
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=viewer)
        TaskFactory.create_batch(2, project=project)
        client.force_login(viewer)

        content = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=list').content.decode()

        assert 'data-quick=' not in content
        assert 'task-quick-menu' not in content
        assert content.count('data-task-row') == 2

    def test_my_tasks_limits_triggers_to_projects_with_an_access_row(self, client):
        user = _user('EditOwnViewAll', tasks_edit_own=True, tasks_view_all=True)
        mine = ProjectFactory()
        ProjectAccessFactory(project=mine, user=user)
        other = ProjectFactory()
        TaskFactory(project=mine, assignee=user)
        TaskFactory(project=other, assignee=user)
        client.force_login(user)

        content = client.get(reverse('my_tasks') + '?group=none').content.decode()

        assert content.count('data-task-row') == 2
        assert content.count('data-quick="status"') == 1

    def test_triggers_cost_no_queries_per_row(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        client.force_login(user)
        url = reverse('project_tasks', args=[project.pk]) + '?layout=list'

        def queries():
            with CaptureQueriesContext(connection) as ctx:
                client.get(url)
            return len(ctx)

        TaskFactory.create_batch(2, project=project)
        queries()  # the first request warms per-process caches
        before = queries()
        TaskFactory.create_batch(6, project=project)
        assert queries() == before
        assert Task.objects.filter(project=project).count() == 8

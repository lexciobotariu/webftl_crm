from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.models import ProjectAccess
from apps.tasks.factories import TaskFactory, TimeEntryFactory
from apps.tasks.models import Task
from apps.tasks.services import entries_on_task


def _preset(name, **overrides):
    fields = {
        'access_dashboard': True,
        'access_projects': True,
        'access_tasks': True,
        'projects_view_all': False,
        'projects_edit_own': False,
        'projects_edit_all': False,
        'tasks_view_all': False,
        'tasks_create': False,
        'tasks_edit_own': False,
        'tasks_edit_all': False,
    }
    fields.update(overrides)
    return PermissionPreset.objects.create(name=name, **fields)


def _user(name, **overrides):
    return UserFactory(permission_preset=_preset(name, **overrides))


@pytest.mark.django_db
class TestProjectFlagsDoNotGrantTasks:
    def test_project_access_view_all_and_edit_do_not_show_or_change_tasks(self, client):
        closed = _user(
            'TasksClosed',
            access_tasks=False,
            projects_view_all=True,
            projects_edit_own=True,
            projects_edit_all=True,
        )
        mine = ProjectFactory(name='Mine Project')
        other = ProjectFactory(name='Other Project')
        ProjectAccessFactory(project=mine, user=closed)
        mine_task = TaskFactory(project=mine, title='Mine Task', priority='low')
        other_task = TaskFactory(project=other, title='Other Task', priority='low')
        client.force_login(closed)

        for project, task in ((mine, mine_task), (other, other_task)):
            board = client.get(reverse('project_tasks', args=[project.pk]) + '?layout=board')
            assert board.status_code == 200
            html = board.content.decode()
            assert task.title not in html
            assert 'Backlog' in html
            assert 'To Do' in html
            assert client.get(reverse('task_detail', args=[task.pk])).status_code == 403
            assert client.post(
                reverse('comment_create', args=[task.pk]),
                {'content': 'Should not land'},
            ).status_code == 403
            assert client.post(reverse('task_create', args=[project.pk]), {
                'title': 'Should Not Land',
                'description': '',
            }).status_code == 403

        renamed = client.post(reverse('project_settings_update', args=[mine.pk]), {
            'name': 'Mine Renamed',
            'description': '',
            'github_repo_url': '',
        })
        assert renamed.status_code == 200
        mine.refresh_from_db()
        assert mine.name == 'Mine Renamed'
        assert not Task.objects.filter(title='Should Not Land').exists()
        mine_task.refresh_from_db()
        assert mine_task.priority == 'low'

        watcher = _user(
            'ProjectWatcher',
            projects_view_all=True,
            projects_edit_all=True,
        )
        client.force_login(watcher)
        watched = client.get(reverse('project_tasks', args=[other.pk]) + '?layout=board')
        assert watched.status_code == 200
        watched_html = watched.content.decode()
        assert 'Other Task' not in watched_html
        assert 'Backlog' in watched_html
        assert client.get(reverse('task_detail', args=[other_task.pk])).status_code == 403
        assert client.get(
            reverse('task_full_page', args=[other.pk, other_task.pk])
        ).status_code == 403
        assert client.post(
            reverse('task_update_priority', args=[other_task.pk]),
            {'priority': 'urgent'},
        ).status_code == 403
        other_task.refresh_from_db()
        assert other_task.priority == 'low'

        settings = client.post(reverse('project_settings_update', args=[other.pk]), {
            'name': 'Other Renamed',
            'description': '',
            'github_repo_url': '',
        })
        assert settings.status_code == 200
        other.refresh_from_db()
        assert other.name == 'Other Renamed'


@pytest.mark.django_db
class TestViewOwn:
    def test_row_shows_tasks_on_that_project_only(self, client):
        user = _user('ViewOwn')
        someone = UserFactory()
        mine = ProjectFactory()
        other = ProjectFactory()
        ProjectAccessFactory(project=mine, user=user)
        TaskFactory(project=mine, assignee=user, title='On My Project')
        TaskFactory(project=mine, assignee=someone, title='Also On Mine')
        TaskFactory(project=other, assignee=user, title='On Their Project')
        client.force_login(user)

        board = client.get(reverse('project_tasks', args=[mine.pk]) + '?layout=board').content.decode()
        assert 'On My Project' in board
        assert 'Also On Mine' in board
        assert client.get(reverse('project_tasks', args=[other.pk]) + '?layout=board').status_code == 403

        foreign = Task.objects.get(title='On Their Project')
        assert client.get(reverse('task_detail', args=[foreign.pk])).status_code == 403
        assert client.get(
            reverse('task_full_page', args=[other.pk, foreign.pk])
        ).status_code == 403

        mine_page = client.get(reverse('my_tasks'), {'layout': 'list'}).content.decode()
        assert 'On My Project' in mine_page
        assert 'On Their Project' not in mine_page
        assert 'Also On Mine' not in mine_page

        dashboard = client.get(reverse('dashboard'))
        assert dashboard.context['my_task_count'] == 1
        titles = [task.title for task in dashboard.context['recent_tasks']]
        assert titles == ['On My Project']


@pytest.mark.django_db
class TestViewAll:
    def test_opens_a_task_they_are_not_on_and_cannot_edit_it(self, client):
        user = _user('TaskViewAll', tasks_view_all=True)
        project = ProjectFactory()
        task = TaskFactory(project=project, title='Far Away', priority='low')
        assert not ProjectAccess.objects.filter(project=project, user=user).exists()
        client.force_login(user)

        assert client.get(reverse('task_detail', args=[task.pk])).status_code == 200
        assert client.get(
            reverse('task_full_page', args=[project.pk, task.pk])
        ).status_code == 200
        # Seeing a task is enough to comment on it (0.20.0).
        assert client.post(
            reverse('comment_create', args=[task.pk]),
            {'content': 'From a viewer'},
        ).status_code == 200
        assert client.post(reverse('task_edit', args=[task.pk]), {
            'title': 'Changed',
            'description': '',
            'priority': 'high',
        }).status_code == 403
        task.refresh_from_db()
        assert task.title == 'Far Away'
        assert task.priority == 'low'
        assert task.activities.filter(activity_type='comment', content='From a viewer').exists()


@pytest.mark.django_db
class TestCreateFlag:
    def test_create_on_a_row_and_not_on_a_view_only_project(self, client):
        user = _user('TaskCreators', tasks_create=True, tasks_view_all=True)
        mine = ProjectFactory()
        viewed = ProjectFactory()
        ProjectAccessFactory(project=mine, user=user)
        parent = TaskFactory(project=mine, title='Parent')
        far = TaskFactory(project=viewed, title='Only Viewed')
        client.force_login(user)

        created = client.post(reverse('task_create', args=[mine.pk]), {
            'title': 'New Task',
            'description': '',
        })
        assert created.status_code == 302
        assert mine.tasks.filter(title='New Task').exists()

        child = client.post(reverse('subtask_create', args=[parent.pk]), {'title': 'Child'})
        assert child.status_code == 200
        assert parent.subtasks.filter(title='Child').exists()

        assert client.get(reverse('task_detail', args=[far.pk])).status_code == 200
        denied = client.post(reverse('task_create', args=[viewed.pk]), {
            'title': 'Nope',
            'description': '',
        })
        assert denied.status_code == 403
        assert not viewed.tasks.filter(title='Nope').exists()
        denied_child = client.post(
            reverse('subtask_create', args=[far.pk]),
            {'title': 'No Child'},
        )
        assert denied_child.status_code == 403
        assert not far.subtasks.filter(title='No Child').exists()


@pytest.mark.django_db
class TestEditFlags:
    def test_edit_own_logs_own_time_but_not_on_a_view_all_task(self, client):
        user = _user('TaskEditOwn', tasks_edit_own=True, tasks_view_all=True)
        mine = ProjectFactory()
        other = ProjectFactory()
        ProjectAccessFactory(project=mine, user=user)
        mine_task = TaskFactory(project=mine, title='Editable', priority='low')
        other_task = TaskFactory(project=other, title='View Only', priority='low')
        client.force_login(user)

        comment = client.post(
            reverse('comment_create', args=[mine_task.pk]),
            {'content': 'Hello'},
        )
        assert comment.status_code == 200
        assert mine_task.activities.filter(activity_type='comment', content='Hello').exists()

        today = timezone.localdate().isoformat()
        logged = client.post(reverse('time_log', args=[mine_task.pk]), {
            'duration': '1h',
            'day': today,
            'note': 'my-hours',
        })
        assert logged.status_code == 200
        assert mine_task.time_entries.filter(user=user, note='my-hours').exists()

        assert client.get(reverse('task_detail', args=[other_task.pk])).status_code == 200
        # Commenting needs only sight of the task (0.20.0); logging time needs edit.
        assert client.post(
            reverse('comment_create', args=[other_task.pk]),
            {'content': 'From a viewer'},
        ).status_code == 200
        assert client.post(reverse('time_log', args=[other_task.pk]), {
            'duration': '1h',
            'day': today,
            'note': 'not-mine',
        }).status_code == 403
        assert other_task.activities.filter(activity_type='comment', content='From a viewer').exists()
        assert not other_task.time_entries.filter(note='not-mine').exists()

    def test_edit_all_edits_a_task_they_are_not_on(self, client):
        user = _user('TaskEditAll', tasks_edit_all=True, tasks_view_all=True)
        project = ProjectFactory()
        task = TaskFactory(project=project, title='Remote', priority='low')
        assert not ProjectAccess.objects.filter(project=project, user=user).exists()
        client.force_login(user)

        updated = client.post(
            reverse('task_update_priority', args=[task.pk]),
            {'priority': 'urgent'},
        )
        assert updated.status_code == 200
        task.refresh_from_db()
        assert task.priority == 'urgent'


@pytest.mark.django_db
class TestDeleteStaysAdmin:
    def test_non_admin_cannot_delete(self, client):
        user = _user(
            'CannotDeleteTasks',
            tasks_view_all=True,
            tasks_create=True,
            tasks_edit_own=True,
            tasks_edit_all=True,
        )
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        task = TaskFactory(project=project, title='Stay')
        client.force_login(user)

        assert client.post(reverse('task_delete', args=[task.pk])).status_code == 403
        assert Task.objects.filter(pk=task.pk).exists()
        detail = client.get(reverse('task_detail', args=[task.pk])).content.decode()
        assert 'Delete task' not in detail
        assert reverse('task_delete', args=[task.pk]) not in detail


@pytest.mark.django_db
class TestTimeEntries:
    def test_view_all_sees_entries_only_admin_changes_them(self, client):
        owner = _user('TimeOwner', tasks_edit_own=True)
        viewer = _user('TimeViewer', tasks_view_all=True, tasks_edit_all=True)
        colleague = _user('TimeColleague', tasks_edit_own=True)
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=owner)
        ProjectAccessFactory(project=project, user=colleague)
        task = TaskFactory(project=project, title='Shared Task')
        started = timezone.now() - timedelta(hours=3)
        ended = timezone.now() - timedelta(hours=2)
        entry = TimeEntryFactory(
            user=owner,
            task=task,
            note='owner-note',
            started_at=started,
            ended_at=ended,
        )

        assert entry in list(entries_on_task(viewer, task))
        assert entry not in list(entries_on_task(colleague, task))

        client.force_login(viewer)
        detail = client.get(reverse('task_detail', args=[task.pk])).content.decode()
        assert 'owner-note' in detail
        denied = client.post(reverse('time_entry_edit', args=[entry.pk]), {
            'duration': '30m',
            'day': timezone.localdate(entry.started_at).isoformat(),
            'note': 'changed',
        })
        assert denied.status_code == 403
        assert client.post(reverse('time_entry_delete', args=[entry.pk])).status_code == 403
        entry.refresh_from_db()
        assert entry.note == 'owner-note'

        admin = AdminUserFactory()
        client.force_login(admin)
        changed = client.post(reverse('time_entry_edit', args=[entry.pk]), {
            'duration': '30m',
            'day': timezone.localdate(entry.started_at).isoformat(),
            'note': 'admin-note',
        })
        assert changed.status_code == 200
        entry.refresh_from_db()
        assert entry.note == 'admin-note'


@pytest.mark.django_db
class TestMyTasksFollowsView:
    def test_view_all_includes_assigned_tasks_on_other_projects(self, client):
        user = _user('AssignedFar', tasks_view_all=True)
        project = ProjectFactory()
        TaskFactory(project=project, assignee=user, title='Assigned Far')
        TaskFactory(project=project, title='Not Mine')
        client.force_login(user)

        page = client.get(reverse('my_tasks'), {'layout': 'list'}).content.decode()
        assert 'Assigned Far' in page
        assert 'Not Mine' not in page
        dashboard = client.get(reverse('dashboard'))
        assert dashboard.context['my_task_count'] == 1
        assert [task.title for task in dashboard.context['recent_tasks']] == ['Assigned Far']

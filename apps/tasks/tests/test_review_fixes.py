"""Fixes from the 2026-10-07 review of the tasks implementation (release 0.19.2)."""
from datetime import date, timedelta

import pytest
from django.template import Context, Template
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.tasks import services
from apps.tasks.factories import LabelFactory, SubtaskFactory, TaskFactory, TimeEntryFactory
from apps.tasks.models import Task, TimeEntry


def _user(name, **flags):
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
    fields.update(flags)
    return UserFactory(permission_preset=PermissionPreset.objects.create(name=name, **fields))


# What an editor's drawer offers and a viewer's must not.
EDIT_URLS = (
    'task_update_status',
    'task_update_assignee',
    'task_update_priority',
    'task_update_due_date',
    'task_update_estimate',
    'task_edit_title',
    'task_edit_description',
    'subtask_create',
    'attachment_upload',
    'comment_create',
)


def _edit_controls(html, task):
    return [name for name in EDIT_URLS if reverse(name, args=[task.pk]) in html]


@pytest.mark.django_db
class TestReadOnlyDrawer:
    def _task(self):
        project = ProjectFactory()
        task = TaskFactory(project=project, title='Shared Task', due_date=None, estimate_minutes=None)
        SubtaskFactory(task=task, title='A step')
        LabelFactory(project=project, name='Bug')
        return task

    def test_a_viewer_sees_values_and_no_edit_controls(self, client):
        task = self._task()
        viewer = _user('Viewers', tasks_view_all=True)
        client.force_login(viewer)

        for url in (
            reverse('task_detail', args=[task.pk]),
            reverse('task_full_page', args=[task.project.pk, task.pk]),
        ):
            html = client.get(url).content.decode()
            assert 'Shared Task' in html
            assert 'A step' in html
            assert _edit_controls(html, task) == []
            assert reverse('subtask_toggle', args=[task.pk, task.subtasks.get().pk]) not in html
            assert reverse('task_toggle_label', args=[task.pk, task.project.labels.get().pk]) not in html
            assert 'Add sub-task' not in html
            assert 'No due date' in html
            assert 'No labels' in html

    def test_an_editor_keeps_every_control(self, client):
        task = self._task()
        editor = _user('Editors', tasks_edit_all=True, tasks_view_all=True)
        client.force_login(editor)

        for url in (
            reverse('task_detail', args=[task.pk]),
            reverse('task_full_page', args=[task.project.pk, task.pk]),
        ):
            html = client.get(url).content.decode()
            assert _edit_controls(html, task) == list(EDIT_URLS)
            assert 'Add due date' in html

    def test_a_creator_who_cannot_edit_may_add_a_sub_task_but_not_tick_it(self, client):
        task = self._task()
        creator = _user('CreateOnly', tasks_create=True, tasks_view_all=True)
        ProjectAccessFactory(project=task.project, user=creator)
        client.force_login(creator)

        html = client.get(reverse('task_detail', args=[task.pk])).content.decode()
        assert _edit_controls(html, task) == ['subtask_create']

        response = client.post(reverse('subtask_create', args=[task.pk]), {'title': 'Next step'})
        assert response.status_code == 200
        added = task.subtasks.get(title='Next step')
        assert reverse('subtask_toggle', args=[task.pk, added.pk]) not in response.content.decode()

    def test_the_board_offers_drag_only_to_editors(self, client):
        task = self._task()
        url = reverse('project_tasks', args=[task.project.pk]) + '?layout=board'

        client.force_login(_user('BoardViewers', tasks_view_all=True, projects_view_all=True))
        html = client.get(url).content.decode()
        assert 'Shared Task' in html
        assert 'x-sort' not in html

        client.force_login(_user('BoardEditors', tasks_view_all=True, tasks_edit_all=True, projects_view_all=True))
        assert 'x-sort:handle' in client.get(url).content.decode()


@pytest.mark.django_db
class TestSubtaskPermission:
    def test_edit_without_create_may_add_a_sub_task(self, client):
        project = ProjectFactory()
        task = TaskFactory(project=project)
        editor = _user('EditOwnOnly', tasks_edit_own=True)
        ProjectAccessFactory(project=project, user=editor)
        client.force_login(editor)

        response = client.post(reverse('subtask_create', args=[task.pk]), {'title': 'From an editor'})

        assert response.status_code == 200
        assert task.subtasks.filter(title='From an editor').exists()

    def test_a_viewer_may_not_add_a_sub_task(self, client):
        task = TaskFactory()
        client.force_login(_user('JustLooking', tasks_view_all=True))

        response = client.post(reverse('subtask_create', args=[task.pk]), {'title': 'Nope'})

        assert response.status_code == 403
        assert not task.subtasks.filter(title='Nope').exists()


@pytest.mark.django_db
class TestTitleLength:
    def test_a_title_over_the_limit_is_refused_with_a_reason(self, client):
        task = TaskFactory(title='Short')
        client.force_login(_user('TitleEditors', tasks_edit_all=True, tasks_view_all=True))

        response = client.post(
            reverse('task_edit_title', args=[task.pk]), {'title': 'x' * 1001}, HTTP_HX_REQUEST='true',
        )

        assert response.status_code == 400
        assert '1000 characters' in response.content.decode()
        task.refresh_from_db()
        assert task.title == 'Short'

    def test_the_edit_form_caps_the_input(self, client):
        task = TaskFactory()
        client.force_login(_user('TitleFormEditors', tasks_edit_all=True, tasks_view_all=True))

        html = client.get(reverse('task_edit_title', args=[task.pk]), HTTP_HX_REQUEST='true').content.decode()

        assert 'maxlength="1000"' in html


@pytest.mark.django_db
def test_task_edit_over_htmx_answers_with_the_whole_drawer(client):
    project = ProjectFactory()
    member = _user('Member', tasks_edit_own=True)
    ProjectAccessFactory(project=project, user=member)
    member.name = 'Ana Member'
    member.save()
    task = TaskFactory(project=project, title='Before')
    client.force_login(member)

    response = client.post(
        reverse('task_edit', args=[task.pk]),
        {'title': 'After', 'description': '', 'priority': '', 'assignee': ''},
        HTTP_HX_REQUEST='true',
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert 'After' in html
    # The assignee menu is filled, which the old fragment left empty.
    assert 'Ana Member' in html


@pytest.mark.django_db
class TestMoveKeepsUpdatedAt:
    def _set_updated(self, task, when):
        Task.objects.filter(pk=task.pk).update(updated_at=when)

    def test_a_reorder_in_the_same_column_does_not_touch_updated_at(self):
        project = ProjectFactory()
        status = project.statuses.first()
        first = TaskFactory(project=project, status=status, order=0)
        second = TaskFactory(project=project, status=status, order=1)
        long_ago = timezone.now() - timedelta(days=30)
        self._set_updated(first, long_ago)
        self._set_updated(second, long_ago)
        user = _user('Movers', tasks_edit_all=True)

        services.move_task(second, status, user, after_id=None)

        first.refresh_from_db()
        second.refresh_from_db()
        assert (second.order, first.order) == (0, 1)
        assert second.updated_at == long_ago
        assert first.updated_at == long_ago
        assert not second.activities.filter(activity_type='status_change').exists()

    def test_a_move_to_another_status_is_an_update(self):
        project = ProjectFactory()
        source, target = project.statuses.all()[:2]
        task = TaskFactory(project=project, status=source)
        long_ago = timezone.now() - timedelta(days=30)
        self._set_updated(task, long_ago)
        user = _user('StatusMovers', tasks_edit_all=True)

        services.move_task(task, target, user)

        task.refresh_from_db()
        assert task.status == target
        assert task.updated_at > long_ago
        assert task.activities.filter(activity_type='status_change', user=user).exists()


@pytest.mark.django_db
def test_sub_task_changes_ask_the_view_to_refresh(client):
    project = ProjectFactory()
    task = TaskFactory(project=project)
    subtask = SubtaskFactory(task=task)
    client.force_login(_user('SubtaskEditors', tasks_edit_all=True, tasks_view_all=True))

    responses = [
        client.post(reverse('subtask_create', args=[task.pk]), {'title': 'New'}),
        client.post(reverse('subtask_toggle', args=[task.pk, subtask.pk])),
        client.post(reverse('subtask_delete', args=[task.pk, subtask.pk])),
    ]

    for response in responses:
        assert response.status_code == 200
        assert response['HX-Trigger'] == 'taskChanged'


class TestDueDateYear:
    def _render(self, value):
        return Template('{% load task_dates %}{{ value|short_date }}').render(Context({'value': value}))

    def test_this_year_has_no_year_and_another_year_does(self):
        this_year = timezone.localdate().year
        assert self._render(date(this_year, 1, 5)) == 'Jan 05'
        assert self._render(date(this_year + 1, 1, 5)) == f'Jan 05, {this_year + 1}'
        assert self._render(None) == ''

    @pytest.mark.django_db
    def test_activity_keeps_the_year(self):
        task = TaskFactory(due_date=None)
        task.due_date = date(2027, 1, 5)
        task.save()

        activity = task.activities.get(activity_type='due_date_change')
        assert activity.new_value == 'Jan 05, 2027'


@pytest.mark.django_db
def test_expired_timers_are_closed_once_per_request(django_assert_num_queries):
    started = timezone.now() - timedelta(hours=13)
    entry = TimeEntryFactory(started_at=started, ended_at=None)
    request = RequestFactory().get('/')

    services.close_expired_timers_for(request)
    with django_assert_num_queries(0):
        services.close_expired_timers_for(request)

    entry.refresh_from_db()
    assert entry.ended_at == started + timedelta(hours=12)
    assert TimeEntry.objects.filter(ended_at__isnull=True).count() == 0

import re
from datetime import datetime, time, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.projects.factories import ProjectAccessFactory
from apps.tasks.factories import TaskFactory, TimeEntryFactory
from apps.tasks.models import TimeEntry


def _member(role='editor', **task_kwargs):
    user = UserFactory()
    task = TaskFactory(**task_kwargs)
    ProjectAccessFactory(project=task.project, user=user)
    return user, task


def _monday_start():
    monday = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
    return monday, timezone.make_aware(datetime.combine(monday, time.min))


def _stamp(dt):
    return timezone.localtime(dt).strftime('%Y-%m-%dT%H:%M')


@pytest.mark.django_db
class TestTimerViews:
    def test_requires_login(self, client):
        task = TaskFactory()
        assert client.get(reverse('time_week')).status_code == 302
        assert client.post(reverse('timer_start', args=[task.pk])).status_code == 302

    def test_requires_access_tasks(self, client):
        user, task = _member()
        user.permission_preset = None
        user.save()
        client.force_login(user)
        assert client.get(reverse('time_week')).status_code == 403
        assert client.post(reverse('timer_start', args=[task.pk])).status_code == 403

    def test_viewer_cannot_start_or_log(self, client):
        from apps.accounts.permissions import PermissionPreset

        task = TaskFactory()
        preset = PermissionPreset.objects.create(
            name='ViewAllTimer',
            access_projects=True,
            access_tasks=True,
            projects_view_all=True,
        )
        user = UserFactory(permission_preset=preset)
        client.force_login(user)

        assert client.post(reverse('timer_start', args=[task.pk])).status_code == 403
        assert client.get(reverse('time_log', args=[task.pk])).status_code == 403
        assert not TimeEntry.objects.filter(user=user).exists()

        detail = client.get(reverse('task_detail', args=[task.pk]))
        full = client.get(reverse('task_full_page', args=[task.project.pk, task.pk]))
        assert detail.status_code == 200
        assert full.status_code == 200
        assert f'time-start-{task.pk}' not in detail.content.decode()
        assert f'time-start-{task.pk}' not in full.content.decode()
        assert 'Log time' not in detail.content.decode()

    def test_editor_can_start_and_a_second_start_closes_the_first(self, client):
        user, task = _member()
        other = TaskFactory(project=task.project, status=task.status)
        client.force_login(user)

        first = client.post(reverse('timer_start', args=[task.pk]))
        assert first.status_code == 204
        assert TimeEntry.objects.filter(user=user, ended_at__isnull=True).count() == 1

        second = client.post(reverse('timer_start', args=[other.pk]))
        assert second.status_code == 204
        open_rows = TimeEntry.objects.filter(user=user, ended_at__isnull=True)
        assert open_rows.count() == 1
        assert open_rows.get().task == other

        stopped = client.post(reverse('timer_stop'))
        assert stopped.status_code == 204
        assert not TimeEntry.objects.filter(user=user, ended_at__isnull=True).exists()

    def test_editor_sees_start_on_the_task_drawer_and_full_page(self, client):
        user, task = _member()
        client.force_login(user)
        detail = client.get(reverse('task_detail', args=[task.pk])).content.decode()
        full = client.get(reverse('task_full_page', args=[task.project.pk, task.pk])).content.decode()
        assert f'id="time-start-{task.pk}"' in detail
        assert f'id="time-start-{task.pk}"' in full

    def test_manual_validation(self, client):
        user, task = _member()
        client.force_login(user)
        start = timezone.now() - timedelta(hours=3)
        end = timezone.now() - timedelta(hours=1)

        bad_order = client.post(reverse('time_log', args=[task.pk]), {
            'started_at': _stamp(end),
            'ended_at': _stamp(start),
            'note': '',
        })
        assert bad_order.status_code == 200
        assert 'End must be after start.' in bad_order.content.decode()
        assert not TimeEntry.objects.filter(task=task).exists()

        inline = client.post(reverse('time_log', args=[task.pk]), {
            'started_at': _stamp(end),
            'ended_at': _stamp(start),
            'note': '',
            'inline': '1',
        })
        assert inline.status_code == 400
        assert inline.content.decode() == 'End must be after start.'

        future = client.post(reverse('time_log', args=[task.pk]), {
            'started_at': _stamp(timezone.now() + timedelta(hours=1)),
            'ended_at': _stamp(timezone.now() + timedelta(hours=2)),
            'note': '',
        })
        assert future.status_code == 200
        assert 'End cannot be in the future.' in future.content.decode()

        ok = client.post(reverse('time_log', args=[task.pk]), {
            'started_at': _stamp(start),
            'ended_at': _stamp(end),
            'note': 'shipped it',
        })
        assert ok.status_code == 200
        assert ok.headers['HX-Trigger']
        entry = TimeEntry.objects.get(task=task, user=user)
        assert entry.note == 'shipped it'
        assert entry.ended_at > entry.started_at

    def test_page_render_closes_at_start_plus_twelve_hours(self, client):
        user, task = _member()
        started = timezone.now() - timedelta(hours=14)
        entry = TimeEntryFactory(user=user, task=task, started_at=started, ended_at=None)
        client.force_login(user)

        response = client.get(reverse('dashboard'))

        entry.refresh_from_db()
        assert entry.ended_at == started + timedelta(hours=12)
        assert response.context['running_timer'] is None

    def test_running_timer_is_in_the_layout(self, client):
        user, task = _member()
        task.title = 'Timer Visible Task'
        task.save()
        TimeEntryFactory(user=user, task=task, running=True)
        client.force_login(user)

        response = client.get(reverse('dashboard'))

        assert response.context['running_timer'].task == task
        content = response.content.decode()
        assert 'Timer Visible Task' in content
        assert 'runningTimer(' in content
        assert reverse('timer_stop') in content


@pytest.mark.django_db
class TestWeekAndProjectViews:
    def test_week_page_is_linked_under_my_tasks(self, client):
        user, _task = _member()
        client.force_login(user)
        content = client.get(reverse('my_tasks')).content.decode()
        assert reverse('time_week') in content
        assert 'My Week' in content

    def test_week_and_project_filters(self, client):
        user, task = _member()
        task.title = 'This Week Task'
        task.save()
        monday, week_start = _monday_start()
        TimeEntryFactory(
            user=user, task=task,
            started_at=week_start + timedelta(hours=9),
            ended_at=week_start + timedelta(hours=10),
        )
        last = TaskFactory(project=task.project, status=task.status, title='Last Week Task')
        TimeEntryFactory(
            user=user, task=last,
            started_at=week_start - timedelta(days=3),
            ended_at=week_start - timedelta(days=3) + timedelta(hours=1),
        )
        other = TaskFactory(title='Other Project Task')
        ProjectAccessFactory(project=other.project, user=user)
        TimeEntryFactory(
            user=user, task=other,
            started_at=week_start + timedelta(hours=11),
            ended_at=week_start + timedelta(hours=12),
        )
        client.force_login(user)

        week = client.get(reverse('time_week')).content.decode()
        assert 'This Week Task' in week
        assert 'Other Project Task' in week
        assert 'Last Week Task' not in week

        filtered = client.get(reverse('time_week'), {'project': task.project.pk}).content.decode()
        assert 'This Week Task' in filtered
        assert 'Other Project Task' not in filtered

        earlier = client.get(
            reverse('time_week'),
            {'week': (monday - timedelta(days=7)).isoformat()},
        ).content.decode()
        assert 'Last Week Task' in earlier
        assert 'This Week Task' not in earlier

    def test_manager_sees_but_cannot_edit_someone_elses_entry(self, client):
        owner, task = _member('editor')
        owner.name = 'Owner Person'
        owner.save()
        task.title = 'Shared Task'
        task.save()
        manager = UserFactory(name='Manager Person')
        ProjectAccessFactory(project=task.project, user=manager)
        monday, week_start = _monday_start()
        entry = TimeEntryFactory(
            user=owner, task=task, note='owner-only-note',
            started_at=week_start + timedelta(hours=3),
            ended_at=week_start + timedelta(hours=4),
        )
        client.force_login(manager)

        week = client.get(reverse('time_week'), {'project': task.project.pk})
        assert week.status_code == 200
        content = week.content.decode()
        assert 'Shared Task' not in content
        assert 'Owner Person' not in content
        assert 'owner-only-note' not in content

        detail = client.get(reverse('task_detail', args=[task.pk])).content.decode()
        assert 'owner-only-note' not in detail
        assert reverse('time_entry_edit', args=[entry.pk]) not in detail

        edit = client.post(reverse('time_entry_edit', args=[entry.pk]), {
            'started_at': _stamp(entry.started_at),
            'ended_at': _stamp(entry.ended_at),
            'note': 'changed',
        })
        assert edit.status_code == 403
        delete = client.post(reverse('time_entry_delete', args=[entry.pk]))
        assert delete.status_code == 403
        entry.refresh_from_db()
        assert entry.note == 'owner-only-note'

    def test_editor_does_not_see_someone_elses_entry_on_the_project_week(self, client):
        owner, task = _member('editor')
        task.title = 'Hidden From Editor'
        task.save()
        editor = UserFactory()
        ProjectAccessFactory(project=task.project, user=editor)
        _, week_start = _monday_start()
        TimeEntryFactory(
            user=owner, task=task, note='not-for-editor',
            started_at=week_start + timedelta(hours=3),
            ended_at=week_start + timedelta(hours=4),
        )
        client.force_login(editor)

        content = client.get(reverse('time_week'), {'project': task.project.pk}).content.decode()
        assert 'Hidden From Editor' not in content
        assert 'not-for-editor' not in content

    def test_admin_can_edit_any_entry(self, client):
        owner, task = _member()
        _, week_start = _monday_start()
        entry = TimeEntryFactory(
            user=owner, task=task, note='before',
            started_at=week_start + timedelta(hours=1),
            ended_at=week_start + timedelta(hours=2),
        )
        admin = AdminUserFactory()
        client.force_login(admin)

        response = client.post(reverse('time_entry_edit', args=[entry.pk]), {
            'started_at': _stamp(entry.started_at),
            'ended_at': _stamp(entry.ended_at),
            'note': 'after',
        })
        assert response.status_code == 200
        entry.refresh_from_db()
        assert entry.note == 'after'

    def test_non_member_cannot_open_a_project_week(self, client):
        user = UserFactory()
        task = TaskFactory()
        client.force_login(user)
        response = client.get(reverse('time_week'), {'project': task.project.pk})
        assert response.status_code == 403

    def test_project_sidebar_links_time_tracking_and_leaves_the_others_disabled(self, client):
        user, task = _member('viewer')
        client.force_login(user)
        content = client.get(reverse('project_detail', args=[task.project.pk])).content.decode()
        assert f'href="{reverse("time_week")}?project={task.project.pk}"' in content
        assert 'Time Tracking' in content
        disabled_icons = re.findall(
            r'cursor-not-allowed">\s*<i data-lucide="([^"]+)"',
            content,
        )
        assert disabled_icons == ['users', 'file-text']


@pytest.mark.django_db
class TestLoggedHoursRow:
    def test_no_entries_shows_zero_hours(self, client):
        user, task = _member('viewer')
        client.force_login(user)

        detail = client.get(reverse('task_detail', args=[task.pk])).content.decode()
        full = client.get(
            reverse('task_full_page', args=[task.project.pk, task.pk])
        ).content.decode()
        row = client.get(reverse('task_logged_total', args=[task.pk]))

        assert row.status_code == 200
        for page in (detail, full, row.content.decode()):
            assert f'id="prop-logged-{task.pk}"' in page
            assert 'Logged' in page
            assert '0h' in page
            assert '0h 00m' not in page

    def test_drawer_and_full_page_render_the_logged_row_for_a_viewer(self, client):
        viewer, task = _member('viewer')
        owner = UserFactory()
        other = UserFactory()
        now = timezone.now()
        TimeEntryFactory(
            user=owner, task=task, note='owner-private-note',
            started_at=now - timedelta(hours=3),
            ended_at=now - timedelta(hours=1),
        )
        TimeEntryFactory(
            user=other, task=task, note='other-private-note',
            started_at=now - timedelta(hours=2, minutes=5),
            ended_at=now - timedelta(hours=1),
        )
        client.force_login(viewer)

        detail = client.get(reverse('task_detail', args=[task.pk])).content.decode()
        full = client.get(
            reverse('task_full_page', args=[task.project.pk, task.pk])
        ).content.decode()

        for page in (detail, full):
            assert f'id="prop-logged-{task.pk}"' in page
            assert 'Logged' in page
            assert '3h 05m' in page
            assert 'timerChanged from:body' in page
            assert 'owner-private-note' not in page
            assert 'other-private-note' not in page

    def test_logged_total_endpoint_is_viewer_only(self, client):
        viewer, task = _member('viewer')
        outsider = UserFactory()
        client.force_login(viewer)
        allowed = client.get(reverse('task_logged_total', args=[task.pk]))
        assert allowed.status_code == 200
        body = allowed.content.decode()
        assert 'timerChanged from:body' in body
        assert reverse('task_logged_total', args=[task.pk]) in body

        client.force_login(outsider)
        assert client.get(reverse('task_logged_total', args=[task.pk])).status_code == 403


@pytest.mark.django_db
class TestCloseExpiredCommand:
    def test_command_closes_with_the_same_twelve_hour_mark(self):
        user, task = _member()
        started = timezone.now() - timedelta(hours=20)
        entry = TimeEntryFactory(user=user, task=task, started_at=started, ended_at=None)
        out = StringIO()

        call_command('close_expired_timers', stdout=out)

        entry.refresh_from_db()
        assert entry.ended_at == started + timedelta(hours=12)
        assert 'Closed 1' in out.getvalue()

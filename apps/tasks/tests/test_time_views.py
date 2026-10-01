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
            name='TaskViewerTimer',
            access_projects=True,
            access_tasks=True,
        )
        user = UserFactory(permission_preset=preset)
        ProjectAccessFactory(project=task.project, user=user)
        client.force_login(user)

        assert client.post(reverse('timer_start', args=[task.pk])).status_code == 403
        assert client.post(reverse('time_log', args=[task.pk])).status_code == 403
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

    def test_logging_by_duration_and_day(self, client):
        user, task = _member()
        client.force_login(user)
        url = reverse('time_log', args=[task.pk])
        today = timezone.localdate()

        def post(**data):
            return client.post(url, {'duration': '45m', 'day': today.isoformat(), 'note': '', **data})

        bare = post(duration='15')
        assert bare.status_code == 200
        assert '30m or 2h' in bare.content.decode()

        future = post(day=(today + timedelta(days=1)).isoformat())
        assert future.status_code == 200
        assert 'future' in future.content.decode()

        no_day = post(day='')
        assert 'required' in no_day.content.decode().lower()
        assert not TimeEntry.objects.filter(task=task).exists()

        ok = post(duration='1h 30m', day=(today - timedelta(days=1)).isoformat(), note='shipped it')
        assert ok.status_code == 200
        assert ok.content == b''
        assert ok.headers['HX-Trigger'] == 'timerChanged'
        entry = TimeEntry.objects.get(task=task, user=user)
        assert entry.note == 'shipped it'
        assert entry.ended_at - entry.started_at == timedelta(minutes=90)
        assert timezone.localdate(entry.started_at) == today - timedelta(days=1)

    def test_logging_from_the_popover_does_not_close_the_drawer(self, client):
        user, task = _member()
        client.force_login(user)
        response = client.post(reverse('time_log', args=[task.pk]), {
            'duration': '20m', 'day': timezone.localdate().isoformat(), 'note': '',
        })
        assert 'closeSlideOver' not in response.headers['HX-Trigger']

    def test_editing_an_entry_closes_its_drawer_and_keeps_the_start(self, client):
        user, task = _member()
        started = timezone.now() - timedelta(hours=2)
        entry = TimeEntryFactory(user=user, task=task, started_at=started, ended_at=started + timedelta(hours=1))
        client.force_login(user)
        url = reverse('time_entry_edit', args=[entry.pk])

        form = client.get(url).content.decode()
        assert 'name="duration"' in form and 'value="1h"' in form
        assert 'name="started_at"' not in form

        response = client.post(url, {
            'duration': '2h 15m', 'day': timezone.localdate(started).isoformat(), 'note': 'longer',
        })
        assert 'closeSlideOver' in response.headers['HX-Trigger']
        entry.refresh_from_db()
        assert entry.started_at == started
        assert entry.ended_at == started + timedelta(minutes=135)

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
        content = client.get(reverse('my_tasks'), {'layout': 'list'}).content.decode()
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
            'duration': '30m',
            'day': timezone.localdate(entry.started_at).isoformat(),
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
            'duration': '30m',
            'day': timezone.localdate(entry.started_at).isoformat(),
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

    def test_project_sidebar_links_time_tracking_and_team(self, client):
        user, task = _member('viewer')
        client.force_login(user)
        content = client.get(reverse('project_detail', args=[task.project.pk])).content.decode()
        assert f'href="{reverse("time_week")}?project={task.project.pk}"' in content
        assert 'Time Tracking' in content
        assert f'href="{reverse("project_detail_team", args=[task.project.pk])}"' in content
        disabled_icons = re.findall(
            r'cursor-not-allowed">\s*<i data-lucide="([^"]+)"',
            content,
        )
        assert disabled_icons == ['file-text']


def _view_only_user(task):
    from apps.accounts.permissions import PermissionPreset

    preset = PermissionPreset.objects.create(name='TimeViewOnly', access_projects=True, access_tasks=True)
    user = UserFactory(permission_preset=preset)
    ProjectAccessFactory(project=task.project, user=user)
    return user


def _pages(client, task):
    detail = client.get(reverse('task_detail', args=[task.pk])).content.decode()
    full = client.get(reverse('task_full_page', args=[task.project.pk, task.pk])).content.decode()
    return detail, full


@pytest.mark.django_db
class TestTimeProperty:
    def test_one_time_property_replaces_the_estimate_and_logged_rows(self, client):
        user, task = _member()
        client.force_login(user)
        for page in _pages(client, task):
            assert f'id="prop-time-{task.pk}"' in page
            assert f'id="prop-logged-{task.pk}"' not in page
            assert f'id="prop-estimate-{task.pk}"' not in page

    def test_it_reads_logged_over_estimate(self, client):
        user, task = _member(estimate_minutes=240)
        now = timezone.now()
        TimeEntryFactory(user=user, task=task, started_at=now - timedelta(hours=3), ended_at=now - timedelta(minutes=45))
        client.force_login(user)

        response = client.get(reverse('task_time_property', args=[task.pk]))

        html = response.content.decode()
        assert response.status_code == 200
        assert re.search(r'id="time-logged-\d+"[^>]*>\s*2h 15m\s*/', html)
        assert '4h' in client.get(reverse('task_detail', args=[task.pk])).content.decode()
        assert 'role="progressbar"' in html
        assert 'aria-valuenow="135"' in html and 'aria-valuemax="240"' in html
        assert 'Over by' not in html

    def test_going_over_is_written_out_and_not_only_coloured(self, client):
        user, task = _member(estimate_minutes=60)
        now = timezone.now()
        TimeEntryFactory(user=user, task=task, started_at=now - timedelta(hours=2), ended_at=now - timedelta(minutes=15))
        client.force_login(user)

        html = client.get(reverse('task_time_property', args=[task.pk])).content.decode()

        assert 'Over by 45m' in html
        assert 'width: 100%' in html

    def test_no_estimate_means_no_bar(self, client):
        user, task = _member()
        now = timezone.now()
        TimeEntryFactory(user=user, task=task, started_at=now - timedelta(hours=1), ended_at=now)
        client.force_login(user)

        html = client.get(reverse('task_time_property', args=[task.pk])).content.decode()

        assert 'progressbar' not in html
        assert '1h' in html

    def test_nothing_logged_reads_zero(self, client):
        user, task = _member(estimate_minutes=60)
        client.force_login(user)
        html = client.get(reverse('task_time_property', args=[task.pk])).content.decode()
        assert re.search(r'id="time-logged-\d+"[^>]*>\s*0m\s*/', html)
        assert 'Over by' not in html

    def test_someone_who_cannot_log_sees_the_total_and_no_controls(self, client):
        task = TaskFactory(estimate_minutes=120)
        user = _view_only_user(task)
        TimeEntryFactory(user=UserFactory(), task=task, started_at=timezone.now() - timedelta(hours=2),
                         ended_at=timezone.now() - timedelta(hours=1))
        client.force_login(user)

        detail, full = _pages(client, task)
        live = client.get(reverse('task_time_property', args=[task.pk])).content.decode()

        for page in (detail, full, live):
            assert f'id="time-start-{task.pk}"' not in page
            assert f'id="time-header-{task.pk}"' not in page
            assert 'Log time' not in page
            assert '1h' in page

    def test_the_header_button_is_for_people_who_can_log_and_has_its_own_id(self, client):
        user, task = _member()
        client.force_login(user)
        for page in _pages(client, task):
            assert f'id="time-header-{task.pk}"' in page
            assert f'id="time-header-start-{task.pk}"' in page

    def test_the_header_button_arrives_out_of_band_from_the_same_endpoint(self, client):
        user, task = _member()
        client.force_login(user)
        html = client.get(reverse('task_time_property', args=[task.pk])).content.decode()
        assert re.search(rf'id="time-header-{task.pk}"[^>]*hx-swap-oob', html) or re.search(
            rf'hx-swap-oob="[^"]*"[^>]*id="time-header-{task.pk}"', html
        )
        # Only the property listens for the refresh.
        assert html.count('timerChanged from:body') == 1

    def test_start_and_stop_follow_the_running_timer(self, client):
        user, task = _member()
        client.force_login(user)
        idle = client.get(reverse('task_time_property', args=[task.pk])).content.decode()
        assert f'id="time-start-{task.pk}"' in idle and f'id="time-header-start-{task.pk}"' in idle

        TimeEntryFactory(user=user, task=task, running=True)
        running = client.get(reverse('task_time_property', args=[task.pk])).content.decode()
        assert f'id="time-stop-{task.pk}"' in running and f'id="time-header-stop-{task.pk}"' in running
        assert f'id="time-start-{task.pk}"' not in running

    def test_it_says_where_the_running_timer_stops(self, client):
        user, task = _member()
        elsewhere = TaskFactory(project=task.project, status=task.status, title='Elsewhere task')
        TimeEntryFactory(user=user, task=elsewhere, running=True)
        client.force_login(user)
        html = client.get(reverse('task_time_property', args=[task.pk])).content.decode()
        assert 'Starting here stops the timer on Elsewhere task' in html

    def test_the_popovers_are_not_replaced_by_the_refresh(self, client):
        user, task = _member()
        client.force_login(user)
        live = client.get(reverse('task_time_property', args=[task.pk])).content.decode()
        page, _ = _pages(client, task)
        # The log form and its dropdown exist on the page, not in what the refresh swaps in.
        assert 'name="duration"' in page
        assert 'name="duration"' not in live
        assert 'name="estimate"' not in live

    def test_the_endpoint_is_for_people_who_can_view_the_task(self, client):
        task = TaskFactory()
        client.force_login(UserFactory())
        assert client.get(reverse('task_time_property', args=[task.pk])).status_code == 403

    def test_the_body_no_longer_has_start_stop_or_the_two_date_form(self, client):
        user, task = _member()
        client.force_login(user)
        section = client.get(reverse('task_time_section', args=[task.pk])).content.decode()
        assert f'id="time-start-{task.pk}"' not in section
        assert 'datetime-local' not in section
        assert 'No time logged yet.' in section

    def test_the_full_page_list_keeps_its_spacing_when_it_refreshes(self, client):
        user, task = _member()
        client.force_login(user)
        page = client.get(reverse('task_full_page', args=[task.project.pk, task.pk])).content.decode()
        refresh_url = reverse('task_time_section', args=[task.pk]) + '?full_page=1'
        assert refresh_url in page
        assert 'mb-5' in client.get(refresh_url).content.decode()
        assert 'mb-5' not in client.get(reverse('task_time_section', args=[task.pk])).content.decode()

    def test_entries_show_a_date_and_a_duration_and_no_clock_times(self, client):
        user, task = _member()
        day = timezone.localdate() - timedelta(days=2)
        started = timezone.make_aware(datetime.combine(day, time(9, 41)))
        TimeEntryFactory(user=user, task=task, started_at=started, ended_at=started + timedelta(minutes=90))
        client.force_login(user)

        section = client.get(reverse('task_time_section', args=[task.pk])).content.decode()

        assert f'{day:%b} {day.day}' in section
        assert '1h 30m' in section
        assert '09:41' not in section and '11:11' not in section

    def test_my_week_has_date_and_duration_columns(self, client):
        user, task = _member()
        _, week_start = _monday_start()
        TimeEntryFactory(user=user, task=task, started_at=week_start, ended_at=week_start + timedelta(minutes=45))
        client.force_login(user)

        html = client.get(reverse('time_week')).content.decode()

        assert '>Date<' in html and '>Duration<' in html
        assert '>Start<' not in html and '>End<' not in html
        assert '45m' in html


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

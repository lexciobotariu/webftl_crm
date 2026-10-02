import re
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.projects.factories import ProjectAccessFactory
from apps.tasks import services
from apps.tasks.factories import TaskFactory, TimeEntryFactory
from apps.tasks.models import TaskActivity, TimeEntry
from apps.tasks.templatetags.task_activity import task_activities


def _text(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


def _member(name='Lex', **task_kwargs):
    user = UserFactory(name=name)
    task = TaskFactory(**task_kwargs)
    ProjectAccessFactory(project=task.project, user=user)
    return user, task


def _teammate(task, name):
    user = UserFactory(name=name)
    ProjectAccessFactory(project=task.project, user=user)
    return user


def _view_all_user(task, name='Boss'):
    preset = PermissionPreset.objects.create(
        name=f'ViewAll{name}', access_projects=True, access_tasks=True, tasks_view_all=True,
    )
    return UserFactory(name=name, permission_preset=preset)


def _log(task, user, minutes, note='', days_ago=0):
    return services.log_duration(task, user, minutes, timezone.localdate() - timedelta(days=days_ago), note)


def _feed_html(client, task):
    return client.get(reverse('task_activity_list', args=[task.pk])).content.decode()


@pytest.mark.django_db
class TestTheMergedFeed:
    def test_it_orders_activity_and_time_by_when_each_was_logged(self):
        user, task = _member()
        task.activities.all().delete()
        early = TaskActivity.objects.create(task=task, user=user, activity_type='comment', content='first')
        TaskActivity.objects.filter(pk=early.pk).update(created_at=timezone.now() - timedelta(hours=3))
        # Logged now, for two days ago: it belongs next to today's activity, not days back.
        late_entry = _log(task, user, 30, 'old work', days_ago=2)
        newer = TaskActivity.objects.create(task=task, user=user, activity_type='comment', content='last')

        items = task_activities(task, user)

        assert [(i.item_type, i.pk) for i in items] == [
            ('activity', early.pk), ('work', late_entry.pk), ('activity', newer.pk),
        ]

    def test_time_rows_have_their_own_ids(self, client):
        user, task = _member()
        entry = _log(task, user, 90, 'pairing')
        client.force_login(user)
        html = _feed_html(client, task)
        assert f'id="time-entry-{entry.pk}"' in html
        assert f'id="activity-{entry.pk}"' not in html

    def test_a_row_reads_who_logged_how_much_and_the_note(self, client):
        user, task = _member('Lex')
        _log(task, user, 90, 'pairing on the API')
        client.force_login(user)
        text = _text(_feed_html(client, task))
        assert 'Lex logged 1h 30m — pairing on the API' in text

    def test_a_running_timer_reads_as_such(self, client):
        user, task = _member('Lex')
        TimeEntryFactory(user=user, task=task, running=True)
        client.force_login(user)
        assert 'timer running' in _text(_feed_html(client, task))

    def test_rows_are_marked_by_kind_for_the_tabs(self, client):
        user, task = _member()
        entry = _log(task, user, 20)
        comment = TaskActivity.objects.create(task=task, user=user, activity_type='comment', content='hello')
        client.force_login(user)
        html = _feed_html(client, task)
        assert re.search(rf'id="time-entry-{entry.pk}"[^>]*data-kind="work"', html)
        assert re.search(rf'id="activity-{comment.pk}"[^>]*data-kind="comment"', html)
        assert 'data-kind="event"' in html  # "created this task" and the like

    def test_the_tabs_show_empty_states_for_what_they_hide(self, client):
        user, task = _member()
        client.force_login(user)
        html = _feed_html(client, task)
        assert 'data-empty="comments"' in html and 'data-empty="work"' in html


@pytest.mark.django_db
class TestWhoSeesWhichTime:
    def test_you_see_your_own_time_and_not_a_colleagues(self, client):
        user, task = _member('Lex')
        other = _teammate(task, 'Ana')
        _log(task, user, 30, 'mine')
        _log(task, other, 45, 'hers')
        client.force_login(user)
        text = _text(_feed_html(client, task))
        assert 'mine' in text
        assert 'her-note' not in text and 'Ana logged' not in text

    def test_an_admin_and_view_all_see_everyones(self, client):
        user, task = _member('Lex')
        _log(task, user, 30, 'mine')
        for viewer in (AdminUserFactory(name='Root'), _view_all_user(task)):
            client.force_login(viewer)
            assert 'Lex logged 30m — mine' in _text(_feed_html(client, task))

    def test_nothing_without_access_to_the_task(self, client):
        user, task = _member()
        _log(task, user, 30, 'secret')
        client.force_login(UserFactory())
        assert client.get(reverse('task_activity_list', args=[task.pk])).status_code == 403


@pytest.mark.django_db
class TestQueryCount:
    def _count(self, client, task):
        with CaptureQueriesContext(connection) as queries:
            assert client.get(reverse('task_activity_list', args=[task.pk])).status_code == 200
        return len(queries)

    def test_more_entries_and_more_people_cost_no_more_queries(self, client):
        user, task = _member()
        people = [_teammate(task, f'P{i}') for i in range(4)]
        client.force_login(user)
        _log(task, user, 10)
        self._count(client, task)  # the first request also loads the session and the user
        baseline = self._count(client, task)

        for i in range(12):
            _log(task, user, 5 + i, f'n{i}')
            TaskActivity.objects.create(task=task, user=people[i % 4], activity_type='comment', content=f'c{i}')

        assert self._count(client, task) == baseline

    def test_the_same_holds_for_someone_who_sees_everyones(self, client):
        user, task = _member()
        boss = _view_all_user(task)
        client.force_login(boss)
        _log(task, user, 10)
        self._count(client, task)
        baseline = self._count(client, task)
        for i in range(10):
            _log(task, _teammate(task, f'Q{i}'), 5)
        assert self._count(client, task) == baseline


@pytest.mark.django_db
class TestRowActions:
    def test_the_author_gets_edit_and_delete(self, client):
        user, task = _member()
        entry = _log(task, user, 30)
        client.force_login(user)
        html = _feed_html(client, task)
        assert reverse('time_entry_edit', args=[entry.pk]) in html
        assert reverse('time_entry_delete', args=[entry.pk]) in html

    def test_an_admin_gets_them_on_anyones_row(self, client):
        user, task = _member()
        entry = _log(task, user, 30)
        client.force_login(AdminUserFactory())
        assert reverse('time_entry_edit', args=[entry.pk]) in _feed_html(client, task)

    def test_a_view_all_user_sees_but_cannot_change_someone_elses(self, client):
        user, task = _member()
        entry = _log(task, user, 30, 'theirs')
        client.force_login(_view_all_user(task))
        html = _feed_html(client, task)
        assert 'theirs' in html
        assert reverse('time_entry_edit', args=[entry.pk]) not in html
        assert reverse('time_entry_delete', args=[entry.pk]) not in html

    def test_an_author_who_can_no_longer_edit_the_task_loses_them(self, client):
        task = TaskFactory()
        preset = PermissionPreset.objects.create(name='ViewOnlyAuthor', access_projects=True, access_tasks=True)
        user = UserFactory(permission_preset=preset)
        ProjectAccessFactory(project=task.project, user=user)
        entry = TimeEntryFactory(user=user, task=task)
        client.force_login(user)
        html = _feed_html(client, task)
        assert f'id="time-entry-{entry.pk}"' in html
        assert reverse('time_entry_edit', args=[entry.pk]) not in html

    def test_a_running_timer_can_be_deleted_but_not_edited(self, client):
        user, task = _member()
        entry = TimeEntryFactory(user=user, task=task, running=True)
        client.force_login(user)
        html = _feed_html(client, task)
        assert reverse('time_entry_delete', args=[entry.pk]) in html
        assert reverse('time_entry_edit', args=[entry.pk]) not in html


@pytest.mark.django_db
class TestInPlaceEditAndDelete:
    def test_edit_opens_a_form_in_place_of_the_row(self, client):
        user, task = _member()
        entry = _log(task, user, 90, 'pairing')
        client.force_login(user)

        response = client.get(reverse('time_entry_edit', args=[entry.pk]))

        html = response.content.decode()
        assert f'id="time-entry-{entry.pk}"' in html
        assert 'name="duration"' in html and 'value="1h 30m"' in html
        assert 'name="day"' in html and 'pairing' in html
        assert '<form' in html

    def test_saving_swaps_the_row_back_and_tells_the_property(self, client):
        user, task = _member()
        entry = _log(task, user, 90, 'pairing')
        client.force_login(user)

        response = client.post(reverse('time_entry_edit', args=[entry.pk]), {
            'duration': '2h', 'day': timezone.localdate().isoformat(), 'note': 'longer',
        })

        assert response.status_code == 200
        # After the swap: while the edit form is still in the list, the list skips a
        # refresh, and the Work log totals would keep the old duration.
        assert response.headers['HX-Trigger-After-Settle'] == 'timerChanged'
        assert 'HX-Trigger' not in response.headers
        text = _text(response.content.decode())
        assert 'logged 2h — longer' in text
        assert '<form' not in response.content.decode()
        entry.refresh_from_db()
        assert entry.ended_at - entry.started_at == timedelta(hours=2)

    def test_a_refused_save_keeps_the_form_with_the_reason(self, client):
        user, task = _member()
        entry = _log(task, user, 90)
        client.force_login(user)
        response = client.post(reverse('time_entry_edit', args=[entry.pk]), {
            'duration': '15', 'day': timezone.localdate().isoformat(), 'note': '',
        })
        html = response.content.decode()
        assert '<form' in html and '30m or 2h' in html
        assert f'id="time-entry-{entry.pk}"' in html

    def test_cancel_puts_the_row_back(self, client):
        user, task = _member()
        entry = _log(task, user, 90, 'pairing')
        client.force_login(user)
        response = client.get(reverse('time_entry_edit', args=[entry.pk]) + '?cancel=1')
        html = response.content.decode()
        assert '<form' not in html and 'pairing' in html

    def test_delete_answers_with_an_empty_200_and_tells_the_property(self, client):
        user, task = _member()
        entry = _log(task, user, 30)
        client.force_login(user)

        response = client.post(reverse('time_entry_delete', args=[entry.pk]))

        assert response.status_code == 200
        assert response.content == b''
        assert response.headers['HX-Trigger'] == 'timerChanged'
        assert not TimeEntry.objects.filter(pk=entry.pk).exists()

    def test_someone_else_cannot_edit_or_delete(self, client):
        user, task = _member()
        entry = _log(task, user, 30)
        other = _teammate(task, 'Ana')
        client.force_login(other)
        assert client.get(reverse('time_entry_edit', args=[entry.pk])).status_code == 403
        assert client.post(reverse('time_entry_delete', args=[entry.pk])).status_code == 403


@pytest.mark.django_db
class TestWorkLogTotals:
    def test_the_work_log_starts_with_a_total_per_person(self, client):
        user, task = _member('Lex')
        ana = _teammate(task, 'Ana')
        _log(task, user, 90)
        _log(task, user, 30)
        _log(task, ana, 45)
        client.force_login(_view_all_user(task))

        html = _feed_html(client, task)

        assert 'data-kind="summary"' in html
        summary = _text(html[html.index('data-kind="summary"'):html.index('id="time-entry-')])
        assert 'Lex 2h' in summary and 'Ana 45m' in summary
        assert 'Others' not in summary
        assert 'Total 2h 45m' in summary

    def test_what_you_cannot_see_is_one_others_line_so_the_sum_matches_the_property(self, client):
        user, task = _member('Lex')
        ana = _teammate(task, 'Ana')
        _log(task, user, 60)
        _log(task, ana, 45)
        _log(task, ana, 30)
        client.force_login(user)

        html = _feed_html(client, task)
        summary = _text(html[html.index('data-kind="summary"'):html.index('id="time-entry-')])
        prop = client.get(reverse('task_time_property', args=[task.pk])).content.decode()

        assert 'Lex 1h' in summary
        assert 'Others 1h 15m' in summary
        assert 'Ana' not in summary
        assert 'Total 2h 15m' in summary
        assert '2h 15m' in _text(prop)

    def test_no_summary_when_there_is_no_time(self, client):
        user, task = _member()
        client.force_login(user)
        assert 'data-kind="summary"' not in _feed_html(client, task)


@pytest.mark.django_db
class TestTabs:
    def _page(self, client, task):
        return client.get(reverse('task_full_page', args=[task.project.pk, task.pk])).content.decode()

    def test_an_accessible_tablist_with_all_comments_and_work_log(self, client):
        user, task = _member()
        client.force_login(user)
        for page in (self._page(client, task), client.get(reverse('task_detail', args=[task.pk])).content.decode()):
            assert re.search(r'role="tablist"[^>]*aria-label="Filter activity"', page)
            tabs = re.findall(r'role="tab"[^>]*>\s*([A-Za-z ]+?)\s*<', page)
            assert [t for t in tabs if t in ('All', 'Comments', 'Work log')] == ['All', 'Comments', 'Work log']
            assert 'activityFilter' in page

    def test_every_open_starts_on_all(self, client):
        user, task = _member()
        client.force_login(user)
        page = self._page(client, task)
        assert 'x-data="activityFilter"' in page
        assert 'data-filter="all"' in page

    def test_a_comment_written_from_work_log_brings_the_tab_back_to_all(self, client):
        user, task = _member()
        client.force_login(user)
        page = self._page(client, task)
        form = page[page.index(reverse('comment_create', args=[task.pk])):]
        assert "filter = 'all'" in form[:600]

    def test_the_list_also_refreshes_on_timer_changes_but_not_while_editing(self, client):
        user, task = _member()
        client.force_login(user)
        page = self._page(client, task)
        trigger = re.search(r'id="activity-list-\d+"[^>]*hx-trigger="([^"]+)"', page, re.S).group(1)
        assert 'timerChanged' in trigger and 'activityUpdated' in trigger
        assert trigger.count("document.querySelector('#activity-items-") == 2

    def test_the_task_body_has_no_time_section_any_more(self, client):
        user, task = _member()
        client.force_login(user)
        for page in (self._page(client, task), client.get(reverse('task_detail', args=[task.pk])).content.decode()):
            assert f'id="time-tracking-{task.pk}"' not in page
            assert 'No time logged yet.' not in page.split('id="activity-items-')[0]


@pytest.mark.django_db
class TestEditReviewFixes:
    def test_a_refused_edit_keeps_the_date(self, client):
        user, task = _member()
        entry = _log(task, user, 90, days_ago=1)
        day = (timezone.localdate() - timedelta(days=1)).isoformat()
        client.force_login(user)

        html = client.post(reverse('time_entry_edit', args=[entry.pk]), {
            'duration': '15', 'day': day, 'note': '',
        }).content.decode()

        assert 'Add a unit' in html
        assert f'name="day" id="id_day-{entry.pk}" value="{day}"' in html

    def test_editing_only_the_note_leaves_the_times_alone(self, client):
        # A timer of 29m 45s shows as 29m. Saving a note must not round it to 30m.
        user, task = _member()
        start = timezone.now() - timedelta(hours=2)
        entry = TimeEntryFactory(task=task, user=user, started_at=start,
                                 ended_at=start + timedelta(minutes=29, seconds=45))
        client.force_login(user)

        form = client.get(reverse('time_entry_edit', args=[entry.pk])).content.decode()
        assert 'value="29m"' in form

        services.update_entry(entry, user, minutes=29, day=timezone.localdate(start), note='noted')
        entry.refresh_from_db()

        assert entry.note == 'noted'
        assert entry.ended_at - entry.started_at == timedelta(minutes=29, seconds=45)

    def test_the_note_of_an_entry_longer_than_a_day_can_still_be_edited(self):
        # log_manual (imports) allows any length; the 24-hour rule is for new durations.
        user, task = _member()
        start = timezone.now() - timedelta(days=3)
        entry = TimeEntryFactory(task=task, user=user, started_at=start, ended_at=start + timedelta(hours=30))

        services.update_entry(entry, user, minutes=30 * 60, day=timezone.localdate(start), note='imported')
        entry.refresh_from_db()

        assert entry.note == 'imported'
        assert entry.ended_at - entry.started_at == timedelta(hours=30)

    def test_a_day_with_a_mistyped_year_is_refused(self):
        from datetime import date

        user, task = _member()

        with pytest.raises(ValueError, match='year'):
            services.log_duration(task, user, 30, date(25, 10, 1))
        assert not TimeEntry.objects.exists()


@pytest.mark.django_db
class TestTotalsReviewFixes:
    def test_two_people_with_the_same_name_are_two_lines(self, client):
        user, task = _member(name='Alex')
        twin = _teammate(task, 'Alex')
        boss = _view_all_user(task)
        _log(task, user, 60)
        _log(task, twin, 30)
        client.force_login(boss)

        text = _text(_feed_html(client, task))

        assert 'Alex 1h' in text and 'Alex 30m' in text
        assert 'Total 1h 30m' in text

    def test_a_running_timer_never_leaves_a_phantom_others_line(self, client):
        # The summary reads the clock once; two readings could differ by a second.
        user, task = _member()
        services.start_timer(task, user)
        client.force_login(user)

        text = _text(_feed_html(client, task))

        assert 'Others' not in text

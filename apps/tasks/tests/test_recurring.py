"""Recurring tasks: the schedule, the daily job and the views."""
import json
from datetime import date

import pytest
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.projects.factories import ProjectFactory
from apps.projects.models import Project
from apps.tasks import recurring
from apps.tasks.factories import SubtaskFactory, TaskFactory
from apps.tasks.models import RecurringTask, Task

pytestmark = pytest.mark.django_db


def _rule(project=None, **extra):
    values = {
        'project': project or ProjectFactory(), 'title': 'Checks', 'frequency': RecurringTask.MONTHLY,
        'start_date': date(2026, 1, 1), 'month_day': 1,
    }
    values.update(extra)
    return RecurringTask.objects.create(**values)


def _dates(rule, since, count):
    items = []
    for day in recurring.occurrences(rule, since):
        items.append(day)
        if len(items) == count:
            break
    return items


# --- The schedule --------------------------------------------------------


def test_daily_every_two_days():
    rule = _rule(frequency=RecurringTask.DAILY, interval=2, month_day=None, start_date=date(2026, 11, 1))
    assert _dates(rule, date(2026, 11, 4), 3) == [date(2026, 11, 5), date(2026, 11, 7), date(2026, 11, 9)]


def test_weekly_on_chosen_days_every_other_week():
    # 2 Nov 2026 is a Monday.
    rule = _rule(frequency=RecurringTask.WEEKLY, interval=2, weekdays='0,3', month_day=None,
                 start_date=date(2026, 11, 2))
    assert _dates(rule, date(2026, 11, 2), 4) == [
        date(2026, 11, 2), date(2026, 11, 5), date(2026, 11, 16), date(2026, 11, 19),
    ]
    assert recurring.describe(rule) == 'Every 2 weeks on Mon, Thu'


def test_monthly_on_the_last_day_and_on_day_31():
    last = _rule(month_day=RecurringTask.LAST_DAY, start_date=date(2026, 1, 15))
    assert _dates(last, date(2026, 1, 1), 3) == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
    day31 = _rule(month_day=31, start_date=date(2026, 1, 1))
    assert _dates(day31, date(2026, 2, 1), 2) == [date(2026, 2, 28), date(2026, 3, 31)]
    assert recurring.describe(last) == 'Every month on the last day'


def test_every_three_months_from_the_start():
    rule = _rule(interval=3, start_date=date(2026, 1, 1))
    assert _dates(rule, date(2026, 5, 1), 2) == [date(2026, 7, 1), date(2026, 10, 1)]


def test_yearly_on_29_february_falls_back_to_28():
    rule = _rule(frequency=RecurringTask.YEARLY, month_day=None, start_date=date(2028, 2, 29))
    assert _dates(rule, date(2028, 3, 1), 2) == [date(2029, 2, 28), date(2030, 2, 28)]
    assert recurring.date_label(rule, date(2029, 2, 28)) == '2029'


def test_schedule_stops_at_the_end_date():
    rule = _rule(start_date=date(2026, 1, 1), end_date=date(2026, 3, 15))
    assert list(recurring.occurrences(rule)) == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]


def test_saving_schedules_from_today_not_the_past():
    rule = _rule(start_date=date(2026, 1, 1))
    recurring.schedule(rule, today=date(2026, 11, 19))
    assert rule.next_date == date(2026, 12, 1)


# --- Creating tasks ------------------------------------------------------


def test_daily_job_creates_the_task_with_its_settings():
    admin = AdminUserFactory()
    project = ProjectFactory()
    rule = _rule(project, checklist='Backup\n\nUpdate plugins', assignee=admin, priority='high',
                 due_after_days=5, estimate_minutes=90, billable=False, next_date=date(2026, 11, 1))
    created = recurring.create_due_tasks(date(2026, 11, 1))
    assert len(created) == 1
    task = created[0]
    assert task.title == 'Checks · November 2026'
    assert task.assignee == admin and task.priority == 'high'
    assert task.start_date == date(2026, 11, 1) and task.due_date == date(2026, 11, 6)
    assert task.estimate_minutes == 90 and task.billable is False
    assert list(task.subtasks.values_list('title', flat=True)) == ['Backup', 'Update plugins']
    assert task.recurring == rule and task.recurring_date == date(2026, 11, 1)
    rule.refresh_from_db()
    assert rule.next_date == date(2026, 12, 1)
    assert recurring.create_due_tasks(date(2026, 11, 2)) == []


def test_a_new_task_comes_even_when_the_last_one_is_open():
    rule = _rule(next_date=date(2026, 10, 1))
    first = recurring.create_due_tasks(date(2026, 10, 1))
    second = recurring.create_due_tasks(date(2026, 11, 1))
    assert first[0].closed_at is None
    assert len(second) == 1 and rule.tasks.count() == 2


def test_missed_dates_are_skipped_not_created_late():
    rule = _rule(next_date=date(2026, 8, 1))
    created = recurring.create_due_tasks(date(2026, 11, 19))
    assert [task.recurring_date for task in created] == [date(2026, 11, 1)]
    rule.refresh_from_db()
    assert rule.next_date == date(2026, 12, 1)


def test_paused_rule_or_inactive_project_creates_nothing_but_moves_on():
    paused = _rule(paused=True, next_date=date(2026, 11, 1))
    on_hold = _rule(ProjectFactory(status=Project.ON_HOLD), next_date=date(2026, 11, 1))
    assert recurring.create_due_tasks(date(2026, 11, 1)) == []
    for rule in (paused, on_hold):
        rule.refresh_from_db()
        assert rule.next_date == date(2026, 12, 1)


def test_one_task_per_date():
    rule = _rule()
    assert recurring.create_task_for(rule, date(2026, 11, 1)) is not None
    assert recurring.create_task_for(rule, date(2026, 11, 1)) is None
    assert Task.objects.filter(recurring=rule).count() == 1


def test_assignee_without_access_is_dropped():
    rule = _rule(assignee=UserFactory())
    task = recurring.create_task_for(rule, date(2026, 11, 1))
    assert task.assignee is None


def test_create_now_makes_the_current_periods_task():
    rule = _rule(start_date=date(2026, 1, 1))
    day, task = recurring.create_now(rule, today=date(2026, 11, 19))
    assert day == date(2026, 11, 1) and task.recurring_date == day
    assert recurring.create_now(rule, today=date(2026, 11, 20)) == (day, None)
    rule.refresh_from_db()
    assert rule.next_date == date(2026, 12, 1)


def test_create_now_before_the_start_says_when_it_starts():
    from django.core.exceptions import ValidationError

    rule = _rule(start_date=date(2027, 1, 1))
    with pytest.raises(ValidationError) as error:
        recurring.create_now(rule, today=date(2026, 11, 19))
    assert '1 Jan 2027' in error.value.messages[0]


def test_title_without_the_date():
    rule = _rule(add_date_to_title=False)
    assert recurring.task_title(rule, date(2026, 11, 1)) == 'Checks'


# --- Views ---------------------------------------------------------------


def _post_rule(client, project, **extra):
    data = {
        'title': 'Weekly report', 'frequency': 'weekly', 'interval': '1', 'weekday_choices': ['0', '4'],
        'start_date': '2026-11-02', 'due_after_days': '2', 'estimate': '1h 30m', 'add_date_to_title': 'on',
        'priority': '', 'checklist': 'Collect numbers\nSend',
    }
    data.update(extra)
    return client.post(reverse('recurring_create', args=[project.pk]), data)


def test_create_edit_pause_run_and_delete(client):
    admin = AdminUserFactory()
    project = ProjectFactory()
    client.force_login(admin)
    assert client.get(reverse('recurring_create', args=[project.pk])).status_code == 200

    response = _post_rule(client, project)
    assert response.status_code == 200, response.content
    events = json.loads(response['HX-Trigger'])
    assert 'recurringChanged' in events and 'closeSlideOver' in events
    assert events['infoToast']['message'].startswith('Recurring task saved: Weekly report.')
    rule = RecurringTask.objects.get()
    assert rule.weekday_list == [0, 4] and rule.estimate_minutes == 90 and rule.created_by == admin
    assert rule.next_date is not None

    assert client.get(reverse('recurring_edit', args=[rule.pk])).status_code == 200
    response = client.post(reverse('recurring_edit', args=[rule.pk]), {
        'title': 'Monthly numbers', 'frequency': 'monthly', 'interval': '1', 'month_day_choice': '0',
        'start_date': '2026-01-01', 'priority': '',
    })
    assert response.status_code == 200, response.content
    rule.refresh_from_db()
    assert rule.title == 'Monthly numbers' and rule.month_day == RecurringTask.LAST_DAY

    client.post(reverse('recurring_pause', args=[rule.pk]))
    rule.refresh_from_db()
    assert rule.paused
    client.post(reverse('recurring_pause', args=[rule.pk]))
    rule.refresh_from_db()
    assert not rule.paused

    response = client.post(reverse('recurring_run', args=[rule.pk]))
    events = json.loads(response['HX-Trigger'])
    task = rule.tasks.get()
    assert events['infoToast']['message'] == f'Created {task.identifier}: {task.title}'
    assert 'taskChanged' in events

    panel = client.get(reverse('recurring_panel', args=[project.pk]))
    assert task.identifier.encode() in panel.content and b'Every month on the last day' in panel.content
    assert client.get(reverse('recurring_list', args=[project.pk])).status_code == 200

    client.post(reverse('recurring_delete', args=[rule.pk]))
    assert not RecurringTask.objects.filter(pk=rule.pk).exists()
    task.refresh_from_db()
    assert task.recurring is None


def test_make_recurring_prefills_from_the_task(client):
    admin = AdminUserFactory()
    task = TaskFactory(title='Send newsletter', priority='high')
    SubtaskFactory(task=task, title='Write intro')
    client.force_login(admin)
    drawer = client.get(reverse('task_detail', args=[task.pk]))
    assert reverse('recurring_create', args=[task.project_id]).encode() in drawer.content
    response = client.get(reverse('recurring_create', args=[task.project_id]), {'from_task': task.pk})
    html = response.content.decode()
    assert 'value="Send newsletter"' in html and 'Write intro' in html


def test_end_before_start_is_refused(client):
    client.force_login(AdminUserFactory())
    project = ProjectFactory()
    response = _post_rule(client, project, end_date='2026-10-01')
    assert not RecurringTask.objects.exists()
    assert b'before the start' in response.content


def test_people_without_task_rights_cannot_change_rules(client):
    rule = _rule()
    client.force_login(UserFactory())
    assert client.get(reverse('recurring_create', args=[rule.project_id])).status_code == 403
    assert client.post(reverse('recurring_run', args=[rule.pk])).status_code == 403
    assert client.post(reverse('recurring_delete', args=[rule.pk])).status_code == 403
    assert client.get(reverse('recurring_panel', args=[rule.project_id])).status_code == 403
    assert RecurringTask.objects.filter(pk=rule.pk).exists()


def test_new_rule_drawer_starts_today(client):
    from django.utils import timezone

    client.force_login(AdminUserFactory())
    project = ProjectFactory()
    html = client.get(reverse('recurring_create', args=[project.pk])).content.decode()
    assert f'value="{timezone.localdate():%Y-%m-%d}"' in html

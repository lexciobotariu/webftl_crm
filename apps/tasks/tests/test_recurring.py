"""Repeat on a task: the schedule, the copies the daily job makes, and the views."""
import json
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.http import QueryDict
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.models import Project
from apps.tasks import recurring
from apps.tasks.factories import LabelFactory, SubtaskFactory, TaskFactory
from apps.tasks.models import RecurringTask, Task

pytestmark = pytest.mark.django_db


def _rule(project=None, **extra):
    values = {
        'project': project or ProjectFactory(), 'frequency': RecurringTask.MONTHLY,
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


def test_schedule_stops_at_the_end_date():
    rule = _rule(start_date=date(2026, 1, 1), end_date=date(2026, 3, 15))
    assert list(recurring.occurrences(rule)) == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]


# --- Reading and setting Repeat ------------------------------------------


def test_parse_repeat():
    assert recurring.parse_repeat({'repeat': 'never'}) is None
    assert recurring.parse_repeat({}) is None
    spec = recurring.parse_repeat(QueryDict('repeat=weekly&repeat_interval=2&repeat_days=3&repeat_days=0&repeat_days=9'))
    assert spec == {'frequency': 'weekly', 'interval': 2, 'weekdays': '0,3', 'month_day': None, 'end_date': None}
    spec = recurring.parse_repeat({'repeat': 'monthly', 'repeat_month_day': '0', 'repeat_end': '2027-06-30'})
    assert spec['month_day'] == RecurringTask.LAST_DAY and spec['end_date'] == date(2027, 6, 30)
    for bad in ({'repeat': 'hourly'}, {'repeat': 'daily', 'repeat_interval': 'x'},
                {'repeat': 'daily', 'repeat_interval': '0'}, {'repeat': 'daily', 'repeat_end': 'soon'}):
        with pytest.raises(ValidationError):
            recurring.parse_repeat(bad)


def _repeat(task, today=date(2026, 11, 19), **values):
    data = {'repeat': 'monthly', 'repeat_month_day': '1', **values}
    return recurring.set_repeat(task, recurring.parse_repeat(data), today=today)


def test_setting_repeat_makes_the_task_this_periods_and_schedules_the_next():
    task = TaskFactory(title='Checks')
    rule = _repeat(task)
    task.refresh_from_db()
    # The series starts today, so today is this task's date; the first copy comes on 1 Dec.
    assert task.recurring == rule and task.recurring_date == date(2026, 11, 19)
    assert rule.start_date == date(2026, 11, 19) and rule.next_date == date(2026, 12, 1)
    assert recurring.summary(task) == 'Every month on day 1'


def test_changing_repeat_on_any_task_changes_the_series():
    task = TaskFactory()
    rule = _repeat(task)
    copy = recurring.create_task_for(rule, date(2026, 12, 1))
    _repeat(copy, today=date(2026, 12, 2), repeat='weekly', repeat_days='0', repeat_end='2027-03-01')
    rule.refresh_from_db()
    assert RecurringTask.objects.count() == 1
    assert rule.frequency == RecurringTask.WEEKLY and rule.weekdays == '0' and rule.end_date == date(2027, 3, 1)
    assert rule.next_date == date(2026, 12, 7)
    assert recurring.summary(copy) == 'Every week on Mon, until 1 Mar 2027'


def test_never_ends_the_series_and_keeps_the_tasks():
    task = TaskFactory()
    rule = _repeat(task)
    copy = recurring.create_task_for(rule, date(2026, 12, 1))
    assert recurring.set_repeat(copy, None) is None
    assert not RecurringTask.objects.exists()
    assert Task.objects.filter(pk__in=[task.pk, copy.pk], recurring__isnull=True).count() == 2


def test_an_end_date_in_the_past_is_refused():
    with pytest.raises(ValidationError):
        _repeat(TaskFactory(), repeat_end='2026-11-01')
    assert not RecurringTask.objects.exists()


# --- The copies ------------------------------------------------------------


def test_a_copy_is_the_latest_task_again():
    project = ProjectFactory()
    member = UserFactory()
    ProjectAccessFactory(project=project, user=member)
    label = LabelFactory(project=project)
    done = project.statuses.exclude(pk=project.statuses.first().pk).last()
    task = TaskFactory(project=project, status=done, title='Checks', description='Update plugins', assignee=member,
                       priority='high', estimate_minutes=90, billable=False,
                       start_date=date(2026, 11, 3), due_date=date(2026, 11, 10))
    task.labels.set([label])
    SubtaskFactory(task=task, title='Backups', completed=True, order=1)
    SubtaskFactory(task=task, title='Plugins', order=0)
    rule = _repeat(task)

    created = recurring.create_due_tasks(today=date(2026, 12, 1))

    assert len(created) == 1
    copy = created[0]
    assert copy.title == 'Checks' and copy.description == 'Update plugins'
    assert copy.assignee == member and copy.priority == 'high' and copy.estimate_minutes == 90
    assert copy.billable is False and list(copy.labels.all()) == [label]
    assert copy.status == recurring._first_column(project) and copy.status != done
    assert copy.start_date == date(2026, 12, 1) and copy.due_date == date(2026, 12, 8)
    assert list(copy.subtasks.order_by('order').values_list('title', 'completed')) == [
        ('Plugins', False), ('Backups', False),
    ]
    assert copy.recurring == rule and copy.recurring_date == date(2026, 12, 1)
    rule.refresh_from_db()
    assert rule.next_date == date(2027, 1, 1)


def test_the_next_copy_follows_changes_to_the_latest_task():
    task = TaskFactory(title='Checks')
    rule = _repeat(task)
    copy = recurring.create_task_for(rule, date(2026, 12, 1))
    Task.objects.filter(pk=copy.pk).update(title='Checks and report', due_date=None)
    following = recurring.create_task_for(rule, date(2027, 1, 1))
    assert following.title == 'Checks and report' and following.due_date is None


def test_a_new_task_comes_even_when_the_last_one_is_open():
    task = TaskFactory()
    _repeat(task)
    assert len(recurring.create_due_tasks(today=date(2026, 12, 1))) == 1
    assert len(recurring.create_due_tasks(today=date(2027, 1, 1))) == 1
    assert Task.objects.filter(recurring__isnull=False).count() == 3


def test_missed_dates_are_skipped_not_created_late():
    task = TaskFactory()
    rule = _repeat(task)
    created = recurring.create_due_tasks(today=date(2027, 2, 10))
    assert [item.recurring_date for item in created] == [date(2027, 2, 1)]
    rule.refresh_from_db()
    assert rule.next_date == date(2027, 3, 1)


def test_inactive_project_creates_nothing_but_moves_on():
    task = TaskFactory()
    rule = _repeat(task)
    Project.objects.filter(pk=task.project_id).update(status=Project.ON_HOLD)
    assert recurring.create_due_tasks(today=date(2026, 12, 1)) == []
    rule.refresh_from_db()
    assert rule.next_date == date(2027, 1, 1)


def test_one_task_per_date():
    rule = _repeat(TaskFactory())
    assert recurring.create_task_for(rule, date(2026, 12, 1)) is not None
    assert recurring.create_task_for(rule, date(2026, 12, 1)) is None


def test_assignee_without_access_is_dropped():
    outsider = UserFactory()
    task = TaskFactory(assignee=outsider)
    rule = _repeat(task)
    assert recurring.create_task_for(rule, date(2026, 12, 1)).assignee is None


def test_daily_command_reports_tasks(capsys):
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command('create_recurring_invoices', stdout=out)
    assert 'Repeating tasks: 0 created.' in out.getvalue()


# --- The views ---------------------------------------------------------------


def _post_repeat(client, task, **data):
    return client.post(reverse('task_update_repeat', args=[task.pk]), data, HTTP_HX_REQUEST='true')


def test_drawer_shows_repeat_and_saves_it(client):
    client.force_login(AdminUserFactory())
    task = TaskFactory()
    drawer = client.get(reverse('task_detail', args=[task.pk]), HTTP_HX_REQUEST='true')
    assert drawer.status_code == 200
    assert f'id="repeat-value-{task.pk}"'.encode() in drawer.content
    assert reverse('task_update_repeat', args=[task.pk]).encode() in drawer.content

    response = _post_repeat(client, task, repeat='weekly', repeat_interval='1', repeat_days=['0', '3'])
    assert response.status_code == 200
    assert b'Next task ' in response.content and b'value="0" checked' in response.content
    trigger = json.loads(response['HX-Trigger'])
    assert trigger['infoToast']['message'].startswith('Repeats every week on Mon, Thu. Next task on ')
    assert f'taskUpdated-{task.pk}' in trigger
    task.refresh_from_db()
    assert task.recurring.weekdays == '0,3'

    response = _post_repeat(client, task, repeat='never')
    assert json.loads(response['HX-Trigger'])['infoToast']['message'] == 'This task no longer repeats.'
    assert not RecurringTask.objects.exists()


def test_a_wrong_value_shows_the_error_and_saves_nothing(client):
    client.force_login(AdminUserFactory())
    task = TaskFactory()
    response = _post_repeat(client, task, repeat='daily', repeat_end='2000-01-01')
    assert response.status_code == 200
    assert b'The end date has passed.' in response.content
    assert 'HX-Trigger' not in response
    assert not RecurringTask.objects.exists()


def test_people_without_task_rights_cannot_change_repeat(client):
    task = TaskFactory()
    member = UserFactory()
    ProjectAccessFactory(project=task.project, user=member)
    member.permission_preset.tasks_create = False
    member.permission_preset.save()
    client.force_login(member)
    assert _post_repeat(client, task, repeat='daily').status_code == 403
    assert not RecurringTask.objects.exists()


def test_new_task_with_repeat(client):
    client.force_login(AdminUserFactory())
    project = ProjectFactory()
    response = client.post(reverse('task_create', args=[project.pk]), {
        'title': 'Social posts', 'priority': '', 'billable': 'on',
        'repeat': 'weekly', 'repeat_interval': '1', 'repeat_days': ['4'],
    }, HTTP_HX_REQUEST='true')
    assert response.status_code == 200
    task = Task.objects.get(title='Social posts')
    assert task.recurring.frequency == RecurringTask.WEEKLY and task.recurring.weekdays == '4'


def test_new_task_with_a_wrong_repeat_is_not_created(client):
    client.force_login(AdminUserFactory())
    project = ProjectFactory()
    response = client.post(reverse('task_create', args=[project.pk]), {
        'title': 'Social posts', 'priority': '', 'repeat': 'daily', 'repeat_end': '2000-01-01',
    }, HTTP_HX_REQUEST='true')
    assert b'The end date has passed.' in response.content
    assert not Task.objects.filter(title='Social posts').exists()

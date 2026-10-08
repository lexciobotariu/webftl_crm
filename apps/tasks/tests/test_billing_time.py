"""Billable time, hourly rates, start dates and time totals (release 0.20.0)."""
import csv
from datetime import datetime, time, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.http import QueryDict
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.crm.models import Currency
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.views import parse_hourly_rate
from apps.tasks import timesheet
from apps.tasks.factories import TaskFactory, TimeEntryFactory
from apps.tasks.models import Task, TaskActivity
from apps.tasks.viewspec import TaskViewOptions, TaskViewSpec


def _monday():
    today = timezone.localdate()
    return today - timedelta(days=today.weekday())


def _at(day, hour=9):
    return timezone.make_aware(datetime.combine(day, time(hour)))


def _entry(task, user, minutes, day=None, hour=9):
    start = _at(day or _monday(), hour)
    return TimeEntryFactory(task=task, user=user, started_at=start,
                            ended_at=start + timedelta(minutes=minutes))


def _currency(code, symbol, before=True):
    return Currency.objects.get_or_create(
        code=code, defaults={'name': code, 'symbol': symbol, 'symbol_before': before},
    )[0]


class TestParseHourlyRate:
    @pytest.mark.parametrize('text, rate', [
        ('', None), ('  ', None), ('50', Decimal('50')), ('49,50', Decimal('49.50')), ('0', Decimal('0')),
    ])
    def test_accepted(self, text, rate):
        assert parse_hourly_rate(text) == (rate, None)

    @pytest.mark.parametrize('text', ['abc', '-5', '1.234', 'NaN', 'Infinity', '100000000'])
    def test_rejected(self, text):
        rate, error = parse_hourly_rate(text)
        assert rate is None and error


@pytest.mark.django_db
class TestProjectHourlyRate:
    def test_saved_from_settings_and_cleared_when_empty(self, client):
        project = ProjectFactory()
        client.force_login(AdminUserFactory())
        url = reverse('project_settings_update', args=[project.pk])
        data = {'name': project.name, 'key': project.key, 'description': '', 'github_repo_url': ''}

        assert client.post(url, {**data, 'hourly_rate': '75,5'}).status_code == 200
        project.refresh_from_db()
        assert project.hourly_rate == Decimal('75.50')

        client.post(url, {**data, 'hourly_rate': ''})
        project.refresh_from_db()
        assert project.hourly_rate is None

    def test_invalid_rate_is_shown_back_and_nothing_saved(self, client):
        project = ProjectFactory(hourly_rate=Decimal('10'))
        client.force_login(AdminUserFactory())
        response = client.post(reverse('project_settings_update', args=[project.pk]), {
            'name': 'Renamed', 'key': project.key, 'hourly_rate': 'ten',
        })
        content = response.content.decode()
        assert 'Enter a number' in content
        assert 'value="ten"' in content
        project.refresh_from_db()
        assert project.hourly_rate == Decimal('10')
        assert project.name != 'Renamed'

    def test_a_form_without_the_field_keeps_the_rate(self, client):
        project = ProjectFactory(hourly_rate=Decimal('10'))
        client.force_login(AdminUserFactory())
        client.post(reverse('project_settings_update', args=[project.pk]),
                    {'name': project.name, 'key': project.key})
        project.refresh_from_db()
        assert project.hourly_rate == Decimal('10')


@pytest.mark.django_db
class TestTaskBillingAndStartDate:
    def test_new_tasks_are_billable(self):
        assert TaskFactory().billable is True

    def test_billable_toggle_logs_activity(self, client):
        task = TaskFactory()
        client.force_login(AdminUserFactory())
        response = client.post(reverse('task_update_billable', args=[task.pk]), {'billable': '0'})
        assert response.status_code == 200
        assert f'taskUpdated-{task.pk}' in response['HX-Trigger']
        task.refresh_from_db()
        assert task.billable is False
        assert TaskActivity.objects.filter(task=task, activity_type='billable_change').exists()

    def test_start_date_set_and_cleared(self, client):
        task = TaskFactory()
        client.force_login(AdminUserFactory())
        url = reverse('task_update_start_date', args=[task.pk])
        client.post(url, {'start_date': '2026-11-02'})
        task.refresh_from_db()
        assert str(task.start_date) == '2026-11-02'
        client.post(url, {'start_date': ''})
        task.refresh_from_db()
        assert task.start_date is None
        assert TaskActivity.objects.filter(task=task, activity_type='start_date_change').count() == 2

    def test_viewers_cannot_change_billing_or_start(self, client):
        from apps.accounts.permissions import PermissionPreset

        task = TaskFactory()
        preset = PermissionPreset.objects.create(name='BillingViewer', access_projects=True, access_tasks=True)
        user = UserFactory(permission_preset=preset)
        ProjectAccessFactory(project=task.project, user=user)
        client.force_login(user)
        assert client.post(reverse('task_update_billable', args=[task.pk]), {'billable': '0'}).status_code == 403
        assert client.post(reverse('task_update_start_date', args=[task.pk]),
                           {'start_date': '2026-11-02'}).status_code == 403

    def test_drawer_shows_both_properties(self, client):
        task = TaskFactory()
        client.force_login(AdminUserFactory())
        content = client.get(reverse('task_detail', args=[task.pk])).content.decode()
        assert f'start-date-value-{task.pk}' in content
        assert f'billable-value-{task.pk}' in content


@pytest.mark.django_db
class TestStartFilter:
    def _spec(self, project, query):
        options = TaskViewOptions(status_ids=frozenset(project.statuses.values_list('pk', flat=True)))
        return TaskViewSpec.from_params(QueryDict(query), options)

    def test_started_includes_no_date_and_later_only_future(self):
        project = ProjectFactory()
        today = timezone.localdate()
        undated = TaskFactory(project=project)
        begun = TaskFactory(project=project, start_date=today)
        future = TaskFactory(project=project, start_date=today + timedelta(days=3))
        tasks = Task.objects.filter(project=project)

        started = self._spec(project, 'start=started')
        assert set(tasks.matching(started)) == {undated, begun}
        later = self._spec(project, 'start=later')
        assert set(tasks.matching(later)) == {future}
        assert set(tasks.matching(self._spec(project, ''))) == {undated, begun, future}

    def test_spec_round_trip_badge_and_clear(self):
        project = ProjectFactory()
        spec = self._spec(project, 'start=later')
        assert spec.to_params()['start'] == 'later'
        assert spec.filter_count == 1
        assert self._spec(project, 'start=bogus').start == ''
        assert self._spec(project, 'start=later&clear=1').start == ''

    def test_toolbar_offers_the_filter(self, client):
        project = ProjectFactory()
        client.force_login(AdminUserFactory())
        content = client.get(reverse('project_tasks', args=[project.pk]), {'start': 'later'}).content.decode()
        assert 'Not started yet' in content
        assert 'name="start" value="later" checked' in content


@pytest.mark.django_db
class TestTimeTotals:
    def _setup(self):
        eur = _currency('ZZE', '€', before=False)
        project = ProjectFactory(hourly_rate=Decimal('60'), name='Alpha')
        project.client.currency = eur
        project.client.save()
        billable = TaskFactory(project=project)
        internal = TaskFactory(project=project, billable=False)
        return project, billable, internal

    def test_summary_splits_billable_and_prices_it(self):
        project, billable, internal = self._setup()
        user = UserFactory()
        entries = [_entry(billable, user, 90), _entry(internal, user, 30, hour=12)]
        overall, groups = timesheet.summarize(entries)
        assert overall.billable_seconds == 5400
        assert overall.non_billable_seconds == 1800
        assert overall.amount_label == '90.00 €'
        assert groups == []

    def test_currencies_are_never_added_together(self):
        project, billable, _ = self._setup()
        usd = _currency('ZZU', '$')
        other = ProjectFactory(hourly_rate=Decimal('100'))
        other.client.currency = usd
        other.client.save()
        user = UserFactory()
        entries = [_entry(billable, user, 60), _entry(TaskFactory(project=other), user, 30, hour=12)]
        overall, groups = timesheet.summarize(entries, 'client')
        assert overall.amount_label == '60.00 € + $50.00'
        assert len(groups) == 2

    def test_no_rate_means_hours_without_amount(self):
        task = TaskFactory(project=ProjectFactory(hourly_rate=None))
        overall, _ = timesheet.summarize([_entry(task, UserFactory(), 60)])
        assert overall.billable_seconds == 3600
        assert overall.amount_label == ''

    def test_page_shows_totals_and_groups(self, client):
        project, billable, internal = self._setup()
        admin = AdminUserFactory()
        ProjectAccessFactory(project=project, user=admin)
        _entry(billable, admin, 90)
        _entry(internal, admin, 30, hour=12)
        client.force_login(admin)

        page = client.get(reverse('time_week')).content.decode()
        assert 'Billable 1h 30m' in page
        assert 'Non-billable 30m' in page
        assert 'Amount 90.00 €' in page

        grouped = client.get(reverse('time_week'), {'by': 'project'}).content.decode()
        assert grouped.count('data-time-group') == 1
        assert 'Alpha' in grouped

    def test_person_grouping_only_for_those_who_see_everyone(self, client):
        project, billable, _ = self._setup()
        user = UserFactory()
        ProjectAccessFactory(project=project, user=user)
        _entry(billable, user, 60)
        client.force_login(user)
        page = client.get(reverse('time_week'), {'by': 'person', 'project': project.pk}).content.decode()
        assert 'value="person"' not in page
        assert 'data-time-group' not in page

    def test_month_range(self, client):
        project, billable, _ = self._setup()
        admin = AdminUserFactory()
        first = timezone.localdate().replace(day=1)
        _entry(billable, admin, 60, day=first)
        _entry(billable, admin, 60, day=first - timedelta(days=1))
        client.force_login(admin)
        page = client.get(reverse('time_week'), {'month': f'{first:%Y-%m}'}).content.decode()
        assert 'My Month' in page
        assert 'Total 1h' in page
        assert client.get(reverse('time_week'), {'month': '2026-13'}).status_code == 400
        assert client.get(reverse('time_week'), {'month': 'x'}).status_code == 400
        assert client.get(reverse('time_week'), {'week': '2026-02-30'}).status_code == 400

    def test_csv_of_entries_and_of_totals(self, client):
        project, billable, internal = self._setup()
        admin = AdminUserFactory()
        _entry(billable, admin, 90)
        _entry(internal, admin, 30, hour=12)
        client.force_login(admin)

        response = client.get(reverse('time_week'), {'format': 'csv'})
        assert response['Content-Type'].startswith('text/csv')
        assert 'attachment' in response['Content-Disposition']
        rows = list(csv.DictReader(StringIO(response.content.decode())))
        assert [(row['Hours'], row['Billable'], row['Amount']) for row in rows] == [
            ('1.50', 'yes', '90.00'), ('0.50', 'no', ''),
        ]
        assert rows[0]['Task ID'] == billable.identifier
        assert rows[0]['Currency'] == 'ZZE'

        summary = client.get(reverse('time_week'), {'format': 'csv', 'by': 'client'}).content.decode()
        rows = list(csv.reader(StringIO(summary)))
        assert rows[0][0] == 'Client'
        assert rows[1][1:] == ['1.50', '0.50', '2.00', '90.00', 'ZZE']
        assert rows[-1][0] == 'Total'

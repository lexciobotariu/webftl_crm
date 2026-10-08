"""Project start date, deadline and billing type (release 0.23.0)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.clients.factories import ClientFactory
from apps.projects.factories import ProjectFactory
from apps.projects.models import Project
from apps.tasks import timesheet
from apps.tasks.factories import TaskFactory, TimeEntryFactory


def _settings(client, project, **fields):
    data = {'name': project.name, 'key': project.key, **fields}
    return client.post(reverse('project_settings_update', args=[project.pk]), data)


@pytest.mark.django_db
class TestDefaults:
    def test_a_new_project_is_hourly_without_dates(self):
        project = ProjectFactory()
        assert project.billing_type == Project.HOURLY
        assert project.start_date is None and project.deadline is None
        assert project.fixed_price is None


@pytest.mark.django_db
class TestSettings:
    def test_dates_and_fixed_price_are_saved(self, client):
        project = ProjectFactory()
        client.force_login(AdminUserFactory())

        _settings(client, project, start_date='2026-10-01', deadline='2026-12-31',
                  billing_type='fixed', fixed_price='2500,50')
        project.refresh_from_db()
        assert str(project.start_date) == '2026-10-01'
        assert str(project.deadline) == '2026-12-31'
        assert project.billing_type == Project.FIXED
        assert project.fixed_price == Decimal('2500.50')

        # Empty fields clear; a form without them keeps them.
        _settings(client, project, start_date='', deadline='')
        project.refresh_from_db()
        assert project.start_date is None and project.deadline is None
        assert project.billing_type == Project.FIXED

    def test_a_deadline_before_the_start_is_refused(self, client):
        project = ProjectFactory()
        client.force_login(AdminUserFactory())

        response = _settings(client, project, start_date='2026-10-10', deadline='2026-10-01')
        assert 'cannot be before the start date' in response.content.decode()
        project.refresh_from_db()
        assert project.start_date is None and project.deadline is None

    @pytest.mark.parametrize('fields, message', [
        ({'start_date': '31/12/2026'}, 'Enter a date'),
        ({'billing_type': 'barter'}, 'Choose a billing type'),
        ({'fixed_price': '-5'}, 'positive amount'),
    ])
    def test_bad_values_are_refused(self, client, fields, message):
        project = ProjectFactory()
        client.force_login(AdminUserFactory())

        response = _settings(client, project, **fields)
        assert message in response.content.decode()
        project.refresh_from_db()
        assert project.billing_type == Project.HOURLY
        assert project.start_date is None and project.fixed_price is None


@pytest.mark.django_db
class TestCreateDrawer:
    def test_dates_are_saved_from_the_drawer(self, client):
        owner = ClientFactory()
        client.force_login(AdminUserFactory())

        client.post(reverse('client_create_project', args=[owner.pk]), {
            'name': 'Dated', 'start_date': '2026-11-01', 'deadline': '2026-11-30',
        }, HTTP_HX_REQUEST='true')
        project = Project.objects.get(name='Dated')
        assert str(project.start_date) == '2026-11-01'
        assert str(project.deadline) == '2026-11-30'

    def test_a_deadline_before_the_start_is_refused(self, client):
        owner = ClientFactory()
        client.force_login(AdminUserFactory())

        response = client.post(reverse('project_create'), {
            'client': owner.pk, 'name': 'Backwards', 'start_date': '2026-11-30', 'deadline': '2026-11-01',
        }, HTTP_HX_REQUEST='true')
        body = response.content.decode()
        assert 'cannot be before the start date' in body
        assert 'value="2026-11-30"' in body
        assert not Project.objects.filter(name='Backwards').exists()


@pytest.mark.django_db
class TestDisplay:
    def test_an_open_project_past_its_deadline_is_overdue(self, client):
        yesterday = timezone.localdate() - timedelta(days=1)
        late = ProjectFactory(name='Late', deadline=yesterday)
        assert late.is_overdue
        assert not ProjectFactory(deadline=yesterday, status=Project.FINISHED).is_overdue
        assert not ProjectFactory(deadline=timezone.localdate()).is_overdue

        client.force_login(AdminUserFactory())
        overview = client.get(reverse('project_detail', args=[late.pk])).content.decode()
        assert 'Overdue' in overview
        listing = client.get(reverse('project_list')).content.decode()
        assert 'Due ' in listing

    def test_the_overview_shows_the_billing(self, client):
        project = ProjectFactory(billing_type=Project.FIXED, fixed_price=Decimal('1200.00'))
        client.force_login(AdminUserFactory())
        html = client.get(reverse('project_detail', args=[project.pk])).content.decode()
        assert 'Fixed price' in html
        assert '1200.00' in html


@pytest.mark.django_db
class TestTimeAmounts:
    def test_fixed_price_time_has_hours_but_no_amount(self):
        project = ProjectFactory(hourly_rate=Decimal('50'))
        task = TaskFactory(project=project, billable=True)
        entry = TimeEntryFactory(task=task)
        assert timesheet.entry_amount(entry) == Decimal('25')

        project.billing_type = Project.FIXED
        project.save(update_fields=['billing_type'])
        entry.refresh_from_db()
        assert project.billing_rate is None
        assert timesheet.entry_amount(entry) is None

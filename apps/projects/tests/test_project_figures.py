"""Time and money on the project Overview tab (release 0.26.0)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.crm.models import Currency
from apps.invoices.services import add_line, create_invoice
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.figures import project_figures
from apps.projects.models import Project
from apps.tasks.factories import TaskFactory, TimeEntryFactory
from apps.tasks.models import Task


def _project(**fields):
    owner = ClientFactory()
    owner.currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
    owner.save(update_fields=['currency'])
    return ProjectFactory(client=owner, **fields)


def _entry(task, minutes, user=None):
    start = timezone.now() - timedelta(days=1)
    extra = {'user': user} if user else {}
    return TimeEntryFactory(task=task, started_at=start, ended_at=start + timedelta(minutes=minutes), **extra)


def _figures(user, project):
    return project_figures(user, project, Task.objects.filter(project=project))


def _user(name, **flags):
    fields = {'access_dashboard': True, 'access_projects': True, 'access_tasks': True}
    fields.update(flags)
    return UserFactory(permission_preset=PermissionPreset.objects.create(name=name, **fields))


@pytest.mark.django_db
class TestHours:
    def test_billable_non_billable_and_the_estimate(self):
        project = _project(hourly_rate=Decimal('40'))
        estimated = TaskFactory(project=project, billable=True, estimate_minutes=120)
        loose = TaskFactory(project=project, billable=False)
        _entry(estimated, 180)
        _entry(loose, 30)

        figures = _figures(AdminUserFactory(), project)
        assert figures.billable_hours == Decimal('3.0')
        assert figures.non_billable_hours == Decimal('0.5')
        assert figures.total_hours == Decimal('3.5')
        assert figures.estimate_hours == Decimal('2.0')
        assert figures.estimated_task_hours == Decimal('3.0')
        assert figures.over_estimate
        assert figures.billable_amount == '120.00 €'

    def test_a_running_timer_is_not_counted(self):
        project = _project()
        TimeEntryFactory(task=TaskFactory(project=project), ended_at=None)
        assert _figures(AdminUserFactory(), project).total_hours == Decimal('0.0')

    def test_without_tasks_view_all_only_own_time_and_no_hourly_amount(self):
        project = _project(hourly_rate=Decimal('40'))
        user = _user('Own', access_invoices=True, tasks_view_all=False)
        ProjectAccessFactory(project=project, user=user)
        task = TaskFactory(project=project, billable=True)
        _entry(task, 60, user=user)
        _entry(task, 120)

        figures = _figures(user, project)
        assert not figures.everyones_time
        assert figures.total_hours == Decimal('1.0')
        assert figures.billable_amount == ''


@pytest.mark.django_db
class TestMoney:
    def test_fixed_price_and_what_was_invoiced(self):
        project = _project(billing_type=Project.FIXED, fixed_price=Decimal('2000'))
        today = timezone.localdate()
        sent = create_invoice(client=project.client, issue_date=today, due_date=today, tax_rate=Decimal('19'))
        add_line(sent, project=project, description='', quantity=Decimal('1'), unit_price=Decimal('500'))
        add_line(sent, project=None, description='Hosting', quantity=Decimal('1'), unit_price=Decimal('99'))
        sent.sent_at = timezone.now()
        sent.save(update_fields=['sent_at'])
        draft = create_invoice(client=project.client, issue_date=today, due_date=today, tax_rate=Decimal('0'))
        add_line(draft, project=project, description='', quantity=Decimal('1'), unit_price=Decimal('300'))

        figures = _figures(AdminUserFactory(), project)
        assert figures.billable_amount == '2000.00 €'
        assert figures.billable_amount_note == 'Fixed price'
        assert figures.invoiced == '500.00 €'
        assert figures.invoiced_count == 1

    def test_without_the_invoices_module_there_is_no_money_on_the_page(self, client):
        project = _project(hourly_rate=Decimal('40'))
        user = _user('NoMoney', access_invoices=False, tasks_view_all=True)
        ProjectAccessFactory(project=project, user=user)
        _entry(TaskFactory(project=project, billable=True), 60, user=user)
        client.force_login(user)

        html = client.get(reverse('project_detail', args=[project.pk])).content.decode()
        assert 'Time and money' in html
        assert '1.0 h' in html
        assert 'Billable amount' not in html
        assert 'Invoiced' not in html

    def test_the_admin_sees_the_whole_card(self, client):
        project = _project(hourly_rate=Decimal('50'))
        _entry(TaskFactory(project=project, billable=True), 90)
        client.force_login(AdminUserFactory())

        html = client.get(reverse('project_detail', args=[project.pk])).content.decode()
        assert 'Billable amount' in html
        assert '75.00 €' in html
        assert 'Invoiced' in html

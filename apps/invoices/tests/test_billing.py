"""Billing tasks' time and fixed-price projects onto invoices (release 0.32.0)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.clients.factories import ClientFactory
from apps.crm.models import Currency
from apps.invoices.billing import (
    PER_PROJECT,
    bill_tasks,
    fixed_price_left,
    invoice_project,
    tasks_to_bill,
)
from apps.invoices.models import Invoice
from apps.invoices.services import add_line, cancel_invoice, create_invoice, mark_sent
from apps.projects.factories import ProjectFactory
from apps.tasks.factories import TaskFactory, TimeEntryFactory
from apps.tasks.services import TimeEntryValidationError, delete_entry


def _today():
    return timezone.localdate()


def _client(name='Acme'):
    owner = ClientFactory(name=name)
    owner.currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
    owner.save(update_fields=['currency'])
    return owner


def _project(owner, name='Website', rate='50', **extra):
    return ProjectFactory(client=owner, name=name, hourly_rate=Decimal(rate) if rate else None, **extra)


def _time(task, minutes):
    start = timezone.now() - timedelta(days=1)
    return TimeEntryFactory(task=task, started_at=start, ended_at=start + timedelta(minutes=minutes))


def _invoice(owner, project=None):
    return create_invoice(client=owner, project=project, issue_date=_today(),
                          due_date=_today() + timedelta(days=30), tax_rate=Decimal('0'))


@pytest.mark.django_db
class TestTasksToBill:
    def test_only_unbilled_billable_finished_time_on_hourly_projects(self):
        owner = _client()
        website = _project(owner)
        design = TaskFactory(project=website, title='Design')
        _time(design, 90)
        _time(TaskFactory(project=website, billable=False), 60)
        TimeEntryFactory(task=TaskFactory(project=website), ended_at=None)
        _time(TaskFactory(project=_project(owner, 'Retainer', billing_type='fixed', fixed_price=Decimal('900'))), 60)
        _time(TaskFactory(project=_project(_client('Other'))), 60)

        rows = tasks_to_bill(owner)
        assert [(row.task, row.hours, row.amount) for row in rows] == [(design, Decimal('1.50'), Decimal('75.00'))]

    def test_the_invoice_project_narrows_the_list(self):
        owner = _client()
        website, app = _project(owner, 'Website'), _project(owner, 'App')
        _time(TaskFactory(project=website), 60)
        app_task = TaskFactory(project=app)
        _time(app_task, 60)
        assert len(tasks_to_bill(owner)) == 2
        assert [row.task for row in tasks_to_bill(owner, app)] == [app_task]


@pytest.mark.django_db
class TestBillTasks:
    def test_one_line_per_task_links_the_time(self):
        owner = _client()
        website = _project(owner)
        design = TaskFactory(project=website, title='Design')
        build = TaskFactory(project=website, title='Build')
        first, second = _time(design, 30), _time(design, 60)
        _time(build, 120)
        invoice = _invoice(owner)

        lines = bill_tasks(invoice, [design.pk], 'task')
        assert len(lines) == 1
        line = lines[0]
        assert (line.description, line.quantity, line.unit_price, line.task, line.project) == (
            'Website: Design', Decimal('1.50'), Decimal('50.00'), design, website,
        )
        first.refresh_from_db()
        second.refresh_from_db()
        assert first.invoice_line == line and second.invoice_line == line
        assert [row.task for row in tasks_to_bill(owner)] == [build]

        with pytest.raises(ValidationError):
            bill_tasks(invoice, [design.pk], 'task')

    def test_one_line_per_project_and_no_prefix_when_the_invoice_has_the_project(self):
        owner = _client()
        website = _project(owner, rate=None)
        _time(TaskFactory(project=website), 30)
        _time(TaskFactory(project=website), 45)
        invoice = _invoice(owner, website)
        task_ids = [row.task.pk for row in tasks_to_bill(owner)]

        (line,) = bill_tasks(invoice, task_ids, PER_PROJECT)
        assert (line.description, line.quantity, line.unit_price, line.task) == (
            'Website', Decimal('1.25'), Decimal('0.00'), None,
        )
        assert line.time_entries.count() == 2

    def test_removing_the_line_or_deleting_the_draft_frees_the_time(self):
        owner = _client()
        task = TaskFactory(project=_project(owner))
        entry = _time(task, 60)
        invoice = _invoice(owner)
        (line,) = bill_tasks(invoice, [task.pk])
        line.delete()
        entry.refresh_from_db()
        assert entry.invoice_line is None

        bill_tasks(invoice, [task.pk])
        invoice.delete()
        entry.refresh_from_db()
        assert entry.invoice_line is None

    def test_cancelling_a_sent_invoice_frees_the_time_and_sent_time_is_locked(self):
        owner = _client()
        task = TaskFactory(project=_project(owner))
        entry = _time(task, 60)
        invoice = _invoice(owner)
        bill_tasks(invoice, [task.pk])
        mark_sent(invoice)
        entry.refresh_from_db()

        with pytest.raises(TimeEntryValidationError):
            delete_entry(entry, AdminUserFactory())

        cancel_invoice(invoice)
        entry.refresh_from_db()
        assert entry.invoice_line is None
        assert [row.task for row in tasks_to_bill(owner)] == [task]

    def test_a_sent_invoice_takes_no_tasks(self):
        from apps.invoices.models import InvoiceLocked

        owner = _client()
        task = TaskFactory(project=_project(owner))
        _time(task, 60)
        invoice = _invoice(owner)
        add_line(invoice, project=None, description='Setup', quantity=Decimal('1'), unit_price=Decimal('10'))
        mark_sent(invoice)
        with pytest.raises(InvoiceLocked):
            bill_tasks(invoice, [task.pk])


@pytest.mark.django_db
class TestInvoiceProject:
    def test_hourly_project_creates_a_draft_with_its_tasks(self):
        owner = _client()
        website = _project(owner)
        task = TaskFactory(project=website, title='Design')
        _time(task, 120)
        earlier = _invoice(owner)
        earlier.tax_rate = Decimal('19.00')
        earlier.save(update_fields=['tax_rate'])

        invoice = invoice_project(website, task_ids=[task.pk])
        assert invoice.project == website
        assert invoice.is_draft
        assert invoice.tax_rate == Decimal('19.00')
        assert invoice.due_date == _today() + timedelta(days=30)
        assert [(line.description, line.amount) for line in invoice.lines.all()] == [('Design', Decimal('100.00'))]

    def test_fixed_price_bills_what_is_left(self):
        owner = _client()
        retainer = _project(owner, 'Retainer', billing_type='fixed', fixed_price=Decimal('1000'))
        deposit = _invoice(owner, retainer)
        add_line(deposit, project=retainer, description='Deposit', quantity=Decimal('1'), unit_price=Decimal('400'))
        assert fixed_price_left(retainer) == Decimal('600.00')

        invoice = invoice_project(retainer)
        assert [(line.description, line.amount) for line in invoice.lines.all()] == [('Retainer', Decimal('600.00'))]
        assert fixed_price_left(retainer) == Decimal('0.00')
        with pytest.raises(ValidationError):
            invoice_project(retainer)


@pytest.mark.django_db
class TestScreens:
    def test_add_tasks_drawer_lists_and_bills(self, client):
        client.force_login(AdminUserFactory())
        owner = _client()
        task = TaskFactory(project=_project(owner), title='Design')
        _time(task, 60)
        invoice = _invoice(owner)

        page = client.get(reverse('invoice_detail', args=[invoice.pk])).content.decode()
        assert reverse('invoice_add_tasks', args=[invoice.pk]) in page

        drawer = client.get(reverse('invoice_add_tasks', args=[invoice.pk])).content.decode()
        assert 'Design' in drawer
        assert task.identifier in drawer

        none_chosen = client.post(reverse('invoice_add_tasks', args=[invoice.pk]), {'per': 'task'})
        assert 'Choose at least one task' in none_chosen.content.decode()

        billed = client.post(reverse('invoice_add_tasks', args=[invoice.pk]), {'per': 'task', 'task': [task.pk]})
        assert billed['HX-Refresh'] == 'true'
        assert invoice.lines.get().task == task

        task_page = client.get(reverse('task_detail', args=[task.pk]))
        assert f'Invoiced {invoice.number_label}' in task_page.content.decode()

    def test_invoice_project_from_the_project_page(self, client):
        client.force_login(AdminUserFactory())
        owner = _client()
        website = _project(owner)
        task = TaskFactory(project=website)
        _time(task, 60)

        overview = client.get(reverse('project_detail', args=[website.pk])).content.decode()
        assert reverse('invoice_project', args=[website.pk]) in overview
        assert '1.0 h billable not invoiced yet' in overview

        response = client.post(reverse('invoice_project', args=[website.pk]), {'per': 'task', 'task': [task.pk]})
        invoice = Invoice.objects.get()
        assert response['HX-Redirect'] == reverse('invoice_detail', args=[invoice.pk])
        overview = client.get(reverse('project_detail', args=[website.pk])).content.decode()
        assert 'billable not invoiced yet' not in overview

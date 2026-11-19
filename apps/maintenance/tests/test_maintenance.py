"""Maintenance plans: project, hours, invoices, extra hours, checks, renewals, sites and logins, reports."""
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.clients.models import ClientContact, ClientMessage
from apps.crm.models import Currency
from apps.invoices.models import Invoice, add_months
from apps.invoices.recurring import create_due_invoices
from apps.maintenance import services
from apps.maintenance.models import (
    MaintenanceCheck,
    MaintenanceCheckRun,
    MaintenancePlan,
    MaintenanceReport,
    Site,
    SiteCredential,
)
from apps.projects.models import Project, ProjectAccess
from apps.tasks.factories import TaskFactory, TimeEntryFactory

pytestmark = pytest.mark.django_db


def _eur():
    currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
    return currency


def _plan(user=None, **extra):
    user = user or AdminUserFactory()
    client = extra.pop('client', None) or ClientFactory(currency=_eur())
    values = {
        'client': client, 'name': 'Acme website care', 'start_date': date(2026, 1, 1),
        'price': Decimal('300'), 'included_hours': Decimal('5'), 'overage_rate': Decimal('60'),
    }
    values.update(extra)
    return services.create_plan(MaintenancePlan(**values), user)


def _log(plan, hours, day=None, user=None):
    day = day or timezone.localdate()
    start = timezone.make_aware(datetime.combine(day, time(10)))
    task = TaskFactory(project=plan.project)
    return TimeEntryFactory(task=task, user=user or AdminUserFactory(), started_at=start,
                            ended_at=start + timedelta(minutes=int(hours * 60)))


def _member(**flags):
    preset = PermissionPreset.objects.create(name=f'P{PermissionPreset.objects.count()}', **flags)
    return UserFactory(permission_preset=preset)


# --- Plan and project -------------------------------------------------


def test_plan_gets_its_own_fixed_price_project_with_access_for_its_creator():
    user = AdminUserFactory()
    plan = _plan(user)
    assert plan.project.client == plan.client
    assert plan.project.name == plan.name
    assert plan.project.billing_type == Project.FIXED
    assert ProjectAccess.objects.filter(project=plan.project, user=user).exists()


def test_status_moves_the_project_along():
    plan = _plan()
    services.set_status(plan, MaintenancePlan.PAUSED)
    assert Project.objects.get(pk=plan.project_id).status == Project.ON_HOLD
    services.set_status(plan, MaintenancePlan.ENDED)
    assert Project.objects.get(pk=plan.project_id).status == Project.FINISHED
    services.set_status(plan, MaintenancePlan.ACTIVE)
    assert Project.objects.get(pk=plan.project_id).status == Project.ACTIVE


def test_renaming_the_plan_renames_its_project():
    plan = _plan()
    plan.name = 'New name'
    services.update_plan(plan)
    assert Project.objects.get(pk=plan.project_id).name == 'New name'


def test_project_takes_the_plans_dates():
    plan = _plan(renewal_date=date(2026, 12, 31), auto_renew=True, term_months=12)
    assert (plan.project.start_date, plan.project.deadline) == (date(2026, 1, 1), date(2026, 12, 31))
    plan.start_date, plan.renewal_date = date(2026, 2, 1), None
    services.update_plan(plan)
    project = Project.objects.get(pk=plan.project_id)
    assert (project.start_date, project.deadline) == (date(2026, 2, 1), None)


# --- Hours ------------------------------------------------------------


def test_usage_counts_this_months_time_only():
    plan = _plan()
    today = timezone.localdate()
    _log(plan, 3, today)
    _log(plan, 2, add_months(services.month_start(today), -1))
    used = services.usage(plan, today)
    assert used.hours == Decimal('3.00')
    assert used.state == ''
    _log(plan, 1.5, today)
    assert services.usage(plan, today).state == 'warn'
    _log(plan, 1, today)
    used = services.usage(plan, today)
    assert used.state == 'over'
    assert used.extra_hours == Decimal('0.50')
    assert used.percent == 100


def test_plan_without_limit_has_no_extra_hours():
    plan = _plan(included_hours=Decimal('0'))
    _log(plan, 20)
    assert services.usage(plan).extra_hours == 0
    assert services.usage(plan).state == ''


# --- Invoices -----------------------------------------------------------


def test_set_up_invoicing_creates_a_draft_that_repeats():
    plan = _plan()
    issue = timezone.localdate()
    invoice = services.set_up_invoicing(plan, plan.created_by, issue_date=issue)
    plan.refresh_from_db()
    assert invoice.sent_at is None
    assert invoice.lines.get().unit_price == Decimal('300')
    assert plan.recurring_invoice.template == invoice
    assert plan.recurring_invoice.next_date == add_months(issue, 1)
    with pytest.raises(ValidationError, match='already'):
        services.set_up_invoicing(plan, plan.created_by, issue_date=issue)


def test_paused_plan_gets_no_repeated_draft_but_its_date_moves_on():
    plan = _plan()
    issue = timezone.localdate()
    services.set_up_invoicing(plan, plan.created_by, issue_date=issue)
    plan.refresh_from_db()
    next_date = plan.recurring_invoice.next_date
    services.set_status(plan, MaintenancePlan.PAUSED)
    assert create_due_invoices(today=next_date) == []
    plan.recurring_invoice.refresh_from_db()
    assert plan.recurring_invoice.next_date > next_date

    services.set_status(plan, MaintenancePlan.ACTIVE)
    created = create_due_invoices(today=plan.recurring_invoice.next_date)
    assert len(created) == 1


def test_extra_hours_go_on_the_plans_draft_once():
    plan = _plan()
    services.set_up_invoicing(plan, plan.created_by, issue_date=timezone.localdate())
    _log(plan, 7)
    invoice = services.add_extra_hours(plan, timezone.localdate(), plan.created_by)
    plan.refresh_from_db()
    assert invoice == plan.recurring_invoice.template
    line = invoice.lines.get(description__startswith='Extra hours')
    assert line.quantity == Decimal('2.00')
    assert line.unit_price == Decimal('60')
    with pytest.raises(ValidationError, match='already'):
        services.add_extra_hours(plan, timezone.localdate(), plan.created_by)


def test_extra_hours_without_a_draft_make_a_new_one():
    plan = _plan()
    _log(plan, 6)
    invoice = services.add_extra_hours(plan, timezone.localdate(), plan.created_by)
    assert invoice.client == plan.client
    assert invoice.sent_at is None
    assert invoice.lines.get().quantity == Decimal('1.00')


def test_extra_hours_need_a_rate_and_extra_time():
    plan = _plan(overage_rate=None)
    _log(plan, 9)
    with pytest.raises(ValidationError, match='extra hour'):
        services.add_extra_hours(plan, timezone.localdate(), plan.created_by)
    plan = _plan()
    _log(plan, 1)
    with pytest.raises(ValidationError, match='no extra hours'):
        services.add_extra_hours(plan, timezone.localdate(), plan.created_by)


def test_plan_time_is_not_offered_for_hourly_billing():
    """The plan's project is fixed price, so "Add tasks" never bills its time again."""
    from apps.invoices.billing import unbilled_entries

    plan = _plan()
    _log(plan, 2)
    assert not unbilled_entries(plan.client).exists()


# --- Checks -----------------------------------------------------------


def test_checks_task_is_created_once_per_period_with_subtasks():
    plan = _plan()
    for title in ('Update plugins', 'Test backup'):
        MaintenanceCheck.objects.create(plan=plan, title=title)
    today = timezone.localdate()
    services.schedule_checks(plan, today)
    tasks = services.create_due_checks(today)
    assert len(tasks) == 1
    task = tasks[0]
    assert task.project == plan.project
    assert task.title == f'Checks {services.month_start(today):%B %Y}'
    assert list(task.subtasks.values_list('title', flat=True)) == ['Update plugins', 'Test backup']
    assert task.billable is False
    assert services.create_due_checks(today) == []
    plan.refresh_from_db()
    assert plan.next_check_date == add_months(services.month_start(today), 1)
    assert services.create_checks_task(plan, services.month_start(today)) is None


def test_paused_plan_gets_no_checks():
    plan = _plan()
    MaintenanceCheck.objects.create(plan=plan, title='Update plugins')
    services.schedule_checks(plan)
    services.set_status(plan, MaintenancePlan.PAUSED)
    assert services.create_due_checks() == []
    assert not MaintenanceCheckRun.objects.exists()


def test_missed_periods_create_only_the_current_one():
    plan = _plan()
    MaintenanceCheck.objects.create(plan=plan, title='Update plugins')
    today = timezone.localdate()
    plan.next_check_date = add_months(services.month_start(today), -3)
    plan.save()
    tasks = services.create_due_checks(today)
    assert len(tasks) == 1
    assert MaintenanceCheckRun.objects.get().period_start == services.month_start(today)


# --- Renewals -----------------------------------------------------------


def test_auto_renewing_plan_moves_its_date_and_others_end():
    today = timezone.localdate()
    renewing = _plan(renewal_date=today - timedelta(days=1), auto_renew=True, term_months=12)
    ending = _plan(renewal_date=today - timedelta(days=1), auto_renew=False)
    result = services.run_daily(today)
    renewing.refresh_from_db()
    ending.refresh_from_db()
    assert renewing.renewal_date == add_months(today - timedelta(days=1), 12)
    assert Project.objects.get(pk=renewing.project_id).deadline == renewing.renewal_date
    assert renewing.status == MaintenancePlan.ACTIVE
    assert ending.status == MaintenancePlan.ENDED
    assert ending.project.status == Project.FINISHED
    assert result['renewed'] == [renewing] and result['ended'] == [ending]


def test_daily_command_runs_maintenance(capsys):
    from django.core.management import call_command

    call_command('create_recurring_invoices')
    assert 'Maintenance:' in capsys.readouterr().out


# --- Sites and logins ---------------------------------------------------


def test_logins_are_stored_encrypted():
    site = Site.objects.create(client=ClientFactory(), name='acme.test')
    credential = SiteCredential.objects.create(site=site, label='WordPress', username='admin', password='s3cret!',
                                               notes='2FA on the phone')
    with connection.cursor() as cursor:
        cursor.execute('SELECT username, password, notes FROM maintenance_sitecredential WHERE id = %s', [credential.pk])
        row = cursor.fetchone()
    assert all(value.startswith('gAAAAA') for value in row)
    assert SiteCredential.objects.get(pk=credential.pk).password == 's3cret!'


def test_password_shows_only_when_asked(client):
    admin = AdminUserFactory()
    site = Site.objects.create(client=ClientFactory(), name='acme.test')
    credential = SiteCredential.objects.create(site=site, label='Hosting', password='s3cret!')
    client.force_login(admin)
    page = client.get(reverse('maintenance_site_detail', args=[site.pk]))
    assert page.status_code == 200
    assert b's3cret!' not in page.content
    shown = client.get(reverse('maintenance_credential_reveal', args=[site.pk, credential.pk]))
    assert b's3cret!' in shown.content


def test_without_the_module_nothing_opens(client):
    plan = _plan()
    site = Site.objects.create(client=plan.client, name='acme.test')
    credential = SiteCredential.objects.create(site=site, label='Hosting', password='s3cret!')
    client.force_login(_member(access_clients=True, clients_view_all=True))
    for url in (
        reverse('maintenance_plan_list'),
        reverse('maintenance_plan_detail', args=[plan.pk]),
        reverse('maintenance_site_detail', args=[site.pk]),
        reverse('maintenance_credential_reveal', args=[site.pk, credential.pk]),
        reverse('client_detail_sites', args=[plan.client_id]),
    ):
        assert client.get(url).status_code == 403, url


def test_member_with_the_module_sees_plans(client):
    plan = _plan()
    client.force_login(_member(access_maintenance=True))
    assert client.get(reverse('maintenance_plan_detail', args=[plan.pk])).status_code == 200


def test_admin_preset_has_maintenance():
    from apps.accounts.factories import admin_preset, developer_preset

    assert admin_preset().access_maintenance is True
    assert developer_preset().access_maintenance is False


# --- Pages --------------------------------------------------------------


def test_create_plan_and_site_from_the_drawers(client):
    admin = AdminUserFactory()
    customer = ClientFactory(currency=_eur())
    client.force_login(admin)
    response = client.post(reverse('maintenance_site_create') + f'?client={customer.pk}', {
        'name': 'Shop', 'url': 'https://shop.test', 'built_by': 'other', 'built_by_name': 'Other Agency',
    })
    assert response.status_code == 200 and response['HX-Redirect']
    site = Site.objects.get()
    assert site.built_by_label == 'Other Agency'

    assert client.get(reverse('maintenance_plan_create') + f'?client={customer.pk}').status_code == 200
    response = client.post(reverse('maintenance_plan_create'), {
        'client': customer.pk, 'name': 'Shop care', 'sites': [site.pk], 'start_date': '2026-11-01',
        'auto_renew': 'on', 'term_months': 12, 'notice_days': 30, 'frequency': 'monthly',
        'price': '250', 'included_hours': '4', 'overage_rate': '55', 'check_frequency': 'monthly',
    })
    assert response.status_code == 200, response.content
    plan = MaintenancePlan.objects.get()
    assert list(plan.sites.all()) == [site]
    assert response['HX-Redirect'] == reverse('maintenance_plan_detail', args=[plan.pk])


def test_plan_form_refuses_another_clients_site():
    from apps.maintenance.forms import PlanForm

    customer = ClientFactory()
    other_site = Site.objects.create(client=ClientFactory(), name='Not theirs')
    form = PlanForm({
        'client': customer.pk, 'name': 'Care', 'sites': [other_site.pk], 'start_date': '2026-11-01',
        'term_months': 12, 'notice_days': 30, 'frequency': 'monthly', 'included_hours': '0',
        'check_frequency': 'monthly',
    }, user=AdminUserFactory())
    assert not form.is_valid()
    assert 'sites' in form.errors


def test_pages_render(client):
    admin = AdminUserFactory()
    plan = _plan(admin)
    site = Site.objects.create(client=plan.client, name='acme.test', domain_expires=timezone.localdate())
    plan.sites.add(site)
    MaintenanceCheck.objects.create(plan=plan, title='Update plugins')
    _log(plan, 6)
    client.force_login(admin)
    today = timezone.localdate()
    for url in (
        reverse('maintenance_plan_list'),
        reverse('maintenance_plan_list') + '?status=all&q=acme',
        reverse('maintenance_plan_detail', args=[plan.pk]),
        reverse('maintenance_plan_edit', args=[plan.pk]),
        reverse('maintenance_plan_invoicing', args=[plan.pk]),
        reverse('maintenance_site_detail', args=[site.pk]),
        reverse('maintenance_site_edit', args=[site.pk]),
        reverse('maintenance_credential_create', args=[site.pk]),
        reverse('maintenance_report', args=[plan.pk, today.year, today.month]),
        reverse('maintenance_report_email', args=[plan.pk, today.year, today.month]),
        reverse('client_detail_maintenance', args=[plan.client_id]),
        reverse('client_detail_sites', args=[plan.client_id]),
        reverse('dashboard'),
    ):
        response = client.get(url)
        assert response.status_code == 200, url
    dashboard = client.get(reverse('dashboard'))
    assert b'dashboard-maintenance' in dashboard.content


def test_check_buttons(client):
    admin = AdminUserFactory()
    plan = _plan(admin)
    client.force_login(admin)
    response = client.post(reverse('maintenance_check_create', args=[plan.pk]), {'title': 'Update plugins'})
    assert b'Update plugins' in response.content
    plan.refresh_from_db()
    assert plan.next_check_date == services.month_start(timezone.localdate())
    assert json.loads(response['HX-Trigger'])['infoToast']['message'] == 'Check added: Update plugins'
    assert b'id="plan-sections"' in response.content and b'<html' not in response.content

    response = client.post(reverse('maintenance_check_run', args=[plan.pk]))
    run = MaintenanceCheckRun.objects.get(plan=plan)
    assert json.loads(response['HX-Trigger'])['infoToast']['message'] == f'Created {run.task.identifier}: {run.task.title}'
    # The new task shows in Open tasks and under Checks tasks straight away.
    assert response.content.count(run.task.title.encode()) >= 2

    again = client.post(reverse('maintenance_check_run', args=[plan.pk]))
    assert 'was already created' in json.loads(again['HX-Trigger'])['infoToast']['message']
    assert MaintenanceCheckRun.objects.filter(plan=plan).count() == 1


def test_check_run_creates_only_this_plans_task(client):
    admin = AdminUserFactory()
    plan, other = _plan(admin), _plan(admin)
    for item in (plan, other):
        MaintenanceCheck.objects.create(plan=item, title='Backups', position=1)
        services.schedule_checks(item)
    client.force_login(admin)
    client.post(reverse('maintenance_check_run', args=[plan.pk]))
    assert MaintenanceCheckRun.objects.filter(plan=plan).count() == 1
    assert not MaintenanceCheckRun.objects.filter(plan=other).exists()


def test_plan_sections_render_alone(client):
    admin = AdminUserFactory()
    plan = _plan(admin)
    TaskFactory(project=plan.project, title='Fix the contact form')
    client.force_login(admin)
    response = client.get(reverse('maintenance_plan_sections', args=[plan.pk]), {'month': '2026-01'})
    assert response.status_code == 200
    assert b'Fix the contact form' in response.content
    assert b'month=2026-01' in response.content
    page = client.get(reverse('maintenance_plan_detail', args=[plan.pk]))
    assert b'data-live-section=' in page.content and b'id="live-tasks"' in page.content


def test_report_pdf_email_and_portal(client):
    admin = AdminUserFactory()
    plan = _plan(admin)
    ClientContact.objects.create(client=plan.client, name='Ana', email='ana@acme.test', is_primary=True)
    _log(plan, 2)
    today = timezone.localdate()
    client.force_login(admin)
    pdf = client.get(reverse('maintenance_report_pdf', args=[plan.pk, today.year, today.month]))
    assert pdf['Content-Type'] == 'application/pdf'
    assert pdf.content.startswith(b'%PDF')

    response = client.post(reverse('maintenance_report_email', args=[plan.pk, today.year, today.month]), {
        'to': 'ana@acme.test', 'subject': 'Report', 'message': 'Hello',
    })
    assert response.status_code == 200 and response['HX-Redirect']
    assert len(mail.outbox) == 1
    assert mail.outbox[0].attachments[0][2] == 'application/pdf'
    report = MaintenanceReport.objects.get()
    assert report.sent_at is not None
    assert ClientMessage.objects.filter(client=plan.client, subject='Report', error='').exists()

    from apps.portal.views import _maintenance_reports

    assert list(_maintenance_reports(plan.client)) == [report]


def test_report_lists_tasks_worked_on_this_month():
    plan = _plan()
    entry = _log(plan, 1.5)
    data = services.report_data(plan, timezone.localdate())
    assert [item.task for item in data['work']] == [entry.task]
    assert data['work'][0].hours == Decimal('1.50')


def test_dashboard_alerts():
    today = timezone.localdate()
    plan = _plan(renewal_date=today + timedelta(days=10))
    Site.objects.create(client=plan.client, name='old.test', ssl_expires=today - timedelta(days=1))
    Site.objects.create(client=plan.client, name='fine.test', ssl_expires=today + timedelta(days=200))
    _log(plan, 6)
    labels = [(alert.label, alert.icon) for alert in services.dashboard_alerts(today)]
    assert ('old.test', 'lock') in labels
    assert (plan.name, 'refresh-cw') in labels
    assert (plan.name, 'clock') in labels
    assert all(label != 'fine.test' for label, _icon in labels)


def test_invoices_of_the_plan():
    plan = _plan()
    invoice = services.set_up_invoicing(plan, plan.created_by, issue_date=timezone.localdate())
    assert list(services.plan_invoices(plan)) == [invoice]
    assert Invoice.objects.count() == 1

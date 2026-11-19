"""Maintenance services: project, hours, invoices, extra hours, checks, renewals, sites and logins, reports."""
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
from apps.projects.models import Project, ProjectAccess
from apps.services import core
from apps.services.models import (
    Service,
    ServiceReport,
    ServiceType,
    Site,
    SiteCredential,
)
from apps.tasks.factories import TaskFactory, TimeEntryFactory

pytestmark = pytest.mark.django_db


def _eur():
    currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
    return currency


def _service(user=None, **extra):
    user = user or AdminUserFactory()
    client = extra.pop('client', None) or ClientFactory(currency=_eur())
    values = {
        'client': client, 'name': 'Acme website care', 'start_date': date(2026, 1, 1),
        'price': Decimal('300'), 'included_hours': Decimal('5'), 'overage_rate': Decimal('60'),
    }
    values.update(extra)
    return core.create_service(Service(**values), user)


def _log(service, hours, day=None, user=None):
    day = day or timezone.localdate()
    start = timezone.make_aware(datetime.combine(day, time(10)))
    task = TaskFactory(project=service.project)
    return TimeEntryFactory(task=task, user=user or AdminUserFactory(), started_at=start,
                            ended_at=start + timedelta(minutes=int(hours * 60)))


def _member(**flags):
    preset = PermissionPreset.objects.create(name=f'P{PermissionPreset.objects.count()}', **flags)
    return UserFactory(permission_preset=preset)


# --- Plan and project -------------------------------------------------


def test_plan_gets_its_own_fixed_price_project_with_access_for_its_creator():
    user = AdminUserFactory()
    service = _service(user)
    assert service.project.client == service.client
    assert service.project.name == service.name
    assert service.project.billing_type == Project.FIXED
    assert ProjectAccess.objects.filter(project=service.project, user=user).exists()


def test_status_moves_the_project_along():
    service = _service()
    core.set_status(service, Service.PAUSED)
    assert Project.objects.get(pk=service.project_id).status == Project.ON_HOLD
    core.set_status(service, Service.ENDED)
    assert Project.objects.get(pk=service.project_id).status == Project.FINISHED
    core.set_status(service, Service.ACTIVE)
    assert Project.objects.get(pk=service.project_id).status == Project.ACTIVE


def test_renaming_the_plan_renames_its_project():
    service = _service()
    service.name = 'New name'
    core.update_service(service)
    assert Project.objects.get(pk=service.project_id).name == 'New name'


def test_project_takes_the_plans_dates():
    service = _service(renewal_date=date(2026, 12, 31), auto_renew=True, term_months=12)
    assert (service.project.start_date, service.project.deadline) == (date(2026, 1, 1), date(2026, 12, 31))
    service.start_date, service.renewal_date = date(2026, 2, 1), None
    core.update_service(service)
    project = Project.objects.get(pk=service.project_id)
    assert (project.start_date, project.deadline) == (date(2026, 2, 1), None)


# --- Hours ------------------------------------------------------------


def test_usage_counts_this_months_time_only():
    service = _service()
    today = timezone.localdate()
    _log(service, 3, today)
    _log(service, 2, add_months(core.month_start(today), -1))
    used = core.usage(service, today)
    assert used.hours == Decimal('3.00')
    assert used.state == ''
    _log(service, 1.5, today)
    assert core.usage(service, today).state == 'warn'
    _log(service, 1, today)
    used = core.usage(service, today)
    assert used.state == 'over'
    assert used.extra_hours == Decimal('0.50')
    assert used.percent == 100


def test_plan_without_limit_has_no_extra_hours():
    service = _service(included_hours=Decimal('0'))
    _log(service, 20)
    assert core.usage(service).extra_hours == 0
    assert core.usage(service).state == ''


# --- Invoices -----------------------------------------------------------


def test_set_up_invoicing_creates_a_draft_that_repeats():
    service = _service()
    issue = timezone.localdate()
    invoice = core.set_up_invoicing(service, service.created_by, issue_date=issue)
    service.refresh_from_db()
    assert invoice.sent_at is None
    assert invoice.lines.get().unit_price == Decimal('300')
    assert service.recurring_invoice.template == invoice
    assert service.recurring_invoice.next_date == add_months(issue, 1)
    with pytest.raises(ValidationError, match='already'):
        core.set_up_invoicing(service, service.created_by, issue_date=issue)


def test_paused_plan_gets_no_repeated_draft_but_its_date_moves_on():
    service = _service()
    issue = timezone.localdate()
    core.set_up_invoicing(service, service.created_by, issue_date=issue)
    service.refresh_from_db()
    next_date = service.recurring_invoice.next_date
    core.set_status(service, Service.PAUSED)
    assert create_due_invoices(today=next_date) == []
    service.recurring_invoice.refresh_from_db()
    assert service.recurring_invoice.next_date > next_date

    core.set_status(service, Service.ACTIVE)
    created = create_due_invoices(today=service.recurring_invoice.next_date)
    assert len(created) == 1


def test_extra_hours_go_on_the_plans_draft_once():
    service = _service()
    core.set_up_invoicing(service, service.created_by, issue_date=timezone.localdate())
    _log(service, 7)
    invoice = core.add_extra_hours(service, timezone.localdate(), service.created_by)
    service.refresh_from_db()
    assert invoice == service.recurring_invoice.template
    line = invoice.lines.get(description__startswith='Extra hours')
    assert line.quantity == Decimal('2.00')
    assert line.unit_price == Decimal('60')
    with pytest.raises(ValidationError, match='already'):
        core.add_extra_hours(service, timezone.localdate(), service.created_by)


def test_extra_hours_without_a_draft_make_a_new_one():
    service = _service()
    _log(service, 6)
    invoice = core.add_extra_hours(service, timezone.localdate(), service.created_by)
    assert invoice.client == service.client
    assert invoice.sent_at is None
    assert invoice.lines.get().quantity == Decimal('1.00')


def test_extra_hours_need_a_rate_and_extra_time():
    service = _service(overage_rate=None)
    _log(service, 9)
    with pytest.raises(ValidationError, match='extra hour'):
        core.add_extra_hours(service, timezone.localdate(), service.created_by)
    service = _service()
    _log(service, 1)
    with pytest.raises(ValidationError, match='no extra hours'):
        core.add_extra_hours(service, timezone.localdate(), service.created_by)


def test_plan_time_is_not_offered_for_hourly_billing():
    """The service's project is fixed price, so "Add tasks" never bills its time again."""
    from apps.invoices.billing import unbilled_entries

    service = _service()
    _log(service, 2)
    assert not unbilled_entries(service.client).exists()


# --- Service types and their checklist -------------------------------


def _type(**extra):
    values = {
        'name': 'Maintenance', 'description': 'Updates and backups', 'price': Decimal('120'),
        'included_hours': Decimal('2'), 'overage_rate': Decimal('50'), 'checklist': 'Update plugins\nTest backup\n',
    }
    values.update(extra)
    return ServiceType.objects.create(**values)


def test_service_of_a_type_with_a_checklist_gets_a_monthly_recurring_task():
    from apps.tasks import recurring
    from apps.tasks.models import RecurringTask

    service = _service(service_type=_type())
    rule = RecurringTask.objects.get(project=service.project)
    assert rule.title == 'Checks'
    assert rule.checklist_items == ['Update plugins', 'Test backup']
    assert rule.frequency == RecurringTask.MONTHLY and rule.month_day == 1
    assert rule.billable is False
    today = timezone.localdate()
    day, task = recurring.create_now(rule, today=today)
    assert day == core.month_start(today)
    assert task.title == f'Checks · {day:%B %Y}'
    assert list(task.subtasks.values_list('title', flat=True)) == ['Update plugins', 'Test backup']


def test_service_without_a_checklist_gets_no_recurring_task():
    from apps.tasks.models import RecurringTask

    _service(service_type=_type(checklist=''))
    _service()
    assert not RecurringTask.objects.exists()


def test_paused_service_creates_no_recurring_tasks():
    from apps.tasks import recurring

    service = _service(service_type=_type())
    core.set_status(service, Service.PAUSED)
    assert recurring.create_due_tasks(add_months(timezone.localdate(), 1)) == []


def test_report_lists_the_months_checklists():
    from apps.tasks import recurring

    service = _service(service_type=_type())
    rule = service.project.recurring_tasks.get()
    day, task = recurring.create_now(rule)
    task.subtasks.filter(title='Test backup').update(completed=True)
    data = core.report_data(service, day)
    assert [item.pk for item in data['checklists']] == [task.pk]


def test_choosing_a_type_fills_in_the_new_service_drawer(client):
    admin = AdminUserFactory()
    customer = ClientFactory(currency=_eur(), name='Acme')
    kind = _type()
    client.force_login(admin)
    response = client.get(reverse('service_create'), {'client': customer.pk, 'service_type': kind.pk, 'apply_type': '1'})
    html = response.content.decode()
    assert 'value="Acme · Maintenance"' in html
    assert 'value="120' in html and 'Updates and backups' in html
    assert 'Checks, 2 items' in html


def test_service_types_in_settings(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    assert client.get(reverse('settings_service_types')).status_code == 200
    response = client.post(reverse('settings_service_type_add'), {
        'name': 'Social media', 'description': '12 posts a month', 'frequency': 'monthly', 'price': '400',
        'included_hours': '0', 'overage_rate': '', 'checklist_title': 'Posts', 'checklist': 'Plan\nDesign',
        'position': '0',
    })
    assert response.status_code in (200, 302), response.content
    kind = ServiceType.objects.get(name='Social media')
    assert kind.checklist_title == 'Posts'
    response = client.post(reverse('settings_service_type_delete', args=[kind.pk]))
    assert not ServiceType.objects.filter(pk=kind.pk).exists()

    used = _type()
    _service(service_type=used)
    client.post(reverse('settings_service_type_delete', args=[used.pk]))
    assert ServiceType.objects.filter(pk=used.pk).exists()

    client.force_login(_member(access_services=True))
    assert client.get(reverse('settings_service_types')).status_code in (302, 403)


def test_old_maintenance_links_redirect(client):
    response = client.get('/maintenance/12/reports/2026-11/?x=1')
    assert response.status_code == 301
    assert response['Location'] == '/services/12/reports/2026-11/?x=1'


# --- Renewals -----------------------------------------------------------


def test_auto_renewing_plan_moves_its_date_and_others_end():
    today = timezone.localdate()
    renewing = _service(renewal_date=today - timedelta(days=1), auto_renew=True, term_months=12)
    ending = _service(renewal_date=today - timedelta(days=1), auto_renew=False)
    result = core.run_daily(today)
    renewing.refresh_from_db()
    ending.refresh_from_db()
    assert renewing.renewal_date == add_months(today - timedelta(days=1), 12)
    assert Project.objects.get(pk=renewing.project_id).deadline == renewing.renewal_date
    assert renewing.status == Service.ACTIVE
    assert ending.status == Service.ENDED
    assert ending.project.status == Project.FINISHED
    assert result['renewed'] == [renewing] and result['ended'] == [ending]


def test_daily_command_runs_services_and_recurring_tasks(capsys):
    from django.core.management import call_command

    call_command('create_recurring_invoices')
    out = capsys.readouterr().out
    assert 'Services:' in out and 'Recurring tasks:' in out


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
    page = client.get(reverse('site_detail', args=[site.pk]))
    assert page.status_code == 200
    assert b's3cret!' not in page.content
    shown = client.get(reverse('site_credential_reveal', args=[site.pk, credential.pk]))
    assert b's3cret!' in shown.content


def test_without_the_module_nothing_opens(client):
    service = _service()
    site = Site.objects.create(client=service.client, name='acme.test')
    credential = SiteCredential.objects.create(site=site, label='Hosting', password='s3cret!')
    client.force_login(_member(access_clients=True, clients_view_all=True))
    for url in (
        reverse('service_list'),
        reverse('service_detail', args=[service.pk]),
        reverse('site_detail', args=[site.pk]),
        reverse('site_credential_reveal', args=[site.pk, credential.pk]),
        reverse('client_detail_sites', args=[service.client_id]),
    ):
        assert client.get(url).status_code == 403, url


def test_member_with_the_module_sees_plans(client):
    service = _service()
    client.force_login(_member(access_services=True))
    assert client.get(reverse('service_detail', args=[service.pk])).status_code == 200


def test_admin_preset_has_maintenance():
    from apps.accounts.factories import admin_preset, developer_preset

    assert admin_preset().access_services is True
    assert developer_preset().access_services is False


# --- Pages --------------------------------------------------------------


def test_create_plan_and_site_from_the_drawers(client):
    admin = AdminUserFactory()
    customer = ClientFactory(currency=_eur())
    client.force_login(admin)
    response = client.post(reverse('site_create') + f'?client={customer.pk}', {
        'name': 'Shop', 'url': 'https://shop.test', 'built_by': 'other', 'built_by_name': 'Other Agency',
    })
    assert response.status_code == 200 and response['HX-Redirect']
    site = Site.objects.get()
    assert site.built_by_label == 'Other Agency'

    assert client.get(reverse('service_create') + f'?client={customer.pk}').status_code == 200
    response = client.post(reverse('service_create'), {
        'client': customer.pk, 'name': 'Shop care', 'sites': [site.pk], 'start_date': '2026-11-01',
        'auto_renew': 'on', 'term_months': 12, 'notice_days': 30, 'frequency': 'monthly',
        'price': '250', 'included_hours': '4', 'overage_rate': '55',
    })
    assert response.status_code == 200, response.content
    service = Service.objects.get()
    assert list(service.sites.all()) == [site]
    assert response['HX-Redirect'] == reverse('service_detail', args=[service.pk])


def test_plan_form_refuses_another_clients_site():
    from apps.services.forms import ServiceForm

    customer = ClientFactory()
    other_site = Site.objects.create(client=ClientFactory(), name='Not theirs')
    form = ServiceForm({
        'client': customer.pk, 'name': 'Care', 'sites': [other_site.pk], 'start_date': '2026-11-01',
        'term_months': 12, 'notice_days': 30, 'frequency': 'monthly', 'included_hours': '0',
    }, user=AdminUserFactory())
    assert not form.is_valid()
    assert 'sites' in form.errors


def test_pages_render(client):
    admin = AdminUserFactory()
    service = _service(admin)
    site = Site.objects.create(client=service.client, name='acme.test', domain_expires=timezone.localdate())
    service.sites.add(site)
    _log(service, 6)
    client.force_login(admin)
    today = timezone.localdate()
    for url in (
        reverse('service_list'),
        reverse('service_list') + '?status=all&q=acme',
        reverse('service_detail', args=[service.pk]),
        reverse('service_edit', args=[service.pk]),
        reverse('service_invoicing', args=[service.pk]),
        reverse('site_detail', args=[site.pk]),
        reverse('site_edit', args=[site.pk]),
        reverse('site_credential_create', args=[site.pk]),
        reverse('service_report', args=[service.pk, today.year, today.month]),
        reverse('service_report_email', args=[service.pk, today.year, today.month]),
        reverse('client_detail_services', args=[service.client_id]),
        reverse('client_detail_sites', args=[service.client_id]),
        reverse('dashboard'),
    ):
        response = client.get(url)
        assert response.status_code == 200, url
    dashboard = client.get(reverse('dashboard'))
    assert b'dashboard-services' in dashboard.content


def test_service_page_shows_the_recurring_tasks(client):
    from apps.tasks import recurring

    admin = AdminUserFactory()
    service = _service(admin, service_type=_type())
    rule = service.project.recurring_tasks.get()
    _day, task = recurring.create_now(rule, admin)
    client.force_login(admin)
    response = client.get(reverse('service_sections', args=[service.pk]))
    html = response.content.decode()
    assert 'id="recurring-panel"' in html
    assert 'Every month on day 1' in html
    assert task.identifier in html


def test_plan_sections_render_alone(client):
    admin = AdminUserFactory()
    service = _service(admin)
    TaskFactory(project=service.project, title='Fix the contact form')
    client.force_login(admin)
    response = client.get(reverse('service_sections', args=[service.pk]), {'month': '2026-01'})
    assert response.status_code == 200
    assert b'Fix the contact form' in response.content
    assert b'month=2026-01' in response.content
    page = client.get(reverse('service_detail', args=[service.pk]))
    assert b'data-live-section=' in page.content and b'id="live-tasks"' in page.content


def test_report_pdf_email_and_portal(client):
    admin = AdminUserFactory()
    service = _service(admin)
    ClientContact.objects.create(client=service.client, name='Ana', email='ana@acme.test', is_primary=True)
    _log(service, 2)
    today = timezone.localdate()
    client.force_login(admin)
    pdf = client.get(reverse('service_report_pdf', args=[service.pk, today.year, today.month]))
    assert pdf['Content-Type'] == 'application/pdf'
    assert pdf.content.startswith(b'%PDF')

    response = client.post(reverse('service_report_email', args=[service.pk, today.year, today.month]), {
        'to': 'ana@acme.test', 'subject': 'Report', 'message': 'Hello',
    })
    assert response.status_code == 200 and response['HX-Redirect']
    assert len(mail.outbox) == 1
    assert mail.outbox[0].attachments[0][2] == 'application/pdf'
    report = ServiceReport.objects.get()
    assert report.sent_at is not None
    assert ClientMessage.objects.filter(client=service.client, subject='Report', error='').exists()

    from apps.portal.views import _service_reports

    assert list(_service_reports(service.client)) == [report]


def test_report_lists_tasks_worked_on_this_month():
    service = _service()
    entry = _log(service, 1.5)
    data = core.report_data(service, timezone.localdate())
    assert [item.task for item in data['work']] == [entry.task]
    assert data['work'][0].hours == Decimal('1.50')


def test_dashboard_alerts():
    today = timezone.localdate()
    service = _service(renewal_date=today + timedelta(days=10))
    Site.objects.create(client=service.client, name='old.test', ssl_expires=today - timedelta(days=1))
    Site.objects.create(client=service.client, name='fine.test', ssl_expires=today + timedelta(days=200))
    _log(service, 6)
    labels = [(alert.label, alert.icon) for alert in core.dashboard_alerts(today)]
    assert ('old.test', 'lock') in labels
    assert (service.name, 'refresh-cw') in labels
    assert (service.name, 'clock') in labels
    assert all(label != 'fine.test' for label, _icon in labels)


def test_invoices_of_the_service():
    service = _service()
    invoice = core.set_up_invoicing(service, service.created_by, issue_date=timezone.localdate())
    assert list(core.service_invoices(service)) == [invoice]
    assert Invoice.objects.count() == 1

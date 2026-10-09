"""Recurring invoices created as drafts by a daily job (release 0.29.0)."""
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.crm.models import Currency
from apps.invoices.models import Invoice, RecurringInvoice, add_months
from apps.invoices.recurring import create_due_invoices, save_recurring, suggested_next_date
from apps.invoices.services import add_line, create_invoice, mark_sent
from apps.projects.factories import ProjectFactory


def _template(issue=date(2026, 1, 31), due=date(2026, 2, 14), tax='19'):
    owner = ClientFactory(name='Acme', billing_email='pay@acme.test')
    owner.currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
    owner.save(update_fields=['currency'])
    invoice = create_invoice(client=owner, issue_date=issue, due_date=due, tax_rate=Decimal(tax))
    add_line(invoice, project=None, description='Hosting', quantity=Decimal('1'), unit_price=Decimal('50'))
    add_line(invoice, project=ProjectFactory(client=owner, name='Website'), description='',
             quantity=Decimal('10'), unit_price=Decimal('40'))
    return mark_sent(invoice)


def _schedule(template, next_date, frequency=RecurringInvoice.MONTHLY, end_date=None):
    return save_recurring(template, frequency=frequency, next_date=next_date, end_date=end_date,
                          today=next_date)


def test_months_keep_the_day_or_the_last_day():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 2, 28), 1, anchor_day=31) == date(2026, 3, 31)
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)


@pytest.mark.django_db
class TestCreatingDrafts:
    def test_a_draft_copies_lines_tax_and_payment_days(self):
        template = _template()
        _schedule(template, date(2026, 2, 28))

        [draft] = create_due_invoices(today=date(2026, 2, 28))
        assert draft.is_draft
        assert draft.number != template.number
        assert (draft.issue_date, draft.due_date) == (date(2026, 2, 28), date(2026, 3, 14))
        assert draft.tax_rate == Decimal('19.00')
        assert [(line.description, line.quantity, line.unit_price, line.project_id) for line in draft.lines.all()] == [
            (line.description, line.quantity, line.unit_price, line.project_id) for line in template.lines.all()
        ]
        assert draft.from_recurring == template.recurring
        template.recurring.refresh_from_db()
        # The schedule keeps the start date's day: Feb 28 is followed by Mar 28, not drifting.
        assert template.recurring.next_date == date(2026, 3, 28)

    def test_running_twice_does_not_duplicate_and_a_missed_period_is_caught_up(self):
        template = _template()
        _schedule(template, date(2026, 3, 15))
        assert create_due_invoices(today=date(2026, 3, 14)) == []
        assert len(create_due_invoices(today=date(2026, 5, 20))) == 3  # Mar 15, Apr 15, May 15
        assert create_due_invoices(today=date(2026, 5, 20)) == []
        assert Invoice.objects.filter(from_recurring__isnull=False).count() == 3

    def test_quarterly_and_the_end_date(self):
        template = _template()
        _schedule(template, date(2026, 3, 1), RecurringInvoice.QUARTERLY, end_date=date(2026, 8, 1))
        drafts = create_due_invoices(today=date(2027, 1, 1))
        assert [draft.issue_date for draft in drafts] == [date(2026, 3, 1), date(2026, 6, 1)]
        template.recurring.refresh_from_db()
        assert template.recurring.finished

    def test_an_archived_client_gets_no_drafts(self):
        template = _template()
        _schedule(template, date(2026, 3, 1))
        template.client.archived_at = timezone.now()
        template.client.save(update_fields=['archived_at'])
        assert create_due_invoices(today=date(2026, 3, 1)) == []
        template.recurring.refresh_from_db()
        assert template.recurring.next_date == date(2026, 4, 1)

    def test_the_command(self):
        template = _template()
        _schedule(template, timezone.localdate())
        out = StringIO()
        call_command('create_recurring_invoices', stdout=out)
        assert 'Created 1 draft invoice(s).' in out.getvalue()


@pytest.mark.django_db
class TestScreens:
    def test_start_change_and_stop(self, client):
        template = _template()
        client.force_login(AdminUserFactory())
        url = reverse('invoice_recurring', args=[template.pk])

        form = client.get(url).context['form']
        assert form.initial['next_date'] == suggested_next_date(template)
        assert form.initial['next_date'] >= timezone.localdate()

        next_date = timezone.localdate()
        response = client.post(url, {'frequency': 'yearly', 'next_date': next_date.isoformat()})
        assert response['HX-Redirect'] == reverse('invoice_detail', args=[template.pk])
        recurring = RecurringInvoice.objects.get(template=template)
        assert (recurring.frequency, recurring.next_date) == ('yearly', next_date)
        assert 'Repeats yearly' in client.get(reverse('invoice_detail', args=[template.pk])).content.decode()

        past = client.post(url, {'frequency': 'monthly', 'next_date': '2020-01-01'})
        assert 'Pick today or a later date' in past.content.decode()

        client.post(reverse('invoice_recurring_stop', args=[template.pk]))
        assert not RecurringInvoice.objects.exists()

    def test_a_draft_links_back_to_its_template(self, client):
        template = _template()
        _schedule(template, date(2026, 3, 1))
        [draft] = create_due_invoices(today=date(2026, 3, 1))
        client.force_login(AdminUserFactory())
        html = client.get(reverse('invoice_detail', args=[draft.pk])).content.decode()
        assert 'Created from the repeat on' in html
        assert template.number_label in html

    def test_needs_invoices_create(self, client):
        template = _template()
        preset = PermissionPreset.objects.create(
            name='Editor', access_dashboard=True, access_invoices=True, invoices_view_all=True,
            invoices_edit=True, invoices_create=False,
        )
        client.force_login(UserFactory(permission_preset=preset))
        assert client.get(reverse('invoice_recurring', args=[template.pk])).status_code == 403
        html = client.get(reverse('invoice_detail', args=[template.pk])).content.decode()
        assert reverse('invoice_recurring', args=[template.pk]) not in html

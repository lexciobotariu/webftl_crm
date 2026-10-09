"""Emailing invoices and reminders, with the PDF attached and every attempt logged (release 0.28.0)."""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.clients.models import ClientMessage, messages_visible_to
from apps.crm.models import Company, Currency
from apps.invoices.models import Invoice
from apps.invoices.services import add_line, create_invoice, mark_sent


def _invoice(amount='100', due_in=14, sent=False):
    owner = ClientFactory(name='Acme', billing_name='Acme Billing', billing_email='pay@acme.test')
    owner.currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
    owner.save(update_fields=['currency'])
    today = timezone.localdate()
    invoice = create_invoice(client=owner, issue_date=today, due_date=today + timedelta(days=due_in),
                             tax_rate=Decimal('0'))
    if amount:
        add_line(invoice, project=None, description='Website', quantity=Decimal('1'), unit_price=Decimal(amount))
    if sent:
        invoice = mark_sent(invoice)
    return invoice


def _send(client, invoice, kind='invoice', **data):
    fields = {'to': 'pay@acme.test', 'subject': 'Your invoice', 'message': 'Hello'}
    fields.update(data)
    return client.post(reverse('invoice_email', args=[invoice.pk, kind]), fields, HTTP_HX_REQUEST='true')


@pytest.mark.django_db
class TestEmailInvoice:
    def test_the_drawer_is_prefilled_from_the_invoice(self, client):
        invoice = _invoice()
        client.force_login(AdminUserFactory())
        response = client.get(reverse('invoice_email', args=[invoice.pk, 'invoice']))
        form = response.context['form']
        assert form.initial['to'] == 'pay@acme.test'
        assert form.initial['subject'].startswith(f'Invoice {invoice.number_label}')
        assert 'Total: 100.00 €' in form.initial['message']

    def test_sending_a_draft_attaches_the_pdf_marks_it_sent_and_logs_it(self, client):
        Company.objects.update_or_create(pk=1, defaults={'email': 'office@agency.test', 'legal_name': 'Agency'})
        invoice = _invoice()
        admin = AdminUserFactory()
        client.force_login(admin)

        response = _send(client, invoice, to='pay@acme.test; boss@acme.test')
        assert response['HX-Redirect'] == reverse('invoice_detail', args=[invoice.pk])

        [email] = mail.outbox
        assert email.to == ['pay@acme.test', 'boss@acme.test']
        assert email.reply_to == ['office@agency.test']
        [(filename, content, mimetype)] = email.attachments
        assert (filename, mimetype) == (f'{invoice.number_label}.pdf', 'application/pdf')
        assert content.startswith(b'%PDF')

        invoice.refresh_from_db()
        assert invoice.sent_at is not None
        logged = invoice.emails.get()
        assert (logged.kind, logged.client, logged.author) == (ClientMessage.EMAIL, invoice.client, admin)
        assert logged.recipients == 'pay@acme.test, boss@acme.test'
        assert not logged.failed
        assert 'Your invoice' in client.get(reverse('invoice_detail', args=[invoice.pk])).content.decode()

    def test_a_failed_send_keeps_the_draft_and_logs_the_error(self, client):
        invoice = _invoice()
        client.force_login(AdminUserFactory())
        with mock.patch('django.core.mail.EmailMessage.send', side_effect=RuntimeError('Domain not verified')):
            response = _send(client, invoice)
        assert 'The email was not sent: Domain not verified' in response.content.decode()
        invoice.refresh_from_db()
        assert invoice.sent_at is None
        assert invoice.emails.get().error == 'Domain not verified'

    def test_an_empty_invoice_is_refused_before_anything_is_sent(self, client):
        invoice = _invoice(amount=None)
        client.force_login(AdminUserFactory())
        assert 'Add a line with an amount' in _send(client, invoice).content.decode()
        assert not mail.outbox
        assert not ClientMessage.objects.exists()

    def test_bad_addresses_are_refused(self, client):
        invoice = _invoice()
        client.force_login(AdminUserFactory())
        assert 'is not a valid email address' in _send(client, invoice, to='pay@acme.test, nope').content.decode()
        assert not mail.outbox

    def test_needs_invoices_edit(self, client):
        invoice = _invoice()
        preset = PermissionPreset.objects.create(
            name='Viewer', access_dashboard=True, access_invoices=True, invoices_view_all=True, invoices_edit=False,
        )
        client.force_login(UserFactory(permission_preset=preset))
        assert _send(client, invoice).status_code == 403
        assert not mail.outbox


@pytest.mark.django_db
class TestReminder:
    def test_a_reminder_for_an_overdue_invoice(self, client):
        invoice = _invoice(sent=True)
        Invoice.objects.filter(pk=invoice.pk).update(due_date=timezone.localdate() - timedelta(days=5))
        client.force_login(AdminUserFactory())

        form = client.get(reverse('invoice_email', args=[invoice.pk, 'reminder'])).context['form']
        assert form.initial['subject'].startswith('Reminder:')
        assert 'is still open' in form.initial['message']

        _send(client, invoice, kind='reminder', subject='Reminder')
        assert len(mail.outbox) == 1
        assert invoice.emails.get().subject == 'Reminder'

    def test_no_reminder_for_a_draft(self, client):
        invoice = _invoice()
        client.force_login(AdminUserFactory())
        assert _send(client, invoice, kind='reminder').status_code == 400
        html = client.get(reverse('invoice_detail', args=[invoice.pk])).content.decode()
        assert 'Send reminder' not in html
        assert 'Email invoice' in html


@pytest.mark.django_db
class TestPdfAndVisibility:
    def test_pdf_download(self, client):
        invoice = _invoice()
        client.force_login(AdminUserFactory())
        response = client.get(reverse('invoice_pdf', args=[invoice.pk]))
        assert response['Content-Type'] == 'application/pdf'
        assert response.content.startswith(b'%PDF')

    def test_invoice_emails_in_the_client_log_need_the_invoices_module(self):
        invoice = _invoice(sent=True)
        note = ClientMessage.objects.create(client=invoice.client, body='Called them')
        email = ClientMessage.objects.create(client=invoice.client, invoice=invoice, kind=ClientMessage.EMAIL,
                                             subject='Invoice', body='Total: 100.00 €')
        preset = PermissionPreset.objects.create(
            name='No money', access_dashboard=True, access_clients=True, clients_view_all=True, access_invoices=False,
        )
        assert set(messages_visible_to(UserFactory(permission_preset=preset), invoice.client)) == {note}
        assert set(messages_visible_to(AdminUserFactory(), invoice.client)) == {note, email}

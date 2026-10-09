"""Estimates: create, send, answer, turn into an invoice, email (release 0.30.0)."""
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
from apps.crm.models import Currency
from apps.invoices.estimates import (
    EstimateLocked,
    add_estimate_line,
    convert_to_invoice,
    create_estimate,
    mark_estimate_sent,
    record_answer,
)
from apps.invoices.models import Estimate
from apps.projects.factories import ProjectFactory


def _client():
    owner = ClientFactory(name='Acme', billing_email='pay@acme.test')
    owner.currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
    owner.save(update_fields=['currency'])
    return owner


def _estimate(lines=True, sent=False, valid_days=30):
    owner = _client()
    today = timezone.localdate()
    estimate = create_estimate(client=owner, issue_date=today, valid_until=today + timedelta(days=valid_days),
                               tax_rate=Decimal('19'), notes='Two weeks of work')
    if lines:
        add_estimate_line(estimate, project=None, description='Design', quantity=Decimal('2'),
                          unit_price=Decimal('100'))
        add_estimate_line(estimate, project=ProjectFactory(client=owner, name='Website'), description='',
                          quantity=Decimal('1'), unit_price=Decimal('300'))
    if sent:
        estimate = mark_estimate_sent(estimate)
    return Estimate.objects.get(pk=estimate.pk)


@pytest.mark.django_db
class TestLifecycle:
    def test_numbers_totals_and_status(self):
        first, second = _estimate(), _estimate()
        assert (first.number_label, second.number_label) == ('EST-0001', 'EST-0002')
        assert first.total == Decimal('595.00')  # 500 + 19%
        assert first.lines.last().description == 'Website'
        assert first.status == 'draft'

    def test_sent_estimates_are_locked_and_expire(self):
        estimate = _estimate(sent=True)
        assert estimate.status == 'sent'
        with pytest.raises(EstimateLocked):
            add_estimate_line(estimate, project=None, description='More', quantity=Decimal('1'),
                              unit_price=Decimal('1'))
        Estimate.objects.filter(pk=estimate.pk).update(valid_until=timezone.localdate() - timedelta(days=1))
        assert Estimate.objects.get(pk=estimate.pk).status == 'expired'

    def test_an_empty_estimate_is_not_sent(self):
        with pytest.raises(Exception, match='Add a line'):
            mark_estimate_sent(_estimate(lines=False))

    def test_accept_then_convert_once(self):
        estimate = record_answer(_estimate(sent=True), 'accepted')
        assert estimate.status == 'accepted'
        invoice = convert_to_invoice(estimate)
        assert invoice.is_draft
        assert invoice.tax_rate == Decimal('19.00')
        assert invoice.total == Decimal('595.00')
        assert [line.description for line in invoice.lines.all()] == ['Design', 'Website']
        assert invoice.lines.last().project.name == 'Website'
        estimate.refresh_from_db()
        assert estimate.status == 'invoiced'
        with pytest.raises(Exception, match='already been invoiced'):
            convert_to_invoice(estimate)

    def test_only_an_accepted_estimate_is_converted(self):
        estimate = record_answer(_estimate(sent=True), 'declined')
        with pytest.raises(Exception, match='Mark the estimate accepted'):
            convert_to_invoice(estimate)
        assert record_answer(estimate, 'open').status == 'sent'


@pytest.mark.django_db
class TestScreens:
    def test_create_add_line_send_accept_convert(self, client):
        owner = _client()
        client.force_login(AdminUserFactory())
        today = timezone.localdate()
        response = client.post(reverse('estimate_create'), {
            'client': owner.pk, 'issue_date': today.isoformat(),
            'valid_until': (today + timedelta(days=14)).isoformat(), 'tax_rate': '0', 'notes': 'Scope',
        })
        estimate = Estimate.objects.get()
        assert response['HX-Redirect'] == reverse('estimate_detail', args=[estimate.pk])

        client.post(reverse('estimate_line_create', args=[estimate.pk]),
                    {'description': 'Audit', 'quantity': '1', 'unit_price': '250'})
        assert estimate.lines.get().description == 'Audit'

        client.post(reverse('estimate_mark_sent', args=[estimate.pk]))
        client.post(reverse('estimate_answer', args=[estimate.pk, 'accepted']))
        html = client.get(reverse('estimate_detail', args=[estimate.pk])).content.decode()
        assert 'Convert to invoice' in html

        response = client.post(reverse('estimate_convert', args=[estimate.pk]))
        estimate.refresh_from_db()
        assert response['HX-Redirect'] == reverse('invoice_detail', args=[estimate.invoice_id])
        assert 'Created from estimate' in client.get(response['HX-Redirect']).content.decode()

        listing = client.get(reverse('estimate_list'), {'status': 'invoiced'})
        assert [e.pk for e in listing.context['estimates']] == [estimate.pk]

    def test_valid_until_before_issue_date_is_refused(self, client):
        owner = _client()
        client.force_login(AdminUserFactory())
        today = timezone.localdate()
        html = client.post(reverse('estimate_create'), {
            'client': owner.pk, 'issue_date': today.isoformat(),
            'valid_until': (today - timedelta(days=1)).isoformat(), 'tax_rate': '0',
        }).content.decode()
        assert 'Valid until cannot be before the issue date' in html
        assert not Estimate.objects.exists()

    def test_a_hidden_client_estimate_is_404_and_editing_needs_invoices_edit(self, client):
        estimate = _estimate()
        preset = PermissionPreset.objects.create(
            name='Viewer', access_dashboard=True, access_invoices=True, invoices_view_all=False,
        )
        client.force_login(UserFactory(permission_preset=preset))
        assert client.get(reverse('estimate_detail', args=[estimate.pk])).status_code == 404
        preset.invoices_view_all = True
        preset.save()
        assert client.get(reverse('estimate_detail', args=[estimate.pk])).status_code == 200
        assert client.post(reverse('estimate_mark_sent', args=[estimate.pk])).status_code == 403

    def test_print_and_pdf(self, client):
        estimate = _estimate()
        client.force_login(AdminUserFactory())
        html = client.get(reverse('estimate_print', args=[estimate.pk])).content.decode()
        assert 'Valid until' in html and 'Two weeks of work' in html
        assert client.get(reverse('estimate_pdf', args=[estimate.pk])).content.startswith(b'%PDF')


@pytest.mark.django_db
class TestEmail:
    def _send(self, client, estimate):
        return client.post(reverse('estimate_email', args=[estimate.pk]), {
            'to': 'pay@acme.test', 'subject': 'Your estimate', 'message': 'Hello',
        })

    def test_emailing_a_draft_sends_the_pdf_marks_it_sent_and_logs_it(self, client):
        estimate = _estimate()
        client.force_login(AdminUserFactory())
        form = client.get(reverse('estimate_email', args=[estimate.pk])).context['form']
        assert form.initial['subject'].startswith('Estimate EST-0001')
        assert 'Valid until' in form.initial['message']

        self._send(client, estimate)
        [email] = mail.outbox
        assert email.attachments[0][0] == 'EST-0001.pdf'
        estimate.refresh_from_db()
        assert estimate.status == 'sent'
        logged = estimate.emails.get()
        assert logged.kind == ClientMessage.EMAIL and logged.invoice is None

    def test_a_failed_send_keeps_the_draft(self, client):
        estimate = _estimate()
        client.force_login(AdminUserFactory())
        with mock.patch('django.core.mail.EmailMessage.send', side_effect=RuntimeError('Rejected')):
            assert 'The email was not sent: Rejected' in self._send(client, estimate).content.decode()
        estimate.refresh_from_db()
        assert estimate.is_draft

    def test_estimate_emails_in_the_client_log_need_the_invoices_module(self):
        estimate = _estimate(sent=True)
        logged = ClientMessage.objects.create(client=estimate.client, estimate=estimate,
                                              kind=ClientMessage.EMAIL, subject='Estimate', body='x')
        preset = PermissionPreset.objects.create(
            name='No money', access_dashboard=True, access_clients=True, clients_view_all=True,
        )
        assert list(messages_visible_to(UserFactory(permission_preset=preset), estimate.client)) == []
        assert list(messages_visible_to(AdminUserFactory(), estimate.client)) == [logged]

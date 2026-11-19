"""Leads (CRM-4): estimates for a lead, the online link, the board, and Convert to client."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.clients.models import Client, ClientMessage
from apps.crm.models import Company, Currency
from apps.invoices import public
from apps.invoices.estimates import (
    add_estimate_line,
    convert_to_invoice,
    create_estimate,
    mark_estimate_sent,
    update_estimate,
)
from apps.invoices.models import Estimate, visible_estimates
from apps.leads import services
from apps.leads.factories import LeadFactory, ensure_statuses, status
from apps.leads.models import Lead, LeadNote, LeadStatus
from apps.notes.models import Note
from apps.projects.models import Project


def _eur():
    currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
    return currency


def _lead(**extra):
    ensure_statuses()
    values = {'name': 'Nova Studio', 'contact_name': 'Ana Pop', 'email': 'ana@nova.test', 'currency': _eur()}
    values.update(extra)
    return LeadFactory(**values)


def _estimate(lead=None, sent=False, introduction=''):
    lead = lead or _lead()
    today = timezone.localdate()
    estimate = create_estimate(lead=lead, issue_date=today, valid_until=today + timedelta(days=30),
                               tax_rate=Decimal('0'), introduction=introduction)
    add_estimate_line(estimate, project=None, description='Website', quantity=Decimal('1'),
                      unit_price=Decimal('1000'))
    if sent:
        estimate = mark_estimate_sent(estimate)
    return Estimate.objects.get(pk=estimate.pk)


def _member(**flags):
    preset = PermissionPreset.objects.create(name=f'P{PermissionPreset.objects.count()}', **flags)
    return UserFactory(permission_preset=preset)


@pytest.mark.django_db
class TestEstimateForLead:
    def test_copies_the_lead_and_has_no_client(self):
        estimate = _estimate()
        assert estimate.client is None and estimate.for_lead
        assert (estimate.bill_to_name, estimate.bill_to_email, estimate.currency_code) == (
            'Nova Studio', 'ana@nova.test', 'EUR')
        assert estimate.recipient_name == 'Nova Studio'
        assert not Client.objects.exists()

    def test_needs_a_currency_and_exactly_one_recipient(self):
        today = timezone.localdate()
        with pytest.raises(ValidationError, match='currency for this lead'):
            create_estimate(lead=_lead(currency=None), issue_date=today, valid_until=today, tax_rate=0)
        with pytest.raises(ValidationError, match='client or a lead'):
            create_estimate(issue_date=today, valid_until=today, tax_rate=0)

    def test_header_keeps_the_lead(self):
        estimate = _estimate()
        today = timezone.localdate()
        update_estimate(estimate, issue_date=today, valid_until=today, tax_rate=5, introduction='## Scope')
        estimate.refresh_from_db()
        assert estimate.lead_id and estimate.client_id is None and estimate.introduction == '## Scope'
        with pytest.raises(ValidationError):
            update_estimate(estimate, client=ClientFactory(), issue_date=today, valid_until=today, tax_rate=0)

    def test_cannot_be_invoiced_before_the_lead_is_a_client(self):
        estimate = _estimate(sent=True)
        estimate.accepted_at = timezone.now()
        estimate.save()
        with pytest.raises(ValidationError, match='Convert the lead'):
            convert_to_invoice(estimate)

    def test_seen_only_with_the_leads_module(self):
        estimate = _estimate()
        money_only = _member(access_invoices=True, invoices_view_all=True)
        with_leads = _member(access_invoices=True, access_leads=True)
        assert not visible_estimates(money_only).filter(pk=estimate.pk).exists()
        assert visible_estimates(with_leads).filter(pk=estimate.pk).exists()

    def test_create_view_for_a_lead(self, client):
        lead = _lead()
        client.force_login(AdminUserFactory())
        page = client.get(reverse('estimate_create') + f'?lead={lead.pk}')
        assert b'Prepared for the lead' in page.content
        today = timezone.localdate()
        response = client.post(reverse('estimate_create'), {
            'lead': lead.pk, 'issue_date': today.isoformat(),
            'valid_until': (today + timedelta(days=14)).isoformat(), 'tax_rate': '0', 'notes': '',
            'introduction': 'Hello **there**',
        })
        estimate = Estimate.objects.get()
        assert response['HX-Redirect'] == reverse('estimate_detail', args=[estimate.pk])
        assert estimate.lead == lead and estimate.introduction == 'Hello **there**'
        detail = client.get(reverse('estimate_detail', args=[estimate.pk]))
        assert detail.status_code == 200 and b'name="introduction"' in detail.content

    def test_introduction_is_markdown_without_html(self, client):
        estimate = _estimate(sent=True, introduction='## Scope\n\n<script>alert(1)</script>')
        client.force_login(AdminUserFactory())
        page = client.get(reverse('estimate_print', args=[estimate.pk]))
        assert b'<h2>Scope</h2>' in page.content
        assert b'<script>alert(1)</script>' not in page.content


@pytest.mark.django_db
class TestOnlineLink:
    def test_works_once_sent_with_the_right_token(self, client):
        draft = _estimate()
        path = public.public_path(draft)
        assert client.get(path).status_code == 404  # still a draft
        estimate = mark_estimate_sent(draft)
        path = public.public_path(estimate)
        page = client.get(path)
        assert page.status_code == 200 and b'Accept estimate' in page.content
        assert client.get(path[:-3] + 'xx/').status_code == 404
        assert client.get(reverse('estimate_public_pdf', args=[estimate.pk, path.rstrip('/').split('/')[-1]]))[
            'Content-Type'] == 'application/pdf'

    def test_accept_needs_name_and_tick_and_records_them(self, client):
        Company.objects.update_or_create(pk=1, defaults={'email': 'team@agency.test'})
        estimate = _estimate(sent=True)
        path = public.public_path(estimate)
        refused = client.post(path, {'answer': 'accepted', 'name': 'Ana Pop'})
        assert refused.status_code == 400 and b'Tick the box' in refused.content
        response = client.post(path, {'answer': 'accepted', 'name': '  Ana   Pop ', 'agree': '1'},
                               REMOTE_ADDR='203.0.113.9')
        assert response.status_code == 302
        estimate.refresh_from_db()
        assert estimate.status == 'accepted'
        assert (estimate.answered_name, estimate.answered_ip) == ('Ana Pop', '203.0.113.9')
        note = ClientMessage.objects.get(kind=ClientMessage.NOTE)
        assert note.lead == estimate.lead and note.client is None
        assert 'Ana Pop accepted' in note.body
        assert mail.outbox[-1].to == ['team@agency.test']
        # Answered: the page shows it and takes no second answer.
        assert b'Accepted by Ana Pop' in client.get(path).content
        assert client.post(path, {'answer': 'declined'}).status_code == 400

    def test_decline(self, client):
        estimate = _estimate(sent=True)
        client.post(public.public_path(estimate), {'answer': 'declined', 'name': ''})
        estimate.refresh_from_db()
        assert estimate.status == 'declined'

    def test_new_link_revokes_the_old_one(self, client):
        estimate = _estimate(sent=True)
        old = public.public_path(estimate)
        client.force_login(AdminUserFactory())
        client.post(reverse('estimate_link_reset', args=[estimate.pk]))
        estimate.refresh_from_db()
        assert client.get(old).status_code == 404
        assert client.get(public.public_path(estimate)).status_code == 200

    def test_expired_shows_no_offer(self, client):
        estimate = _estimate(sent=True)
        Estimate.objects.filter(pk=estimate.pk).update(valid_until=timezone.localdate() - timedelta(days=1))
        page = client.get(public.public_path(estimate))
        assert b'has expired' in page.content and b'Accept estimate' not in page.content

    def test_email_carries_the_link_and_logs_on_the_lead(self, client):
        estimate = _estimate()
        client.force_login(AdminUserFactory())
        drawer = client.get(reverse('estimate_email', args=[estimate.pk]))
        assert b'accept it online: http' in drawer.content
        client.post(reverse('estimate_email', args=[estimate.pk]), {
            'to': 'ana@nova.test', 'subject': 'Estimate', 'message': 'See ' + public.public_url(
                drawer.wsgi_request, estimate),
        })
        logged = ClientMessage.objects.get(kind=ClientMessage.EMAIL)
        assert logged.lead == estimate.lead and logged.client is None


@pytest.mark.django_db
class TestConvert:
    def test_new_client_takes_everything_over(self):
        lead = _lead(phone='+40 700', address='Str. 1', tax_id='RO1', description='Big site')
        estimate = _estimate(lead, sent=True)
        ClientMessage.objects.create(lead=lead, kind=ClientMessage.EMAIL, subject='s', body='b')
        author = AdminUserFactory()
        LeadNote.objects.create(lead=lead, body='Called, wants May', author=author)

        client, project = services.convert(lead, user=author, project_name='Nova website',
                                           project_estimate=estimate)

        lead.refresh_from_db()
        estimate.refresh_from_db()
        assert lead.client == client and lead.status.kind == LeadStatus.WON and lead.converted_at
        assert (client.name, client.currency.code, client.tax_id, client.notes) == ('Nova Studio', 'EUR', 'RO1',
                                                                                   'Big site')
        contact = client.contacts.get()
        assert (contact.name, contact.email, contact.is_primary, contact.is_billing) == (
            'Ana Pop', 'ana@nova.test', True, True)
        assert estimate.client == client and estimate.lead == lead and estimate.project == project
        assert ClientMessage.objects.get().client == client
        assert Note.objects.get(client=client).description == 'Called, wants May'
        assert Project.objects.get().client == client
        with pytest.raises(ValidationError):
            services.convert(lead, user=author)

    def test_existing_client_in_another_currency_is_refused(self):
        lead = _lead()
        _estimate(lead)
        other = ClientFactory(currency=Currency.objects.get_or_create(code='GBP', defaults={'name': 'Pound', 'symbol': '£'})[0])
        with pytest.raises(ValidationError, match='in EUR'):
            services.convert(lead, user=AdminUserFactory(), client=other)
        same = ClientFactory(currency=_eur())
        client, _ = services.convert(lead, user=AdminUserFactory(), client=same)
        assert client == same and same.contacts.get().email == 'ana@nova.test'

    def test_convert_from_accepted_estimate_makes_the_invoice(self, client):
        estimate = _estimate(sent=True)
        Estimate.objects.filter(pk=estimate.pk).update(accepted_at=timezone.now())
        client.force_login(AdminUserFactory())
        drawer = client.get(reverse('lead_convert', args=[estimate.lead_id]) + f'?estimate={estimate.pk}')
        assert b'Convert and create invoice' in drawer.content
        response = client.post(reverse('lead_convert', args=[estimate.lead_id]),
                               {'target': 'new', 'estimate': estimate.pk, 'project_name': ''})
        estimate.refresh_from_db()
        assert estimate.invoice_id and response['HX-Redirect'] == reverse('invoice_detail', args=[estimate.invoice_id])
        assert estimate.invoice.client == estimate.client


@pytest.mark.django_db
class TestBoardAndPages:
    def test_won_only_by_converting(self, client):
        lead = _lead()
        client.force_login(AdminUserFactory())
        refused = client.post(reverse('lead_move', args=[lead.pk]), {'status': status('Won').pk})
        assert refused.status_code == 400
        assert client.post(reverse('lead_move', args=[lead.pk]), {'status': status('Lost').pk}).status_code == 204
        lead.refresh_from_db()
        assert lead.status.name == 'Lost'

    def test_pages_render_and_need_the_module(self, client):
        lead = _lead(value=Decimal('2500'), next_follow_up=timezone.localdate())
        _estimate(lead)
        client.force_login(AdminUserFactory())
        board = client.get(reverse('lead_list'))
        assert board.status_code == 200 and b'Nova Studio' in board.content and b'2500.00' in board.content
        assert b'Nova Studio' in client.get(reverse('lead_list') + '?view=list&follow_up=due').content
        detail = client.get(reverse('lead_detail', args=[lead.pk]))
        assert b'EST-0001' in detail.content and b'Convert to client' in detail.content
        client.force_login(_member(access_invoices=True))
        assert client.get(reverse('lead_list')).status_code == 403

    def test_create_and_note(self, client):
        ensure_statuses()
        user = AdminUserFactory()
        client.force_login(user)
        client.post(reverse('lead_create'), {'name': 'Orbit', 'status': status('New').pk})
        lead = Lead.objects.get()
        assert lead.created_by == user
        client.post(reverse('lead_note_create', args=[lead.pk]), {'body': 'First call'})
        assert lead.lead_notes.get().author == user

    def test_delete_guard(self, client):
        lead = _lead()
        _estimate(lead)
        client.force_login(AdminUserFactory())
        assert client.post(reverse('lead_delete', args=[lead.pk])).status_code == 400
        spam = _lead(name='Spam')
        client.post(reverse('lead_delete', args=[spam.pk]))
        assert not Lead.objects.filter(pk=spam.pk).exists()

    def test_dashboard_follow_ups(self, client):
        user = AdminUserFactory()
        _lead(name='Call me', assignee=user, next_follow_up=timezone.localdate() - timedelta(days=1))
        _lead(name='Later', assignee=user, next_follow_up=timezone.localdate() + timedelta(days=30))
        client.force_login(user)
        page = client.get(reverse('dashboard'))
        assert b'Follow-ups' in page.content and b'Call me' in page.content and b'Later' not in page.content

    def test_settings_keep_one_won_status(self, client):
        ensure_statuses()
        client.force_login(AdminUserFactory())
        assert client.get(reverse('settings_lead_statuses')).status_code == 200
        assert client.get(reverse('settings_lead_sources')).status_code == 200
        response = client.post(reverse('lead_status_delete', args=[status('Won').pk]))
        assert response.status_code == 400 and LeadStatus.objects.filter(kind=LeadStatus.WON).exists()

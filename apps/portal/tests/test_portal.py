"""The client portal: magic-link sign-in, what a contact sees, answering an estimate (release 0.36.0)."""
import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.clients.factories import ClientFactory
from apps.clients.models import ClientContact, ClientMessage
from apps.crm.models import Company, Currency
from apps.invoices.estimates import add_estimate_line, create_estimate, mark_estimate_sent
from apps.invoices.services import add_line, create_invoice
from apps.portal import access
from apps.portal.models import PortalLink
from apps.projects.factories import ProjectFactory
from apps.projects.models import Project

LINK = re.compile(r'https?://\S+/portal/sign-in/(\S+)/')


def _owner(**fields):
    owner = ClientFactory(**fields)
    owner.currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
    owner.save(update_fields=['currency'])
    return owner


def _contact(owner=None, email='ana@client.test', access_on=True):
    return ClientContact.objects.create(
        client=owner or _owner(), name='Ana', email=email, portal_access=access_on,
    )


def _invoice(owner, sent=True, cancelled=False):
    today = timezone.localdate()
    invoice = create_invoice(client=owner, issue_date=today, due_date=today + timedelta(days=14),
                             tax_rate=Decimal('0'))
    add_line(invoice, project=None, description='Work', quantity=Decimal('1'), unit_price=Decimal('100'))
    if sent:
        invoice.sent_at = timezone.now()
    if cancelled:
        invoice.cancelled_at = timezone.now()
    invoice.save()
    return invoice


def _estimate(owner, sent=True):
    today = timezone.localdate()
    estimate = create_estimate(client=owner, issue_date=today, valid_until=today + timedelta(days=30),
                               tax_rate=Decimal('0'))
    add_estimate_line(estimate, project=None, description='Website', quantity=Decimal('1'),
                      unit_price=Decimal('900'))
    return mark_estimate_sent(estimate) if sent else estimate


def _request_link(client, email):
    mail.outbox.clear()
    client.post(reverse('portal_login'), {'email': email})
    if not mail.outbox:
        return None
    return LINK.search(mail.outbox[-1].body).group(1)


def _sign_in(client, contact):
    token = access.create_link(contact)
    response = client.post(reverse('portal_link', args=[token]))
    assert response.status_code == 302
    return response


@pytest.mark.django_db
class TestSignIn:
    def test_a_contact_with_access_signs_in_with_the_emailed_link_once(self, client):
        contact = _contact()
        token = _request_link(client, 'ANA@client.test ')
        assert token

        # Opening the link only asks for a click, so a mail scanner does not spend it.
        page = client.get(reverse('portal_link', args=[token]))
        assert page.status_code == 200
        assert 'Continue to the portal' in page.content.decode()

        response = client.post(reverse('portal_link', args=[token]))
        assert response.status_code == 302
        assert response['Location'] == reverse('portal_home')
        assert client.get(reverse('portal_home')).status_code == 200
        contact.refresh_from_db()
        assert contact.portal_last_login_at is not None

        # Used once: a second click shows it no longer works.
        client.cookies.clear()
        assert client.post(reverse('portal_link', args=[token])).status_code == 410

    def test_an_email_without_access_gets_the_same_page_and_no_email(self, client):
        _contact(access_on=False)
        response = client.post(reverse('portal_login'), {'email': 'ana@client.test'})
        assert 'has access to the portal' in response.content.decode()
        assert _request_link(client, 'ana@client.test') is None
        assert _request_link(client, 'nobody@client.test') is None

    def test_an_archived_client_gets_no_link(self, client):
        owner = ClientFactory(archived_at=timezone.now())
        _contact(owner)
        assert _request_link(client, 'ana@client.test') is None

    def test_an_expired_link_does_not_sign_in(self, client):
        contact = _contact()
        token = access.create_link(contact)
        PortalLink.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        assert client.get(reverse('portal_link', args=[token])).status_code == 410
        assert client.post(reverse('portal_link', args=[token])).status_code == 410
        assert client.get(reverse('portal_home')).status_code == 302

    def test_links_per_hour_are_limited(self, client):
        contact = _contact()
        for _ in range(access.LINKS_PER_HOUR):
            assert access.create_link(contact)
        assert access.create_link(contact) is None

    def test_removing_access_or_changing_the_email_ends_the_session(self, client):
        contact = _contact()
        _sign_in(client, contact)
        assert client.get(reverse('portal_home')).status_code == 200

        contact.email = 'someone.else@client.test'
        contact.save()
        assert client.get(reverse('portal_home')).status_code == 302

        contact.email = 'ana@client.test'
        contact.portal_access = False
        contact.save()
        assert client.get(reverse('portal_home')).status_code == 302

    def test_sign_out(self, client):
        _sign_in(client, _contact())
        client.post(reverse('portal_logout'))
        assert client.get(reverse('portal_home')).status_code == 302

    def test_a_staff_login_is_not_a_portal_login(self, client):
        client.force_login(AdminUserFactory())
        response = client.get(reverse('portal_home'))
        assert response.status_code == 302
        assert response['Location'] == reverse('portal_login')

    def test_one_email_at_two_clients_gets_a_link_for_each(self, client):
        _contact(ClientFactory(name='Acme'))
        _contact(ClientFactory(name='Globex'))
        client.post(reverse('portal_login'), {'email': 'ana@client.test'})
        assert len(mail.outbox) == 1
        assert len(LINK.findall(mail.outbox[0].body)) == 2


@pytest.mark.django_db
class TestWhatTheContactSees:
    def test_only_their_clients_sent_documents_and_projects(self, client):
        contact = _contact()
        owner = contact.client
        other = _owner()
        sent, draft, cancelled = _invoice(owner), _invoice(owner, sent=False), _invoice(owner, cancelled=True)
        foreign = _invoice(other)
        estimate, draft_estimate = _estimate(owner), _estimate(owner, sent=False)
        ProjectFactory(client=owner, name='Website redesign')
        ProjectFactory(client=owner, name='Dropped idea', status=Project.CANCELLED)
        ProjectFactory(client=other, name='Someone else')

        _sign_in(client, contact)
        response = client.get(reverse('portal_home'))
        assert list(response.context['invoices']) == [sent]
        assert list(response.context['estimates']) == [estimate]
        assert list(response.context['waiting']) == [estimate]
        assert [p.name for p in response.context['projects']] == ['Website redesign']

        assert client.get(reverse('portal_invoice_pdf', args=[sent.pk])).status_code == 200
        for hidden in (draft, cancelled, foreign):
            assert client.get(reverse('portal_invoice_pdf', args=[hidden.pk])).status_code == 404
        assert client.get(reverse('portal_estimate', args=[draft_estimate.pk])).status_code == 404

    def test_emails_are_listed_but_internal_notes_are_not(self, client):
        contact = _contact()
        ClientMessage.objects.create(client=contact.client, kind=ClientMessage.EMAIL, subject='Invoice INV-1',
                                     body='Please find attached', recipients=contact.email)
        ClientMessage.objects.create(client=contact.client, kind=ClientMessage.EMAIL, subject='Failed one',
                                     body='x', error='SMTP down')
        ClientMessage.objects.create(client=contact.client, kind=ClientMessage.NOTE, subject='Internal',
                                     body='Slow payer')
        _sign_in(client, contact)
        page = client.get(reverse('portal_messages')).content.decode()
        assert 'Invoice INV-1' in page
        assert 'Failed one' not in page
        assert 'Slow payer' not in page


@pytest.mark.django_db
class TestEstimateAnswer:
    def test_accepting_records_it_logs_a_note_and_emails_the_company(self, client):
        company = Company.load()
        company.email = 'office@agency.test'
        company.save()
        contact = _contact()
        estimate = _estimate(contact.client)
        _sign_in(client, contact)
        mail.outbox.clear()

        response = client.post(reverse('portal_estimate', args=[estimate.pk]), {'answer': 'accepted'})
        assert response.status_code == 302
        estimate.refresh_from_db()
        assert estimate.status == 'accepted'
        note = ClientMessage.objects.get(estimate=estimate, kind=ClientMessage.NOTE)
        assert 'Ana (ana@client.test) accepted' in note.body
        assert mail.outbox[0].to == ['office@agency.test']

        # Answered: a second answer is refused.
        again = client.post(reverse('portal_estimate', args=[estimate.pk]), {'answer': 'declined'})
        assert 'can no longer be answered' in again.content.decode()
        estimate.refresh_from_db()
        assert estimate.status == 'accepted'

    def test_declining(self, client):
        contact = _contact()
        estimate = _estimate(contact.client)
        _sign_in(client, contact)
        client.post(reverse('portal_estimate', args=[estimate.pk]), {'answer': 'declined'})
        estimate.refresh_from_db()
        assert estimate.status == 'declined'

    def test_an_expired_estimate_cannot_be_accepted(self, client):
        contact = _contact()
        estimate = _estimate(contact.client)
        estimate.valid_until = timezone.localdate() - timedelta(days=1)
        estimate.save()
        _sign_in(client, contact)
        client.post(reverse('portal_estimate', args=[estimate.pk]), {'answer': 'accepted'})
        estimate.refresh_from_db()
        assert estimate.status == 'expired'


@pytest.mark.django_db
class TestStaffSide:
    def test_portal_access_needs_an_email(self, client):
        owner = ClientFactory()
        client.force_login(AdminUserFactory())
        response = client.post(reverse('client_contact_create', args=[owner.pk]),
                               {'name': 'Ana', 'portal_access': 'on'}, HTTP_HX_REQUEST='true')
        assert 'Add an email' in response.content.decode()
        assert not owner.contacts.exists()

    def test_invite_emails_the_contact_and_is_logged(self, client):
        contact = _contact()
        client.force_login(AdminUserFactory())
        mail.outbox.clear()
        response = client.post(reverse('client_contact_portal_invite', args=[contact.client.pk, contact.pk]),
                               HTTP_HX_REQUEST='true')
        assert response.status_code == 200
        assert mail.outbox[0].to == ['ana@client.test']
        assert '/portal/sign-in/?email=ana@client.test' in mail.outbox[0].body
        contact.refresh_from_db()
        assert contact.portal_invited_at is not None
        assert ClientMessage.objects.filter(client=contact.client, kind=ClientMessage.EMAIL).count() == 1

    def test_no_invite_without_portal_access(self, client):
        contact = _contact(access_on=False)
        client.force_login(AdminUserFactory())
        response = client.post(reverse('client_contact_portal_invite', args=[contact.client.pk, contact.pk]))
        assert response.status_code == 400
        assert not mail.outbox

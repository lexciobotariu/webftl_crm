"""Contacts per client: several people, one primary and one billing contact (release 0.24.0)."""
from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.clients.models import ClientContact
from apps.crm.models import Currency
from apps.invoices.services import create_invoice
from apps.search.services import search


def _viewer(**flags):
    fields = {'access_dashboard': True, 'access_clients': True, 'clients_view_all': True, 'clients_edit': False}
    fields.update(flags)
    return UserFactory(permission_preset=PermissionPreset.objects.create(name='Viewer', **fields))


def _add(client, owner, **fields):
    return client.post(reverse('client_contact_create', args=[owner.pk]), fields, HTTP_HX_REQUEST='true')


@pytest.mark.django_db
class TestManageContacts:
    def test_contacts_are_added_edited_and_removed(self, client):
        owner = ClientFactory()
        client.force_login(AdminUserFactory())

        drawer = client.get(reverse('client_contact_create', args=[owner.pk]), HTTP_HX_REQUEST='true')
        # The first contact starts as the primary one.
        assert 'name="is_primary" value="on" checked' in drawer.content.decode()

        response = _add(client, owner, name='Ana Pop', role='CEO', email='ana@example.com', phone='0722',
                        is_primary='on')
        assert 'profileChanged' in response['HX-Trigger']
        ana = owner.contacts.get()
        assert (ana.name, ana.role, ana.email, ana.is_primary, ana.is_billing) == (
            'Ana Pop', 'CEO', 'ana@example.com', True, False)

        client.post(reverse('client_contact_edit', args=[owner.pk, ana.pk]),
                    {'name': 'Ana Popescu', 'is_billing': 'on'}, HTTP_HX_REQUEST='true')
        ana.refresh_from_db()
        assert ana.name == 'Ana Popescu' and ana.is_billing and not ana.is_primary

        page = client.get(reverse('client_detail', args=[owner.pk])).content.decode()
        assert 'Ana Popescu' in page
        assert reverse('client_contact_delete', args=[owner.pk, ana.pk]) in page

        client.post(reverse('client_contact_delete', args=[owner.pk, ana.pk]))
        assert not owner.contacts.exists()

    def test_a_contact_needs_a_name_and_a_valid_email(self, client):
        owner = ClientFactory()
        client.force_login(AdminUserFactory())

        body = _add(client, owner, name='', email='not-an-email').content.decode()
        assert 'This field is required' in body
        assert 'Enter a valid email address' in body
        assert not owner.contacts.exists()

    def test_marking_a_new_primary_or_billing_contact_moves_the_mark(self, client):
        owner = ClientFactory()
        first = ClientContact.objects.create(client=owner, name='First', is_primary=True, is_billing=True)
        client.force_login(AdminUserFactory())

        _add(client, owner, name='Second', is_primary='on', is_billing='on')
        first.refresh_from_db()
        second = owner.contacts.get(name='Second')
        assert second.is_primary and second.is_billing
        assert not first.is_primary and not first.is_billing

    def test_the_database_allows_one_primary_contact_per_client(self):
        owner = ClientFactory()
        ClientContact.objects.create(client=owner, name='One', is_primary=True)
        ClientContact.objects.create(client=ClientFactory(), name='Elsewhere', is_primary=True)
        with pytest.raises(IntegrityError):
            ClientContact.objects.create(client=owner, name='Two', is_primary=True)

    def test_a_contact_of_another_client_is_not_found(self, client):
        owner = ClientFactory()
        stranger = ClientContact.objects.create(client=ClientFactory(), name='Other')
        client.force_login(AdminUserFactory())

        response = client.post(reverse('client_contact_delete', args=[owner.pk, stranger.pk]))
        assert response.status_code == 404
        assert ClientContact.objects.filter(pk=stranger.pk).exists()


@pytest.mark.django_db
class TestPermissions:
    def test_without_edit_rights_contacts_are_shown_but_not_changed(self, client):
        owner = ClientFactory()
        contact = ClientContact.objects.create(client=owner, name='Read Only')
        client.force_login(_viewer())

        page = client.get(reverse('client_detail', args=[owner.pk])).content.decode()
        assert 'Read Only' in page
        assert reverse('client_contact_create', args=[owner.pk]) not in page

        assert _add(client, owner, name='Sneaky').status_code == 403
        assert client.post(reverse('client_contact_delete', args=[owner.pk, contact.pk])).status_code == 403
        assert list(owner.contacts.values_list('name', flat=True)) == ['Read Only']

    def test_a_client_out_of_sight_is_not_found(self, client):
        owner = ClientFactory()
        client.force_login(_viewer(clients_view_all=False, clients_edit=True))
        assert _add(client, owner, name='Nope').status_code == 404


@pytest.mark.django_db
class TestBillingEmail:
    def test_the_billing_contact_is_used_when_there_is_no_billing_email(self):
        owner = ClientFactory(email='office@example.com', billing_email='')
        assert owner.bill_to_email == 'office@example.com'

        ClientContact.objects.create(client=owner, name='Accounts', email='accounts@example.com', is_billing=True)
        assert owner.bill_to_email == 'accounts@example.com'

        owner.currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
        owner.save(update_fields=['currency'])
        invoice = create_invoice(client=owner, issue_date=date(2026, 10, 1), due_date=date(2026, 10, 31),
                                 tax_rate=Decimal('0'))
        assert invoice.bill_to_email == 'accounts@example.com'

        owner.billing_email = 'billing@example.com'
        assert owner.bill_to_email == 'billing@example.com'


@pytest.mark.django_db
class TestSearch:
    def test_a_contact_name_or_email_finds_the_client(self):
        admin = AdminUserFactory()
        owner = ClientFactory(name='Acme Ltd')
        ClientContact.objects.create(client=owner, name='Ioana Zamfir', email='ioana@acme.test')
        ClientContact.objects.create(client=owner, name='Ioana Two', email='two@acme.test')

        assert [c.name for c in search(admin, 'Zamfir').clients] == ['Acme Ltd']
        # Two matching contacts still give one result.
        assert [c.name for c in search(admin, 'Ioana').clients] == ['Acme Ltd']
        assert [c.name for c in search(admin, 'two@acme').clients] == ['Acme Ltd']

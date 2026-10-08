"""Archiving clients, and a delete that can no longer take invoices with it."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.clients.models import Client
from apps.crm.models import Currency
from apps.invoices.models import Invoice
from apps.invoices.services import add_line, create_invoice, mark_sent, record_payment
from apps.projects.factories import ProjectFactory
from apps.projects.models import Project


def _user(name, **flags):
    fields = {
        'access_dashboard': True,
        'access_clients': True,
        'clients_view_all': True,
        'access_projects': True,
        'projects_create': True,
        'access_invoices': True,
        'invoices_create': True,
    }
    fields.update(flags)
    return UserFactory(permission_preset=PermissionPreset.objects.create(name=name, **fields))


def _paid_invoice(client):
    client.currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
    client.save(update_fields=['currency'])
    today = timezone.localdate()
    invoice = create_invoice(
        client=client, issue_date=today, due_date=today + timedelta(days=14), tax_rate=Decimal('0'),
    )
    add_line(invoice, project=None, description='Work', quantity=Decimal('1'), unit_price=Decimal('50'))
    mark_sent(invoice)
    record_payment(invoice, date=today, amount=Decimal('50'))
    return invoice


@pytest.mark.django_db
class TestArchive:
    def test_archive_hides_the_client_from_the_list_and_restore_brings_it_back(self, client):
        user = _user('Editor', clients_edit=True)
        active = ClientFactory(name='Active Co')
        gone = ClientFactory(name='Gone Co')
        client.force_login(user)

        assert client.post(reverse('client_archive', args=[gone.pk])).status_code == 302
        gone.refresh_from_db()
        assert gone.is_archived

        listing = client.get(reverse('client_list'))
        assert [c.name for c in listing.context['clients']] == ['Active Co']
        assert listing.context['archived_count'] == 1
        archived = client.get(reverse('client_list') + '?archived=1')
        assert [c.name for c in archived.context['clients']] == ['Gone Co']
        # The record itself still opens.
        assert client.get(reverse('client_detail', args=[gone.pk])).status_code == 200

        client.post(reverse('client_archive', args=[gone.pk]), {'restore': '1'})
        gone.refresh_from_db()
        assert not gone.is_archived
        assert active.pk in [c.pk for c in client.get(reverse('client_list')).context['clients']]

    def test_archive_needs_clients_edit(self, client):
        user = _user('Viewer')
        target = ClientFactory()
        client.force_login(user)
        assert client.post(reverse('client_archive', args=[target.pk])).status_code == 403
        target.refresh_from_db()
        assert not target.is_archived

    def test_archived_clients_are_not_offered_for_new_projects_or_invoices(self, client):
        user = _user('Creator')
        archived = ClientFactory(name='Old Co', archived_at=timezone.now())
        client.force_login(user)

        project_form = client.get(reverse('project_create'), HTTP_HX_REQUEST='true').context['form']
        assert archived not in project_form.fields['client'].queryset
        invoice_form = client.get(reverse('invoice_create')).context['form']
        assert archived not in invoice_form.fields['client'].queryset

        response = client.post(reverse('client_create_project', args=[archived.pk]), {'name': 'New'})
        assert response.status_code == 400
        assert not Project.objects.filter(name='New').exists()

    def test_dashboard_counts_active_clients(self, client):
        user = _user('Dash')
        ClientFactory()
        ClientFactory(archived_at=timezone.now())
        client.force_login(user)
        assert client.get(reverse('dashboard')).context['client_count'] == 1


@pytest.mark.django_db
class TestDelete:
    def test_a_client_with_invoices_cannot_be_deleted(self, client):
        admin = AdminUserFactory()
        target = ClientFactory()
        ProjectFactory(client=target)
        invoice = _paid_invoice(target)
        client.force_login(admin)

        detail = client.get(reverse('client_detail', args=[target.pk]))
        assert reverse('client_delete', args=[target.pk]) not in detail.content.decode()

        response = client.post(reverse('client_delete', args=[target.pk]))
        assert response.status_code == 400
        assert 'archive' in response.content.decode().lower()
        assert Client.objects.filter(pk=target.pk).exists()
        assert Invoice.objects.filter(pk=invoice.pk).exists()
        assert invoice.payments.count() == 1

    def test_a_client_without_invoices_can_still_be_deleted(self, client):
        admin = AdminUserFactory()
        target = ClientFactory()
        client.force_login(admin)
        assert client.post(reverse('client_delete', args=[target.pk])).status_code == 302
        assert not Client.objects.filter(pk=target.pk).exists()


@pytest.mark.django_db
class TestProfile:
    def test_old_free_text_notes_are_shown(self, client):
        admin = AdminUserFactory()
        target = ClientFactory(notes='Prefers calls on Fridays')
        client.force_login(admin)
        page = client.get(reverse('client_detail_profile', args=[target.pk])).content.decode()
        assert 'Prefers calls on Fridays' in page

    def test_delete_confirm_shows_the_name_as_written(self, client):
        admin = AdminUserFactory()
        target = ClientFactory(name="O'Brien")
        client.force_login(admin)
        page = client.get(reverse('client_detail', args=[target.pk])).content.decode()
        assert '\\u0027' not in page

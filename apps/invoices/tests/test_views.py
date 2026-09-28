from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.invoices.models import Invoice
from apps.invoices.services import add_line, create_invoice, mark_sent, record_payment
from apps.projects.factories import ProjectAccessFactory, ProjectFactory

_seq = 0


def _today():
    return timezone.localdate()


def _user(**flags):
    global _seq
    _seq += 1
    defaults = {
        'access_dashboard': True,
        'access_clients': True,
        'access_invoices': True,
        'invoices_view_all': False,
        'invoices_create': False,
        'invoices_edit': False,
        'access_salaries': False,
    }
    defaults.update(flags)
    preset = PermissionPreset.objects.create(name=f'Invoices {_seq}', **defaults)
    return UserFactory(permission_preset=preset)


def _ensure_currency(client):
    from apps.crm.models import Currency

    if client.currency_id:
        return client
    currency, _created = Currency.objects.get_or_create(
        code='USD',
        defaults={'name': 'US Dollar', 'symbol': '$'},
    )
    client.currency = currency
    client.save(update_fields=['currency'])
    return client


def _visible_client(user, name='Visible Co'):
    client = ClientFactory(
        name=name,
        email=f'{name.split()[0].lower()}@client.test',
        billing_name=f'{name} Billing',
        billing_email=f'{name.split()[0].lower()}@bill.test',
        address='9 Ledger Lane',
        tax_id='TAX-9',
    )
    project = ProjectFactory(client=client, name=f'{name} Project')
    ProjectAccessFactory(project=project, user=user)
    return _ensure_currency(client), project


def _invoice(client, *, tax_rate='0', due_in=14):
    today = _today()
    return create_invoice(
        client=_ensure_currency(client),
        issue_date=today,
        due_date=today + timedelta(days=due_in),
        tax_rate=Decimal(tax_rate),
    )


@pytest.mark.django_db
class TestVisibility:
    def test_view_own_is_limited_to_visible_clients_and_a_hidden_invoice_is_404(self, client):
        owner = _user()
        visible, _project = _visible_client(owner, 'Visible Co')
        hidden = ClientFactory(name='Hidden Co')
        own = _invoice(visible)
        other = _invoice(hidden)
        client.force_login(owner)

        listing = client.get(reverse('invoice_list'))
        assert listing.status_code == 200
        body = listing.content.decode()
        assert own.number_label in body
        assert other.number_label not in body
        assert client.get(reverse('invoice_detail', args=[own.pk])).status_code == 200
        assert client.get(reverse('invoice_detail', args=[other.pk])).status_code == 404

    def test_view_all_sees_the_rest(self, client):
        owner = _user(invoices_view_all=True)
        _visible, _project = _visible_client(owner, 'Visible Co')
        hidden = ClientFactory(name='Hidden Co')
        other = _invoice(hidden)
        client.force_login(owner)

        listing = client.get(reverse('invoice_list'))
        assert other.number_label in listing.content.decode()
        assert client.get(reverse('invoice_detail', args=[other.pk])).status_code == 200


@pytest.mark.django_db
class TestCreate:
    def test_create_requires_invoices_create(self, client):
        user = _user(invoices_create=False)
        visible, _project = _visible_client(user)
        client.force_login(user)
        response = client.post(reverse('invoice_create'), {
            'client': visible.pk,
            'issue_date': _today().isoformat(),
            'due_date': (_today() + timedelta(days=14)).isoformat(),
            'tax_rate': '0',
        })
        assert response.status_code == 403
        assert Invoice.objects.count() == 0

    def test_free_text_line_saves_and_a_foreign_project_is_rejected(self, client):
        user = _user(invoices_create=True, invoices_edit=True)
        visible, project = _visible_client(user)
        other = ProjectFactory(name='Someone else')
        client.force_login(user)
        created = client.post(reverse('invoice_create'), {
            'client': visible.pk,
            'issue_date': _today().isoformat(),
            'due_date': (_today() + timedelta(days=14)).isoformat(),
            'tax_rate': '0',
        })
        invoice = Invoice.objects.get()
        assert created['HX-Redirect'] == reverse('invoice_detail', args=[invoice.pk])

        foreign = client.post(reverse('invoice_line_create', args=[invoice.pk]), {
            'project': other.pk,
            'description': 'Should not save',
            'quantity': '1',
            'unit_price': '10',
        })
        assert foreign.status_code == 200
        assert invoice.lines.count() == 0
        assert 'valid choice' in foreign.content.decode().lower()

        saved = client.post(reverse('invoice_line_create', args=[invoice.pk]), {
            'project': '',
            'description': 'Discovery workshop',
            'quantity': '2',
            'unit_price': '50',
        })
        assert saved.status_code == 200
        line = invoice.lines.get()
        assert line.project_id is None
        assert line.description == 'Discovery workshop'
        assert line.amount == Decimal('100.00')

        project_line = client.post(reverse('invoice_line_create', args=[invoice.pk]), {
            'project': project.pk,
            'description': 'typed over',
            'quantity': '1',
            'unit_price': '25',
        })
        assert project_line.status_code == 200
        stored = invoice.lines.get(project=project)
        assert stored.description == project.name

    def test_bill_to_is_the_snapshot_from_create_time(self, client):
        user = _user(invoices_create=True)
        visible, _project = _visible_client(user, 'Snapshot Co')
        client.force_login(user)
        client.post(reverse('invoice_create'), {
            'client': visible.pk,
            'issue_date': _today().isoformat(),
            'due_date': (_today() + timedelta(days=30)).isoformat(),
            'tax_rate': '0',
        })
        invoice = Invoice.objects.get()
        visible.billing_name = 'Renamed Billing'
        visible.address = 'Elsewhere'
        visible.tax_id = 'NEW'
        visible.billing_email = 'new@bill.test'
        visible.save()

        detail = client.get(reverse('invoice_detail', args=[invoice.pk]))
        html = detail.content.decode()
        assert 'Snapshot Co Billing' in html
        assert 'snapshot@bill.test' in html
        assert '9 Ledger Lane' in html
        assert 'TAX-9' in html
        assert 'Renamed Billing' not in html
        assert 'Elsewhere' not in html
        assert 'NEW' not in html


@pytest.mark.django_db
class TestPaymentsAndSent:
    def test_a_payment_over_the_balance_is_refused(self, client):
        user = _user(invoices_edit=True)
        visible, _project = _visible_client(user)
        invoice = _invoice(visible, tax_rate='10')
        add_line(
            invoice,
            project=None,
            description='Work',
            quantity=Decimal('1'),
            unit_price=Decimal('10'),
        )
        client.force_login(user)
        response = client.post(reverse('invoice_payment_create', args=[invoice.pk]), {
            'date': _today().isoformat(),
            'amount': '11.01',
            'note': 'Too much',
        })
        assert response.status_code == 200
        assert 'cannot exceed the balance' in response.content.decode().lower()
        assert invoice.payments.count() == 0
        invoice.refresh_from_db()
        assert invoice.total == Decimal('11.00')
        assert invoice.balance == Decimal('11.00')

    def test_after_sent_a_line_edit_is_refused_and_a_payment_is_accepted(self, client):
        user = _user(invoices_edit=True)
        visible, _project = _visible_client(user)
        invoice = _invoice(visible, due_in=10)
        line = add_line(
            invoice,
            project=None,
            description='Design',
            quantity=Decimal('1'),
            unit_price=Decimal('80'),
        )
        mark_sent(invoice)
        client.force_login(user)

        edited = client.post(reverse('invoice_line_edit', args=[invoice.pk, line.pk]), {
            'description': 'Changed',
            'quantity': '4',
            'unit_price': '1',
        })
        assert edited.status_code == 403
        line.refresh_from_db()
        assert line.description == 'Design'
        assert line.unit_price == Decimal('80.00')

        added = client.post(reverse('invoice_line_create', args=[invoice.pk]), {
            'description': 'Extra',
            'quantity': '1',
            'unit_price': '5',
        })
        assert added.status_code == 403
        assert invoice.lines.count() == 1

        paid = client.post(reverse('invoice_payment_create', args=[invoice.pk]), {
            'date': _today().isoformat(),
            'amount': '30.00',
            'note': 'Part',
        })
        assert paid.status_code == 200
        assert invoice.payments.get().amount == Decimal('30.00')
        invoice.refresh_from_db()
        assert invoice.status == 'partial'


@pytest.mark.django_db
class TestDelete:
    def test_delete_is_admin_only_and_refused_once_a_payment_exists(self, client):
        member = _user(invoices_edit=True)
        visible, _project = _visible_client(member)
        invoice = _invoice(visible)
        add_line(
            invoice,
            project=None,
            description='Work',
            quantity=Decimal('1'),
            unit_price=Decimal('20'),
        )
        hidden = _invoice(ClientFactory(name='Hidden Co'))

        client.force_login(member)
        assert client.post(reverse('invoice_delete', args=[invoice.pk])).status_code == 403
        assert client.post(reverse('invoice_delete', args=[hidden.pk])).status_code == 404
        assert Invoice.objects.filter(pk=invoice.pk).exists()

        admin = AdminUserFactory()
        client.force_login(admin)
        record_payment(invoice, date=_today(), amount=Decimal('5'))
        refused = client.post(reverse('invoice_delete', args=[invoice.pk]))
        assert refused.status_code == 400
        assert Invoice.objects.filter(pk=invoice.pk).exists()

        unpaid = _invoice(visible)
        deleted = client.post(reverse('invoice_delete', args=[unpaid.pk]))
        assert deleted.status_code == 302
        assert not Invoice.objects.filter(pk=unpaid.pk).exists()


@pytest.mark.django_db
class TestScreens:
    def test_sidebar_finances_heading_follows_either_module(self, client):
        invoices_only = _user(access_invoices=True, access_salaries=False)
        client.force_login(invoices_only)
        html = client.get(reverse('dashboard')).content.decode()
        assert 'Finances' in html
        assert reverse('invoice_list') in html
        assert reverse('salary_list') not in html

        salaries_only = _user(access_invoices=False, access_salaries=True)
        client.force_login(salaries_only)
        html = client.get(reverse('dashboard')).content.decode()
        assert 'Finances' in html
        assert reverse('salary_list') in html
        assert reverse('invoice_list') not in html

        developer = UserFactory(permission_preset=PermissionPreset.objects.get(name='Developer'))
        client.force_login(developer)
        html = client.get(reverse('dashboard')).content.decode()
        assert 'Finances' not in html
        assert reverse('invoice_list') not in html

    def test_client_menu_lists_that_clients_invoices(self, client):
        user = _user(access_invoices=True)
        visible, _project = _visible_client(user, 'Menu Co')
        invoice = _invoice(visible)
        other = _invoice(ClientFactory(name='Other Co'))
        client.force_login(user)

        profile = client.get(reverse('client_detail', args=[visible.pk]))
        assert profile.status_code == 200
        assert reverse('client_detail_invoices', args=[visible.pk]) in profile.content.decode()

        tab = client.get(reverse('client_detail_invoices', args=[visible.pk]))
        body = tab.content.decode()
        assert invoice.number_label in body
        assert other.number_label not in body

        closed = _user(access_invoices=False, access_clients=True)
        ProjectAccessFactory(project=visible.projects.first(), user=closed)
        client.force_login(closed)
        profile = client.get(reverse('client_detail', args=[visible.pk]))
        assert reverse('client_detail_invoices', args=[visible.pk]) not in profile.content.decode()
        assert client.get(reverse('client_detail_invoices', args=[visible.pk])).status_code == 403

    def test_print_page_has_no_app_chrome(self, client):
        user = _user()
        visible, _project = _visible_client(user, 'Print Co')
        invoice = _invoice(visible, tax_rate='5')
        add_line(
            invoice,
            project=None,
            description='Printed line',
            quantity=Decimal('1'),
            unit_price=Decimal('20'),
        )
        client.force_login(user)
        response = client.get(reverse('invoice_print', args=[invoice.pk]))
        html = response.content.decode()
        assert response.status_code == 200
        assert invoice.number_label in html
        assert 'Printed line' in html
        assert 'Print Co Billing' in html
        assert '<aside' not in html
        assert 'layout-dashboard' not in html
        assert 'account_logout' not in html

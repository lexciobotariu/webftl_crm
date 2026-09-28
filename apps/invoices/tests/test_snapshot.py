from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.crm.models import Company, Currency
from apps.invoices.models import Invoice, InvoiceLocked
from apps.invoices.services import add_line, create_invoice, mark_sent
from apps.projects.factories import ProjectAccessFactory, ProjectFactory


def _user():
    preset = PermissionPreset.objects.create(
        name='Snapshot invoices',
        access_dashboard=True,
        access_clients=True,
        access_invoices=True,
        invoices_view_all=True,
        invoices_create=True,
        invoices_edit=True,
    )
    return UserFactory(permission_preset=preset)


@pytest.mark.django_db
class TestInvoiceSnapshot:
    def test_create_copies_company_and_currency_and_refuses_a_client_with_none(self, client):
        company = Company.load()
        company.legal_name = 'Harbor Studio LLC'
        company.address = '4 Quay Street'
        company.email = 'billing@harbor.test'
        company.phone = '555-0100'
        company.tax_id = 'VAT-1'
        company.save()
        euro = Currency.objects.create(code='EUR', name='Euro', symbol='€')
        billed = ClientFactory(name='Billed Co', currency=euro)
        bare = ClientFactory(name='Bare Co')
        user = _user()
        for owned in (billed, bare):
            project = ProjectFactory(client=owned)
            ProjectAccessFactory(project=project, user=user)
        client.force_login(user)
        today = timezone.localdate()

        created = client.post(reverse('invoice_create'), {
            'client': billed.pk,
            'issue_date': today.isoformat(),
            'due_date': (today + timedelta(days=14)).isoformat(),
            'tax_rate': '0',
        })
        invoice = Invoice.objects.get()
        assert created['HX-Redirect'] == reverse('invoice_detail', args=[invoice.pk])
        assert invoice.company_legal_name == 'Harbor Studio LLC'
        assert invoice.company_address == '4 Quay Street'
        assert invoice.company_email == 'billing@harbor.test'
        assert invoice.company_phone == '555-0100'
        assert invoice.company_tax_id == 'VAT-1'
        assert invoice.currency_code == 'EUR'
        assert invoice.currency_symbol == '€'

        company.legal_name = 'Renamed Studio'
        company.phone = '555-0199'
        company.save()
        euro.symbol = 'EUR'
        euro.save()
        invoice.refresh_from_db()
        assert invoice.company_legal_name == 'Harbor Studio LLC'
        assert invoice.company_phone == '555-0100'
        assert invoice.currency_symbol == '€'

        listing = client.get(reverse('invoice_list')).content.decode()
        assert '0.00 EUR' in listing

        refused = client.post(reverse('invoice_create'), {
            'client': bare.pk,
            'issue_date': today.isoformat(),
            'due_date': (today + timedelta(days=14)).isoformat(),
            'tax_rate': '0',
        })
        assert refused.status_code == 200
        assert 'Choose a currency' in refused.content.decode()
        assert Invoice.objects.count() == 1
        with pytest.raises(ValidationError):
            create_invoice(
                client=bare,
                issue_date=today,
                due_date=today + timedelta(days=14),
                tax_rate=Decimal('0'),
            )

        mark_sent(invoice)
        invoice.refresh_from_db()
        invoice.currency_code = 'USD'
        with pytest.raises(InvoiceLocked):
            invoice.save()
        invoice.refresh_from_db()
        assert invoice.currency_code == 'EUR'

    def test_print_shows_the_company_block_and_the_symbol(self, client):
        company = Company.load()
        company.legal_name = 'Harbor Studio LLC'
        company.address = '4 Quay Street'
        company.email = 'billing@harbor.test'
        company.phone = '555-0100'
        company.tax_id = 'VAT-1'
        company.save()
        euro = Currency.objects.create(code='EUR', name='Euro', symbol='€')
        billed = ClientFactory(
            name='Billed Co',
            billing_name='Billed Co',
            currency=euro,
        )
        user = _user()
        ProjectAccessFactory(project=ProjectFactory(client=billed), user=user)
        client.force_login(user)
        today = timezone.localdate()
        invoice = create_invoice(
            client=billed,
            issue_date=today,
            due_date=today + timedelta(days=14),
            tax_rate=Decimal('0'),
        )
        add_line(
            invoice,
            project=None,
            description='Design',
            quantity=Decimal('1'),
            unit_price=Decimal('10.00'),
        )

        printed = client.get(reverse('invoice_print', args=[invoice.pk]))
        html = printed.content.decode()
        company_block = html.split('>Company<', 1)[1].split('>Bill to<', 1)[0]
        assert 'Harbor Studio LLC' in company_block
        assert '4 Quay Street' in company_block
        assert 'billing@harbor.test' in company_block
        assert '555-0100' in company_block
        assert 'VAT-1' in company_block
        assert '€10.00' in html
        assert '€0.00' in html

        detail = client.get(reverse('invoice_detail', args=[invoice.pk])).content.decode()
        detail_company = detail.split('>Company<', 1)[1].split('>Bill to<', 1)[0]
        assert 'Harbor Studio LLC' in detail_company
        assert '€10.00' in detail

        legacy_client = ClientFactory(name='Legacy Co', billing_name='Legacy Co')
        legacy = Invoice.objects.create(
            client=legacy_client,
            number=9000,
            issue_date=today,
            due_date=today,
            tax_rate=Decimal('0.00'),
            bill_to_name='Legacy Co',
        )
        add_line(
            legacy,
            project=None,
            description='Old work',
            quantity=Decimal('1'),
            unit_price=Decimal('8.00'),
        )
        old = client.get(reverse('invoice_print', args=[legacy.pk])).content.decode()
        assert '>Company<' not in old
        assert '€' not in old
        assert '8.00' in old

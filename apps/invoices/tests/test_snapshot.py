import importlib
from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.crm.models import Company, Currency
from apps.invoices.models import Invoice, InvoiceLocked, format_money
from apps.invoices.services import add_line, create_invoice, mark_sent, record_payment
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
        euro = Currency.objects.get(code='EUR')
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
        assert invoice.symbol_before is False

        company.legal_name = 'Renamed Studio'
        company.phone = '555-0199'
        company.save()
        euro.symbol = 'EUR'
        euro.symbol_before = True
        euro.save()
        invoice.refresh_from_db()
        assert invoice.company_legal_name == 'Harbor Studio LLC'
        assert invoice.company_phone == '555-0100'
        assert invoice.currency_symbol == '€'
        assert invoice.symbol_before is False

        listing = client.get(reverse('invoice_list')).content.decode()
        assert '0.00 €' in listing
        assert '0.00 EUR' not in listing

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

        add_line(
            invoice,
            project=None,
            description='Work',
            quantity=Decimal('1'),
            unit_price=Decimal('10.00'),
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
        euro = Currency.objects.get(code='EUR')
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
        assert '10.00 €' in html
        assert '0.00 €' in html
        assert '€10.00' not in html

        detail = client.get(reverse('invoice_detail', args=[invoice.pk])).content.decode()
        detail_company = detail.split('>Company<', 1)[1].split('>Bill to<', 1)[0]
        assert 'Harbor Studio LLC' in detail_company
        assert '10.00 €' in detail
        assert '€10.00' not in detail

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
        old_detail = client.get(reverse('invoice_detail', args=[legacy.pk])).content.decode()
        assert '€' not in old_detail
        assert '8.00' in old_detail


def _place_existing_invoice_symbols():
    migration = importlib.import_module(
        'apps.invoices.migrations.0003_invoice_symbol_before'
    )
    migration.place_existing_invoice_symbols(django_apps, None)


@pytest.mark.django_db
class TestSymbolPlacement:
    def test_format_puts_eur_and_ron_after_the_amount_and_gbp_and_usd_before_it(self):
        assert format_money(Decimal('1'), symbol='€', symbol_before=False) == '1.00 €'
        assert format_money(Decimal('1'), symbol='lei', symbol_before=False) == '1.00 lei'
        assert format_money(Decimal('1'), symbol='£', symbol_before=True) == '£1.00'
        assert format_money(Decimal('1'), symbol='$', symbol_before=True) == '$1.00'
        assert format_money(Decimal('1'), symbol='', symbol_before=True) == '1.00'
        assert format_money(Decimal('1'), symbol='', symbol_before=False) == '1.00'

    def test_a_new_invoice_copies_placement_and_a_later_change_does_not_rewrite_it(self):
        pound = Currency.objects.get(code='GBP')
        leu = Currency.objects.get(code='RON')
        assert pound.symbol_before is True
        assert leu.symbol_before is False
        gbp_client = ClientFactory(name='Pound Co', currency=pound)
        ron_client = ClientFactory(name='Leu Co', currency=leu)
        today = timezone.localdate()

        gbp_invoice = create_invoice(
            client=gbp_client,
            issue_date=today,
            due_date=today + timedelta(days=14),
            tax_rate=Decimal('0'),
        )
        ron_invoice = create_invoice(
            client=ron_client,
            issue_date=today,
            due_date=today + timedelta(days=14),
            tax_rate=Decimal('0'),
        )
        assert gbp_invoice.symbol_before is True
        assert gbp_invoice.currency_symbol == '£'
        assert ron_invoice.symbol_before is False
        assert ron_invoice.currency_symbol == 'lei'

        pound.symbol_before = False
        pound.symbol = 'GBP'
        pound.save()
        leu.symbol_before = True
        leu.symbol = 'RON'
        leu.save()
        gbp_invoice.refresh_from_db()
        ron_invoice.refresh_from_db()
        assert gbp_invoice.symbol_before is True
        assert gbp_invoice.currency_symbol == '£'
        assert ron_invoice.symbol_before is False
        assert ron_invoice.currency_symbol == 'lei'

        later = create_invoice(
            client=gbp_client,
            issue_date=today,
            due_date=today + timedelta(days=14),
            tax_rate=Decimal('0'),
        )
        assert later.symbol_before is False
        assert later.currency_symbol == 'GBP'

    def test_list_detail_and_print_use_the_stored_placement(self, client):
        user = _user()
        client.force_login(user)
        today = timezone.localdate()
        made = {}
        for code in ('GBP', 'USD', 'EUR', 'RON'):
            currency = Currency.objects.get(code=code)
            billed = ClientFactory(name=f'{code} Client', currency=currency)
            ProjectAccessFactory(project=ProjectFactory(client=billed), user=user)
            invoice = create_invoice(
                client=billed,
                issue_date=today,
                due_date=today + timedelta(days=14),
                tax_rate=Decimal('10'),
            )
            add_line(
                invoice,
                project=None,
                description='Work',
                quantity=Decimal('1'),
                unit_price=Decimal('10.00'),
            )
            mark_sent(invoice)
            record_payment(invoice, date=today, amount=Decimal('4.00'))
            made[code] = (billed, invoice)

        expected = {
            'GBP': ('£10.00', '£1.00', '£11.00', '£4.00', '£7.00'),
            'USD': ('$10.00', '$1.00', '$11.00', '$4.00', '$7.00'),
            'EUR': ('10.00 €', '1.00 €', '11.00 €', '4.00 €', '7.00 €'),
            'RON': ('10.00 lei', '1.00 lei', '11.00 lei', '4.00 lei', '7.00 lei'),
        }
        swapped_total = {
            'GBP': '11.00 £',
            'USD': '11.00 $',
            'EUR': '€11.00',
            'RON': 'lei11.00',
        }
        listing = client.get(reverse('invoice_list')).content.decode()
        for code, figures in expected.items():
            _price, _tax, total, _paid, balance = figures
            assert total in listing
            assert balance in listing
            assert swapped_total[code] not in listing

        for code in ('GBP', 'RON'):
            billed, invoice = made[code]
            detail = client.get(reverse('invoice_detail', args=[invoice.pk])).content.decode()
            printed = client.get(reverse('invoice_print', args=[invoice.pk])).content.decode()
            on_client = client.get(
                reverse('client_detail_invoices', args=[billed.pk])
            ).content.decode()
            for figure in expected[code]:
                assert figure in detail
                assert figure in printed
            assert expected[code][2] in on_client
            assert swapped_total[code] not in detail
            assert swapped_total[code] not in printed
            assert swapped_total[code] not in on_client

    def test_existing_rows_place_eur_and_ron_after_and_leave_blank_rows_blank(self):
        owner = ClientFactory(name='Backfill Co')
        today = timezone.localdate()

        def make(number, code, symbol, symbol_before=True):
            return Invoice.objects.create(
                client=owner,
                number=number,
                issue_date=today,
                due_date=today,
                tax_rate=Decimal('0.00'),
                bill_to_name='Backfill Co',
                currency_code=code,
                currency_symbol=symbol,
                symbol_before=symbol_before,
            )

        blank = make(9101, '', '')
        euro = make(9102, 'EUR', '€')
        leu = make(9103, 'RON', 'lei')
        pound = make(9104, 'GBP', '£', symbol_before=False)
        dollar = make(9105, 'USD', '$')

        _place_existing_invoice_symbols()
        _place_existing_invoice_symbols()

        blank.refresh_from_db()
        assert blank.currency_code == ''
        assert blank.currency_symbol == ''
        euro.refresh_from_db()
        leu.refresh_from_db()
        pound.refresh_from_db()
        dollar.refresh_from_db()
        assert euro.symbol_before is False
        assert euro.currency_symbol == '€'
        assert leu.symbol_before is False
        assert leu.currency_symbol == 'lei'
        assert pound.symbol_before is True
        assert pound.currency_symbol == '£'
        assert dollar.symbol_before is True
        assert dollar.currency_symbol == '$'

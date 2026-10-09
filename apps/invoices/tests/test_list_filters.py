"""Paging, filters and totals on the invoice list (release 0.27.0)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.clients.factories import ClientFactory
from apps.crm.models import Currency
from apps.invoices.listing import period_range
from apps.invoices.models import Payment
from apps.invoices.services import add_line, create_invoice


def _client(name, code='EUR', symbol='€'):
    owner = ClientFactory(name=name)
    owner.currency, _ = Currency.objects.get_or_create(code=code, defaults={'name': code, 'symbol': symbol})
    owner.save(update_fields=['currency'])
    return owner


def _invoice(owner, amount, issued=None, due=None, sent=True, paid=None, cancelled=False):
    today = timezone.localdate()
    invoice = create_invoice(client=owner, issue_date=issued or today, due_date=due or today + timedelta(days=30),
                             tax_rate=Decimal('0'))
    add_line(invoice, project=None, description='Work', quantity=Decimal('1'), unit_price=Decimal(amount))
    if sent:
        invoice.sent_at = timezone.now()
    if cancelled:
        invoice.cancelled_at = timezone.now()
    invoice.save()
    if paid:
        Payment.objects.create(invoice=invoice, amount=Decimal(paid), date=today)
    return invoice


def _numbers(response):
    return [invoice.number_label for invoice in response.context['invoices']]


@pytest.mark.django_db
class TestFilters:
    @pytest.fixture
    def data(self):
        acme, globex = _client('Acme'), _client('Globex', 'USD', '$')
        today = timezone.localdate()
        return {
            'draft': _invoice(acme, '10', sent=False),
            'sent': _invoice(acme, '100'),
            'overdue': _invoice(globex, '200', due=today - timedelta(days=3)),
            'partial': _invoice(acme, '50', paid='20'),
            'paid': _invoice(globex, '30', paid='30'),
            'cancelled': _invoice(acme, '70', cancelled=True),
            'acme': acme,
            'globex': globex,
        }

    @pytest.mark.parametrize('status, expected', [
        ('draft', ['draft']),
        ('outstanding', ['sent', 'overdue', 'partial']),
        ('overdue', ['overdue']),
        ('paid', ['paid']),
        ('cancelled', ['cancelled']),
    ])
    def test_status(self, client, data, status, expected):
        client.force_login(AdminUserFactory())
        response = client.get(reverse('invoice_list'), {'status': status})
        assert set(_numbers(response)) == {data[name].number_label for name in expected}

    def test_client_and_totals_per_currency(self, client, data):
        client.force_login(AdminUserFactory())

        everything = client.get(reverse('invoice_list'))
        totals = everything.context['totals']
        # Drafts and cancelled invoices are not invoiced; each currency keeps its own total.
        assert totals.invoiced == ['150.00 €', '$230.00']
        assert totals.outstanding == ['130.00 €', '$200.00']
        assert totals.overdue == ['$200.00']

        acme = client.get(reverse('invoice_list'), {'client': data['acme'].pk})
        assert len(_numbers(acme)) == 4
        assert acme.context['totals'].overdue == []
        assert 'Globex' in acme.content.decode()  # still offered in the client picker

    def test_unknown_values_are_ignored(self, client, data):
        client.force_login(AdminUserFactory())
        response = client.get(reverse('invoice_list'), {'status': 'lost', 'period': 'someday', 'client': 'x'})
        assert response.status_code == 200
        assert len(_numbers(response)) == 6
        assert not response.context['filters'].active

    def test_no_match_says_so(self, client, data):
        client.force_login(AdminUserFactory())
        html = client.get(reverse('invoice_list'), {'period': 'last_year'}).content.decode()
        assert 'No invoices match these filters' in html


@pytest.mark.django_db
class TestPeriodAndPaging:
    def test_period_ranges(self):
        today = date(2026, 2, 14)
        assert period_range('this_month', today) == (date(2026, 2, 1), date(2026, 2, 28))
        assert period_range('last_month', today) == (date(2026, 1, 1), date(2026, 1, 31))
        assert period_range('this_quarter', today) == (date(2026, 1, 1), date(2026, 3, 31))
        assert period_range('this_quarter', date(2026, 11, 2)) == (date(2026, 10, 1), date(2026, 12, 31))
        assert period_range('last_year', today) == (date(2025, 1, 1), date(2025, 12, 31))
        assert period_range('', today) is None

    def test_period_filters_on_the_issue_date(self, client):
        owner = _client('Acme')
        today = timezone.localdate()
        recent = _invoice(owner, '10', issued=today)
        _invoice(owner, '10', issued=date(today.year - 1, 6, 1))
        client.force_login(AdminUserFactory())
        response = client.get(reverse('invoice_list'), {'period': 'this_year'})
        assert _numbers(response) == [recent.number_label]

    def test_paging_keeps_the_filters(self, client):
        owner = _client('Acme')
        for _ in range(27):
            _invoice(owner, '10')
        client.force_login(AdminUserFactory())

        first = client.get(reverse('invoice_list'), {'status': 'outstanding'})
        assert len(_numbers(first)) == 25
        assert first.context['total_count'] == 27
        assert 'status=outstanding' in first.content.decode()
        second = client.get(reverse('invoice_list'), {'status': 'outstanding', 'page': 2})
        assert len(_numbers(second)) == 2

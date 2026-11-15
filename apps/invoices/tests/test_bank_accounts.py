"""Bank accounts in Settings, chosen per invoice and printed under the lines (release 0.43.0)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.clients.factories import ClientFactory
from apps.crm.models import BankAccount, Currency, iban_is_valid
from apps.invoices.estimates import (
    add_estimate_line,
    convert_to_invoice,
    create_estimate,
    mark_estimate_sent,
    record_answer,
)
from apps.invoices.models import Invoice, InvoiceLocked
from apps.invoices.recurring import create_due_invoices, save_recurring
from apps.invoices.services import add_line, create_invoice, mark_sent, update_invoice

GB_IBAN = 'GB82WEST12345698765432'
DE_IBAN = 'DE89370400440532013000'


def _today():
    return timezone.localdate()


def _currency(code, symbol):
    currency, _ = Currency.objects.get_or_create(code=code, defaults={'name': code, 'symbol': symbol})
    return currency


def _client(code='GBP', symbol='£', name='Acme'):
    owner = ClientFactory(name=name, billing_email=f'{name.lower()}@bill.test')
    owner.currency = _currency(code, symbol)
    owner.save(update_fields=['currency'])
    return owner


def _uk(**kwargs):
    values = dict(
        kind=BankAccount.UK, label='Starling GBP', beneficiary_name='Web FTL Ltd',
        bank_name='Starling Bank', sort_code='608371', account_number='12345678',
        currency=_currency('GBP', '£'), is_default=True,
    )
    values.update(kwargs)
    return BankAccount.objects.create(**values)


def _intl(**kwargs):
    values = dict(
        kind=BankAccount.INTERNATIONAL, label='Wise EUR', beneficiary_name='Web FTL Ltd',
        bank_name='Wise', swift_bic='TRWIBEB1XXX', iban=DE_IBAN,
        currency=_currency('EUR', '€'), is_default=True,
    )
    values.update(kwargs)
    return BankAccount.objects.create(**values)


def _invoice(owner, **kwargs):
    return create_invoice(
        client=owner, issue_date=_today(), due_date=_today() + timedelta(days=14),
        tax_rate=Decimal('0'), **kwargs,
    )


def _header(invoice, **changes):
    data = {
        'client': invoice.client_id,
        'project': invoice.project_id or '',
        'issue_date': invoice.issue_date.isoformat(),
        'due_date': invoice.due_date.isoformat(),
        'tax_rate': str(invoice.tax_rate),
        'bank_account': invoice.bank_account_id or '',
    }
    data.update(changes)
    return data


class TestValidation:
    def test_iban_checksum(self):
        assert iban_is_valid(GB_IBAN)
        assert iban_is_valid(DE_IBAN)
        assert not iban_is_valid('GB82WEST12345698765433')
        assert not iban_is_valid('GB82')

    @pytest.mark.django_db
    def test_uk_needs_six_digit_sort_code_and_eight_digit_account(self):
        account = BankAccount(kind=BankAccount.UK, label='x', beneficiary_name='x', bank_name='x',
                              sort_code='12-34-5', account_number='1234567')
        with pytest.raises(ValidationError) as exc:
            account.full_clean()
        assert set(exc.value.message_dict) == {'sort_code', 'account_number'}

        account.sort_code, account.account_number = '12-34-56', '1234 5678'
        account.iban = GB_IBAN
        account.full_clean()
        assert account.sort_code == '123456'
        assert account.sort_code_display == '12-34-56'
        assert account.account_number == '12345678'
        assert account.iban == ''

    @pytest.mark.django_db
    def test_international_needs_swift_and_a_valid_iban(self):
        account = BankAccount(kind=BankAccount.INTERNATIONAL, label='x', beneficiary_name='x', bank_name='x',
                              swift_bic='TRWI', iban='DE89 3704 0044 0532 0130 01')
        with pytest.raises(ValidationError) as exc:
            account.full_clean()
        assert set(exc.value.message_dict) == {'swift_bic', 'iban'}

        account.swift_bic, account.iban = 'trwibeb1', 'de89 3704 0044 0532 0130 00'
        account.full_clean()
        assert account.iban == DE_IBAN
        assert account.iban_display == 'DE89 3704 0044 0532 0130 00'


@pytest.mark.django_db
class TestDefaults:
    def test_new_invoice_gets_the_default_for_its_currency_then_the_general_default(self):
        uk = _uk()
        eur = _intl()
        general = _intl(label='Revolut any', currency=None, iban=GB_IBAN, swift_bic='REVOGB21')

        assert _invoice(_client('GBP', '£')).bank_account == uk
        invoice = _invoice(_client('EUR', '€', name='Euro Co'))
        assert invoice.bank_account == eur
        assert invoice.bank_iban == DE_IBAN
        assert invoice.bank_kind == BankAccount.INTERNATIONAL
        assert _invoice(_client('USD', '$', name='Dollar Co')).bank_account == general

    def test_no_default_means_no_bank_details(self):
        _uk(is_default=False)
        invoice = _invoice(_client())
        assert invoice.bank_account is None
        assert not invoice.has_bank_details

    def test_one_default_per_currency(self):
        first = _uk()
        second = _uk(label='Monzo GBP')
        first.refresh_from_db()
        assert not first.is_default
        assert second.is_default

    def test_archived_account_is_not_a_default(self):
        account = _uk()
        account.archived_at = timezone.now()
        account.save()
        account.refresh_from_db()
        assert not account.is_default
        assert _invoice(_client()).bank_account is None

    def test_changing_client_to_another_currency_moves_to_its_default(self):
        uk = _uk()
        eur = _intl()
        invoice = _invoice(_client('GBP', '£'))
        assert invoice.bank_account == uk
        euro_client = _client('EUR', '€', name='Euro Co')
        invoice = update_invoice(invoice, client=euro_client, issue_date=invoice.issue_date,
                                 due_date=invoice.due_date, tax_rate=invoice.tax_rate)
        assert invoice.bank_account == eur
        assert invoice.bank_sort_code == ''


@pytest.mark.django_db
class TestSnapshot:
    def test_draft_follows_account_edits_and_sent_invoice_keeps_its_copy(self):
        account = _uk()
        owner = _client()
        draft = _invoice(owner)
        sent = _invoice(owner)
        add_line(sent, project=None, description='Design', quantity=Decimal('1'), unit_price=Decimal('100'))
        mark_sent(sent)

        account.account_number = '87654321'
        account.save()

        draft.refresh_from_db()
        sent.refresh_from_db()
        assert draft.bank_account_number == '87654321'
        assert sent.bank_account_number == '12345678'

    def test_sent_invoice_cannot_change_account(self):
        account = _uk()
        other = _uk(label='Monzo', is_default=False)
        invoice = _invoice(_client())
        add_line(invoice, project=None, description='Design', quantity=Decimal('1'), unit_price=Decimal('100'))
        mark_sent(invoice)
        invoice.refresh_from_db()
        assert invoice.bank_account == account
        invoice.bank_account = other
        with pytest.raises(InvoiceLocked):
            invoice.save()

    def test_account_on_an_invoice_cannot_be_deleted_only_archived(self, client):
        client.force_login(AdminUserFactory())
        account = _uk()
        _invoice(_client())
        response = client.post(reverse('bank_account_delete', args=[account.pk]))
        assert response.status_code == 400
        assert BankAccount.objects.filter(pk=account.pk).exists()

        client.post(reverse('bank_account_archive', args=[account.pk]))
        account.refresh_from_db()
        assert account.archived_at is not None

        unused = _uk(label='Unused', is_default=False)
        client.post(reverse('bank_account_delete', args=[unused.pk]))
        assert not BankAccount.objects.filter(pk=unused.pk).exists()


@pytest.mark.django_db
class TestEditorAndPrint:
    def test_header_chooses_or_clears_the_account(self, client):
        client.force_login(AdminUserFactory())
        _uk()
        other = _intl(label='Wise GBP IBAN', currency=None, is_default=False, iban=GB_IBAN)
        invoice = _invoice(_client())
        page = client.get(reverse('invoice_detail', args=[invoice.pk])).content.decode()
        assert 'id="doc-bank"' in page

        response = client.post(reverse('invoice_header', args=[invoice.pk]), _header(invoice, bank_account=other.pk))
        assert response.status_code == 200
        invoice.refresh_from_db()
        assert invoice.bank_account == other
        assert invoice.bank_iban == GB_IBAN

        client.post(reverse('invoice_header', args=[invoice.pk]), _header(invoice, bank_account=''))
        invoice.refresh_from_db()
        assert invoice.bank_account is None
        assert invoice.bank_iban == ''

    def test_archived_account_is_not_offered_on_a_new_draft(self, client):
        client.force_login(AdminUserFactory())
        archived = _uk(label='Old bank', is_default=False, archived_at=timezone.now())
        invoice = _invoice(_client())
        page = client.get(reverse('invoice_detail', args=[invoice.pk])).content.decode()
        assert 'Old bank' not in page
        response = client.post(reverse('invoice_header', args=[invoice.pk]), _header(invoice, bank_account=archived.pk))
        assert 'Old bank' not in response.content.decode()
        invoice.refresh_from_db()
        assert invoice.bank_account is None

    def test_print_shows_payment_details_with_reference(self, client):
        client.force_login(AdminUserFactory())
        _uk()
        invoice = _invoice(_client())
        html = client.get(reverse('invoice_print', args=[invoice.pk])).content.decode()
        assert 'Payment details' in html
        assert '60-83-71' in html
        assert '12345678' in html
        assert invoice.number_label in html

    def test_print_without_account_has_no_payment_block(self, client):
        client.force_login(AdminUserFactory())
        invoice = _invoice(_client())
        html = client.get(reverse('invoice_print', args=[invoice.pk])).content.decode()
        assert 'Payment details' not in html


@pytest.mark.django_db
class TestRecurringAndEstimates:
    def test_repeat_keeps_the_template_account_or_falls_back_to_default(self):
        default = _uk()
        chosen = _uk(label='Monzo', is_default=False)
        template = _invoice(_client(), bank_account=chosen)
        add_line(template, project=None, description='Retainer', quantity=Decimal('1'), unit_price=Decimal('100'))
        save_recurring(template, frequency='monthly', next_date=_today())
        create_due_invoices(today=_today())
        created = Invoice.objects.filter(from_recurring__template=template).get()
        assert created.bank_account == chosen

        chosen.archived_at = timezone.now()
        chosen.save()
        recurring = template.recurring
        recurring.refresh_from_db()
        recurring.next_date = _today()
        recurring.save(update_fields=['next_date'])
        create_due_invoices(today=_today())
        latest = Invoice.objects.filter(from_recurring__template=template).order_by('-number').first()
        assert latest.bank_account == default

    def test_converted_estimate_gets_the_currency_default(self):
        account = _uk()
        estimate = create_estimate(
            client=_client(), issue_date=_today(), valid_until=_today() + timedelta(days=30),
            tax_rate=Decimal('0'),
        )
        add_estimate_line(estimate, project=None, description='Site', quantity=Decimal('1'), unit_price=Decimal('500'))
        mark_estimate_sent(estimate)
        record_answer(estimate, 'accepted')
        invoice = convert_to_invoice(estimate)
        assert invoice.bank_account == account


@pytest.mark.django_db
class TestSettings:
    def test_admin_adds_and_edits_an_account(self, client):
        client.force_login(AdminUserFactory())
        gbp = _currency('GBP', '£')
        response = client.post(reverse('bank_account_add'), {
            'kind': 'uk', 'label': 'Starling', 'beneficiary_name': 'Web FTL Ltd',
            'bank_name': 'Starling Bank', 'sort_code': '60-83-71', 'account_number': '1234 5678',
            'currency': gbp.pk, 'is_default': 'on',
        })
        assert response.status_code == 302
        account = BankAccount.objects.get()
        assert account.sort_code == '608371'
        assert account.is_default

        page = client.get(reverse('settings')).content.decode()
        assert 'Starling' in page and '60-83-71' in page

        bad = client.post(reverse('bank_account_edit', args=[account.pk]), {
            'kind': 'international', 'label': 'Starling', 'beneficiary_name': 'Web FTL Ltd',
            'bank_name': 'Starling Bank', 'swift_bic': 'SRLGGB2L', 'iban': 'GB82WEST12345698765433',
        })
        assert bad.status_code == 400
        assert 'This IBAN is not valid' in bad.content.decode()

    def test_member_cannot_manage_accounts(self, client, user):
        client.force_login(user)
        assert client.get(reverse('bank_account_add')).status_code == 403

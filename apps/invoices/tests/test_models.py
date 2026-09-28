from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.clients.factories import ClientFactory
from apps.invoices.models import InvoiceHasPayments, InvoiceLocked
from apps.invoices.services import (
    add_line,
    create_invoice,
    mark_sent,
    record_payment,
    update_invoice,
)
from apps.projects.factories import ProjectFactory


def _today():
    return timezone.localdate()


def _invoice(client=None, *, tax_rate='0', due_in=14):
    today = _today()
    return create_invoice(
        client=client or ClientFactory(),
        issue_date=today,
        due_date=today + timedelta(days=due_in),
        tax_rate=Decimal(tax_rate),
    )


@pytest.mark.django_db
class TestTotals:
    def test_tax_and_balance(self):
        client = ClientFactory()
        project = ProjectFactory(client=client, name='Website rebuild')
        invoice = _invoice(client, tax_rate='10')
        add_line(
            invoice,
            project=project,
            description='ignored',
            quantity=Decimal('2'),
            unit_price=Decimal('100.00'),
        )
        add_line(
            invoice,
            project=None,
            description='Hosting',
            quantity=Decimal('1'),
            unit_price=Decimal('50.50'),
        )
        invoice.refresh_from_db()

        project_line = invoice.lines.get(project=project)
        assert project_line.description == 'Website rebuild'
        assert invoice.lines.get(project=None).description == 'Hosting'
        assert invoice.subtotal == Decimal('250.50')
        assert invoice.tax_amount == Decimal('25.05')
        assert invoice.total == Decimal('275.55')
        assert invoice.balance == Decimal('275.55')

        record_payment(invoice, date=_today(), amount=Decimal('100.00'), note='Wire')
        invoice.refresh_from_db()
        assert invoice.amount_paid == Decimal('100.00')
        assert invoice.balance == Decimal('175.55')

        with pytest.raises(ValidationError):
            record_payment(invoice, date=_today(), amount=Decimal('175.56'))
        assert invoice.payments.count() == 1

    def test_tax_rounds_half_up(self):
        invoice = _invoice(tax_rate='10')
        add_line(
            invoice,
            project=None,
            description='Odd cent',
            quantity=Decimal('1'),
            unit_price=Decimal('1.05'),
        )
        invoice.refresh_from_db()
        assert invoice.tax_amount == Decimal('0.11')
        assert invoice.total == Decimal('1.16')

    def test_project_from_another_client_is_rejected(self):
        invoice = _invoice()
        other = ProjectFactory()
        with pytest.raises(ValidationError):
            add_line(
                invoice,
                project=other,
                description='Nope',
                quantity=Decimal('1'),
                unit_price=Decimal('10'),
            )
        assert invoice.lines.count() == 0

    def test_bill_to_is_a_snapshot_from_create(self):
        client = ClientFactory(
            name='Contact Co',
            email='contact@client.test',
            billing_name='Acme Billing',
            billing_email='billing@acme.test',
            address='1 Ledger Lane',
            tax_id='TAX-1',
        )
        invoice = _invoice(client)
        client.billing_name = 'Renamed Billing'
        client.billing_email = 'new@acme.test'
        client.address = '2 Other Road'
        client.tax_id = 'TAX-2'
        client.name = 'New Contact'
        client.save()
        invoice.refresh_from_db()
        assert invoice.bill_to_name == 'Acme Billing'
        assert invoice.bill_to_email == 'billing@acme.test'
        assert invoice.bill_to_address == '1 Ledger Lane'
        assert invoice.bill_to_tax_id == 'TAX-1'

    def test_blank_billing_name_copies_the_contact_name(self):
        client = ClientFactory(name='Plain Co', billing_name='', email='plain@client.test')
        invoice = _invoice(client)
        assert invoice.bill_to_name == 'Plain Co'
        assert invoice.bill_to_email == 'plain@client.test'


@pytest.mark.django_db
class TestStatus:
    def _owed(self, invoice):
        add_line(
            invoice,
            project=None,
            description='Work',
            quantity=Decimal('1'),
            unit_price=Decimal('40'),
        )
        return invoice

    def test_draft_stays_draft_when_the_due_date_has_passed(self):
        invoice = self._owed(_invoice(due_in=-1))
        assert invoice.status == 'draft'

    def test_sent_partial_paid_and_overdue(self):
        today = _today()
        sent = self._owed(_invoice(due_in=7))
        mark_sent(sent)
        sent.refresh_from_db()
        assert sent.status == 'sent'

        partial = self._owed(_invoice(due_in=7))
        mark_sent(partial)
        record_payment(partial, date=today, amount=Decimal('10'))
        partial.refresh_from_db()
        assert partial.status == 'partial'

        paid = self._owed(_invoice(due_in=-3))
        mark_sent(paid)
        record_payment(paid, date=today, amount=Decimal('40'))
        paid.refresh_from_db()
        assert paid.balance == Decimal('0.00')
        assert paid.status == 'paid'

        overdue = self._owed(_invoice(due_in=-1))
        mark_sent(overdue)
        overdue.refresh_from_db()
        assert overdue.status == 'overdue'

        overdue_partial = self._owed(_invoice(due_in=-1))
        mark_sent(overdue_partial)
        record_payment(overdue_partial, date=today, amount=Decimal('10'))
        overdue_partial.refresh_from_db()
        assert overdue_partial.status == 'overdue'

    def test_draft_with_a_payment_is_still_a_draft(self):
        invoice = self._owed(_invoice(due_in=-1))
        record_payment(invoice, date=_today(), amount=Decimal('10'))
        invoice.refresh_from_db()
        assert invoice.status == 'draft'


@pytest.mark.django_db
class TestSentLock:
    def test_sent_invoice_refuses_line_edits_and_accepts_a_payment(self):
        invoice = _invoice(tax_rate='0')
        line = add_line(
            invoice,
            project=None,
            description='Design',
            quantity=Decimal('1'),
            unit_price=Decimal('80'),
        )
        mark_sent(invoice)
        line.unit_price = Decimal('1')
        with pytest.raises(InvoiceLocked):
            line.save()
        line.refresh_from_db()
        assert line.unit_price == Decimal('80.00')

        with pytest.raises(InvoiceLocked):
            add_line(
                invoice,
                project=None,
                description='Extra',
                quantity=Decimal('1'),
                unit_price=Decimal('5'),
            )

        record_payment(invoice, date=_today(), amount=Decimal('80'), note='Paid')
        invoice.refresh_from_db()
        assert invoice.payments.count() == 1
        assert invoice.status == 'paid'

    def test_changing_client_on_a_draft_refreshes_bill_to(self):
        first = ClientFactory(billing_name='First Billing', address='First St', tax_id='F-1')
        second = ClientFactory(billing_name='Second Billing', address='Second St', tax_id='S-2')
        invoice = _invoice(first)
        updated = update_invoice(
            invoice,
            client=second,
            issue_date=invoice.issue_date,
            due_date=invoice.due_date,
            tax_rate=invoice.tax_rate,
        )
        assert updated.client_id == second.pk
        assert updated.bill_to_name == 'Second Billing'
        assert updated.bill_to_address == 'Second St'
        assert updated.bill_to_tax_id == 'S-2'

    def test_delete_is_refused_once_a_payment_exists(self):
        invoice = _invoice()
        add_line(
            invoice,
            project=None,
            description='Work',
            quantity=Decimal('1'),
            unit_price=Decimal('15'),
        )
        record_payment(invoice, date=_today(), amount=Decimal('5'))
        with pytest.raises(InvoiceHasPayments):
            invoice.delete()
        invoice.refresh_from_db()
        assert invoice.pk

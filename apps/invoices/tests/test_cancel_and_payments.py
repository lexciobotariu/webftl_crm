"""Sending needs an amount, payments need a sent invoice, and a sent one can be cancelled."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.clients.factories import ClientFactory
from apps.crm.models import Currency
from apps.invoices.services import (
    add_line,
    cancel_invoice,
    create_invoice,
    mark_sent,
    record_payment,
)


def _invoice(amount=None):
    owner = ClientFactory()
    owner.currency, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'symbol': '€'})
    owner.save(update_fields=['currency'])
    today = timezone.localdate()
    invoice = create_invoice(
        client=owner, issue_date=today, due_date=today - timedelta(days=1), tax_rate=Decimal('0'),
    )
    if amount is not None:
        add_line(invoice, project=None, description='Work', quantity=Decimal('1'), unit_price=Decimal(amount))
    return invoice


@pytest.mark.django_db
class TestSend:
    def test_an_invoice_with_nothing_to_pay_is_not_sent(self, client):
        client.force_login(AdminUserFactory())
        empty = _invoice()
        response = client.post(reverse('invoice_mark_sent', args=[empty.pk]))
        assert response.status_code == 400
        empty.refresh_from_db()
        assert empty.status == 'draft'

        free = _invoice('0')
        with pytest.raises(ValidationError):
            mark_sent(free)


@pytest.mark.django_db
class TestPayments:
    def test_a_draft_takes_no_payment(self, client):
        client.force_login(AdminUserFactory())
        draft = _invoice('40')
        response = client.post(reverse('invoice_payment_create', args=[draft.pk]), {
            'date': timezone.localdate().isoformat(), 'amount': '10',
        })
        assert response.status_code == 400
        assert draft.payments.count() == 0

    def test_a_payment_can_be_removed(self, client):
        client.force_login(AdminUserFactory())
        invoice = _invoice('40')
        mark_sent(invoice)
        payment = record_payment(invoice, date=timezone.localdate(), amount=Decimal('40'))
        invoice.refresh_from_db()
        assert invoice.status == 'paid'

        response = client.post(reverse('invoice_payment_delete', args=[invoice.pk, payment.pk]))
        assert response.status_code == 200
        invoice.refresh_from_db()
        assert invoice.payments.count() == 0
        assert invoice.status == 'overdue'


@pytest.mark.django_db
class TestCancel:
    def test_a_sent_invoice_can_be_cancelled_and_owes_nothing(self, client):
        client.force_login(AdminUserFactory())
        invoice = _invoice('40')
        mark_sent(invoice)
        response = client.post(reverse('invoice_cancel', args=[invoice.pk]))
        assert response.status_code == 200
        invoice.refresh_from_db()
        assert invoice.status == 'cancelled'
        assert invoice.balance == Decimal('0.00')
        assert invoice.total == Decimal('40.00')
        with pytest.raises(ValidationError):
            record_payment(invoice, date=timezone.localdate(), amount=Decimal('1'))

    def test_a_draft_or_a_paid_invoice_is_not_cancelled(self):
        draft = _invoice('40')
        with pytest.raises(ValidationError):
            cancel_invoice(draft)

        paid = _invoice('40')
        mark_sent(paid)
        record_payment(paid, date=timezone.localdate(), amount=Decimal('10'))
        with pytest.raises(ValidationError):
            cancel_invoice(paid)
        paid.refresh_from_db()
        assert paid.cancelled_at is None

    def test_cancel_needs_invoices_edit(self, client):
        from apps.accounts.factories import UserFactory
        from apps.accounts.permissions import PermissionPreset

        preset = PermissionPreset.objects.create(
            name='Reader', access_invoices=True, invoices_view_all=True, invoices_edit=False,
        )
        client.force_login(UserFactory(permission_preset=preset))
        invoice = _invoice('40')
        mark_sent(invoice)
        assert client.post(reverse('invoice_cancel', args=[invoice.pk])).status_code == 403
        invoice.refresh_from_db()
        assert invoice.cancelled_at is None

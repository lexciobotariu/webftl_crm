from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Invoice, InvoiceLine, Payment, money


def bill_to_snapshot(client):
    """Copy the client's billing fields. Later client edits do not change it."""
    return {
        'bill_to_name': client.bill_to_name,
        'bill_to_email': client.bill_to_email or '',
        'bill_to_address': client.address or '',
        'bill_to_tax_id': client.tax_id or '',
    }


def _next_number():
    last = Invoice.objects.select_for_update().order_by('-number').first()
    return (last.number if last else 0) + 1


def create_invoice(*, client, issue_date, due_date, tax_rate):
    """Allocate the next number and store the bill-to snapshot."""
    snapshot = bill_to_snapshot(client)
    rate = money(tax_rate)
    for _ in range(5):
        try:
            with transaction.atomic():
                return Invoice.objects.create(
                    client=client,
                    number=_next_number(),
                    issue_date=issue_date,
                    due_date=due_date,
                    tax_rate=rate,
                    **snapshot,
                )
        except IntegrityError:
            continue
    raise IntegrityError('Could not allocate an invoice number.')


def update_invoice(invoice, *, client, issue_date, due_date, tax_rate):
    """Update a draft. Changing the client refreshes the bill-to snapshot."""
    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if client.pk != locked.client_id:
            foreign_lines = locked.lines.filter(project__isnull=False).exclude(
                project__client=client
            )
            if foreign_lines.exists():
                raise ValidationError(
                    'Remove project lines from the previous client before changing it.'
                )
            locked.client = client
            for key, value in bill_to_snapshot(client).items():
                setattr(locked, key, value)
        locked.issue_date = issue_date
        locked.due_date = due_date
        locked.tax_rate = money(tax_rate)
        locked.save()
        return locked


def add_line(invoice, *, project, description, quantity, unit_price):
    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        line = InvoiceLine(
            invoice=locked,
            project=project,
            description=(description or '').strip(),
            quantity=quantity,
            unit_price=unit_price,
        )
        line.save()
        return line


def update_line(line, *, project, description, quantity, unit_price):
    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=line.invoice_id)
        current = locked.lines.select_for_update().get(pk=line.pk)
        current.project = project
        current.description = (description or '').strip()
        current.quantity = quantity
        current.unit_price = unit_price
        current.save()
        return current


def mark_sent(invoice):
    """Set ``sent_at``. Sending twice leaves the original timestamp."""
    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if locked.sent_at is not None:
            return locked
        locked.sent_at = timezone.now()
        locked.save(update_fields=['sent_at', 'updated_at'])
        return locked


def record_payment(invoice, *, date, amount, note=''):
    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        payment = Payment(
            invoice=locked,
            date=date,
            amount=money(amount),
            note=(note or '').strip(),
        )
        payment.save()
        return payment

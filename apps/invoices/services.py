from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.crm.models import Company

from .models import Invoice, InvoiceLine, Payment, money


def bill_to_snapshot(client):
    """Copy the client's billing fields. Later client edits do not change it."""
    return {
        'bill_to_name': client.bill_to_name,
        'bill_to_email': client.bill_to_email or '',
        'bill_to_address': client.address or '',
        'bill_to_tax_id': client.tax_id or '',
    }


def company_snapshot():
    """Copy the company row. A later settings edit does not rewrite invoices."""
    company = Company.load()
    return {
        'company_legal_name': company.legal_name,
        'company_address': company.address,
        'company_email': company.email,
        'company_phone': company.phone,
        'company_tax_id': company.tax_id,
    }


def currency_snapshot(client):
    """Copy the client's currency, including which side the symbol sits on.

    A later settings change does not rewrite an invoice already stored.
    A client with no currency cannot be invoiced.
    """
    currency = client.currency
    if currency is None:
        raise ValidationError(
            'Choose a currency for this client before creating an invoice.'
        )
    return {
        'currency_code': currency.code,
        'currency_symbol': currency.symbol,
        'symbol_before': currency.symbol_before,
    }


def check_project(client, project):
    """A document's project must belong to its client."""
    if project is not None and project.client_id != client.pk:
        raise ValidationError({'project': 'Choose a project that belongs to this client.'})


def _next_number():
    last = Invoice.objects.select_for_update().order_by('-number').first()
    return (last.number if last else 0) + 1


def create_invoice(*, client, issue_date, due_date, tax_rate, project=None):
    """Allocate the next number and store bill-to, company, and currency."""
    check_project(client, project)
    snapshot = {
        **currency_snapshot(client),
        **company_snapshot(),
        **bill_to_snapshot(client),
    }
    rate = money(tax_rate)
    for _ in range(5):
        try:
            with transaction.atomic():
                return Invoice.objects.create(
                    client=client,
                    project=project,
                    number=_next_number(),
                    issue_date=issue_date,
                    due_date=due_date,
                    tax_rate=rate,
                    **snapshot,
                )
        except IntegrityError:
            continue
    raise IntegrityError('Could not allocate an invoice number.')


def update_invoice(invoice, *, client, issue_date, due_date, tax_rate, project=None):
    """Update a draft. Changing the client refreshes bill-to and currency."""
    check_project(client, project)
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
            for key, value in currency_snapshot(client).items():
                setattr(locked, key, value)
        locked.project = project
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
    """Set ``sent_at``. Sending twice leaves the original timestamp.

    An invoice with nothing to pay is refused: sent with a zero total it would
    read as paid the moment it went out.
    """
    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if locked.sent_at is not None:
            return locked
        if locked.total <= 0:
            raise ValidationError('Add a line with an amount before sending this invoice.')
        locked.sent_at = timezone.now()
        locked.save(update_fields=['sent_at', 'updated_at'])
        return locked


def record_payment(invoice, *, date, amount, note=''):
    """Record money received. A draft is not owed yet and a cancelled invoice not at all."""
    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if locked.sent_at is None:
            raise ValidationError('Mark the invoice sent before recording a payment.')
        if locked.cancelled_at is not None:
            raise ValidationError('This invoice has been cancelled.')
        payment = Payment(
            invoice=locked,
            date=date,
            amount=money(amount),
            note=(note or '').strip(),
        )
        payment.save()
        return payment


def cancel_invoice(invoice):
    """Cancel a sent invoice. It keeps its number and lines and owes nothing.

    A draft is deleted rather than cancelled. An invoice with payments is
    refused: remove the payments first, so money is never silently written off.
    Cancelling cannot be undone.
    """
    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if locked.cancelled_at is not None:
            return locked
        if locked.sent_at is None:
            raise ValidationError('A draft is deleted, not cancelled.')
        if locked.payments.exists():
            raise ValidationError('Remove the payments before cancelling this invoice.')
        locked.cancelled_at = timezone.now()
        locked.save(update_fields=['cancelled_at', 'updated_at'])
        return locked


def delete_payment(payment):
    """Remove a payment recorded by mistake; the invoice owes that amount again."""
    with transaction.atomic():
        Invoice.objects.select_for_update().get(pk=payment.invoice_id)
        payment.delete()

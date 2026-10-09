"""Emailing an invoice, or a reminder about one, to the client.

The email carries a short summary and the invoice as a PDF. Replies go to the
company email from Settings. Every attempt, sent or failed, is logged on the
client's Messages tab and on the invoice.
"""
import logging

from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import formats

from apps.clients.models import ClientMessage
from apps.crm.models import Company

from .models import format_money
from .pdf import invoice_pdf, invoice_pdf_filename
from .services import mark_sent

logger = logging.getLogger(__name__)

INVOICE = 'invoice'
REMINDER = 'reminder'
KINDS = (INVOICE, REMINDER)
# A reminder is for an invoice that went out and is still owed.
REMINDER_STATUSES = {'sent', 'partial', 'overdue'}


def can_email(invoice, kind):
    if kind == REMINDER:
        return invoice.status in REMINDER_STATUSES
    return not invoice.is_cancelled


def default_recipient(invoice):
    return invoice.bill_to_email or invoice.client.bill_to_email or ''


def _money(invoice, amount):
    return format_money(amount, invoice.currency_symbol, invoice.symbol_before)


def default_subject(invoice, kind):
    sender = invoice.company_legal_name or Company.load().legal_name
    suffix = f' from {sender}' if sender else ''
    if kind == REMINDER:
        return f'Reminder: invoice {invoice.number_label}{suffix}'
    return f'Invoice {invoice.number_label}{suffix}'


def default_message(invoice, kind):
    due = formats.date_format(invoice.due_date, 'j F Y')
    greeting = f'Hello {invoice.bill_to_name},' if invoice.bill_to_name else 'Hello,'
    if kind == REMINDER:
        if invoice.status == 'overdue':
            opening = f'This is a reminder that invoice {invoice.number_label} was due on {due} and is still open.'
        else:
            opening = f'This is a reminder that invoice {invoice.number_label} is due on {due}.'
    else:
        opening = f'Please find attached invoice {invoice.number_label}.'
    lines = [
        greeting,
        '',
        opening,
        '',
        f'Invoice: {invoice.number_label}',
        f'Total: {_money(invoice, invoice.total)}',
    ]
    if invoice.amount_paid > 0:
        lines.append(f'Still to pay: {_money(invoice, invoice.balance)}')
    lines += [f'Due date: {due}', '', 'Thank you,']
    sender = invoice.company_legal_name or Company.load().legal_name
    if sender:
        lines.append(sender)
    return '\n'.join(lines)


def send_invoice_email(invoice, *, kind, to, subject, message, author=None):
    """Send the email and log it. Returns the log entry; its ``error`` is set when sending failed.

    Emailing a draft marks it sent, in the same transaction as the send, so a
    failed send leaves it a draft. That refusal (``ValidationError``, for an
    invoice with nothing to pay) is raised before anything is sent or logged.
    """
    error = ''
    try:
        with transaction.atomic():
            if kind == INVOICE and invoice.is_draft:
                invoice = mark_sent(invoice)
            email = EmailMessage(subject=subject, body=message, to=list(to))
            reply_to = Company.load().email
            if reply_to:
                email.reply_to = [reply_to]
            email.attach(invoice_pdf_filename(invoice), invoice_pdf(invoice), 'application/pdf')
            email.send()
    except ValidationError:
        raise
    except Exception as exc:
        logger.exception('Emailing invoice %s failed', invoice.pk)
        error = str(exc) or exc.__class__.__name__
        invoice.refresh_from_db()

    return ClientMessage.objects.create(
        client=invoice.client,
        invoice=invoice,
        kind=ClientMessage.EMAIL,
        subject=subject,
        body=message,
        recipients=', '.join(to),
        error=error,
        author=author,
    )

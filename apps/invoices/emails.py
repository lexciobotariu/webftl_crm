"""Emailing an invoice, a reminder about one, or an estimate to the client.

The email carries a short summary and the document as a PDF. Replies go to the
company email from Settings. Every attempt, sent or failed, is logged on the
client's Messages tab and on the invoice or estimate.
"""
import logging

from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import formats

from apps.clients.models import ClientMessage
from apps.crm.models import Company

from .models import format_money
from .pdf import document_pdf, invoice_pdf_filename
from .services import mark_sent

logger = logging.getLogger(__name__)

INVOICE = 'invoice'
REMINDER = 'reminder'
ESTIMATE = 'estimate'
KINDS = (INVOICE, REMINDER)
# A reminder is for an invoice that went out and is still owed.
REMINDER_STATUSES = {'sent', 'partial', 'overdue'}


def can_email(invoice, kind):
    if kind == REMINDER:
        return invoice.status in REMINDER_STATUSES
    if kind == ESTIMATE:
        return invoice.status in {'draft', 'sent', 'expired'}
    return not invoice.is_cancelled


def default_recipient(invoice):
    return invoice.bill_to_email or invoice.client.bill_to_email or ''


def _money(invoice, amount):
    return format_money(amount, invoice.currency_symbol, invoice.symbol_before)


def _sender(document):
    return document.company_legal_name or Company.load().legal_name


def default_subject(invoice, kind):
    sender = _sender(invoice)
    suffix = f' from {sender}' if sender else ''
    if kind == ESTIMATE:
        return f'Estimate {invoice.number_label}{suffix}'
    if kind == REMINDER:
        return f'Reminder: invoice {invoice.number_label}{suffix}'
    return f'Invoice {invoice.number_label}{suffix}'


def default_message(invoice, kind):
    greeting = f'Hello {invoice.bill_to_name},' if invoice.bill_to_name else 'Hello,'
    if kind == ESTIMATE:
        valid = formats.date_format(invoice.valid_until, 'j F Y')
        lines = [
            greeting,
            '',
            f'Please find attached estimate {invoice.number_label}.',
            '',
            f'Estimate: {invoice.number_label}',
            f'Total: {_money(invoice, invoice.total)}',
            f'Valid until: {valid}',
            '',
            'Let us know if you would like to go ahead.',
            '',
            'Thank you,',
        ]
    else:
        due = formats.date_format(invoice.due_date, 'j F Y')
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
    sender = _sender(invoice)
    if sender:
        lines.append(sender)
    return '\n'.join(lines)


def send_invoice_email(invoice, *, kind, to, subject, message, author=None):
    """Send the email and log it. Returns the log entry; its ``error`` is set when sending failed.

    ``invoice`` is an estimate when ``kind`` is ``estimate``. Emailing a draft
    marks it sent, in the same transaction as the send, so a failed send leaves
    it a draft. That refusal (``ValidationError``, for one with nothing to pay)
    is raised before anything is sent or logged.
    """
    from .estimates import mark_estimate_sent

    error = ''
    try:
        with transaction.atomic():
            if invoice.is_draft and kind == ESTIMATE:
                invoice = mark_estimate_sent(invoice)
            elif invoice.is_draft and kind == INVOICE:
                invoice = mark_sent(invoice)
            email = EmailMessage(subject=subject, body=message, to=list(to))
            reply_to = Company.load().email
            if reply_to:
                email.reply_to = [reply_to]
            email.attach(invoice_pdf_filename(invoice), document_pdf(invoice), 'application/pdf')
            email.send()
    except ValidationError:
        raise
    except Exception as exc:
        logger.exception('Emailing %s failed', invoice)
        error = str(exc) or exc.__class__.__name__
        invoice.refresh_from_db()

    link = {'estimate': invoice} if kind == ESTIMATE else {'invoice': invoice}
    return ClientMessage.objects.create(
        client=invoice.client,
        kind=ClientMessage.EMAIL,
        subject=subject,
        body=message,
        recipients=', '.join(to),
        error=error,
        author=author,
        **link,
    )

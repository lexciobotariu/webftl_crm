"""Recurring invoices: a template invoice and a schedule that turns it into new drafts.

``create_due_invoices`` runs from the daily ``create_recurring_invoices``
command. It is safe to run more than once a day: each schedule moves to its
next date in the same transaction that creates the draft, so a date is never
invoiced twice. A missed day is caught up on the next run.
"""
import logging
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import RecurringInvoice
from .services import add_line, create_invoice

logger = logging.getLogger(__name__)

# A schedule that fell far behind still stops after this many drafts in one run.
MAX_CATCH_UP = 24


def save_recurring(invoice, *, frequency, next_date, end_date=None, user=None, today=None):
    """Start repeating ``invoice``, or change its schedule. ``next_date`` is the next draft's issue date."""
    today = today or timezone.localdate()
    if next_date < today:
        raise ValidationError({'next_date': 'Pick today or a later date.'})
    if end_date and end_date < next_date:
        raise ValidationError({'end_date': 'The end date cannot be before the next draft.'})
    recurring, _created = RecurringInvoice.objects.update_or_create(
        template=invoice,
        defaults={
            'frequency': frequency,
            'start_date': next_date,
            'next_date': next_date,
            'end_date': end_date,
        },
        create_defaults={
            'frequency': frequency,
            'start_date': next_date,
            'next_date': next_date,
            'end_date': end_date,
            'created_by': user,
        },
    )
    return recurring


def suggested_next_date(invoice, frequency=RecurringInvoice.MONTHLY, today=None):
    """One period after the template's issue date, moved forward past today if needed."""
    today = today or timezone.localdate()
    schedule = RecurringInvoice(frequency=frequency, start_date=invoice.issue_date)
    day = schedule.date_after(invoice.issue_date)
    while day < today:
        day = schedule.date_after(day)
    return day


def _create_one(recurring):
    template = recurring.template
    issue_date = recurring.next_date
    payment_days = max((template.due_date - template.issue_date).days, 0)
    invoice = create_invoice(
        client=template.client,
        issue_date=issue_date,
        due_date=issue_date + timedelta(days=payment_days),
        tax_rate=template.tax_rate,
        project=template.project,
    )
    invoice.from_recurring = recurring
    invoice.save(update_fields=['from_recurring', 'updated_at'])
    for line in template.lines.all():
        add_line(
            invoice,
            project=line.project,
            description=line.description,
            details=line.details,
            quantity=line.quantity,
            unit_price=line.unit_price,
        )
    return invoice


def create_due_invoices(today=None):
    """Create every draft that is due by ``today``. Returns the new invoices.

    A client that has been archived gets no new drafts; its dates still move on.
    A schedule that cannot be invoiced (a client with no currency) is logged and
    left on its date, so it is tried again on the next run.
    """
    today = today or timezone.localdate()
    created = []
    due = RecurringInvoice.objects.filter(next_date__lte=today).values_list('pk', flat=True)
    for pk in due:
        for _ in range(MAX_CATCH_UP):
            try:
                with transaction.atomic():
                    recurring = (
                        RecurringInvoice.objects.select_for_update()
                        .select_related('template__client').get(pk=pk)
                    )
                    if recurring.next_date > today or recurring.finished:
                        break
                    if recurring.template.client.archived_at is None:
                        created.append(_create_one(recurring))
                    recurring.next_date = recurring.date_after(recurring.next_date)
                    recurring.save(update_fields=['next_date', 'updated_at'])
            except RecurringInvoice.DoesNotExist:
                break
            except ValidationError:
                logger.exception('Recurring invoice %s could not create its draft', pk)
                break
    return created

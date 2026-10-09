"""Estimates: create, change while a draft, send, record the client's answer, turn into an invoice."""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Estimate, EstimateLine, money
from .services import (
    add_line,
    bill_to_snapshot,
    check_project,
    company_snapshot,
    create_invoice,
    currency_snapshot,
)

# Days a new invoice made from an estimate gets to be paid.
INVOICE_PAYMENT_DAYS = 30


class EstimateLocked(Exception):
    """Lines, tax, dates and client stay as they were once the estimate is sent."""


def _next_number():
    last = Estimate.objects.select_for_update().order_by('-number').first()
    return (last.number if last else 0) + 1


def _check_dates(issue_date, valid_until):
    if valid_until < issue_date:
        raise ValidationError({'valid_until': 'Valid until cannot be before the issue date.'})


def create_estimate(*, client, issue_date, valid_until, tax_rate, notes='', project=None):
    _check_dates(issue_date, valid_until)
    check_project(client, project)
    snapshot = {**currency_snapshot(client), **company_snapshot(), **bill_to_snapshot(client)}
    for _ in range(5):
        try:
            with transaction.atomic():
                return Estimate.objects.create(
                    client=client,
                    project=project,
                    number=_next_number(),
                    issue_date=issue_date,
                    valid_until=valid_until,
                    tax_rate=money(tax_rate),
                    notes=(notes or '').strip(),
                    **snapshot,
                )
        except IntegrityError:
            continue
    raise IntegrityError('Could not allocate an estimate number.')


def _locked_draft(estimate):
    locked = Estimate.objects.select_for_update().get(pk=estimate.pk)
    if locked.sent_at is not None:
        raise EstimateLocked('This estimate has been sent.')
    return locked


def update_estimate(estimate, *, client, issue_date, valid_until, tax_rate, notes='', project=None):
    """Change a draft. A new client refreshes bill-to and currency."""
    _check_dates(issue_date, valid_until)
    check_project(client, project)
    with transaction.atomic():
        locked = _locked_draft(estimate)
        if client.pk != locked.client_id:
            if locked.lines.filter(project__isnull=False).exclude(project__client=client).exists():
                raise ValidationError('Remove project lines from the previous client before changing it.')
            locked.client = client
            for key, value in {**bill_to_snapshot(client), **currency_snapshot(client)}.items():
                setattr(locked, key, value)
        locked.project = project
        locked.issue_date = issue_date
        locked.valid_until = valid_until
        locked.tax_rate = money(tax_rate)
        locked.notes = (notes or '').strip()
        locked.save()
        return locked


def _line_description(estimate, project, description):
    description = (description or '').strip()
    if project is not None:
        if project.client_id != estimate.client_id:
            raise ValidationError({'project': 'Choose a project that belongs to this client.'})
        return description or project.name
    if not description:
        raise ValidationError({'description': 'Enter a description for a free-text line.'})
    return description


def add_estimate_line(estimate, *, project, description, quantity, unit_price, details=''):
    with transaction.atomic():
        locked = _locked_draft(estimate)
        return EstimateLine.objects.create(
            estimate=locked,
            project=project,
            description=_line_description(locked, project, description),
            details=(details or '').strip(),
            quantity=quantity,
            unit_price=unit_price,
        )


def update_estimate_line(line, *, project, description, quantity, unit_price, details=''):
    with transaction.atomic():
        locked = _locked_draft(line.estimate)
        current = locked.lines.select_for_update().get(pk=line.pk)
        current.project = project
        current.description = _line_description(locked, project, description)
        current.details = (details or '').strip()
        current.quantity = quantity
        current.unit_price = unit_price
        current.save()
        return current


def delete_estimate_line(line):
    with transaction.atomic():
        _locked_draft(line.estimate)
        line.delete()


def mark_estimate_sent(estimate):
    """Set ``sent_at``. An estimate with nothing on it is refused."""
    with transaction.atomic():
        locked = Estimate.objects.select_for_update().get(pk=estimate.pk)
        if locked.sent_at is not None:
            return locked
        if locked.total <= 0:
            raise ValidationError('Add a line with an amount before sending this estimate.')
        locked.sent_at = timezone.now()
        locked.save(update_fields=['sent_at', 'updated_at'])
        return locked


def record_answer(estimate, answer):
    """``accepted``, ``declined``, or ``open`` to clear a mistaken answer. Only a sent estimate has one."""
    with transaction.atomic():
        locked = Estimate.objects.select_for_update().get(pk=estimate.pk)
        if locked.sent_at is None:
            raise ValidationError('Send the estimate before recording the answer.')
        if locked.invoice_id:
            raise ValidationError('This estimate has already been invoiced.')
        now = timezone.now()
        locked.accepted_at = now if answer == 'accepted' else None
        locked.declined_at = now if answer == 'declined' else None
        locked.save(update_fields=['accepted_at', 'declined_at', 'updated_at'])
        return locked


def convert_to_invoice(estimate, today=None):
    """A draft invoice with the estimate's client, tax rate and lines. Only once, and only when accepted."""
    today = today or timezone.localdate()
    with transaction.atomic():
        locked = Estimate.objects.select_for_update().get(pk=estimate.pk)
        if locked.invoice_id:
            raise ValidationError('This estimate has already been invoiced.')
        if locked.accepted_at is None:
            raise ValidationError('Mark the estimate accepted before invoicing it.')
        invoice = create_invoice(
            client=locked.client,
            issue_date=today,
            due_date=today + timedelta(days=INVOICE_PAYMENT_DAYS),
            tax_rate=locked.tax_rate,
            project=locked.project,
        )
        for line in locked.lines.all():
            add_line(
                invoice,
                project=line.project,
                description=line.description,
                details=line.details,
                quantity=line.quantity,
                unit_price=line.unit_price,
            )
        locked.invoice = invoice
        locked.save(update_fields=['invoice', 'updated_at'])
        return invoice

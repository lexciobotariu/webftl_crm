"""Billing logged time and fixed-price projects onto invoices.

Only billable time on hourly projects is billed by the hour. Each time entry
can be on one invoice line at a time: billing it links the entry to the line,
and removing the line, deleting its draft or cancelling its invoice frees the
entry to be billed again. A fixed-price project is billed as one line for
what is left of its price.
"""
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Invoice, InvoiceLine, money

HOUR = Decimal(3600)
PER_TASK = 'task'
PER_PROJECT = 'project'
PER_CHOICES = [(PER_TASK, 'One line per task'), (PER_PROJECT, 'One line per project')]
# Days a new invoice made from a project gets to be paid, as on the invoice form.
PAYMENT_DAYS = 30


def _hours(seconds):
    return (Decimal(seconds) / HOUR).quantize(Decimal('0.01'))


def _seconds(entry):
    return max(int((entry.ended_at - entry.started_at).total_seconds()), 0)


@dataclass
class TaskToBill:
    task: object
    seconds: int = 0
    entry_ids: list = field(default_factory=list)

    @property
    def project(self):
        return self.task.project

    @property
    def hours(self):
        return _hours(self.seconds)

    @property
    def rate(self):
        return self.project.billing_rate

    @property
    def amount(self):
        return money(self.hours * (self.rate or 0))


def unbilled_entries(client, project=None):
    """Finished time on billable tasks of ``client``'s hourly projects, not on any invoice line."""
    from apps.projects.models import Project
    from apps.tasks.models import TimeEntry

    entries = TimeEntry.objects.filter(
        ended_at__isnull=False,
        invoice_line__isnull=True,
        task__billable=True,
        task__project__client=client,
        task__project__billing_type=Project.HOURLY,
    )
    if project is not None:
        entries = entries.filter(task__project=project)
    return entries


def tasks_to_bill(client, project=None, entries=None):
    """Tasks with unbilled time, by project name then task number."""
    if entries is None:
        entries = unbilled_entries(client, project)
    rows = OrderedDict()
    for entry in entries.select_related('task__project').order_by(
        'task__project__name', 'task__project_id', 'task__pk', 'started_at'
    ):
        row = rows.setdefault(entry.task_id, TaskToBill(task=entry.task))
        row.seconds += _seconds(entry)
        row.entry_ids.append(entry.pk)
    return [row for row in rows.values() if row.hours > 0]


def unbilled_seconds(project):
    """Billable time on ``project`` that is not on an invoice yet (hourly projects only)."""
    if project.client_id is None:
        return 0
    return sum(_seconds(entry) for entry in unbilled_entries(project.client, project))


def _description(text, prefix=''):
    text = f'{prefix}{text}' if prefix else text
    return text if len(text) <= 255 else text[:254] + '…'


def bill_tasks(invoice, task_ids, per=PER_TASK):
    """Add the unbilled time of ``task_ids`` to a draft as lines. Returns the new lines.

    Per task: one line per task, the task's title, its hours and the project's
    rate. Per project: one line per project with the hours of the chosen tasks.
    When the invoice has a project only that project's tasks are billed. A
    project with no hourly rate gets a price of 0 to fill in.
    """
    from apps.tasks.models import TimeEntry

    if per not in (PER_TASK, PER_PROJECT):
        raise ValidationError('Choose one line per task or one line per project.')
    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if locked.sent_at is not None:
            from .models import InvoiceLocked

            raise InvoiceLocked('This invoice has been sent.')
        entries = unbilled_entries(locked.client, locked.project).filter(task_id__in=task_ids)
        # Lock the rows so two people billing at once cannot bill the same time.
        list(TimeEntry.objects.select_for_update().filter(pk__in=entries.values('pk')).values_list('pk'))
        rows = tasks_to_bill(locked.client, entries=entries)
        if not rows:
            raise ValidationError('Choose at least one task with unbilled time.')

        groups = []
        if per == PER_TASK:
            prefix_project = locked.project_id is None
            for row in rows:
                prefix = f'{row.project.name}: ' if prefix_project else ''
                groups.append((row.project, row.task, _description(row.task.title, prefix), [row]))
        else:
            by_project = OrderedDict()
            for row in rows:
                by_project.setdefault(row.project.pk, []).append(row)
            for project_rows in by_project.values():
                project = project_rows[0].project
                groups.append((project, None, _description(project.name), project_rows))

        lines = []
        for project, task, description, group in groups:
            seconds = sum(row.seconds for row in group)
            line = InvoiceLine.objects.create(
                invoice=locked,
                project=project,
                task=task,
                description=description,
                quantity=_hours(seconds),
                unit_price=project.billing_rate or Decimal('0.00'),
            )
            TimeEntry.objects.filter(pk__in=[pk for row in group for pk in row.entry_ids]).update(invoice_line=line)
            lines.append(line)
        return lines


def fixed_price_left(project):
    """The fixed price less what is already on invoices for the project (drafts included, cancelled not)."""
    if project.billing_type != project.FIXED or project.fixed_price is None:
        return None
    lines = InvoiceLine.objects.filter(project=project, invoice__cancelled_at__isnull=True)
    billed = sum((line.amount for line in lines), Decimal('0.00'))
    return max(money(project.fixed_price - billed), Decimal('0.00'))


def _tax_rate_for(client):
    """The tax rate on the client's latest invoice, so a new one starts the same; 0 for a first invoice."""
    latest = Invoice.objects.filter(client=client).order_by('-issue_date', '-number').first()
    return latest.tax_rate if latest else Decimal('0.00')


def invoice_project(project, *, task_ids=(), per=PER_TASK, today=None):
    """A new draft for the project's client with the project set.

    Hourly: the chosen tasks' unbilled time, as :func:`bill_tasks`. Fixed price:
    one line for what is left of the price.
    """
    from .services import add_line, create_invoice

    today = today or timezone.localdate()
    if project.client_id is None:
        raise ValidationError('Link the project to a client before invoicing it.')
    left = None
    if project.billing_type == project.FIXED:
        left = fixed_price_left(project)
        if left is None:
            raise ValidationError('Set the fixed price on the project first.')
        if left <= 0:
            raise ValidationError('The fixed price is already invoiced in full.')
    with transaction.atomic():
        invoice = create_invoice(
            client=project.client,
            project=project,
            issue_date=today,
            due_date=today + timedelta(days=PAYMENT_DAYS),
            tax_rate=_tax_rate_for(project.client),
        )
        if left is not None:
            add_line(invoice, project=project, description=project.name, quantity=Decimal('1'), unit_price=left)
        else:
            bill_tasks(invoice, task_ids, per)
        return invoice


def release_time(invoice):
    """Free the time billed on ``invoice`` (a cancelled invoice no longer bills it)."""
    from apps.tasks.models import TimeEntry

    return TimeEntry.objects.filter(invoice_line__invoice=invoice).update(invoice_line=None)

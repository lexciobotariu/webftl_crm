"""Money and deadlines on the dashboard.

Money needs the invoices module and covers the invoices the person may open
(``visible_invoices``). Amounts are never added across currencies. Billable time
not invoiced yet is worked out from everyone's time, so like the project
Overview it is only shown to admins and ``tasks_view_all``.

Deadlines are the person's own open tasks due within a week (or already late)
and open projects they can see whose deadline is within two weeks (or passed).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

TASKS_AHEAD = timedelta(days=7)
PROJECTS_AHEAD = timedelta(days=14)
LIST_LIMIT = 8


@dataclass
class Money:
    outstanding: list = field(default_factory=list)
    outstanding_count: int = 0
    overdue: list = field(default_factory=list)
    overdue_invoices: list = field(default_factory=list)
    paid_this_month: list = field(default_factory=list)
    show_unbilled: bool = False
    unbilled_hours: Decimal = Decimal('0')
    unbilled_amounts: list = field(default_factory=list)


def money_summary(user, today=None):
    from apps.invoices.listing import OUTSTANDING
    from apps.invoices.models import Payment, totals_by_currency, visible_invoices

    today = today or timezone.localdate()
    invoices = visible_invoices(user).filter(sent_at__isnull=False, cancelled_at__isnull=True)
    outstanding, overdue = [], []
    for invoice in invoices:
        status = invoice.status
        if status in OUTSTANDING:
            outstanding.append((invoice, invoice.balance))
        if status == 'overdue':
            overdue.append((invoice, invoice.balance))

    first_of_month = today.replace(day=1)
    payments = Payment.objects.filter(
        invoice__in=invoices, date__gte=first_of_month, date__lte=today
    ).select_related('invoice')

    summary = Money(
        outstanding=totals_by_currency(outstanding),
        outstanding_count=len(outstanding),
        overdue=totals_by_currency(overdue),
        overdue_invoices=sorted(
            (invoice for invoice, _balance in overdue), key=lambda invoice: invoice.due_date
        )[:LIST_LIMIT],
        paid_this_month=totals_by_currency((p.invoice, p.amount) for p in payments),
    )
    if user.is_admin or user.has_app_permission('tasks_view_all'):
        summary.show_unbilled = True
        summary.unbilled_hours, summary.unbilled_amounts = _unbilled(user)
    return summary


def _unbilled(user):
    """Hours of billable time not on an invoice, and what they are worth per currency."""
    from apps.clients.models import visible_clients
    from apps.invoices.billing import HOUR, _seconds
    from apps.invoices.models import format_money
    from apps.projects.models import Project
    from apps.tasks.models import TimeEntry

    entries = TimeEntry.objects.filter(
        ended_at__isnull=False,
        invoice_line__isnull=True,
        task__billable=True,
        task__project__billing_type=Project.HOURLY,
        task__project__client__in=visible_clients(user),
    ).select_related('task__project__client__currency')

    seconds = 0
    by_currency = defaultdict(Decimal)
    for entry in entries:
        entry_seconds = _seconds(entry)
        seconds += entry_seconds
        project = entry.task.project
        currency = project.client.currency
        if project.hourly_rate and currency is not None:
            key = (currency.code, currency.symbol, currency.symbol_before)
            by_currency[key] += Decimal(entry_seconds) / HOUR * project.hourly_rate
    hours = (Decimal(seconds) / HOUR).quantize(Decimal('0.1'))
    amounts = [
        format_money(amount, symbol, before)
        for (_code, symbol, before), amount in sorted(by_currency.items())
    ]
    return hours, amounts


@dataclass
class Deadlines:
    late_tasks: list = field(default_factory=list)
    week_tasks: list = field(default_factory=list)
    projects: list = field(default_factory=list)


def deadlines(user, today=None):
    from apps.projects.models import Project, visible_projects
    from apps.tasks.models import Task

    today = today or timezone.localdate()
    result = Deadlines()
    if user.has_app_permission('access_tasks'):
        mine = (
            Task.objects.open_for(user)
            .active()
            .filter(due_date__isnull=False, due_date__lte=today + TASKS_AHEAD)
            .select_related('project', 'status')
            .order_by('due_date', 'pk')
        )
        for task in mine[: LIST_LIMIT * 2]:
            (result.late_tasks if task.due_date < today else result.week_tasks).append(task)
        result.late_tasks = result.late_tasks[:LIST_LIMIT]
        result.week_tasks = result.week_tasks[:LIST_LIMIT]
    if user.has_app_permission('access_projects'):
        result.projects = list(
            visible_projects(user)
            .filter(
                status__in=Project.OPEN_STATUSES,
                deadline__isnull=False,
                deadline__lte=today + PROJECTS_AHEAD,
            )
            .select_related('client')
            .order_by('deadline', 'name')[:LIST_LIMIT]
        )
    return result

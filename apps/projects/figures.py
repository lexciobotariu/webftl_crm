"""Time and money on the project Overview tab.

Hours need the tasks module and follow the time page: everyone's time for
``role=admin`` and ``tasks_view_all``, otherwise only the person's own. Money
needs the invoices module, and the billable amount of an hourly project is
only shown to someone who sees everyone's time, since it is worked out from it.
Amounts are in the client's currency; invoiced amounts are line totals before
tax on sent, not cancelled invoices.
"""
from dataclasses import dataclass
from decimal import Decimal

from apps.invoices.models import format_money

HOUR = Decimal(3600)


def _hours(seconds):
    return (Decimal(seconds) / HOUR).quantize(Decimal('0.1'))


@dataclass
class ProjectFigures:
    show_time: bool = False
    everyones_time: bool = False
    billable_seconds: int = 0
    non_billable_seconds: int = 0
    estimate_minutes: int = 0
    estimated_task_seconds: int = 0
    show_money: bool = False
    billable_amount: str = ''
    billable_amount_note: str = ''
    invoiced: str = ''
    invoiced_count: int = 0

    @property
    def billable_hours(self):
        return _hours(self.billable_seconds)

    @property
    def non_billable_hours(self):
        return _hours(self.non_billable_seconds)

    @property
    def total_hours(self):
        return _hours(self.billable_seconds + self.non_billable_seconds)

    @property
    def estimate_hours(self):
        return _hours(self.estimate_minutes * 60)

    @property
    def estimated_task_hours(self):
        return _hours(self.estimated_task_seconds)

    @property
    def over_estimate(self):
        return bool(self.estimate_minutes) and self.estimated_task_seconds > self.estimate_minutes * 60


def _money(project, amount):
    currency = project.client.currency if project.client_id else None
    if currency is None:
        return f'{amount:.2f}'
    return format_money(amount, currency.symbol, currency.symbol_before)


def project_figures(user, project, tasks):
    """``tasks`` are the project's tasks this person can view, without archived ones."""
    from apps.tasks.models import TimeEntry

    figures = ProjectFigures()
    if user.has_app_permission('access_tasks'):
        figures.show_time = True
        figures.everyones_time = user.is_admin or user.has_app_permission('tasks_view_all')
        entries = TimeEntry.objects.filter(task__project=project, ended_at__isnull=False).select_related('task')
        if not figures.everyones_time:
            entries = entries.filter(user=user)
        estimates = dict(tasks.filter(estimate_minutes__isnull=False).values_list('pk', 'estimate_minutes'))
        figures.estimate_minutes = sum(estimates.values())
        for entry in entries:
            seconds = max(int((entry.ended_at - entry.started_at).total_seconds()), 0)
            if entry.task.billable:
                figures.billable_seconds += seconds
            else:
                figures.non_billable_seconds += seconds
            if entry.task_id in estimates:
                figures.estimated_task_seconds += seconds

    if user.has_app_permission('access_invoices'):
        from apps.invoices.models import InvoiceLine, visible_invoices

        figures.show_money = True
        if project.billing_type == project.FIXED:
            if project.fixed_price is not None:
                figures.billable_amount = _money(project, project.fixed_price)
                figures.billable_amount_note = 'Fixed price'
            else:
                figures.billable_amount_note = 'Fixed price not set'
        elif project.hourly_rate is None:
            figures.billable_amount_note = 'No hourly rate set'
        elif figures.everyones_time:
            amount = Decimal(figures.billable_seconds) / HOUR * project.hourly_rate
            figures.billable_amount = _money(project, amount)
            figures.billable_amount_note = 'Billable hours at the hourly rate'

        lines = InvoiceLine.objects.filter(
            project=project,
            invoice__in=visible_invoices(user).filter(sent_at__isnull=False, cancelled_at__isnull=True),
        )
        total = Decimal('0.00')
        invoices = set()
        for line in lines:
            total += line.amount
            invoices.add(line.invoice_id)
        figures.invoiced = _money(project, total)
        figures.invoiced_count = len(invoices)
    return figures

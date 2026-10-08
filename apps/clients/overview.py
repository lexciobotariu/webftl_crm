"""The client Overview tab: what is owed, what is late, what is running, and recent work.

Every figure uses the visibility of the page it links to. Money needs the
invoices module, hours and tasks the tasks module; a section the person may
not see is left out rather than shown as zero.
"""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import F
from django.utils import timezone

from apps.projects.models import Project, visible_projects
from apps.projects.services import with_task_counts

RECENT_TASKS = 5


@dataclass
class Overview:
    open_projects: list = field(default_factory=list)
    closed_project_count: int = 0
    show_money: bool = False
    outstanding: list = field(default_factory=list)  # formatted amounts, one per currency
    overdue_invoices: list = field(default_factory=list)
    overdue_total: list = field(default_factory=list)
    draft_count: int = 0
    show_time: bool = False
    everyones_time: bool = False
    month_seconds: int = 0
    month_billable_seconds: int = 0
    recent_tasks: list = field(default_factory=list)
    last_activity: datetime | None = None

    @property
    def month_hours(self):
        return _hours(self.month_seconds)

    @property
    def month_billable_hours(self):
        return _hours(self.month_billable_seconds)


def _hours(seconds):
    return (Decimal(seconds) / Decimal(3600)).quantize(Decimal('0.1'))


def _by_currency(invoices):
    """Each currency's total, formatted; amounts in different currencies are never added."""
    from apps.invoices.models import format_money

    totals = {}
    for invoice, amount in invoices:
        key = (invoice.currency_code, invoice.currency_symbol, invoice.symbol_before)
        totals[key] = totals.get(key, Decimal('0.00')) + amount
    return [format_money(amount, symbol, before) for (_code, symbol, before), amount in sorted(totals.items())]


def client_overview(user, client, today=None):
    today = today or timezone.localdate()
    overview = Overview()
    activity = []

    projects = visible_projects(user).filter(client=client)
    overview.open_projects = list(
        with_task_counts(projects.filter(status__in=Project.OPEN_STATUSES), user)
        .order_by(F('deadline').asc(nulls_last=True), 'name')
    )
    overview.closed_project_count = projects.exclude(status__in=Project.OPEN_STATUSES).count()

    if user.has_app_permission('access_invoices'):
        from apps.invoices.models import visible_invoices

        overview.show_money = True
        invoices = visible_invoices(user).filter(client=client, cancelled_at__isnull=True)
        owed, overdue = [], []
        for invoice in invoices:
            activity.append(invoice.updated_at)
            if invoice.is_draft:
                overview.draft_count += 1
                continue
            balance = invoice.balance
            if balance > 0:
                owed.append((invoice, balance))
                if invoice.due_date < today:
                    overdue.append((invoice, balance))
        overview.outstanding = _by_currency(owed)
        overview.overdue_total = _by_currency(overdue)
        overview.overdue_invoices = sorted((invoice for invoice, _ in overdue), key=lambda i: i.due_date)

    if user.has_app_permission('access_tasks'):
        from apps.tasks.models import TimeEntry, visible_tasks

        overview.show_time = True
        overview.everyones_time = user.is_admin or user.has_app_permission('tasks_view_all')
        start = timezone.make_aware(datetime.combine(today.replace(day=1), time.min))
        end = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min))
        entries = TimeEntry.objects.filter(task__project__in=projects).select_related('task')
        if not overview.everyones_time:
            entries = entries.filter(user=user)
        for entry in entries.filter(started_at__gte=start, started_at__lt=end, ended_at__isnull=False):
            seconds = max(int((entry.ended_at - entry.started_at).total_seconds()), 0)
            overview.month_seconds += seconds
            if entry.task.billable:
                overview.month_billable_seconds += seconds
        latest_entry = entries.order_by('-created_at').values_list('created_at', flat=True).first()
        if latest_entry:
            activity.append(latest_entry)

        overview.recent_tasks = list(
            visible_tasks(user).filter(project__client=client).not_archived()
            .select_related('project', 'status', 'assignee').order_by('-updated_at')[:RECENT_TASKS]
        )
        activity.extend(task.updated_at for task in overview.recent_tasks[:1])

    from apps.notes.models import Note, notes_visible_to_user

    latest_note = (
        notes_visible_to_user(user, Note.objects.filter(client=client))
        .order_by('-updated_at').values_list('updated_at', flat=True).first()
    )
    if latest_note:
        activity.append(latest_note)
    overview.last_activity = max(activity) if activity else None
    return overview

"""Filters and totals for the invoice list.

``status`` is derived from lines and payments (see ``Invoice.status``), so the
client and period filters run in the database and the status filter runs on
the rows that are left. Totals cover every invoice that matches the filters,
not only the page on screen, and are kept per currency.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

from .models import totals_by_currency

STATUS_CHOICES = (
    ('', 'All statuses'),
    ('draft', 'Draft'),
    ('outstanding', 'Outstanding'),
    ('overdue', 'Overdue'),
    ('paid', 'Paid'),
    ('cancelled', 'Cancelled'),
)
# Outstanding is everything sent and still owed: sent, partly paid or overdue.
OUTSTANDING = {'sent', 'partial', 'overdue'}

PERIOD_CHOICES = (
    ('', 'Any date'),
    ('this_month', 'This month'),
    ('last_month', 'Last month'),
    ('this_quarter', 'This quarter'),
    ('this_year', 'This year'),
    ('last_year', 'Last year'),
)


def period_range(period, today=None):
    """First and last issue date of ``period``, or ``None`` for any date."""
    today = today or timezone.localdate()
    if period == 'this_month':
        first = today.replace(day=1)
        return first, (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    if period == 'last_month':
        last = today.replace(day=1) - timedelta(days=1)
        return last.replace(day=1), last
    if period == 'this_quarter':
        first = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
        return first, (first + timedelta(days=95)).replace(day=1) - timedelta(days=1)
    if period == 'this_year':
        return date(today.year, 1, 1), date(today.year, 12, 31)
    if period == 'last_year':
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    return None


@dataclass
class InvoiceFilters:
    status: str = ''
    client_id: int | None = None
    project_id: int | None = None
    period: str = ''

    @classmethod
    def from_query(cls, params):
        """Unknown values are ignored rather than refused, so an old link still opens the list."""
        status = params.get('status', '')
        period = params.get('period', '')
        raw_client = params.get('client', '')
        raw_project = params.get('project', '')
        return cls(
            status=status if status in dict(STATUS_CHOICES) else '',
            client_id=int(raw_client) if raw_client.isdigit() else None,
            project_id=int(raw_project) if raw_project.isdigit() else None,
            period=period if period in dict(PERIOD_CHOICES) else '',
        )

    @property
    def active(self):
        return bool(self.status or self.client_id or self.project_id or self.period)


def matches_status(invoice, status):
    if not status:
        return True
    if status == 'outstanding':
        return invoice.status in OUTSTANDING
    return invoice.status == status


@dataclass
class ListTotals:
    invoiced: list = field(default_factory=list)
    outstanding: list = field(default_factory=list)
    overdue: list = field(default_factory=list)


def filter_invoices(invoices, filters, today=None):
    """The matching invoices, newest number first, and their totals."""
    if filters.client_id:
        invoices = invoices.filter(client_id=filters.client_id)
    if filters.project_id:
        invoices = invoices.filter(project_id=filters.project_id)
    span = period_range(filters.period, today)
    if span:
        invoices = invoices.filter(issue_date__range=span)
    rows = [invoice for invoice in invoices if matches_status(invoice, filters.status)]

    invoiced, outstanding, overdue = [], [], []
    for invoice in rows:
        status = invoice.status
        if status in ('draft', 'cancelled'):
            continue
        invoiced.append((invoice, invoice.total))
        if status in OUTSTANDING:
            outstanding.append((invoice, invoice.balance))
        if status == 'overdue':
            overdue.append((invoice, invoice.balance))
    totals = ListTotals(
        invoiced=totals_by_currency(invoiced),
        outstanding=totals_by_currency(outstanding),
        overdue=totals_by_currency(overdue),
    )
    return rows, totals

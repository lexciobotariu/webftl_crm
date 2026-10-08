"""Totals for the time page: billable and non-billable time and what it is worth.

An amount is billable hours times the project's hourly rate, in the client's
currency. A project with no rate adds hours but no amount. Amounts in different
currencies are never added together; each currency keeps its own total.
"""
import csv
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.invoices.models import format_money

from .durations import format_seconds

GROUP_CHOICES = (
    ('none', 'No grouping'),
    ('project', 'Project'),
    ('client', 'Client'),
    ('person', 'Person'),
)
CENT = Decimal('0.01')


def _seconds(entry):
    if entry.duration is None:  # a running timer counts once it stops
        return 0
    return max(int(entry.duration.total_seconds()), 0)


def _currency(project):
    return project.client.currency if project.client_id else None


def entry_amount(entry):
    """What a stopped, billable entry is worth, or ``None`` when it has no price."""
    project = entry.task.project
    if not entry.task.billable or project.hourly_rate is None or entry.duration is None:
        return None
    return Decimal(_seconds(entry)) / Decimal(3600) * project.hourly_rate


@dataclass
class Totals:
    key: object = None
    label: str = ''
    billable_seconds: int = 0
    non_billable_seconds: int = 0
    # currency pk (or None) -> [currency, unrounded amount]
    amounts: dict = field(default_factory=dict)

    def add(self, entry):
        seconds = _seconds(entry)
        if entry.task.billable:
            self.billable_seconds += seconds
        else:
            self.non_billable_seconds += seconds
        amount = entry_amount(entry)
        if amount is not None:
            currency = _currency(entry.task.project)
            slot = self.amounts.setdefault(currency.pk if currency else None, [currency, Decimal(0)])
            slot[1] += amount

    @property
    def total_seconds(self):
        return self.billable_seconds + self.non_billable_seconds

    @property
    def total_label(self):
        return format_seconds(self.total_seconds, zero='0m')

    @property
    def billable_label(self):
        return format_seconds(self.billable_seconds, zero='0m')

    @property
    def non_billable_label(self):
        return format_seconds(self.non_billable_seconds, zero='0m')

    @property
    def money(self):
        """``[(currency, amount rounded to cents)]``, by currency code."""
        rows = [(currency, amount.quantize(CENT, rounding=ROUND_HALF_UP))
                for currency, amount in self.amounts.values()]
        return sorted(rows, key=lambda row: row[0].code if row[0] else '')

    @property
    def amount_label(self):
        return ' + '.join(_money_label(currency, amount) for currency, amount in self.money)


def _money_label(currency, amount):
    if currency is None:
        return format_money(amount)
    return format_money(amount, currency.symbol or currency.code, currency.symbol_before)


def _group_of(entry, by):
    if by == 'project':
        project = entry.task.project
        return project.pk, project.name
    if by == 'client':
        client = entry.task.project.client
        return client.pk, client.name
    if by == 'person':
        return entry.user_id, entry.user.name
    return None, ''


def summarize(entries, by='none'):
    """``(overall, groups)``: one :class:`Totals` for everything and one per group,
    sorted by label. ``groups`` is empty when ``by`` is ``'none'``."""
    overall = Totals()
    groups = {}
    for entry in entries:
        overall.add(entry)
        if by == 'none':
            continue
        key, label = _group_of(entry, by)
        groups.setdefault(key, Totals(key=key, label=label)).add(entry)
    return overall, sorted(groups.values(), key=lambda totals: totals.label.lower())


def _hours(seconds):
    return f'{Decimal(seconds) / Decimal(3600):.2f}'


def write_entries_csv(out, entries):
    writer = csv.writer(out)
    writer.writerow([
        'Date', 'Client', 'Project', 'Task ID', 'Task', 'Person', 'Hours',
        'Billable', 'Hourly rate', 'Amount', 'Currency', 'Note',
    ])
    for entry in entries:
        task, project = entry.task, entry.task.project
        amount = entry_amount(entry)
        currency = _currency(project)
        writer.writerow([
            timezone.localtime(entry.started_at).date().isoformat(),
            project.client.name,
            project.name,
            task.identifier,
            task.title,
            entry.user.name,
            _hours(_seconds(entry)) if entry.duration is not None else 'running',
            'yes' if task.billable else 'no',
            project.hourly_rate if project.hourly_rate is not None else '',
            amount.quantize(CENT, rounding=ROUND_HALF_UP) if amount is not None else '',
            currency.code if (currency and amount is not None) else '',
            entry.note,
        ])


def write_summary_csv(out, by, groups, overall):
    writer = csv.writer(out)
    writer.writerow([dict(GROUP_CHOICES)[by], 'Billable hours', 'Non-billable hours',
                     'Total hours', 'Amount', 'Currency'])

    def rows(label, totals):
        money = totals.money or [(None, None)]
        for index, (currency, amount) in enumerate(money):
            # A group billed in two currencies gets a second row with only the amount.
            hours = ([_hours(totals.billable_seconds), _hours(totals.non_billable_seconds),
                      _hours(totals.total_seconds)] if index == 0 else ['', '', ''])
            writer.writerow([label if index == 0 else '', *hours,
                             amount if amount is not None else '',
                             currency.code if currency else ''])

    for totals in groups:
        rows(totals.label, totals)
    rows('Total', overall)

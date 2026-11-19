"""Repeating tasks: "Repeat" in the task drawer, and the copies it makes.

Setting Repeat on a task puts it in a series (``RecurringTask``, the schedule
only): every ``interval`` days, weeks, months or years, until an optional end
date. The daily job (the ``create_recurring_invoices`` command) calls
``create_due_tasks``: each series whose next date has come gets a copy of its
latest task for the latest date that has come, even when the previous task is
still open. A copy is a normal task: same title, description, assignee,
priority, estimate, billing, labels and sub-tasks (unticked), in the first
column, with its due date as far from its start as on the task it copies.
Dates that went by without a task (the job did not run, the project was not
Active) are skipped, not created late. Repeat set to Never on any task of the
series ends it; the tasks already made stay.
"""
import calendar
import logging
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.invoices.models import add_months
from apps.projects.models import Project, Status, get_assignable_users

from .models import RecurringTask, Subtask, Task

logger = logging.getLogger(__name__)

WEEKDAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
# Enough to walk past any date we ask about (a daily rule over decades).
MAX_STEPS = 50000


# --- The schedule --------------------------------------------------------


def _month_date(rule, month_first):
    """The rule's day in the month that starts on ``month_first``."""
    last = calendar.monthrange(month_first.year, month_first.month)[1]
    if rule.month_day == RecurringTask.LAST_DAY:
        day = last
    else:
        day = min(rule.month_day or rule.start_date.day, last)
    return month_first.replace(day=day)


def occurrences(rule, since=None):
    """The rule's dates in order, from ``since`` (or its start) to its end date."""
    start = rule.start_date
    since = max(since or start, start)
    end = rule.end_date
    interval = max(rule.interval or 1, 1)
    steps = 0

    def candidates():
        if rule.frequency == RecurringTask.DAILY:
            # Jump close to ``since`` instead of walking from the start.
            k = max((since - start).days // interval, 0)
            while True:
                yield start + timedelta(days=k * interval)
                k += 1
        elif rule.frequency == RecurringTask.WEEKLY:
            days = rule.weekday_list or [start.weekday()]
            first_monday = start - timedelta(days=start.weekday())
            k = max(((since - first_monday).days // 7) // interval, 0)
            while True:
                monday = first_monday + timedelta(weeks=k * interval)
                for day in days:
                    yield monday + timedelta(days=day)
                k += 1
        elif rule.frequency == RecurringTask.MONTHLY:
            first = start.replace(day=1)
            months = (since.year - start.year) * 12 + since.month - start.month
            k = max(months // interval - 1, 0)
            while True:
                yield _month_date(rule, add_months(first, k * interval))
                k += 1
        else:  # yearly, on the start date's day (28 Feb in years without 29 Feb)
            k = max((since.year - start.year) // interval - 1, 0)
            while True:
                yield add_months(start, 12 * k * interval, anchor_day=start.day)
                k += 1

    for day in candidates():
        steps += 1
        if steps > MAX_STEPS or (end and day > end):
            return
        if day >= since:
            yield day


def first_on_or_after(rule, day):
    return next(occurrences(rule, day), None)


def next_after(rule, day):
    return first_on_or_after(rule, day + timedelta(days=1))


def latest_on_or_before(rule, day):
    """The last date of the rule up to ``day``, or None when it starts later."""
    latest = None
    for item in occurrences(rule):
        if item > day:
            break
        latest = item
    return latest


def describe(rule):
    """"Every month on day 1", "Every 2 weeks on Mon, Thu", ..."""
    n = rule.interval or 1
    unit = dict(RecurringTask.FREQUENCY_CHOICES)[rule.frequency].lower()
    every = f'Every {unit}' if n == 1 else f'Every {n} {unit}s'
    if rule.frequency == RecurringTask.WEEKLY:
        days = rule.weekday_list or [rule.start_date.weekday()]
        return f'{every} on {", ".join(WEEKDAY_NAMES[day] for day in days)}'
    if rule.frequency == RecurringTask.MONTHLY:
        if rule.month_day == RecurringTask.LAST_DAY:
            return f'{every} on the last day'
        return f'{every} on day {rule.month_day or rule.start_date.day}'
    if rule.frequency == RecurringTask.YEARLY:
        return f'{every} on {rule.start_date:%-d %B}'
    return every


# --- Setting Repeat on a task ---------------------------------------------

FREQUENCIES = {RecurringTask.DAILY, RecurringTask.WEEKLY, RecurringTask.MONTHLY, RecurringTask.YEARLY}


def parse_repeat(data):
    """Read Repeat from a form (``repeat``, ``repeat_interval``, ``repeat_days``,
    ``repeat_month_day``, ``repeat_end``). Returns a dict, or None for Never.

    Raises ValidationError on a value that makes no sense.
    """
    frequency = (data.get('repeat') or '').strip()
    if frequency in ('', 'never'):
        return None
    if frequency not in FREQUENCIES:
        raise ValidationError('Choose how often it repeats.')
    try:
        interval = int(data.get('repeat_interval') or 1)
    except ValueError:
        raise ValidationError('Repeat every must be a number.') from None
    if not 1 <= interval <= 99:
        raise ValidationError('Repeat every 1 to 99.')
    days = data.getlist('repeat_days') if hasattr(data, 'getlist') else (data.get('repeat_days') or [])
    weekdays = sorted({int(day) for day in days if str(day).isdigit() and int(day) < 7})
    raw_day = str(data.get('repeat_month_day') or '').strip()
    month_day = int(raw_day) if raw_day.isdigit() and int(raw_day) <= 31 else None
    raw_end = data.get('repeat_end') or ''
    end_date = date_of(raw_end) if raw_end else None
    if raw_end and end_date is None:
        raise ValidationError('The end date is not a date.')
    return {
        'frequency': frequency,
        'interval': interval,
        'weekdays': ','.join(str(day) for day in weekdays) if frequency == RecurringTask.WEEKLY else '',
        'month_day': month_day if frequency == RecurringTask.MONTHLY else None,
        'end_date': end_date,
    }


def set_repeat(task, spec, user=None, today=None):
    """Make ``task`` repeat as ``spec`` (from ``parse_repeat``), change its series, or end it (None).

    A task that does not repeat yet starts a series from today: it counts as
    the current period's task, and the first copy comes on the next date.
    Returns the series, or None.
    """
    today = today or timezone.localdate()
    rule = task.recurring
    if spec is None:
        if rule is not None:
            rule.delete()  # the tasks stay, out of the series
            task.recurring, task.recurring_date = None, None
        return None
    if spec['end_date'] and spec['end_date'] < today:
        raise ValidationError('The end date has passed.')
    with transaction.atomic():
        if rule is None:
            rule = RecurringTask(project=task.project, start_date=today, created_by=user)
        for name, value in spec.items():
            setattr(rule, name, value)
        rule.next_date = next_after(rule, today)
        rule.save()
        if task.recurring_id != rule.pk:
            task.recurring = rule
            task.recurring_date = latest_on_or_before(rule, today) or today
            Task.objects.filter(pk=task.pk).update(recurring=rule, recurring_date=task.recurring_date)
    return rule


def summary(task):
    """"Every month on day 1, until 31 Dec 2026", or "" when the task does not repeat."""
    rule = task.recurring
    if rule is None:
        return ''
    text = describe(rule)
    if rule.end_date:
        text += f', until {rule.end_date:%-d %b %Y}'
    return text


# --- Creating tasks ------------------------------------------------------


def _first_column(project):
    return (
        project.statuses.filter(category=Status.UNSTARTED, visible_on_board=True).first()
        or project.statuses.filter(visible_on_board=True).first()
        or project.statuses.first()
    )


def _due_offset(task):
    """How many days after its start the task is due, or None."""
    if task.due_date is None:
        return None
    start = task.start_date or task.recurring_date or timezone.localtime(task.created_at).date()
    return max((task.due_date - start).days, 0)


def create_task_for(rule, day):
    """A copy of the series' latest task for ``day``. None when that date has one or the series has no task."""
    if Task.objects.filter(recurring=rule, recurring_date=day).exists():
        return None
    source = rule.latest_task()
    if source is None:
        return None
    assignee = source.assignee
    if assignee is not None and not get_assignable_users(rule.project).filter(pk=assignee.pk).exists():
        assignee = None
    offset = _due_offset(source)
    try:
        with transaction.atomic():
            task = Task(
                project=rule.project,
                status=_first_column(rule.project),
                title=source.title,
                description=source.description,
                assignee=assignee,
                priority=source.priority,
                start_date=day,
                due_date=day + timedelta(days=offset) if offset is not None else None,
                estimate_minutes=source.estimate_minutes,
                billable=source.billable,
                recurring=rule,
                recurring_date=day,
            )
            task.save()
            labels = list(source.labels.all())
            if labels:
                task.labels.set(labels)
            Subtask.objects.bulk_create([
                Subtask(task=task, title=subtask.title, order=index)
                for index, subtask in enumerate(source.subtasks.order_by('order', 'pk'))
            ])
    except IntegrityError:
        # Created at the same moment by another run.
        return None
    return task


def create_due_tasks(today=None):
    """Create the task of every series whose next date has come. Returns the tasks created."""
    today = today or timezone.localdate()
    created = []
    rules = RecurringTask.objects.filter(next_date__isnull=False, next_date__lte=today).select_related('project')
    for rule in rules:
        try:
            day = None
            for item in occurrences(rule, rule.next_date):
                if item > today:
                    break
                day = item
            if day is not None and rule.project.status == Project.ACTIVE:
                task = create_task_for(rule, day)
                if task is not None:
                    created.append(task)
            rule.next_date = next_after(rule, day or today)
            rule.save(update_fields=['next_date', 'updated_at'])
        except Exception:
            logger.exception('Repeating task %s could not create its task', rule.pk)
    return created


def date_of(value):
    """Parse YYYY-MM-DD, or None."""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None

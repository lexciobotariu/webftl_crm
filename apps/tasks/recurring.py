"""Recurring tasks: when a rule repeats, and the task it creates each time.

A ``RecurringTask`` repeats every ``interval`` days, weeks, months or years
from its start date, until its end date. The daily job (the
``create_recurring_invoices`` command) calls ``create_due_tasks``: each rule
whose next date has come gets the task of the latest date that has come, even
when the previous task is still open, so every period has its own task. Dates
that went by without a task (the job did not run, the rule was paused, the
project was not Active) are skipped, not created late.
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


def date_label(rule, day):
    """What goes after the title: "November 2026", "2026", "19 Nov 2026"."""
    if rule.frequency == RecurringTask.MONTHLY:
        return f'{day:%B %Y}'
    if rule.frequency == RecurringTask.YEARLY:
        return f'{day:%Y}'
    return f'{day:%-d %b %Y}'


def task_title(rule, day):
    return f'{rule.title} · {date_label(rule, day)}' if rule.add_date_to_title else rule.title


# --- Saving a rule -------------------------------------------------------


def schedule(rule, today=None):
    """Set the rule's next date: its first date from today on (or from its start).

    Called when a rule is saved: a rule created or changed today does not get
    the tasks of dates already gone; "Create now" makes today's period's task.
    """
    today = today or timezone.localdate()
    rule.next_date = first_on_or_after(rule, today)
    return rule


def validate(rule):
    if rule.end_date and rule.end_date < rule.start_date:
        raise ValidationError('The end date is before the start date.')
    if rule.interval < 1:
        raise ValidationError('Repeat at least every 1.')


# --- Creating tasks ------------------------------------------------------


def _status(rule):
    if rule.status_id and rule.status.project_id == rule.project_id:
        return rule.status
    project = rule.project
    return (
        project.statuses.filter(category=Status.UNSTARTED, visible_on_board=True).first()
        or project.statuses.filter(visible_on_board=True).first()
        or project.statuses.first()
    )


def create_task_for(rule, day, user=None):
    """The rule's task for ``day``, with its sub-tasks. None when that date already has one."""
    if Task.objects.filter(recurring=rule, recurring_date=day).exists():
        return None
    assignee = rule.assignee
    if assignee is not None and not get_assignable_users(rule.project).filter(pk=assignee.pk).exists():
        assignee = None
    try:
        with transaction.atomic():
            task = Task(
                project=rule.project,
                status=_status(rule),
                title=task_title(rule, day)[:1000],
                description=rule.description,
                assignee=assignee,
                priority=rule.priority,
                start_date=day,
                due_date=day + timedelta(days=rule.due_after_days) if rule.due_after_days is not None else None,
                estimate_minutes=rule.estimate_minutes,
                billable=rule.billable,
                recurring=rule,
                recurring_date=day,
            )
            task._changed_by = user
            task.save()
            labels = list(rule.labels.filter(project=rule.project))
            if labels:
                task.labels.set(labels)
            Subtask.objects.bulk_create([
                Subtask(task=task, title=title[:255], order=index)
                for index, title in enumerate(rule.checklist_items)
            ])
    except IntegrityError:
        # Created at the same moment by another run.
        return None
    return task


def create_now(rule, user=None, today=None):
    """Create the task of the rule's current period now. Returns (date, task); task None when it exists.

    Raises ValidationError when the rule has not started yet or has ended.
    """
    today = today or timezone.localdate()
    day = latest_on_or_before(rule, today)
    if day is None:
        raise ValidationError(f'It starts on {first_on_or_after(rule, rule.start_date):%-d %b %Y}.'
                              if first_on_or_after(rule, rule.start_date) else 'Its schedule has ended.')
    task = create_task_for(rule, day, user)
    if rule.next_date is None or rule.next_date <= day:
        rule.next_date = next_after(rule, day)
        rule.save(update_fields=['next_date', 'updated_at'])
    return day, task


def create_due_tasks(today=None):
    """Create the task of every rule whose next date has come. Returns the tasks created."""
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
            if day is not None and not rule.paused and rule.project.status == Project.ACTIVE:
                task = create_task_for(rule, day)
                if task is not None:
                    created.append(task)
            rule.next_date = next_after(rule, day or today)
            rule.save(update_fields=['next_date', 'updated_at'])
        except Exception:
            logger.exception('Recurring task %s could not create its task', rule.pk)
    return created


def recent_tasks(rule, count=4):
    return list(rule.tasks.select_related('status', 'project').order_by('-recurring_date')[:count])


def date_of(value):
    """Parse YYYY-MM-DD, or None."""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None

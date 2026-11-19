"""Repeat is now a property of a task (0.48.0): a series copies its latest task.

Before, a recurring task was a separate rule holding the title, description,
checklist, assignee, ... of the tasks it made, and their titles got the date
("Checks · November 2026"). Now the series keeps only the schedule and copies
its latest task, title unchanged. So, for every series:

- with tasks: the latest one drops the date from its title, so the next copies
  are called like the series ("Checks"). Older tasks keep their titles.
- without a task yet (its first date has not come): its first task is created
  now from the rule, for that first date, so the series has a task to copy.
- paused, or ended with no task: the series is removed. Its tasks stay.
"""
from datetime import timedelta

from django.db import migrations
from django.db.models import F


def _first_column(Status, project_id):
    statuses = Status.objects.filter(project_id=project_id).order_by('order', 'pk')
    return (
        statuses.filter(category='unstarted', visible_on_board=True).first()
        or statuses.filter(visible_on_board=True).first()
        or statuses.first()
    )


def _first_task(apps, rule):
    Project = apps.get_model('projects', 'Project')
    Status = apps.get_model('projects', 'Status')
    Task = apps.get_model('tasks', 'Task')
    Subtask = apps.get_model('tasks', 'Subtask')
    status = rule.status if rule.status and rule.status.project_id == rule.project_id else None
    status = status or _first_column(Status, rule.project_id)
    if status is None:
        return None
    Project.objects.filter(pk=rule.project_id).update(task_counter=F('task_counter') + 1)
    number = Project.objects.filter(pk=rule.project_id).values_list('task_counter', flat=True).get()
    day = rule.next_date
    task = Task.objects.create(
        project_id=rule.project_id,
        number=number,
        status=status,
        title=rule.title,
        description=rule.description,
        assignee_id=rule.assignee_id,
        priority=rule.priority,
        start_date=day,
        due_date=day + timedelta(days=rule.due_after_days) if rule.due_after_days is not None else None,
        estimate_minutes=rule.estimate_minutes,
        billable=rule.billable,
        recurring=rule,
        recurring_date=day,
    )
    task.labels.set(rule.labels.all())
    lines = [line.strip()[:255] for line in rule.checklist.splitlines() if line.strip()][:100]
    Subtask.objects.bulk_create([Subtask(task=task, title=line, order=index) for index, line in enumerate(lines)])
    return task


def _is_dated(title, base, day):
    """Whether ``title`` is ``base`` plus the date of ``day`` ("Checks · November 2026")."""
    if day is None or not title.startswith(base) or title == base:
        return False
    rest = title[len(base):].strip(' ·-–—').strip()
    return rest in (f'{day:%B %Y}', f'{day:%Y}', f'{day:%-d %b %Y}')


def forwards(apps, schema_editor):
    RecurringTask = apps.get_model('tasks', 'RecurringTask')
    Task = apps.get_model('tasks', 'Task')
    for rule in RecurringTask.objects.select_related('status').order_by('pk'):
        latest = (
            Task.objects.filter(recurring=rule)
            .order_by(F('recurring_date').desc(nulls_last=True), '-pk').first()
        )
        if rule.paused or (latest is None and rule.next_date is None):
            rule.delete()  # Task.recurring is SET_NULL: the tasks stay.
            continue
        if latest is None:
            if _first_task(apps, rule) is None:
                rule.delete()
            continue
        if _is_dated(latest.title, rule.title, latest.recurring_date):
            Task.objects.filter(pk=latest.pk).update(title=rule.title)


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0029_recurring_tasks"),
        ("projects", "0019_project_billing_and_dates"),
        # Services turned its checks into recurring tasks; they must exist first.
        ("maintenance", "0004_remove_checks"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

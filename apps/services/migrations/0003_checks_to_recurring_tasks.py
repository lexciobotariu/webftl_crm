"""Existing services get the type "Maintenance", and their checks become a recurring task.

Each service with checks gets one monthly (or every 3 / 12 months) recurring task
"Checks" on its project, with one sub-task per check, continuing from the
period the old checks would have created next. The checks tasks already
created are linked to it, so they show among its latest tasks and in the
reports. Nothing is deleted here; 0004 drops the old check tables afterwards.
"""
from datetime import date

from django.db import migrations

FREQUENCY_MONTHS = {'monthly': 1, 'quarterly': 3, 'yearly': 12}
# Due a few days before the period ends, as the old checks task was due at its end.
DUE_AFTER_DAYS = {'monthly': 27, 'quarterly': 87, 'yearly': 360}


def forwards(apps, schema_editor):
    Service = apps.get_model('maintenance', 'Service')
    ServiceType = apps.get_model('maintenance', 'ServiceType')
    MaintenanceCheck = apps.get_model('maintenance', 'MaintenanceCheck')
    MaintenanceCheckRun = apps.get_model('maintenance', 'MaintenanceCheckRun')
    RecurringTask = apps.get_model('tasks', 'RecurringTask')
    Task = apps.get_model('tasks', 'Task')

    services = list(Service.objects.order_by('pk'))
    if not services:
        return

    first = services[0]
    first_checks = list(MaintenanceCheck.objects.filter(plan=first).order_by('position', 'pk').values_list('title', flat=True))
    kind, _ = ServiceType.objects.get_or_create(name='Maintenance', defaults={
        'description': first.description,
        'frequency': first.frequency,
        'price': first.price,
        'included_hours': first.included_hours,
        'overage_rate': first.overage_rate,
        'checklist_title': 'Checks',
        'checklist': '\n'.join(first_checks),
    })
    Service.objects.filter(service_type__isnull=True).update(service_type=kind)

    for service in services:
        titles = list(MaintenanceCheck.objects.filter(plan=service).order_by('position', 'pk').values_list('title', flat=True))
        runs = list(MaintenanceCheckRun.objects.filter(plan=service).order_by('period_start'))
        if not titles and not runs:
            continue
        frequency = service.check_frequency or 'monthly'
        # Continue the old schedule: from the first period that had a task, else from the next one due.
        this_month = max(date.today().replace(day=1), service.start_date.replace(day=1))
        next_date = service.next_check_date or this_month
        start = runs[0].period_start if runs else next_date
        rule = RecurringTask.objects.create(
            project_id=service.project_id,
            title='Checks',
            checklist='\n'.join(titles),
            frequency='monthly',
            interval=FREQUENCY_MONTHS.get(frequency, 1),
            month_day=1,
            start_date=start,
            due_after_days=DUE_AFTER_DAYS.get(frequency),
            billable=False,
            add_date_to_title=True,
            paused=not titles,
            next_date=next_date if titles else None,
            created_by_id=service.created_by_id,
        )
        for run in runs:
            if run.task_id:
                Task.objects.filter(pk=run.task_id, recurring__isnull=True).update(
                    recurring=rule, recurring_date=run.period_start,
                )


class Migration(migrations.Migration):

    dependencies = [
        ("maintenance", "0002_services"),
        ("tasks", "0029_recurring_tasks"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

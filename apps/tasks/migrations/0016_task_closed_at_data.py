from django.db import migrations
from django.db.models import F, OuterRef, Subquery
from django.db.models.functions import Coalesce

CLOSED_CATEGORIES = ('completed', 'canceled')


def fill_closed_at(apps, schema_editor):
    """Closed tasks are dated by their last status change, else their last update.

    One UPDATE: ``update()`` does not run ``auto_now``, so ``updated_at`` stays.
    """
    Task = apps.get_model('tasks', 'Task')
    TaskActivity = apps.get_model('tasks', 'TaskActivity')
    last_change = (
        TaskActivity.objects.filter(task_id=OuterRef('pk'), activity_type='status_change')
        .order_by('-created_at')
        .values('created_at')[:1]
    )
    Task.objects.filter(status__category__in=CLOSED_CATEGORIES).update(
        closed_at=Coalesce(Subquery(last_change), F('updated_at'))
    )


def clear_closed_at(apps, schema_editor):
    Task = apps.get_model('tasks', 'Task')
    Task.objects.update(closed_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0015_task_closed_at'),
    ]

    operations = [
        migrations.RunPython(fill_closed_at, clear_closed_at),
    ]

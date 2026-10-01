from django.db import migrations
from django.db.models import Case, F, Value, When
from django.db.models.functions import Least

# Mirrors apps.tasks.durations.MAX_MINUTES: an absurd old value is capped
# before it is multiplied, so it can't overflow the column.
MAX_HOURS = 1000


def hours_to_minutes(apps, schema_editor):
    """0 hours meant "no estimate", so it becomes NULL like the rest of the unset ones."""
    Task = apps.get_model('tasks', 'Task')
    Task.objects.filter(time_estimate__gt=0).update(
        estimate_minutes=Least(F('time_estimate'), Value(MAX_HOURS)) * 60
    )


def minutes_to_hours(apps, schema_editor):
    """Rounds up, so a 90 minute estimate becomes 2 hours and never 1."""
    Task = apps.get_model('tasks', 'Task')
    Task.objects.filter(estimate_minutes__gt=0).update(
        time_estimate=Case(
            When(estimate_minutes__gt=0, then=(F('estimate_minutes') + 59) / 60),
        )
    )


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0017_task_estimate_minutes'),
    ]

    operations = [
        migrations.RunPython(hours_to_minutes, minutes_to_hours),
    ]

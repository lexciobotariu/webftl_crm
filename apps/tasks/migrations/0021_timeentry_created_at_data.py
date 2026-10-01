from django.db import migrations
from django.db.models import F
from django.db.models.functions import Coalesce


def fill_created_at(apps, schema_editor):
    """An old entry is dated by when it ended, or by when it started if it is still running."""
    TimeEntry = apps.get_model('tasks', 'TimeEntry')
    TimeEntry.objects.update(created_at=Coalesce(F('ended_at'), F('started_at')))


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0020_timeentry_created_at'),
    ]

    operations = [
        migrations.RunPython(fill_created_at, migrations.RunPython.noop),
    ]

from django.db import migrations

STARTED_NAMES = {'in progress', 'review', 'doing'}
CANCELED_NAMES = {'canceled', 'cancelled'}


def assign_categories(apps, schema_editor):
    Status = apps.get_model('projects', 'Status')
    Status.objects.filter(is_done=True).update(category='completed')
    open_statuses = Status.objects.filter(is_done=False)
    open_statuses.filter(name__iexact='backlog').update(category='backlog')
    for name in STARTED_NAMES:
        open_statuses.filter(name__iexact=name).update(category='started')
    for name in CANCELED_NAMES:
        open_statuses.filter(name__iexact=name).update(category='canceled')


def restore_is_done(apps, schema_editor):
    Status = apps.get_model('projects', 'Status')
    Status.objects.filter(category='completed').update(is_done=True)


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0010_status_category'),
    ]

    operations = [
        migrations.RunPython(assign_categories, restore_is_done),
    ]

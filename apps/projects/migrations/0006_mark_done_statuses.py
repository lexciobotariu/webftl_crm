from django.db import migrations


def mark_done_statuses(apps, schema_editor):
    Status = apps.get_model('projects', 'Status')
    Status.objects.filter(name__iexact='done').update(is_done=True)


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0005_phase_c'),
    ]

    operations = [
        migrations.RunPython(mark_done_statuses, migrations.RunPython.noop),
    ]

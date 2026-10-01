from django.db import migrations

from apps.projects.keys import derive_key


def assign_keys(apps, schema_editor):
    Project = apps.get_model('projects', 'Project')
    taken = set()
    projects = list(Project.objects.order_by('pk'))
    for project in projects:
        project.key = derive_key(project.name, taken, pk=project.pk)
        taken.add(project.key)
    # bulk_update, not save(), so updated_at keeps its value.
    Project.objects.bulk_update(projects, ['key'], batch_size=500)


def clear_keys(apps, schema_editor):
    Project = apps.get_model('projects', 'Project')
    Project.objects.update(key='')


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0014_project_key_task_counter'),
    ]

    operations = [
        migrations.RunPython(assign_keys, clear_keys),
    ]

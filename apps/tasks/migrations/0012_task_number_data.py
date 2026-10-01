from django.db import migrations


def number_tasks(apps, schema_editor):
    """Number each project's tasks from 1 in the order they were created."""
    Project = apps.get_model('projects', 'Project')
    Task = apps.get_model('tasks', 'Task')
    for project_id in Project.objects.order_by('pk').values_list('pk', flat=True):
        tasks = list(Task.objects.filter(project_id=project_id).order_by('created_at', 'pk').only('pk'))
        for number, task in enumerate(tasks, start=1):
            task.number = number
        # bulk_update, not save(), so updated_at keeps its value.
        Task.objects.bulk_update(tasks, ['number'], batch_size=500)
        # update(), not save(): auto_now would move the project's updated_at.
        Project.objects.filter(pk=project_id).update(task_counter=len(tasks))


def clear_numbers(apps, schema_editor):
    Project = apps.get_model('projects', 'Project')
    Task = apps.get_model('tasks', 'Task')
    Task.objects.update(number=None)
    Project.objects.update(task_counter=0)


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0011_task_number'),
        ('projects', '0014_project_key_task_counter'),
    ]

    operations = [
        migrations.RunPython(number_tasks, clear_numbers),
    ]

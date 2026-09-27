from django.db import migrations, models


def enable_admin_task_flags(apps, schema_editor):
    """Seeded Admin can view, create, and edit tasks. Other presets stay off."""
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        tasks_view_all=True,
        tasks_create=True,
        tasks_edit_own=True,
        tasks_edit_all=True,
    )


def disable_admin_task_flags(apps, schema_editor):
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        tasks_view_all=False,
        tasks_create=False,
        tasks_edit_own=False,
        tasks_edit_all=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_projects_create_edit'),
    ]

    operations = [
        migrations.AddField(
            model_name='permissionpreset',
            name='tasks_view_all',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='permissionpreset',
            name='tasks_create',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='permissionpreset',
            name='tasks_edit_own',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='permissionpreset',
            name='tasks_edit_all',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(enable_admin_task_flags, disable_admin_task_flags),
    ]

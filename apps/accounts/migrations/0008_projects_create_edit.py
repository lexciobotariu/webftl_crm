from django.db import migrations, models


def enable_admin_project_write(apps, schema_editor):
    """Seeded Admin can create and edit projects. Other presets stay off."""
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        projects_create=True,
        projects_edit_own=True,
        projects_edit_all=True,
    )


def disable_admin_project_write(apps, schema_editor):
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        projects_create=False,
        projects_edit_own=False,
        projects_edit_all=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_clients_create_edit'),
    ]

    operations = [
        migrations.AddField(
            model_name='permissionpreset',
            name='projects_create',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='permissionpreset',
            name='projects_edit_own',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='permissionpreset',
            name='projects_edit_all',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(enable_admin_project_write, disable_admin_project_write),
    ]

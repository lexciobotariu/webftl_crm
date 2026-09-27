from django.db import migrations, models


def enable_admin_client_write(apps, schema_editor):
    """Seeded Admin can create and edit clients. Other presets stay off."""
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        clients_create=True,
        clients_edit=True,
    )


def disable_admin_client_write(apps, schema_editor):
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        clients_create=False,
        clients_edit=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_client_project_view_all'),
    ]

    operations = [
        migrations.AddField(
            model_name='permissionpreset',
            name='clients_create',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='permissionpreset',
            name='clients_edit',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(enable_admin_client_write, disable_admin_client_write),
    ]

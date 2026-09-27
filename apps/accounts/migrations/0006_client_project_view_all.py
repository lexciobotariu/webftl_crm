from django.db import migrations, models


def enable_admin_view_all(apps, schema_editor):
    """Seeded Admin sees every client and project. Other presets stay view own."""
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        clients_view_all=True,
        projects_view_all=True,
    )


def disable_admin_view_all(apps, schema_editor):
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        clients_view_all=False,
        projects_view_all=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_seed_default_presets'),
    ]

    operations = [
        migrations.AddField(
            model_name='permissionpreset',
            name='clients_view_all',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='permissionpreset',
            name='projects_view_all',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(enable_admin_view_all, disable_admin_view_all),
    ]

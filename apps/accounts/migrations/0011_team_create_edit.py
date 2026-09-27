from django.db import migrations, models


def enable_admin_team_flags(apps, schema_editor):
    """Seeded Admin can invite and edit people. Other presets stay off."""
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        team_create=True,
        team_edit=True,
    )


def disable_admin_team_flags(apps, schema_editor):
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        team_create=False,
        team_edit=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_salaries_view_edit'),
    ]

    operations = [
        migrations.AddField(
            model_name='permissionpreset',
            name='team_create',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='permissionpreset',
            name='team_edit',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(enable_admin_team_flags, disable_admin_team_flags),
    ]

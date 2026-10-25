from django.db import migrations, models


def enable_for_admin_preset(apps, schema_editor):
    """The seeded Admin preset has every flag on. Other presets start with it off."""
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(tasks_mcp=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0013_preset_money_off_by_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="permissionpreset",
            name="tasks_mcp",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(enable_for_admin_preset, migrations.RunPython.noop),
    ]

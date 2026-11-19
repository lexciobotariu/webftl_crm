from django.db import migrations, models


def open_maintenance_for_admin_preset(apps, schema_editor):
    """The seeded Admin preset gets Maintenance; other presets stay off, as for Leads."""
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(access_maintenance=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0015_access_leads"),
    ]

    operations = [
        migrations.AddField(
            model_name="permissionpreset",
            name="access_maintenance",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(open_maintenance_for_admin_preset, migrations.RunPython.noop),
    ]

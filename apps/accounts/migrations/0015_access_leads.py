from django.db import migrations, models


def open_leads_for_admin_preset(apps, schema_editor):
    """The seeded Admin preset gets Leads; other presets stay off, as for money."""
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(access_leads=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0014_permissionpreset_tasks_mcp"),
    ]

    operations = [
        migrations.AddField(
            model_name="permissionpreset",
            name="access_leads",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(open_leads_for_admin_preset, migrations.RunPython.noop),
    ]

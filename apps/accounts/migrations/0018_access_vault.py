from django.db import migrations, models


def open_vault_for_admin_preset(apps, schema_editor):
    """Only the seeded Admin preset gets the Vault; other presets stay off."""
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(access_vault=True)


class Migration(migrations.Migration):
    """Services was removed (0.48.0): its permission goes, the client Vault gets its own."""

    dependencies = [
        ("accounts", "0017_access_services"),
    ]

    operations = [
        migrations.AddField(
            model_name="permissionpreset",
            name="access_vault",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(open_vault_for_admin_preset, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="permissionpreset",
            name="access_services",
        ),
    ]

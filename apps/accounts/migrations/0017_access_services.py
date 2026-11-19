from django.db import migrations


class Migration(migrations.Migration):
    """Maintenance became Services (0.47.0): the same permission, renamed; presets keep their choice."""

    dependencies = [
        ("accounts", "0016_access_maintenance"),
    ]

    operations = [
        migrations.RenameField(
            model_name="permissionpreset",
            old_name="access_maintenance",
            new_name="access_services",
        ),
    ]

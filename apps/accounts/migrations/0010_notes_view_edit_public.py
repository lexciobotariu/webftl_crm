from django.db import migrations, models


def enable_admin_note_flags(apps, schema_editor):
    """Seeded Admin can view and edit public notes. Other presets stay off."""
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        notes_view_all=True,
        notes_edit_public=True,
    )


def disable_admin_note_flags(apps, schema_editor):
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        notes_view_all=False,
        notes_edit_public=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_tasks_view_create_edit'),
    ]

    operations = [
        migrations.AddField(
            model_name='permissionpreset',
            name='notes_view_all',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='permissionpreset',
            name='notes_edit_public',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(enable_admin_note_flags, disable_admin_note_flags),
    ]

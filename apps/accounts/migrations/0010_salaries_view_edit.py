from django.db import migrations, models


def enable_admin_salary_flags(apps, schema_editor):
    """Seeded Admin can view and edit every salary. Other presets stay off."""
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        salaries_view_all=True,
        salaries_edit=True,
    )


def disable_admin_salary_flags(apps, schema_editor):
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name='Admin').update(
        salaries_view_all=False,
        salaries_edit=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_notes_view_edit_public'),
    ]

    operations = [
        migrations.AddField(
            model_name='permissionpreset',
            name='salaries_view_all',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='permissionpreset',
            name='salaries_edit',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(enable_admin_salary_flags, disable_admin_salary_flags),
    ]

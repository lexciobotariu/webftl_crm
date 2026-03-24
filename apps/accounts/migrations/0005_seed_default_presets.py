from django.db import migrations


def seed_presets(apps, schema_editor):
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')

    PermissionPreset.objects.get_or_create(
        name='Admin',
        defaults={
            'description': 'Full access to all sections',
            'is_system': True,
            'access_dashboard': True,
            'access_clients': True,
            'access_projects': True,
            'access_tasks': True,
            'access_todos': True,
            'access_notes': True,
            'access_salaries': True,
            'access_team': True,
        },
    )

    PermissionPreset.objects.get_or_create(
        name='Developer',
        defaults={
            'description': 'Access to assigned projects, tasks, and personal todos',
            'is_system': True,
            'access_dashboard': True,
            'access_clients': False,
            'access_projects': True,
            'access_tasks': True,
            'access_todos': True,
            'access_notes': True,
            'access_salaries': False,
            'access_team': False,
        },
    )


def reverse_presets(apps, schema_editor):
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.filter(name__in=['Admin', 'Developer'], is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0004_add_user_permission_preset'),
    ]

    operations = [
        migrations.RunPython(seed_presets, reverse_presets),
    ]

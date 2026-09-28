from django.db import migrations, models


def set_invoice_flags(apps, schema_editor):
    """Seeded Admin can open, see, create, and edit invoices. Other presets stay off."""
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.exclude(name='Admin').update(
        access_invoices=False,
        invoices_view_all=False,
        invoices_create=False,
        invoices_edit=False,
    )
    PermissionPreset.objects.filter(name='Admin').update(
        access_invoices=True,
        invoices_view_all=True,
        invoices_create=True,
        invoices_edit=True,
    )


def clear_invoice_flags(apps, schema_editor):
    PermissionPreset = apps.get_model('accounts', 'PermissionPreset')
    PermissionPreset.objects.update(
        access_invoices=False,
        invoices_view_all=False,
        invoices_create=False,
        invoices_edit=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_team_create_edit'),
    ]

    operations = [
        migrations.AddField(
            model_name='permissionpreset',
            name='access_invoices',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='permissionpreset',
            name='invoices_view_all',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='permissionpreset',
            name='invoices_create',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='permissionpreset',
            name='invoices_edit',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(set_invoice_flags, clear_invoice_flags),
    ]

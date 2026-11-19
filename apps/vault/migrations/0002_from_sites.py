"""Services' sites and their logins move into the clients' Vault (0.48.0).

Each site becomes a Note (its address, who built it, platform, hosting,
domain, expiry dates, admin and repository links and its notes), and each of
its logins a Login called "<site> · <label>". Usernames, passwords and notes
are copied as stored, still encrypted: they are never decrypted here, so a
value can not be lost to a key problem during the move.
"""
from django.db import migrations


def _site_note(site):
    built_by = {'us': 'Us', 'client': 'The client', 'other': 'Someone else'}.get(site.built_by, site.built_by)
    rows = [
        ('Built by', f'{built_by} ({site.built_by_name})' if site.built_by_name else built_by),
        ('Platform', site.platform),
        ('Hosting', site.hosting),
        ('Domain registrar', site.domain_registrar),
        ('Domain expires', site.domain_expires and f'{site.domain_expires:%-d %b %Y}'),
        ('SSL expires', site.ssl_expires and f'{site.ssl_expires:%-d %b %Y}'),
        ('Admin', site.admin_url),
        ('Repository', site.repo_url),
    ]
    text = '\n'.join(f'{label}: {value}' for label, value in rows if value)
    if site.notes:
        text = f'{text}\n\n{site.notes}' if text else site.notes
    return text[:5000]


def _stored(schema_editor, SiteCredential, pk):
    """The login's username, password and notes as stored (encrypted text).

    Saved as they are: the encrypted field does not encrypt a value twice.
    """
    table = schema_editor.quote_name(SiteCredential._meta.db_table)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'SELECT username, password, notes FROM {table} WHERE id = %s', [pk])
        return [value or '' for value in cursor.fetchone()]


def forwards(apps, schema_editor):
    Site = apps.get_model('maintenance', 'Site')
    SiteCredential = apps.get_model('maintenance', 'SiteCredential')
    VaultEntry = apps.get_model('vault', 'VaultEntry')
    for site in Site.objects.order_by('pk'):
        VaultEntry.objects.create(
            client_id=site.client_id, kind='note', title=site.name[:200], url=site.url or '',
            notes=_site_note(site),
        )
        for login in SiteCredential.objects.filter(site=site).order_by('pk'):
            username, password, notes = _stored(schema_editor, SiteCredential, login.pk)
            VaultEntry.objects.create(
                client_id=site.client_id, kind='login', title=f'{site.name} · {login.label}'[:200],
                url=login.url or site.admin_url or site.url or '',
                username=username, password=password, notes=notes,
                updated_by_id=login.updated_by_id,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("vault", "0001_initial"),
        ("maintenance", "0004_remove_checks"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

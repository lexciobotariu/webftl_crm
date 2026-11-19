"""The client Vault: encrypted entries, Show and Copy logged, Admin-only by default."""
import json

import pytest
from django.db import connection
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.clients.factories import ClientFactory
from apps.vault.models import VaultAccess, VaultEntry, safe_link

pytestmark = pytest.mark.django_db
HTMX = {'HTTP_HX_REQUEST': 'true'}


def _entry(**values):
    data = {'client': values.pop('client', None) or ClientFactory(), 'title': 'Hosting',
            'url': 'panel.example.test', 'username': 'ada', 'password': 's3cret-pass', 'notes': 'Backup codes 1234'}
    data.update(values)
    return VaultEntry.objects.create(**data)


def _stored(entry):
    with connection.cursor() as cursor:
        cursor.execute('SELECT username, password, notes FROM vault_vaultentry WHERE id = %s', [entry.pk])
        return cursor.fetchone()


def test_secrets_are_stored_encrypted():
    entry = _entry()
    assert all(value.startswith('gAAAAA') for value in _stored(entry))
    entry.refresh_from_db()
    assert (entry.username, entry.password, entry.notes) == ('ada', 's3cret-pass', 'Backup codes 1234')


def test_safe_link():
    assert safe_link('panel.example.test') == 'https://panel.example.test'
    assert safe_link('javascript:alert(1)') == ''
    assert safe_link('') == ''


def test_the_list_hides_secrets_until_shown(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    entry = _entry()
    page = client.get(reverse('client_detail_vault', args=[entry.client_id]))
    assert page.status_code == 200
    assert b'Hosting' in page.content and b'ada' in page.content
    assert b's3cret-pass' not in page.content and b'Backup codes' not in page.content
    assert not VaultAccess.objects.exists()

    shown = client.get(reverse('vault_reveal', args=[entry.pk]), **HTMX)
    assert b's3cret-pass' in shown.content and b'Backup codes 1234' in shown.content
    assert shown['Cache-Control'] == 'no-store'

    copied = client.post(reverse('vault_copy', args=[entry.pk]), **HTMX)
    assert copied.content == b's3cret-pass'
    assert list(VaultAccess.objects.values_list('action', 'user')) == [
        (VaultAccess.COPY, admin.pk), (VaultAccess.SHOW, admin.pk),
    ]
    page = client.get(reverse('client_detail_vault', args=[entry.client_id]))
    assert b'Opened 2 times' in page.content


def test_opening_the_edit_form_counts_as_showing(client):
    client.force_login(AdminUserFactory())
    entry = _entry()
    assert client.get(reverse('vault_edit', args=[entry.pk]), **HTMX).status_code == 200
    assert VaultAccess.objects.filter(entry=entry, action=VaultAccess.SHOW).count() == 1


def test_create_edit_and_delete(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    customer = ClientFactory()
    assert client.get(reverse('vault_create', args=[customer.pk]) + '?kind=note', **HTMX).status_code == 200
    response = client.post(reverse('vault_create', args=[customer.pk]), {
        'kind': 'login', 'title': 'Instagram', 'url': 'https://instagram.com', 'username': 'shop',
        'password': 'pw', 'notes': '',
    }, **HTMX)
    trigger = json.loads(response['HX-Trigger'])
    assert trigger['infoToast']['message'] == 'Saved in the vault: Instagram' and 'vaultChanged' in trigger
    entry = VaultEntry.objects.get()
    assert entry.client == customer and entry.created_by == admin and entry.password == 'pw'

    # A note keeps no username or password.
    client.post(reverse('vault_edit', args=[entry.pk]), {
        'kind': 'note', 'title': 'Instagram', 'url': '', 'username': 'shop', 'password': 'pw', 'notes': 'codes',
    }, **HTMX)
    entry.refresh_from_db()
    assert (entry.kind, entry.username, entry.password, entry.notes) == ('note', '', '', 'codes')

    client.post(reverse('vault_delete', args=[entry.pk]), **HTMX)
    assert not VaultEntry.objects.exists()


def test_without_the_vault_permission_everything_is_refused(client):
    member = UserFactory()
    assert member.permission_preset.access_vault is False
    client.force_login(member)
    entry = _entry()
    for method, name, args in [
        ('get', 'vault_list', [entry.client_id]), ('get', 'vault_create', [entry.client_id]),
        ('get', 'vault_edit', [entry.pk]), ('post', 'vault_delete', [entry.pk]),
        ('get', 'vault_reveal', [entry.pk]), ('post', 'vault_copy', [entry.pk]),
    ]:
        response = getattr(client, method)(reverse(name, args=args), **HTMX)
        assert response.status_code in (302, 403), name
    assert VaultEntry.objects.exists() and not VaultAccess.objects.exists()


def test_the_client_page_offers_the_tab_only_with_the_permission(client):
    entry = _entry()
    member = UserFactory()
    member.permission_preset.clients_view_all = True
    member.permission_preset.save()
    client.force_login(member)
    page = client.get(reverse('client_detail', args=[entry.client_id]))
    if page.status_code == 200:
        assert reverse('client_detail_vault', args=[entry.client_id]).encode() not in page.content
    assert client.get(reverse('client_detail_vault', args=[entry.client_id])).status_code == 403


def test_the_seeded_admin_preset_has_the_vault():
    from apps.accounts.factories import admin_preset, member_preset

    assert admin_preset().access_vault is True
    assert member_preset().access_vault is False


def test_search_never_finds_the_vault():
    from apps.search.services import search

    _entry(title='Zanzibar hosting', notes='Zanzibar codes')
    results = search(AdminUserFactory(), 'Zanzibar')
    assert 'Zanzibar' not in repr({key: value for key, value in vars(results).items() if key != 'query'})

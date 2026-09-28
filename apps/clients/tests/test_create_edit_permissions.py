import re

import pytest
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.clients.models import Client
from apps.projects.factories import ProjectAccessFactory, ProjectFactory


def _preset(name, **overrides):
    fields = {
        'access_dashboard': True,
        'access_clients': True,
        'access_projects': True,
        'clients_view_all': False,
        'clients_create': False,
        'clients_edit': False,
    }
    fields.update(overrides)
    return PermissionPreset.objects.create(name=name, **fields)


def _user(name, **overrides):
    return UserFactory(permission_preset=_preset(name, **overrides))


def _attach(user, client_obj):
    project = ProjectFactory(client=client_obj, name=f'{client_obj.name} Project')
    ProjectAccessFactory(project=project, user=user)
    return project


def _checkbox_checked(html, name):
    match = re.search(rf'<input type="checkbox" name="{name}"([^>]*)>', html)
    assert match, name
    return 'checked' in match.group(1)


@pytest.mark.django_db
class TestPresetFlags:
    def test_seeded_admin_on_developer_and_custom_off(self):
        admin = PermissionPreset.objects.get(name='Admin')
        developer = PermissionPreset.objects.get(name='Developer')
        custom = PermissionPreset.objects.create(name='ExistingCustom')
        assert admin.clients_create is True
        assert admin.clients_edit is True
        assert developer.clients_create is False
        assert developer.clients_edit is False
        assert custom.clients_create is False
        assert custom.clients_edit is False

    def test_drawer_labels_defaults_and_save(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)

        create_html = client.get(reverse('preset_create')).content.decode()
        clients = create_html.split('data-module="clients"', 1)[1].split('data-module="projects"', 1)[0]
        assert 'Create' in clients
        assert 'Edit' in clients
        assert _checkbox_checked(create_html, 'clients_create') is False
        assert _checkbox_checked(create_html, 'clients_edit') is False

        admin_preset = PermissionPreset.objects.get(name='Admin')
        admin_html = client.get(reverse('preset_edit', args=[admin_preset.pk])).content.decode()
        assert _checkbox_checked(admin_html, 'clients_create') is True
        assert _checkbox_checked(admin_html, 'clients_edit') is True

        developer = PermissionPreset.objects.get(name='Developer')
        developer_html = client.get(reverse('preset_edit', args=[developer.pk])).content.decode()
        assert _checkbox_checked(developer_html, 'clients_create') is False
        assert _checkbox_checked(developer_html, 'clients_edit') is False

        response = client.post(reverse('preset_create'), {
            'name': 'ClientWriters',
            'access_dashboard': 'on',
            'access_clients': 'on',
            'clients_create': 'on',
            'clients_edit': 'on',
        })
        assert response.status_code == 200
        saved = PermissionPreset.objects.get(name='ClientWriters')
        assert saved.clients_create is True
        assert saved.clients_edit is True
        assert saved.clients_view_all is False


@pytest.mark.django_db
class TestFlagsOff:
    def test_no_add_or_edit_and_writes_forbidden(self, client):
        user = _user('FlagsOff')
        visible = ClientFactory(name='Visible Client')
        _attach(user, visible)
        client.force_login(user)

        listing = client.get(reverse('client_list'))
        assert listing.status_code == 200
        list_html = listing.content.decode()
        assert 'Add Client' not in list_html
        assert reverse('client_create_drawer') not in list_html

        detail = client.get(reverse('client_detail', args=[visible.pk]))
        assert detail.status_code == 200
        detail_html = detail.content.decode()
        assert reverse('client_edit_drawer', args=[visible.pk]) not in detail_html
        assert reverse('client_delete', args=[visible.pk]) not in detail_html

        assert client.get(reverse('client_create')).status_code == 403
        assert client.post(reverse('client_create'), {'name': 'Nope'}).status_code == 403
        assert client.get(reverse('client_create_drawer')).status_code == 403
        assert client.get(reverse('client_edit', args=[visible.pk])).status_code == 403
        assert client.post(
            reverse('client_edit', args=[visible.pk]),
            {'name': 'Renamed'},
        ).status_code == 403
        assert client.get(reverse('client_edit_drawer', args=[visible.pk])).status_code == 403
        assert client.post(reverse('client_delete', args=[visible.pk])).status_code == 403
        assert Client.objects.filter(pk=visible.pk, name='Visible Client').exists()

    def test_empty_state_hides_create_action(self, client):
        user = _user('EmptyFlagsOff')
        client.force_login(user)
        html = client.get(reverse('client_list')).content.decode()
        assert 'No clients yet' in html
        assert 'Add your first client' not in html
        assert 'Add Client' not in html


@pytest.mark.django_db
class TestCreateWithoutViewAll:
    def test_creator_can_open_new_client_but_not_edit_or_others(self, client):
        user = _user('Creators', clients_create=True)
        foreign = ClientFactory(name='Foreign Client')
        attached = ClientFactory(name='Attached Client')
        _attach(user, attached)
        client.force_login(user)

        list_html = client.get(reverse('client_list')).content.decode()
        assert 'Add Client' in list_html
        assert 'Attached Client' in list_html
        assert 'Foreign Client' not in list_html

        created = client.post(reverse('client_create'), {
            'name': 'Fresh Client',
            'email': 'fresh@client.com',
        })
        assert created.status_code == 302
        fresh = Client.objects.get(name='Fresh Client')
        assert fresh.created_by == user
        assert created.url == reverse('client_detail', args=[fresh.pk])

        detail = client.get(reverse('client_detail', args=[fresh.pk]))
        assert detail.status_code == 200
        assert 'Fresh Client' in detail.content.decode()
        assert reverse('client_edit_drawer', args=[fresh.pk]) not in detail.content.decode()
        assert client.get(reverse('client_edit', args=[fresh.pk])).status_code == 403
        assert client.get(reverse('client_edit_drawer', args=[fresh.pk])).status_code == 403

        assert client.get(reverse('client_detail', args=[attached.pk])).status_code == 200
        assert client.get(reverse('client_detail', args=[foreign.pk])).status_code == 404
        assert client.get(reverse('client_edit', args=[foreign.pk])).status_code == 404
        assert client.post(reverse('client_delete', args=[foreign.pk])).status_code == 404
        assert Client.objects.filter(pk=foreign.pk).exists()

        drawer = client.post(reverse('client_create_drawer'), {'name': 'Drawer Client'})
        assert drawer.status_code == 200
        drawer_client = Client.objects.get(name='Drawer Client')
        assert drawer_client.created_by == user
        assert client.get(reverse('client_detail', args=[drawer_client.pk])).status_code == 200

        listed = client.get(reverse('client_list')).content.decode()
        assert 'Fresh Client' in listed
        assert 'Drawer Client' in listed


@pytest.mark.django_db
class TestEditWithoutCreate:
    def test_can_edit_visible_client_only(self, client):
        user = _user('Editors', clients_edit=True)
        visible = ClientFactory(name='Editable Client', email='old@client.com')
        hidden = ClientFactory(name='Hidden Client')
        _attach(user, visible)
        client.force_login(user)

        assert client.get(reverse('client_create')).status_code == 403
        assert client.post(reverse('client_create'), {'name': 'Blocked'}).status_code == 403
        assert client.get(reverse('client_create_drawer')).status_code == 403
        assert not Client.objects.filter(name='Blocked').exists()

        list_html = client.get(reverse('client_list')).content.decode()
        assert 'Add Client' not in list_html

        detail = client.get(reverse('client_detail', args=[visible.pk]))
        assert reverse('client_edit_drawer', args=[visible.pk]) in detail.content.decode()
        assert reverse('client_delete', args=[visible.pk]) not in detail.content.decode()

        page = client.post(reverse('client_edit', args=[visible.pk]), {
            'name': 'Renamed Client',
            'email': 'new@client.com',
            'phone': '',
            'address': '',
            'notes': '',
        })
        assert page.status_code == 302
        visible.refresh_from_db()
        assert visible.name == 'Renamed Client'

        drawer = client.post(reverse('client_edit_drawer', args=[visible.pk]), {
            'name': 'Drawer Rename',
            'email': 'drawer@client.com',
            'phone': '',
            'address': '',
        })
        assert drawer.status_code == 200
        visible.refresh_from_db()
        assert visible.name == 'Drawer Rename'

        assert client.get(reverse('client_detail', args=[hidden.pk])).status_code == 404
        assert client.get(reverse('client_edit', args=[hidden.pk])).status_code == 404
        assert client.post(
            reverse('client_edit', args=[hidden.pk]),
            {'name': 'Should Not Land'},
        ).status_code == 404
        assert client.get(reverse('client_edit_drawer', args=[hidden.pk])).status_code == 404
        assert client.post(reverse('client_delete', args=[hidden.pk])).status_code == 404
        hidden.refresh_from_db()
        assert hidden.name == 'Hidden Client'


@pytest.mark.django_db
class TestBillingEditPermission:
    def test_member_without_clients_edit_cannot_change_billing_fields(self, client):
        user = _user('NoBillingEdit', clients_create=True)
        visible = ClientFactory(
            name='Visible Client',
            email='old@client.com',
            billing_name='Old Billing',
            billing_email='old-bills@client.com',
            tax_id='OLD-1',
        )
        _attach(user, visible)
        client.force_login(user)
        payload = {
            'name': 'Renamed Client',
            'email': 'new@client.com',
            'phone': '555',
            'address': 'New address',
            'notes': 'New notes',
            'billing_name': 'Hacked Billing',
            'billing_email': 'hack@client.com',
            'tax_id': 'NEW-9',
        }

        assert client.post(reverse('client_edit', args=[visible.pk]), payload).status_code == 403
        assert client.post(
            reverse('client_edit_drawer', args=[visible.pk]),
            payload,
        ).status_code == 403
        visible.refresh_from_db()
        assert visible.name == 'Visible Client'
        assert visible.billing_name == 'Old Billing'
        assert visible.billing_email == 'old-bills@client.com'
        assert visible.tax_id == 'OLD-1'


@pytest.mark.django_db
class TestDeleteStaysAdmin:
    def test_either_flag_does_not_allow_delete(self, client):
        user = _user('Writers', clients_create=True, clients_edit=True)
        visible = ClientFactory(name='Kept Client')
        _attach(user, visible)
        client.force_login(user)

        assert client.post(reverse('client_delete', args=[visible.pk])).status_code == 403
        assert Client.objects.filter(pk=visible.pk).exists()
        detail = client.get(reverse('client_detail', args=[visible.pk]))
        assert reverse('client_delete', args=[visible.pk]) not in detail.content.decode()

    def test_admin_can_create_edit_and_delete_with_flags_off(self, client):
        preset = _preset('AdminFlagsOff')
        admin = AdminUserFactory(permission_preset=preset)
        assert preset.clients_create is False
        assert preset.clients_edit is False
        assert admin.has_app_permission('clients_create') is True
        assert admin.has_app_permission('clients_edit') is True
        existing = ClientFactory(name='Admin Target')
        client.force_login(admin)

        created = client.post(reverse('client_create'), {'name': 'Admin Created'})
        assert created.status_code == 302
        made = Client.objects.get(name='Admin Created')
        assert made.created_by == admin
        assert client.get(reverse('client_detail', args=[made.pk])).status_code == 200

        edited = client.post(reverse('client_edit', args=[existing.pk]), {
            'name': 'Admin Edited',
            'email': '',
            'phone': '',
            'address': '',
            'notes': '',
        })
        assert edited.status_code == 302
        existing.refresh_from_db()
        assert existing.name == 'Admin Edited'

        detail = client.get(reverse('client_detail', args=[existing.pk]))
        html = detail.content.decode()
        assert reverse('client_edit_drawer', args=[existing.pk]) in html
        assert reverse('client_delete', args=[existing.pk]) in html
        assert 'Add Project' in client.get(
            reverse('client_detail_projects', args=[existing.pk])
        ).content.decode()

        deleted = client.post(reverse('client_delete', args=[existing.pk]))
        assert deleted.status_code == 302
        assert not Client.objects.filter(pk=existing.pk).exists()


def _record_menu(html):
    start = html.index('w-56 flex-shrink-0 border-r border-border-subtle bg-panel/50')
    return html[start:html.index('flex-1 overflow-y-auto', start)]


@pytest.mark.django_db
class TestRecordMenu:
    def test_client_name_heads_the_menu(self, client):
        user = _user('MenuViewer', clients_view_all=True)
        client_obj = ClientFactory(name='Northwind Studio')
        client.force_login(user)

        html = client.get(reverse('client_detail', args=[client_obj.pk])).content.decode()
        menu = _record_menu(html)
        assert '>Northwind Studio</div>' in menu
        assert 'Navigation' not in menu

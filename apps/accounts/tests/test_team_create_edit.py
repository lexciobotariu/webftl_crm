import pytest
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.models import User
from apps.accounts.permissions import PermissionPreset

PASSWORD = 'analytical-engine-1843'


def _preset(name, **flags):
    fields = {
        'access_dashboard': True,
        'access_team': True,
        'team_create': False,
        'team_edit': False,
    }
    fields.update(flags)
    return PermissionPreset.objects.create(name=name, **fields)


def _member(name, **flags):
    return UserFactory(role='member', permission_preset=_preset(name, **flags))


def _invite(client, *, email, role='member', preset_id=''):
    return client.post(reverse('user_create'), {
        'name': 'Ada Lovelace',
        'email': email,
        'role': role,
        'preset_id': preset_id,
        'password1': PASSWORD,
        'password2': PASSWORD,
    })


@pytest.mark.django_db
class TestTeamViewOnly:
    def test_list_and_read_only_drawer(self, client):
        viewer = _member('Viewers')
        target = UserFactory(name='Visible Person', email='visible@example.com')
        client.force_login(viewer)

        listing = client.get(reverse('team_list'))
        assert listing.status_code == 200
        page = listing.content.decode()
        assert 'Visible Person' in page
        assert 'title="View"' in page
        assert 'title="Edit"' not in page
        assert 'Add Member' not in page
        assert 'Manage Presets' not in page

        drawer = client.get(reverse('user_detail_drawer', args=[target.pk]))
        assert drawer.status_code == 200
        html = drawer.content.decode()
        assert 'View User' in html
        assert 'visible@example.com' in html
        assert 'name="name"' not in html
        assert 'name="email"' not in html
        assert 'name="role"' not in html
        assert 'name="preset_id"' not in html
        assert 'Save Changes' not in html
        assert 'Deactivate User' not in html
        assert 'Delete User' not in html

    def test_cannot_update_invite_or_deactivate(self, client):
        viewer = _member('ViewersOnly')
        target = UserFactory(name='Stay Put', role='member')
        client.force_login(viewer)

        update = client.post(reverse('user_update', args=[target.pk]), {
            'name': 'Changed',
            'email': 'changed@example.com',
            'role': 'admin',
        })
        assert update.status_code == 403
        invite = _invite(client, email='invited@example.com', role='admin')
        assert invite.status_code == 403
        deactivate = client.post(reverse('user_deactivate', args=[target.pk]))
        assert deactivate.status_code == 403

        target.refresh_from_db()
        assert target.name == 'Stay Put'
        assert target.role == 'member'
        assert target.is_active is True
        assert not User.objects.filter(email='invited@example.com').exists()


@pytest.mark.django_db
class TestTeamCreate:
    def test_invites_a_member_and_cannot_create_an_admin(self, client):
        inviter = _member('Inviters', team_create=True)
        client.force_login(inviter)

        listing = client.get(reverse('team_list'))
        page = listing.content.decode()
        assert 'Add Member' in page
        assert 'Manage Presets' not in page

        drawer = client.get(reverse('user_create'))
        assert drawer.status_code == 200
        assert b'value="admin"' not in drawer.content

        created = _invite(client, email='member@example.com', role='admin')
        assert created.status_code == 200
        user = User.objects.get(email='member@example.com')
        assert user.role == 'member'
        assert user.name == 'Ada Lovelace'
        assert client.login(email='member@example.com', password=PASSWORD)

    def test_admin_can_create_an_admin(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        drawer = client.get(reverse('user_create'))
        assert b'value="admin"' in drawer.content

        created = _invite(client, email='new-admin@example.com', role='admin')
        assert created.status_code == 200
        assert User.objects.get(email='new-admin@example.com').role == 'admin'


@pytest.mark.django_db
class TestTeamEdit:
    def test_changes_profile_and_active_state_not_role_or_delete(self, client):
        editor = _member('Editors', team_edit=True)
        target = UserFactory(name='Old Name', email='old@example.com', role='member')
        other = UserFactory(name='Other', is_active=True)
        admin_preset = PermissionPreset.objects.get(name='Admin')
        client.force_login(editor)

        listing = client.get(reverse('team_list'))
        assert 'title="Edit"' in listing.content.decode()
        assert 'Add Member' not in listing.content.decode()

        drawer = client.get(reverse('user_detail_drawer', args=[target.pk]))
        html = drawer.content.decode()
        assert 'Edit User' in html
        assert 'Save Changes' in html
        assert 'name="name"' in html
        assert 'name="preset_id"' in html
        assert 'name="role"' not in html
        assert 'Deactivate User' in html
        assert 'Delete User' not in html

        updated = client.post(reverse('user_update', args=[target.pk]), {
            'name': 'New Name',
            'email': 'new@example.com',
            'role': 'admin',
            'preset_id': admin_preset.pk,
        })
        assert updated.status_code == 200
        target.refresh_from_db()
        assert target.name == 'New Name'
        assert target.email == 'new@example.com'
        assert target.permission_preset == admin_preset
        assert target.role == 'member'
        assert target.is_admin is False

        deactivated = client.post(reverse('user_deactivate', args=[other.pk]))
        assert deactivated.status_code == 200
        other.refresh_from_db()
        assert other.is_active is False
        reactivated = client.post(reverse('user_deactivate', args=[other.pk]))
        assert reactivated.status_code == 200
        other.refresh_from_db()
        assert other.is_active is True

        denied = client.post(reverse('user_delete', args=[other.pk]))
        assert denied.status_code == 403
        assert User.objects.filter(pk=other.pk).exists()
        confirm = client.get(reverse('user_delete_confirm', args=[other.pk]))
        assert confirm.status_code == 403

    def test_cannot_deactivate_self_or_the_last_admin(self, client):
        editor = _member('EditorsLock', team_edit=True)
        last_admin = AdminUserFactory()
        client.force_login(editor)

        self_toggle = client.post(reverse('user_deactivate', args=[editor.pk]))
        assert self_toggle.status_code == 400
        editor.refresh_from_db()
        assert editor.is_active is True

        locked = client.post(reverse('user_deactivate', args=[last_admin.pk]))
        assert locked.status_code == 400
        last_admin.refresh_from_db()
        assert last_admin.is_active is True


@pytest.mark.django_db
class TestTeamAdminOnly:
    def test_member_cannot_manage_presets(self, client):
        member = _member('PresetBlocked', team_create=True, team_edit=True)
        target = PermissionPreset.objects.create(name='Untouched')
        client.force_login(member)

        assert client.get(reverse('preset_list')).status_code == 403
        assert client.get(reverse('preset_create')).status_code == 403
        assert client.post(reverse('preset_create'), {'name': 'Smuggled'}).status_code == 403
        assert client.get(reverse('preset_edit', args=[target.pk])).status_code == 403
        assert client.post(
            reverse('preset_edit', args=[target.pk]),
            {'name': 'Renamed', 'access_team': 'on'},
        ).status_code == 403
        assert client.post(reverse('preset_delete', args=[target.pk])).status_code == 403
        target.refresh_from_db()
        assert target.name == 'Untouched'
        assert not PermissionPreset.objects.filter(name='Smuggled').exists()

    def test_admin_changes_role_and_presets_and_blocks_stay(self, client):
        from apps.salaries.models import EmployeeSalary

        admin = AdminUserFactory()
        target = UserFactory(role='member')
        victim = UserFactory()
        paid = UserFactory()
        EmployeeSalary.objects.create(user=paid, base_salary='5000.00', currency='EUR')
        client.force_login(admin)

        page = client.get(reverse('team_list')).content.decode()
        assert 'Manage Presets' in page
        assert 'Add Member' in page

        demoted = client.post(reverse('user_update', args=[admin.pk]), {
            'name': admin.name,
            'email': admin.email,
            'role': 'member',
        })
        assert demoted.status_code == 200
        admin.refresh_from_db()
        assert admin.role == 'admin'
        assert b'last' in demoted.content.lower()

        promoted = client.post(reverse('user_update', args=[target.pk]), {
            'name': target.name,
            'email': target.email,
            'role': 'admin',
        })
        assert promoted.status_code == 200
        target.refresh_from_db()
        assert target.role == 'admin'

        deleted = client.post(reverse('user_delete', args=[victim.pk]))
        assert deleted.status_code == 200
        assert not User.objects.filter(pk=victim.pk).exists()

        blocked = client.post(reverse('user_delete', args=[paid.pk]))
        assert blocked.status_code == 400
        assert User.objects.filter(pk=paid.pk).exists()

        created = client.post(reverse('preset_create'), {
            'name': 'Ops',
            'access_team': 'on',
            'team_create': 'on',
        })
        assert created.status_code == 200
        preset = PermissionPreset.objects.get(name='Ops')
        assert preset.team_create is True
        assert preset.team_edit is False

        edited = client.post(reverse('preset_edit', args=[preset.pk]), {
            'name': 'Ops',
            'access_team': 'on',
            'team_edit': 'on',
        })
        assert edited.status_code == 200
        preset.refresh_from_db()
        assert preset.team_edit is True
        assert preset.team_create is False

        removed = client.post(reverse('preset_delete', args=[preset.pk]))
        assert removed.status_code == 200
        assert not PermissionPreset.objects.filter(name='Ops').exists()

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.decorators import require_permission
from apps.accounts.permissions import PermissionPreset, PERMISSION_KEYS
from apps.accounts.factories import UserFactory, AdminUserFactory


@pytest.mark.django_db
class TestPermissionPreset:
    def test_permission_keys_defined(self):
        """PERMISSION_KEYS should list all app-level permissions."""
        assert 'access_clients' in PERMISSION_KEYS
        assert 'access_projects' in PERMISSION_KEYS
        assert 'access_salaries' in PERMISSION_KEYS
        assert 'access_team' in PERMISSION_KEYS
        assert 'access_tasks' in PERMISSION_KEYS
        assert 'access_todos' in PERMISSION_KEYS
        assert 'access_notes' in PERMISSION_KEYS
        assert 'access_dashboard' in PERMISSION_KEYS

    def test_create_preset(self):
        """Can create a preset with specific permissions."""
        preset = PermissionPreset.objects.create(
            name='Test Preset',
            access_clients=False,
            access_salaries=False,
        )
        assert preset.name == 'Test Preset'
        assert preset.access_clients is False
        assert preset.access_salaries is False
        assert preset.access_projects is True
        assert preset.access_dashboard is True

    def test_preset_str(self):
        preset = PermissionPreset.objects.create(name='Test Role')
        assert str(preset) == 'Test Role'

    def test_preset_has_permission(self):
        preset = PermissionPreset.objects.create(
            name='Limited',
            access_clients=False,
            access_salaries=False,
        )
        assert preset.has_permission('access_projects') is True
        assert preset.has_permission('access_clients') is False
        assert preset.has_permission('access_salaries') is False

    def test_preset_has_permission_invalid_key(self):
        preset = PermissionPreset.objects.create(name='Test')
        assert preset.has_permission('nonexistent_key') is False


@pytest.mark.django_db
class TestUserPermissions:
    def test_admin_has_all_permissions(self):
        """Admins bypass preset checks — always return True."""
        admin = AdminUserFactory()
        assert admin.has_app_permission('access_clients') is True
        assert admin.has_app_permission('access_salaries') is True
        assert admin.has_app_permission('access_team') is True

    def test_user_with_preset(self):
        """User with a preset uses the preset's permissions."""
        preset = PermissionPreset.objects.create(
            name='Dev',
            access_clients=False,
            access_salaries=False,
            access_team=False,
        )
        user = UserFactory(permission_preset=preset)
        assert user.has_app_permission('access_projects') is True
        assert user.has_app_permission('access_clients') is False
        assert user.has_app_permission('access_salaries') is False

    def test_user_without_preset_denied(self):
        """User without a preset should be denied non-dashboard access."""
        user = UserFactory(permission_preset=None)
        assert user.has_app_permission('access_dashboard') is True
        assert user.has_app_permission('access_clients') is False
        assert user.has_app_permission('access_projects') is False


@pytest.mark.django_db
class TestDefaultPresets:
    def test_admin_preset_exists(self):
        """Admin preset should exist with all permissions True."""
        preset = PermissionPreset.objects.get(name='Admin')
        assert preset.is_system is True
        for key in PERMISSION_KEYS:
            assert preset.has_permission(key) is True

    def test_developer_preset_exists(self):
        """Developer preset should exist with restricted permissions."""
        preset = PermissionPreset.objects.get(name='Developer')
        assert preset.is_system is True
        assert preset.access_dashboard is True
        assert preset.access_projects is True
        assert preset.access_tasks is True
        assert preset.access_todos is True
        assert preset.access_notes is True
        assert preset.access_clients is False
        assert preset.access_salaries is False
        assert preset.access_team is False


@pytest.mark.django_db
class TestRequirePermissionDecorator:
    def _make_request(self, user):
        factory = RequestFactory()
        request = factory.get('/test/')
        request.user = user
        return request

    def test_admin_passes_any_permission(self):
        admin = AdminUserFactory()
        request = self._make_request(admin)

        @require_permission('access_salaries')
        def view(request):
            from django.http import HttpResponse
            return HttpResponse('ok')

        response = view(request)
        assert response.status_code == 200

    def test_user_with_permission_passes(self):
        preset = PermissionPreset.objects.create(
            name='WithAccess',
            access_projects=True,
        )
        user = UserFactory(permission_preset=preset)
        request = self._make_request(user)

        @require_permission('access_projects')
        def view(request):
            from django.http import HttpResponse
            return HttpResponse('ok')

        response = view(request)
        assert response.status_code == 200

    def test_user_without_permission_gets_403(self):
        preset = PermissionPreset.objects.create(
            name='NoClients',
            access_clients=False,
        )
        user = UserFactory(permission_preset=preset)
        request = self._make_request(user)

        @require_permission('access_clients')
        def view(request):
            from django.http import HttpResponse
            return HttpResponse('ok')

        response = view(request)
        assert response.status_code == 403

    def test_user_without_preset_gets_403(self):
        user = UserFactory(permission_preset=None)
        request = self._make_request(user)

        @require_permission('access_projects')
        def view(request):
            from django.http import HttpResponse
            return HttpResponse('ok')

        response = view(request)
        assert response.status_code == 403


@pytest.mark.django_db
class TestPermissionsContextProcessor:
    def test_permissions_in_template_context(self, client):
        """Logged-in user should have 'perms_map' in template context."""
        preset = PermissionPreset.objects.create(
            name='TestPreset',
            access_clients=False,
            access_salaries=False,
        )
        user = UserFactory(permission_preset=preset)
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert 'perms_map' in response.context
        assert response.context['perms_map']['access_dashboard'] is True
        assert response.context['perms_map']['access_clients'] is False
        assert response.context['perms_map']['access_salaries'] is False
        assert response.context['perms_map']['access_projects'] is True

    def test_admin_permissions_all_true(self, client):
        """Admin should have all permissions True in context."""
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('dashboard'))
        perms = response.context['perms_map']
        for key in PERMISSION_KEYS:
            assert perms[key] is True

    def test_anonymous_user_no_perms(self, client):
        """Anonymous requests should have empty perms_map."""
        from config.context_processors import permissions
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser

        factory = RequestFactory()
        request = factory.get('/')
        request.user = AnonymousUser()
        result = permissions(request)
        assert result['perms_map'] == {}


@pytest.mark.django_db
class TestViewEnforcement:
    def test_client_list_denied_for_developer(self, client):
        """Developer preset should not access client list."""
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        client.force_login(user)
        response = client.get(reverse('client_list'))
        assert response.status_code == 403

    def test_salary_list_denied_for_developer(self, client):
        """Developer preset should not access salary list."""
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        client.force_login(user)
        response = client.get(reverse('salary_list'))
        assert response.status_code == 403

    def test_team_list_denied_for_developer(self, client):
        """Developer preset should not access team list."""
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        client.force_login(user)
        response = client.get(reverse('team_list'))
        assert response.status_code == 403

    def test_admin_accesses_all_views(self, client):
        """Admin should access all views regardless of preset."""
        admin = AdminUserFactory()
        client.force_login(admin)
        assert client.get(reverse('client_list')).status_code == 200
        assert client.get(reverse('salary_list')).status_code == 200
        assert client.get(reverse('team_list')).status_code == 200

    def test_project_list_allowed_for_developer(self, client):
        """Developer preset should access project list."""
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        client.force_login(user)
        response = client.get(reverse('project_list'))
        assert response.status_code == 200


@pytest.mark.django_db
class TestSidebarPermissions:
    def test_sidebar_hides_clients_for_developer(self, client):
        """Developer preset should not see Clients link in sidebar."""
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        content = response.content.decode()
        assert 'Clients' not in content
        assert 'Salaries' not in content
        assert 'Team' not in content
        # Should still see these
        assert 'Dashboard' in content
        assert 'Projects' in content
        assert 'My Tasks' in content

    def test_sidebar_shows_all_for_admin(self, client):
        """Admin should see all sidebar links."""
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('dashboard'))
        content = response.content.decode()
        assert 'Clients' in content
        assert 'Projects' in content
        assert 'Salaries' in content
        assert 'Team' in content


@pytest.mark.django_db
class TestUserDetailDrawer:
    def test_drawer_requires_team_permission(self, client):
        """Non-admin without team access should get 403."""
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        target = UserFactory()
        client.force_login(user)
        response = client.get(reverse('user_detail_drawer', args=[target.pk]))
        assert response.status_code == 403

    def test_drawer_requires_admin_role(self, client):
        """Non-admin user with access_team permission should still get 403."""
        preset = PermissionPreset.objects.create(name='TeamViewer', access_team=True)
        user = UserFactory(permission_preset=preset)
        target = UserFactory()
        client.force_login(user)
        response = client.get(reverse('user_detail_drawer', args=[target.pk]))
        assert response.status_code == 403

    def test_drawer_shows_user_info(self, client):
        """Drawer should display user name, email, and current preset."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Developer')
        target = UserFactory(name='John Doe', email='john@test.com', permission_preset=preset)
        client.force_login(admin)
        response = client.get(reverse('user_detail_drawer', args=[target.pk]))
        content = response.content.decode()
        assert 'John Doe' in content
        assert 'john@test.com' in content
        assert response.status_code == 200

    def test_drawer_lists_all_presets(self, client):
        """Drawer should list all available presets in a dropdown."""
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.get(reverse('user_detail_drawer', args=[target.pk]))
        content = response.content.decode()
        assert 'Admin' in content
        assert 'Developer' in content


@pytest.mark.django_db
class TestUpdatePreset:
    def test_assign_preset_to_user(self, client):
        """Admin can assign a preset to a user."""
        admin = AdminUserFactory()
        target = UserFactory(permission_preset=None)
        preset = PermissionPreset.objects.get(name='Developer')
        client.force_login(admin)
        response = client.post(
            reverse('update_preset', args=[target.pk]),
            {'preset_id': preset.pk},
        )
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.permission_preset == preset

    def test_clear_preset_from_user(self, client):
        """Admin can clear a user's preset by sending empty preset_id."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Developer')
        target = UserFactory(permission_preset=preset)
        client.force_login(admin)
        response = client.post(
            reverse('update_preset', args=[target.pk]),
            {'preset_id': ''},
        )
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.permission_preset is None

    def test_update_preset_requires_admin(self, client):
        """Only admins can update presets."""
        preset = PermissionPreset.objects.create(name='WithTeam', access_team=True)
        user = UserFactory(permission_preset=preset)
        target = UserFactory()
        dev_preset = PermissionPreset.objects.get(name='Developer')
        client.force_login(user)
        response = client.post(
            reverse('update_preset', args=[target.pk]),
            {'preset_id': dev_preset.pk},
        )
        assert response.status_code == 403

    def test_update_preset_returns_updated_row(self, client):
        """After updating preset, response should contain the new preset name."""
        admin = AdminUserFactory()
        target = UserFactory(permission_preset=None)
        preset = PermissionPreset.objects.get(name='Developer')
        client.force_login(admin)
        response = client.post(
            reverse('update_preset', args=[target.pk]),
            {'preset_id': preset.pk},
        )
        assert 'Developer' in response.content.decode()


@pytest.mark.django_db
class TestPresetList:
    def test_preset_list_requires_admin(self, client):
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        client.force_login(user)
        response = client.get(reverse('preset_list'))
        assert response.status_code == 403

    def test_preset_list_shows_presets(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('preset_list'))
        content = response.content.decode()
        assert response.status_code == 200
        assert 'Admin' in content
        assert 'Developer' in content

    def test_preset_list_shows_user_count(self, client):
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Developer')
        UserFactory(permission_preset=preset)
        UserFactory(permission_preset=preset)
        client.force_login(admin)
        response = client.get(reverse('preset_list'))
        assert response.status_code == 200

    def test_preset_list_shows_permission_badges(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('preset_list'))
        content = response.content.decode()
        assert 'Projects' in content

    def test_team_list_has_manage_presets_link(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert 'Manage Presets' in response.content.decode()


@pytest.mark.django_db
class TestTeamPresetDisplay:
    def test_team_list_shows_preset_column(self, client):
        """Team list should show a Preset column header."""
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert 'Preset' in response.content.decode()

    def test_team_list_shows_user_preset_name(self, client):
        """Team list should show the assigned preset name for each user."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Developer')
        dev = UserFactory(name='Dev User', permission_preset=preset)
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        content = response.content.decode()
        assert 'Developer' in content

    def test_team_list_shows_no_preset_label(self, client):
        """Users without a preset should show 'No preset' label."""
        admin = AdminUserFactory()
        member = UserFactory(name='New User', permission_preset=None)
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert 'No preset' in response.content.decode()

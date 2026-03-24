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

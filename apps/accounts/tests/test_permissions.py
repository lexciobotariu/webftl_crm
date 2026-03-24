import pytest
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

import pytest
from apps.accounts.permissions import PermissionPreset, PERMISSION_KEYS


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
        preset = PermissionPreset.objects.create(name='Developer')
        assert str(preset) == 'Developer'

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

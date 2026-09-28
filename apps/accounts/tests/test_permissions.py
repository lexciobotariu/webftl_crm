import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.decorators import require_permission
from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PERMISSION_KEYS, PermissionPreset


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
        assert 'notes_view_all' in PERMISSION_KEYS
        assert 'notes_edit_public' in PERMISSION_KEYS
        assert 'access_dashboard' in PERMISSION_KEYS
        assert 'clients_view_all' in PERMISSION_KEYS
        assert 'clients_create' in PERMISSION_KEYS
        assert 'clients_edit' in PERMISSION_KEYS
        assert 'projects_view_all' in PERMISSION_KEYS
        assert 'projects_create' in PERMISSION_KEYS
        assert 'projects_edit_own' in PERMISSION_KEYS
        assert 'projects_edit_all' in PERMISSION_KEYS
        assert 'tasks_view_all' in PERMISSION_KEYS
        assert 'tasks_create' in PERMISSION_KEYS
        assert 'tasks_edit_own' in PERMISSION_KEYS
        assert 'tasks_edit_all' in PERMISSION_KEYS
        assert 'salaries_view_all' in PERMISSION_KEYS
        assert 'salaries_edit' in PERMISSION_KEYS
        assert 'access_invoices' in PERMISSION_KEYS
        assert 'invoices_view_all' in PERMISSION_KEYS
        assert 'invoices_create' in PERMISSION_KEYS
        assert 'invoices_edit' in PERMISSION_KEYS
        assert 'team_create' in PERMISSION_KEYS
        assert 'team_edit' in PERMISSION_KEYS

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
        assert preset.notes_view_all is False
        assert preset.notes_edit_public is False

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
        assert preset.notes_view_all is False
        assert preset.notes_edit_public is False
        assert preset.access_clients is False
        assert preset.access_salaries is False
        assert preset.access_team is False
        assert preset.clients_view_all is False
        assert preset.clients_create is False
        assert preset.clients_edit is False
        assert preset.projects_view_all is False
        assert preset.projects_create is False
        assert preset.projects_edit_own is False
        assert preset.projects_edit_all is False
        assert preset.tasks_view_all is False
        assert preset.tasks_create is False
        assert preset.tasks_edit_own is False
        assert preset.tasks_edit_all is False
        assert preset.salaries_view_all is False
        assert preset.salaries_edit is False
        assert preset.access_invoices is False
        assert preset.invoices_view_all is False
        assert preset.invoices_create is False
        assert preset.invoices_edit is False
        assert preset.team_create is False
        assert preset.team_edit is False


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
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from config.context_processors import permissions

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

    def test_drawer_open_with_access_team(self, client):
        """access_team opens a read-only drawer. Role is not required."""
        preset = PermissionPreset.objects.create(name='TeamViewer', access_team=True)
        user = UserFactory(permission_preset=preset)
        target = UserFactory()
        client.force_login(user)
        response = client.get(reverse('user_detail_drawer', args=[target.pk]))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'View User' in content
        assert 'Save Changes' not in content
        assert 'name="name"' not in content
        assert 'Deactivate User' not in content
        assert 'Delete User' not in content

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
            reverse('user_update', args=[target.pk]),
            {'name': target.name, 'email': target.email, 'role': target.role, 'preset_id': preset.pk},
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
            reverse('user_update', args=[target.pk]),
            {'name': target.name, 'email': target.email, 'role': target.role, 'preset_id': ''},
        )
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.permission_preset is None

    def test_update_preset_with_access_team(self, client):
        """access_team alone cannot assign presets. That needs team_edit."""
        preset = PermissionPreset.objects.create(name='WithTeam', access_team=True)
        user = UserFactory(permission_preset=preset)
        target = UserFactory()
        original = target.permission_preset
        dev_preset = PermissionPreset.objects.get(name='Developer')
        client.force_login(user)
        response = client.post(
            reverse('user_update', args=[target.pk]),
            {'name': 'Renamed', 'email': target.email, 'role': 'admin', 'preset_id': dev_preset.pk},
        )
        assert response.status_code == 403
        target.refresh_from_db()
        assert target.permission_preset == original
        assert target.name != 'Renamed'
        assert target.role != 'admin'

    def test_update_preset_returns_updated_row(self, client):
        """After updating preset, response should contain the new preset name."""
        admin = AdminUserFactory()
        target = UserFactory(permission_preset=None)
        preset = PermissionPreset.objects.get(name='Developer')
        client.force_login(admin)
        response = client.post(
            reverse('user_update', args=[target.pk]),
            {'name': target.name, 'email': target.email, 'role': target.role, 'preset_id': preset.pk},
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
        UserFactory(name='Dev User', permission_preset=preset)
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        content = response.content.decode()
        assert 'Developer' in content

    def test_team_list_shows_no_preset_label(self, client):
        """Users without a preset should show 'No preset' label."""
        admin = AdminUserFactory()
        UserFactory(name='New User', permission_preset=None)
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert 'No preset' in response.content.decode()


@pytest.mark.django_db
class TestPresetCreate:
    def test_create_preset_requires_admin(self, client):
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        client.force_login(user)
        response = client.post(reverse('preset_create'), {'name': 'New Preset'})
        assert response.status_code == 403

    def test_create_preset_success(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('preset_create'), {
            'name': 'Contractor',
            'description': 'External contractors',
            'access_dashboard': 'on',
            'access_projects': 'on',
            'access_tasks': 'on',
        })
        assert response.status_code == 200
        preset = PermissionPreset.objects.get(name='Contractor')
        assert preset.access_dashboard is True
        assert preset.access_projects is True
        assert preset.access_tasks is True
        assert preset.access_clients is False
        assert preset.access_salaries is False
        assert preset.clients_view_all is False
        assert preset.clients_create is False
        assert preset.clients_edit is False
        assert preset.projects_view_all is False
        assert preset.projects_create is False
        assert preset.projects_edit_own is False
        assert preset.projects_edit_all is False
        assert preset.tasks_view_all is False
        assert preset.tasks_create is False
        assert preset.tasks_edit_own is False
        assert preset.tasks_edit_all is False
        assert preset.access_notes is False
        assert preset.notes_view_all is False
        assert preset.notes_edit_public is False
        assert preset.salaries_view_all is False
        assert preset.salaries_edit is False
        assert preset.access_invoices is False
        assert preset.invoices_view_all is False
        assert preset.invoices_create is False
        assert preset.invoices_edit is False
        assert preset.team_create is False
        assert preset.team_edit is False

    def test_create_preset_returns_item(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('preset_create'), {
            'name': 'Viewer',
            'access_dashboard': 'on',
        })
        assert response.status_code == 200
        assert 'refreshPresetList' in response.get('HX-Trigger', '')
        assert PermissionPreset.objects.filter(name='Viewer').exists()

    def test_create_preset_duplicate_name_fails(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('preset_create'), {'name': 'Developer'})
        assert response.status_code == 200
        assert PermissionPreset.objects.filter(name='Developer').count() == 1


@pytest.mark.django_db
class TestPresetEdit:
    def test_edit_preset_get_shows_form(self, client):
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Developer')
        client.force_login(admin)
        response = client.get(reverse('preset_edit', args=[preset.pk]))
        content = response.content.decode()
        assert 'Developer' in content
        assert response.status_code == 200

    def test_edit_preset_updates_permissions(self, client):
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.create(name='Custom', access_clients=False)
        client.force_login(admin)
        response = client.post(reverse('preset_edit', args=[preset.pk]), {
            'name': 'Custom',
            'description': 'Updated',
            'access_dashboard': 'on',
            'access_clients': 'on',
            'access_projects': 'on',
            'access_tasks': 'on',
            'access_todos': 'on',
            'access_notes': 'on',
        })
        assert response.status_code == 200
        preset.refresh_from_db()
        assert preset.access_clients is True
        assert preset.description == 'Updated'

    def test_edit_system_preset_cannot_change_name(self, client):
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Developer')
        client.force_login(admin)
        response = client.post(reverse('preset_edit', args=[preset.pk]), {
            'name': 'Renamed',
            'access_dashboard': 'on',
            'access_projects': 'on',
        })
        assert response.status_code == 200
        preset.refresh_from_db()
        assert preset.name == 'Developer'


def _card(html, module):
    marker = f'data-module="{module}"'
    start = html.index(marker)
    nxt = html.find('data-module="', start + len(marker))
    return html[start:] if nxt == -1 else html[start:nxt]


def _checkbox_attrs(html, name):
    needle = f'<input type="checkbox" name="{name}"'
    start = html.index(needle) + len(needle)
    return html[start:html.index('>', start)]


@pytest.mark.django_db
class TestPresetModuleCards:
    def test_clients_access_off_clears_posted_extras(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)

        created = client.post(reverse('preset_create'), {
            'name': 'No Client Access',
            'access_projects': 'on',
            'projects_view_all': 'on',
            'clients_view_all': 'on',
            'clients_create': 'on',
            'clients_edit': 'on',
        })
        assert created.status_code == 200
        preset = PermissionPreset.objects.get(name='No Client Access')
        assert preset.access_clients is False
        assert preset.clients_view_all is False
        assert preset.clients_create is False
        assert preset.clients_edit is False
        assert preset.access_projects is True
        assert preset.projects_view_all is True

        existing = PermissionPreset.objects.create(
            name='Client Writers',
            access_clients=True,
            clients_view_all=True,
            clients_create=True,
            clients_edit=True,
            access_projects=True,
            projects_view_all=True,
        )
        edited = client.post(reverse('preset_edit', args=[existing.pk]), {
            'name': 'Client Writers',
            'access_projects': 'on',
            'projects_view_all': 'on',
            'clients_view_all': 'on',
            'clients_create': 'on',
            'clients_edit': 'on',
        })
        assert edited.status_code == 200
        existing.refresh_from_db()
        assert existing.access_clients is False
        assert existing.clients_view_all is False
        assert existing.clients_create is False
        assert existing.clients_edit is False
        assert existing.projects_view_all is True

    def test_projects_access_off_clears_posted_view_all(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)

        created = client.post(reverse('preset_create'), {
            'name': 'No Project Access',
            'access_clients': 'on',
            'clients_view_all': 'on',
            'clients_create': 'on',
            'clients_edit': 'on',
            'projects_view_all': 'on',
            'projects_create': 'on',
            'projects_edit_own': 'on',
            'projects_edit_all': 'on',
        })
        assert created.status_code == 200
        preset = PermissionPreset.objects.get(name='No Project Access')
        assert preset.access_projects is False
        assert preset.projects_view_all is False
        assert preset.projects_create is False
        assert preset.projects_edit_own is False
        assert preset.projects_edit_all is False
        assert preset.access_clients is True
        assert preset.clients_view_all is True
        assert preset.clients_create is True
        assert preset.clients_edit is True

        existing = PermissionPreset.objects.create(
            name='Project Viewers',
            access_projects=True,
            projects_view_all=True,
            projects_create=True,
            projects_edit_own=True,
            projects_edit_all=True,
            access_clients=True,
            clients_view_all=True,
        )
        edited = client.post(reverse('preset_edit', args=[existing.pk]), {
            'name': 'Project Viewers',
            'access_clients': 'on',
            'clients_view_all': 'on',
            'projects_view_all': 'on',
            'projects_create': 'on',
            'projects_edit_own': 'on',
            'projects_edit_all': 'on',
        })
        assert edited.status_code == 200
        existing.refresh_from_db()
        assert existing.access_projects is False
        assert existing.projects_view_all is False
        assert existing.projects_create is False
        assert existing.projects_edit_own is False
        assert existing.projects_edit_all is False
        assert existing.clients_view_all is True

    def test_tasks_access_off_clears_posted_extras(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)

        created = client.post(reverse('preset_create'), {
            'name': 'No Task Access',
            'access_projects': 'on',
            'projects_view_all': 'on',
            'tasks_view_all': 'on',
            'tasks_create': 'on',
            'tasks_edit_own': 'on',
            'tasks_edit_all': 'on',
        })
        assert created.status_code == 200
        preset = PermissionPreset.objects.get(name='No Task Access')
        assert preset.access_tasks is False
        assert preset.tasks_view_all is False
        assert preset.tasks_create is False
        assert preset.tasks_edit_own is False
        assert preset.tasks_edit_all is False
        assert preset.access_projects is True
        assert preset.projects_view_all is True

        existing = PermissionPreset.objects.create(
            name='Task Writers',
            access_tasks=True,
            tasks_view_all=True,
            tasks_create=True,
            tasks_edit_own=True,
            tasks_edit_all=True,
            access_projects=True,
            projects_view_all=True,
        )
        edited = client.post(reverse('preset_edit', args=[existing.pk]), {
            'name': 'Task Writers',
            'access_projects': 'on',
            'projects_view_all': 'on',
            'tasks_view_all': 'on',
            'tasks_create': 'on',
            'tasks_edit_own': 'on',
            'tasks_edit_all': 'on',
        })
        assert edited.status_code == 200
        existing.refresh_from_db()
        assert existing.access_tasks is False
        assert existing.tasks_view_all is False
        assert existing.tasks_create is False
        assert existing.tasks_edit_own is False
        assert existing.tasks_edit_all is False
        assert existing.projects_view_all is True

        saved = client.post(reverse('preset_create'), {
            'name': 'Task Flags On',
            'access_tasks': 'on',
            'tasks_view_all': 'on',
            'tasks_create': 'on',
            'tasks_edit_own': 'on',
            'tasks_edit_all': 'on',
        })
        assert saved.status_code == 200
        writers = PermissionPreset.objects.get(name='Task Flags On')
        assert writers.access_tasks is True
        assert writers.tasks_view_all is True
        assert writers.tasks_create is True
        assert writers.tasks_edit_own is True
        assert writers.tasks_edit_all is True

        off = PermissionPreset.objects.create(name='Tasks Closed', access_tasks=False)
        html = client.get(reverse('preset_edit', args=[off.pk])).content.decode()
        for name in (
            'tasks_view_all',
            'tasks_create',
            'tasks_edit_own',
            'tasks_edit_all',
        ):
            attrs = _checkbox_attrs(html, name)
            assert 'checked' not in attrs.split()
            assert 'disabled' in attrs.split()

    def test_salaries_access_off_clears_posted_extras(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)

        created = client.post(reverse('preset_create'), {
            'name': 'No Salary Access',
            'access_projects': 'on',
            'projects_view_all': 'on',
            'salaries_view_all': 'on',
            'salaries_edit': 'on',
        })
        assert created.status_code == 200
        preset = PermissionPreset.objects.get(name='No Salary Access')
        assert preset.access_salaries is False
        assert preset.salaries_view_all is False
        assert preset.salaries_edit is False
        assert preset.access_projects is True
        assert preset.projects_view_all is True

        existing = PermissionPreset.objects.create(
            name='Payroll Writers',
            access_salaries=True,
            salaries_view_all=True,
            salaries_edit=True,
            access_projects=True,
            projects_view_all=True,
        )
        edited = client.post(reverse('preset_edit', args=[existing.pk]), {
            'name': 'Payroll Writers',
            'access_projects': 'on',
            'projects_view_all': 'on',
            'salaries_view_all': 'on',
            'salaries_edit': 'on',
        })
        assert edited.status_code == 200
        existing.refresh_from_db()
        assert existing.access_salaries is False
        assert existing.salaries_view_all is False
        assert existing.salaries_edit is False
        assert existing.projects_view_all is True

        saved = client.post(reverse('preset_create'), {
            'name': 'Salary Flags On',
            'access_salaries': 'on',
            'salaries_view_all': 'on',
            'salaries_edit': 'on',
        })
        assert saved.status_code == 200
        writers = PermissionPreset.objects.get(name='Salary Flags On')
        assert writers.access_salaries is True
        assert writers.salaries_view_all is True
        assert writers.salaries_edit is True

        off = PermissionPreset.objects.create(name='Salaries Closed', access_salaries=False)
        html = client.get(reverse('preset_edit', args=[off.pk])).content.decode()
        for name in ('salaries_view_all', 'salaries_edit'):
            attrs = _checkbox_attrs(html, name)
            assert 'checked' not in attrs.split()
            assert 'disabled' in attrs.split()

    def test_invoices_access_off_clears_posted_extras(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)

        created = client.post(reverse('preset_create'), {
            'name': 'No Invoice Access',
            'access_projects': 'on',
            'projects_view_all': 'on',
            'invoices_view_all': 'on',
            'invoices_create': 'on',
            'invoices_edit': 'on',
        })
        assert created.status_code == 200
        preset = PermissionPreset.objects.get(name='No Invoice Access')
        assert preset.access_invoices is False
        assert preset.invoices_view_all is False
        assert preset.invoices_create is False
        assert preset.invoices_edit is False
        assert preset.access_projects is True
        assert preset.projects_view_all is True

        existing = PermissionPreset.objects.create(
            name='Invoice Writers',
            access_invoices=True,
            invoices_view_all=True,
            invoices_create=True,
            invoices_edit=True,
            access_projects=True,
            projects_view_all=True,
        )
        edited = client.post(reverse('preset_edit', args=[existing.pk]), {
            'name': 'Invoice Writers',
            'access_projects': 'on',
            'projects_view_all': 'on',
            'invoices_view_all': 'on',
            'invoices_create': 'on',
            'invoices_edit': 'on',
        })
        assert edited.status_code == 200
        existing.refresh_from_db()
        assert existing.access_invoices is False
        assert existing.invoices_view_all is False
        assert existing.invoices_create is False
        assert existing.invoices_edit is False
        assert existing.projects_view_all is True

        saved = client.post(reverse('preset_create'), {
            'name': 'Invoice Flags On',
            'access_invoices': 'on',
            'invoices_view_all': 'on',
            'invoices_create': 'on',
            'invoices_edit': 'on',
        })
        assert saved.status_code == 200
        writers = PermissionPreset.objects.get(name='Invoice Flags On')
        assert writers.access_invoices is True
        assert writers.invoices_view_all is True
        assert writers.invoices_create is True
        assert writers.invoices_edit is True

        off = PermissionPreset.objects.create(name='Invoices Closed', access_invoices=False)
        html = client.get(reverse('preset_edit', args=[off.pk])).content.decode()
        for name in ('invoices_view_all', 'invoices_create', 'invoices_edit'):
            attrs = _checkbox_attrs(html, name)
            assert 'checked' not in attrs.split()
            assert 'disabled' in attrs.split()

    def test_team_access_off_clears_posted_extras(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)

        created = client.post(reverse('preset_create'), {
            'name': 'No Team Access',
            'access_projects': 'on',
            'projects_view_all': 'on',
            'team_create': 'on',
            'team_edit': 'on',
        })
        assert created.status_code == 200
        preset = PermissionPreset.objects.get(name='No Team Access')
        assert preset.access_team is False
        assert preset.team_create is False
        assert preset.team_edit is False
        assert preset.access_projects is True
        assert preset.projects_view_all is True

        existing = PermissionPreset.objects.create(
            name='Team Writers',
            access_team=True,
            team_create=True,
            team_edit=True,
            access_projects=True,
            projects_view_all=True,
        )
        edited = client.post(reverse('preset_edit', args=[existing.pk]), {
            'name': 'Team Writers',
            'access_projects': 'on',
            'projects_view_all': 'on',
            'team_create': 'on',
            'team_edit': 'on',
        })
        assert edited.status_code == 200
        existing.refresh_from_db()
        assert existing.access_team is False
        assert existing.team_create is False
        assert existing.team_edit is False
        assert existing.projects_view_all is True

        saved = client.post(reverse('preset_create'), {
            'name': 'Team Flags On',
            'access_team': 'on',
            'team_create': 'on',
            'team_edit': 'on',
        })
        assert saved.status_code == 200
        writers = PermissionPreset.objects.get(name='Team Flags On')
        assert writers.access_team is True
        assert writers.team_create is True
        assert writers.team_edit is True

    def test_drawer_renders_extras_under_their_modules(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        html = client.get(reverse('preset_create')).content.decode()

        clients = _card(html, 'clients')
        projects = _card(html, 'projects')
        assert clients.index('>Clients<') < clients.index('name="clients_view_all"')
        assert clients.index('name="clients_view_all"') < clients.index('name="clients_create"')
        assert clients.index('name="clients_create"') < clients.index('name="clients_edit"')
        assert 'View all' in clients
        assert 'Create' in clients
        assert 'Edit' in clients
        assert 'name="projects_view_all"' not in clients

        assert projects.index('>Projects<') < projects.index('name="projects_view_all"')
        assert projects.index('name="projects_view_all"') < projects.index('name="projects_create"')
        assert projects.index('name="projects_create"') < projects.index('name="projects_edit_own"')
        assert projects.index('name="projects_edit_own"') < projects.index('name="projects_edit_all"')
        assert 'View all' in projects
        assert 'Create' in projects
        assert 'Edit own' in projects
        assert 'Edit all' in projects
        assert 'name="clients_view_all"' not in projects
        assert 'name="clients_create"' not in projects
        assert 'name="clients_edit"' not in projects

        tasks = _card(html, 'tasks')
        assert tasks.index('>Tasks<') < tasks.index('name="tasks_view_all"')
        assert tasks.index('name="tasks_view_all"') < tasks.index('name="tasks_create"')
        assert tasks.index('name="tasks_create"') < tasks.index('name="tasks_edit_own"')
        assert tasks.index('name="tasks_edit_own"') < tasks.index('name="tasks_edit_all"')
        assert 'View all' in tasks
        assert 'Create' in tasks
        assert 'Edit own' in tasks
        assert 'Edit all' in tasks
        assert 'name="projects_view_all"' not in tasks
        assert 'name="clients_view_all"' not in tasks
        assert 'grid-cols-2' in tasks

        notes = _card(html, 'notes')
        assert notes.index('>Notes<') < notes.index('name="notes_view_all"')
        assert notes.index('name="notes_view_all"') < notes.index('name="notes_edit_public"')
        assert 'View all' in notes
        assert 'Edit public' in notes
        assert 'name="tasks_view_all"' not in notes
        assert 'name="clients_view_all"' not in notes
        assert 'grid-cols-2' in notes

        salaries = _card(html, 'salaries')
        assert salaries.index('>Salaries<') < salaries.index('name="salaries_view_all"')
        assert salaries.index('name="salaries_view_all"') < salaries.index('name="salaries_edit"')
        assert 'View all' in salaries
        assert 'Edit' in salaries
        assert 'Create' not in salaries
        assert 'name="tasks_view_all"' not in salaries
        assert 'grid-cols-2' in salaries

        invoices = _card(html, 'invoices')
        assert invoices.index('>Invoices<') < invoices.index('name="invoices_view_all"')
        assert invoices.index('name="invoices_view_all"') < invoices.index('name="invoices_create"')
        assert invoices.index('name="invoices_create"') < invoices.index('name="invoices_edit"')
        assert 'View all' in invoices
        assert '>Create<' in invoices
        assert '>Edit<' in invoices
        assert 'name="salaries_view_all"' not in invoices
        assert 'grid-cols-2' in invoices

        team = _card(html, 'team')
        assert team.index('>Team<') < team.index('name="team_create"')
        assert team.index('name="team_create"') < team.index('name="team_edit"')
        assert '>Create<' in team
        assert '>Edit<' in team
        assert 'View all' not in team
        assert 'name="salaries_view_all"' not in team
        assert 'grid-cols-2' in team

        for module in ('dashboard', 'todos'):
            card = _card(html, module)
            assert 'chevron-right' not in card
            assert 'data-extra' not in card

        for name in (
            'access_dashboard',
            'access_clients',
            'access_projects',
            'access_tasks',
            'access_todos',
            'access_notes',
            'access_salaries',
            'access_invoices',
            'access_team',
        ):
            assert 'checked' in _checkbox_attrs(html, name)
        for name in (
            'clients_view_all',
            'clients_create',
            'clients_edit',
            'projects_view_all',
            'projects_create',
            'projects_edit_own',
            'projects_edit_all',
            'tasks_view_all',
            'tasks_create',
            'tasks_edit_own',
            'tasks_edit_all',
            'notes_view_all',
            'notes_edit_public',
            'salaries_view_all',
            'salaries_edit',
            'invoices_view_all',
            'invoices_create',
            'invoices_edit',
            'team_create',
            'team_edit',
        ):
            attrs = _checkbox_attrs(html, name)
            assert 'checked' not in attrs.split()
            assert 'disabled' not in attrs.split()

        developer = PermissionPreset.objects.get(name='Developer')
        developer_html = client.get(reverse('preset_edit', args=[developer.pk])).content.decode()
        for name in ('clients_view_all', 'clients_create', 'clients_edit'):
            attrs = _checkbox_attrs(developer_html, name)
            assert 'checked' not in attrs.split()
            assert 'disabled' in attrs.split()
        for name in (
            'projects_view_all',
            'projects_create',
            'projects_edit_own',
            'projects_edit_all',
        ):
            project_attrs = _checkbox_attrs(developer_html, name)
            assert 'checked' not in project_attrs.split()
            assert 'disabled' not in project_attrs.split()
        for name in (
            'tasks_view_all',
            'tasks_create',
            'tasks_edit_own',
            'tasks_edit_all',
        ):
            task_attrs = _checkbox_attrs(developer_html, name)
            assert 'checked' not in task_attrs.split()
            assert 'disabled' not in task_attrs.split()
        for name in ('notes_view_all', 'notes_edit_public'):
            note_attrs = _checkbox_attrs(developer_html, name)
            assert 'checked' not in note_attrs.split()
            assert 'disabled' not in note_attrs.split()
        for name in ('salaries_view_all', 'salaries_edit'):
            salary_attrs = _checkbox_attrs(developer_html, name)
            assert 'checked' not in salary_attrs.split()
            assert 'disabled' in salary_attrs.split()
        for name in ('invoices_view_all', 'invoices_create', 'invoices_edit'):
            invoice_attrs = _checkbox_attrs(developer_html, name)
            assert 'checked' not in invoice_attrs.split()
            assert 'disabled' in invoice_attrs.split()
        for name in ('team_create', 'team_edit'):
            team_attrs = _checkbox_attrs(developer_html, name)
            assert 'checked' not in team_attrs.split()
            assert 'disabled' in team_attrs.split()

        admin_preset = PermissionPreset.objects.get(name='Admin')
        admin_html = client.get(reverse('preset_edit', args=[admin_preset.pk])).content.decode()
        for name in (
            'salaries_view_all',
            'salaries_edit',
            'invoices_view_all',
            'invoices_create',
            'invoices_edit',
            'team_create',
            'team_edit',
        ):
            admin_attrs = _checkbox_attrs(admin_html, name)
            assert 'checked' in admin_attrs.split()
            assert 'disabled' not in admin_attrs.split()

    def test_notes_access_off_clears_posted_extras(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)

        created = client.post(reverse('preset_create'), {
            'name': 'No Notes Access',
            'access_clients': 'on',
            'clients_view_all': 'on',
            'notes_view_all': 'on',
            'notes_edit_public': 'on',
        })
        assert created.status_code == 200
        preset = PermissionPreset.objects.get(name='No Notes Access')
        assert preset.access_notes is False
        assert preset.notes_view_all is False
        assert preset.notes_edit_public is False
        assert preset.access_clients is True
        assert preset.clients_view_all is True

        existing = PermissionPreset.objects.create(
            name='Note Editors',
            access_notes=True,
            notes_view_all=True,
            notes_edit_public=True,
            access_clients=True,
            clients_view_all=True,
        )
        edited = client.post(reverse('preset_edit', args=[existing.pk]), {
            'name': 'Note Editors',
            'access_clients': 'on',
            'clients_view_all': 'on',
            'notes_view_all': 'on',
            'notes_edit_public': 'on',
        })
        assert edited.status_code == 200
        existing.refresh_from_db()
        assert existing.access_notes is False
        assert existing.notes_view_all is False
        assert existing.notes_edit_public is False
        assert existing.clients_view_all is True

        saved = client.post(reverse('preset_create'), {
            'name': 'Note Flags On',
            'access_notes': 'on',
            'notes_view_all': 'on',
            'notes_edit_public': 'on',
        })
        assert saved.status_code == 200
        writers = PermissionPreset.objects.get(name='Note Flags On')
        assert writers.access_notes is True
        assert writers.notes_view_all is True
        assert writers.notes_edit_public is True

        off = PermissionPreset.objects.create(name='Notes Closed', access_notes=False)
        html = client.get(reverse('preset_edit', args=[off.pk])).content.decode()
        for name in ('notes_view_all', 'notes_edit_public'):
            attrs = _checkbox_attrs(html, name)
            assert 'checked' not in attrs.split()
            assert 'disabled' in attrs.split()



@pytest.mark.django_db
class TestPresetDelete:
    def test_delete_custom_preset(self, client):
        """Admin can delete a custom preset with no users."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.create(name='ToDelete')
        client.force_login(admin)
        response = client.post(reverse('preset_delete', args=[preset.pk]))
        assert response.status_code == 200
        assert not PermissionPreset.objects.filter(name='ToDelete').exists()

    def test_cannot_delete_system_preset(self, client):
        """System presets cannot be deleted."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Admin')
        client.force_login(admin)
        response = client.post(reverse('preset_delete', args=[preset.pk]))
        assert response.status_code == 400
        assert PermissionPreset.objects.filter(name='Admin').exists()

    def test_cannot_delete_preset_with_users(self, client):
        """Presets assigned to users cannot be deleted."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.create(name='InUse')
        UserFactory(permission_preset=preset)
        client.force_login(admin)
        response = client.post(reverse('preset_delete', args=[preset.pk]))
        assert response.status_code == 400
        assert PermissionPreset.objects.filter(name='InUse').exists()

    def test_delete_with_access_team(self, client):
        """Team flags do not grant preset delete. That stays role=admin."""
        preset_obj = PermissionPreset.objects.create(
            name='WithTeam',
            access_team=True,
            team_create=True,
            team_edit=True,
        )
        user = UserFactory(permission_preset=preset_obj)
        target = PermissionPreset.objects.create(name='ToDelete')
        client.force_login(user)
        response = client.post(reverse('preset_delete', args=[target.pk]))
        assert response.status_code == 403
        assert PermissionPreset.objects.filter(name='ToDelete').exists()

    def test_delete_requires_team_permission(self, client):
        """A member without access_team cannot delete presets."""
        user = UserFactory(permission_preset=PermissionPreset.objects.get(name='Developer'))
        target = PermissionPreset.objects.create(name='ToDelete')
        client.force_login(user)
        response = client.post(reverse('preset_delete', args=[target.pk]))
        assert response.status_code == 403
        assert PermissionPreset.objects.filter(name='ToDelete').exists()

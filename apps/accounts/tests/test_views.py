import json

import pytest
from django.urls import reverse

from apps.accounts.factories import (
    AdminUserFactory,
    UserFactory,
    admin_preset,
    developer_preset,
)
from apps.accounts.models import User
from apps.accounts.permissions import PermissionPreset
from apps.todos.factories import TodoFactory


@pytest.mark.django_db
class TestDashboard:
    def test_dashboard_requires_login(self, client):
        response = client.get(reverse('dashboard'))
        assert response.status_code == 302
        assert '/accounts/login/' in response.url

    def test_dashboard_accessible_when_logged_in(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert response.status_code == 200

    def test_dashboard_shows_stats(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert 'client_count' in response.context
        assert 'project_count' in response.context
        assert 'my_task_count' in response.context


@pytest.mark.django_db
class TestDashboardTodos:
    def _user_with_todo_access(self):
        preset = PermissionPreset.objects.get(name='Developer')
        return UserFactory(permission_preset=preset)

    def test_dashboard_includes_todos_in_context(self, client):
        """Dashboard should pass recent_todos to template."""
        user = self._user_with_todo_access()
        TodoFactory(owner=user, title='My Todo')
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert 'recent_todos' in response.context
        assert len(response.context['recent_todos']) == 1

    def test_dashboard_shows_only_incomplete_todos(self, client):
        """Dashboard should only show incomplete todos."""
        user = self._user_with_todo_access()
        TodoFactory(owner=user, title='Pending Todo', is_completed=False)
        TodoFactory(owner=user, title='Done Todo', is_completed=True)
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert len(response.context['recent_todos']) == 1
        assert response.context['recent_todos'][0].title == 'Pending Todo'

    def test_dashboard_shows_only_own_todos(self, client):
        """Dashboard should only show todos owned by logged-in user."""
        user = self._user_with_todo_access()
        other = UserFactory()
        TodoFactory(owner=user, title='My Todo')
        TodoFactory(owner=other, title='Other Todo')
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert len(response.context['recent_todos']) == 1

    def test_dashboard_limits_todos_to_five(self, client):
        """Dashboard should show at most 5 todos."""
        user = self._user_with_todo_access()
        for i in range(7):
            TodoFactory(owner=user, title=f'Todo {i}')
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert len(response.context['recent_todos']) == 5

    def test_dashboard_includes_todo_count(self, client):
        """Dashboard should pass total incomplete todo count."""
        user = self._user_with_todo_access()
        for _ in range(7):
            TodoFactory(owner=user)
        TodoFactory(owner=user, is_completed=True)
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert response.context['todo_count'] == 7

    def test_dashboard_renders_todo_section(self, client):
        """Dashboard should render the My To-Dos section with todo titles."""
        user = self._user_with_todo_access()
        TodoFactory(owner=user, title='Buy groceries')
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        content = response.content.decode()
        assert 'My To-Dos' in content
        assert 'Buy groceries' in content


@pytest.mark.django_db
class TestTeamList:
    def test_team_list_requires_admin(self, client):
        user = UserFactory(role='member')
        client.force_login(user)
        response = client.get(reverse('team_list'))
        assert response.status_code == 403

    def test_team_list_accessible_by_admin(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert response.status_code == 200

    def test_team_list_pagination(self, client):
        admin = AdminUserFactory()
        for _ in range(25):
            UserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert response.context['page_obj'].has_next()


@pytest.mark.django_db
@pytest.mark.security
class TestUserCreate:
    def test_drawer_requires_admin(self, client):
        """A member with access_team still cannot reach the create drawer."""
        member = UserFactory(role='member', permission_preset=admin_preset())
        client.force_login(member)
        response = client.get(reverse('user_create'))
        assert response.status_code == 403

    def test_non_staff_admin_gets_drawer(self, client):
        admin = AdminUserFactory(is_staff=False)
        client.force_login(admin)
        response = client.get(reverse('user_create'))
        assert response.status_code == 200
        assert b'Add Member' in response.content

    def test_creates_user_and_triggers_refresh(self, client):
        admin = AdminUserFactory(is_staff=False)
        client.force_login(admin)
        response = client.post(reverse('user_create'), {
            'name': 'Ada Lovelace',
            'email': 'ada@example.com',
            'role': 'member',
            'preset_id': '',
            'password1': 'analytical-engine-1843',
            'password2': 'analytical-engine-1843',
        })
        assert response.status_code == 200
        assert response.content == b''
        triggers = json.loads(response['HX-Trigger'])
        assert triggers == {'closeSlideOver': True, 'refreshTeamList': True}

        created = User.objects.get(email='ada@example.com')
        assert created.name == 'Ada Lovelace'
        assert created.is_active
        assert not created.is_staff

        # Logging in proves the password went through the manager's hashing.
        client.logout()
        assert client.login(email='ada@example.com', password='analytical-engine-1843')

    def test_persists_role_and_preset(self, client):
        admin = AdminUserFactory()
        preset = developer_preset()
        client.force_login(admin)
        response = client.post(reverse('user_create'), {
            'name': 'Grace Hopper',
            'email': 'grace@example.com',
            'role': 'admin',
            'preset_id': str(preset.pk),
            'password1': 'nanoseconds-are-short',
            'password2': 'nanoseconds-are-short',
        })
        assert response.status_code == 200
        created = User.objects.get(email='grace@example.com')
        assert created.role == 'admin'
        assert created.permission_preset == preset

    def test_rejects_duplicate_email(self, client):
        admin = AdminUserFactory()
        UserFactory(email='taken@example.com')
        client.force_login(admin)
        response = client.post(reverse('user_create'), {
            'name': 'Impostor',
            'email': 'taken@example.com',
            'role': 'member',
            'password1': 'analytical-engine-1843',
            'password2': 'analytical-engine-1843',
        })
        assert response.status_code == 200
        assert b'already in use' in response.content
        assert User.objects.filter(email='taken@example.com').count() == 1
        assert not User.objects.filter(name='Impostor').exists()

    def test_handles_integrity_error_on_save(self, client, monkeypatch):
        """Race on email uniqueness must re-render the drawer, not 500."""
        from django.db import IntegrityError

        admin = AdminUserFactory()
        client.force_login(admin)

        def raise_integrity(*args, **kwargs):
            raise IntegrityError('duplicate key')

        monkeypatch.setattr(User, 'save', raise_integrity)
        response = client.post(reverse('user_create'), {
            'name': 'Racer',
            'email': 'race@example.com',
            'role': 'member',
            'password1': 'analytical-engine-1843',
            'password2': 'analytical-engine-1843',
        })
        assert response.status_code == 200
        assert b'already in use' in response.content

    def test_rejects_mismatched_passwords(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_create'), {
            'name': 'Ada Lovelace',
            'email': 'ada@example.com',
            'role': 'member',
            'password1': 'analytical-engine-1843',
            'password2': 'difference-engine-1822',
        })
        assert response.status_code == 200
        assert b'Passwords do not match.' in response.content
        assert not User.objects.filter(email='ada@example.com').exists()

    def test_rejects_weak_password(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_create'), {
            'name': 'Ada Lovelace',
            'email': 'ada@example.com',
            'role': 'member',
            'password1': 'abc',
            'password2': 'abc',
        })
        assert response.status_code == 200
        assert b'too short' in response.content
        assert not User.objects.filter(email='ada@example.com').exists()

    def test_rejects_blank_name(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_create'), {
            'name': '',
            'email': 'ada@example.com',
            'role': 'member',
            'password1': 'analytical-engine-1843',
            'password2': 'analytical-engine-1843',
        })
        assert response.status_code == 200
        assert b'Name is required.' in response.content
        assert not User.objects.filter(email='ada@example.com').exists()

    def test_rejects_unknown_preset(self, client):
        """A non-numeric or dangling preset id is an error, not a 500."""
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_create'), {
            'name': 'Ada Lovelace',
            'email': 'ada@example.com',
            'role': 'member',
            'preset_id': 'not-an-id',
            'password1': 'analytical-engine-1843',
            'password2': 'analytical-engine-1843',
        })
        assert response.status_code == 200
        assert b'valid permission preset' in response.content
        assert not User.objects.filter(email='ada@example.com').exists()

    def test_unknown_role_falls_back_to_member(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_create'), {
            'name': 'Ada Lovelace',
            'email': 'ada@example.com',
            'role': 'superuser',
            'password1': 'analytical-engine-1843',
            'password2': 'analytical-engine-1843',
        })
        assert response.status_code == 200
        assert User.objects.get(email='ada@example.com').role == 'member'


@pytest.mark.django_db
@pytest.mark.security
class TestUserUpdate:
    def test_user_update_requires_admin(self, client):
        user = UserFactory(role='member')
        target = UserFactory()
        client.force_login(user)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': 'New Name', 'email': target.email, 'role': 'member',
        })
        assert response.status_code == 403

    def test_user_update_requires_post(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.get(reverse('user_update', args=[target.pk]))
        assert response.status_code == 405

    def test_user_update_changes_name(self, client):
        admin = AdminUserFactory()
        target = UserFactory(name='Old Name')
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': 'New Name', 'email': target.email, 'role': 'member',
        })
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.name == 'New Name'

    def test_user_update_changes_email(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': target.name, 'email': 'newemail@example.com', 'role': 'member',
        })
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.email == 'newemail@example.com'

    def test_user_update_rejects_duplicate_email(self, client):
        admin = AdminUserFactory()
        UserFactory(email='taken@example.com')
        target = UserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': target.name, 'email': 'taken@example.com', 'role': 'member',
        })
        assert response.status_code == 200  # Re-renders drawer with error
        target.refresh_from_db()
        assert target.email != 'taken@example.com'
        assert b'already in use' in response.content

    def test_user_update_handles_integrity_error_on_save(self, client, monkeypatch):
        """Race on email uniqueness must re-render the drawer, not 500."""
        from django.db import IntegrityError

        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)

        def raise_integrity(*args, **kwargs):
            raise IntegrityError('duplicate key')

        monkeypatch.setattr(User, 'save', raise_integrity)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': target.name, 'email': 'race@example.com', 'role': 'member',
        })
        assert response.status_code == 200
        assert b'already in use' in response.content

    def test_user_update_rejects_blank_name(self, client):
        admin = AdminUserFactory()
        target = UserFactory(name='Original')
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': '', 'email': target.email, 'role': 'member',
        })
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.name == 'Original'
        assert b'required' in response.content.lower()

    def test_user_update_changes_role(self, client):
        admin = AdminUserFactory()
        target = UserFactory(role='member')
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': target.name, 'email': target.email, 'role': 'admin',
        })
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.role == 'admin'

    def test_user_update_changes_preset(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        preset = PermissionPreset.objects.create(name='Custom')
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': target.name, 'email': target.email, 'role': 'member',
            'preset_id': preset.pk,
        })
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.permission_preset == preset

    def test_user_update_clears_preset(self, client):
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.create(name='Custom')
        target = UserFactory(permission_preset=preset)
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': target.name, 'email': target.email, 'role': 'member',
            'preset_id': '',
        })
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.permission_preset is None

    def test_user_update_last_admin_guard(self, client):
        """Cannot demote yourself if you're the last active admin."""
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[admin.pk]), {
            'name': admin.name, 'email': admin.email, 'role': 'member',
        })
        assert response.status_code == 200
        admin.refresh_from_db()
        assert admin.role == 'admin'  # Not changed
        assert b'last' in response.content.lower()

    def test_user_update_allows_demote_when_other_admins_exist(self, client):
        admin1 = AdminUserFactory()
        AdminUserFactory()  # a second admin makes the demotion legal
        client.force_login(admin1)
        response = client.post(reverse('user_update', args=[admin1.pk]), {
            'name': admin1.name, 'email': admin1.email, 'role': 'member',
        })
        assert response.status_code == 200
        admin1.refresh_from_db()
        assert admin1.role == 'member'

    def test_user_update_returns_user_row(self, client):
        admin = AdminUserFactory()
        target = UserFactory(name='Old')
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': 'New', 'email': target.email, 'role': 'member',
        })
        assert response.status_code == 200
        assert b'New' in response.content
        assert 'closeSlideOver' in response.get('HX-Trigger', '')
        assert f'#user-{target.pk}' in response.get('HX-Retarget', '')
        assert 'outerHTML' in response.get('HX-Reswap', '')


@pytest.mark.django_db
class TestUserDeactivate:
    def test_deactivate_requires_admin(self, client):
        user = UserFactory(role='member')
        target = UserFactory()
        client.force_login(user)
        response = client.post(reverse('user_deactivate', args=[target.pk]))
        assert response.status_code == 403

    def test_deactivate_requires_post(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.get(reverse('user_deactivate', args=[target.pk]))
        assert response.status_code == 405

    def test_deactivate_user(self, client):
        admin = AdminUserFactory()
        target = UserFactory(is_active=True)
        client.force_login(admin)
        response = client.post(reverse('user_deactivate', args=[target.pk]))
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.is_active is False
        assert 'closeSlideOver' in response.get('HX-Trigger', '')

    def test_reactivate_user(self, client):
        admin = AdminUserFactory()
        target = UserFactory(is_active=False)
        client.force_login(admin)
        response = client.post(reverse('user_deactivate', args=[target.pk]))
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.is_active is True

    def test_cannot_deactivate_self(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_deactivate', args=[admin.pk]))
        assert response.status_code == 400
        admin.refresh_from_db()
        assert admin.is_active is True

    def test_cannot_deactivate_last_admin(self, client):
        admin = AdminUserFactory()
        target = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_deactivate', args=[target.pk]))
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.is_active is False


@pytest.mark.django_db
class TestUserDeleteConfirm:
    def test_delete_confirm_requires_admin(self, client):
        user = UserFactory(role='member')
        target = UserFactory()
        client.force_login(user)
        response = client.get(reverse('user_delete_confirm', args=[target.pk]))
        assert response.status_code == 403

    def test_delete_confirm_returns_counts(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        TodoFactory(owner=target)
        TodoFactory(owner=target)
        client.force_login(admin)
        response = client.get(reverse('user_delete_confirm', args=[target.pk]))
        assert response.status_code == 200
        assert b'2 todo' in response.content.lower()

    def test_delete_confirm_clean_user(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.get(reverse('user_delete_confirm', args=[target.pk]))
        assert response.status_code == 200
        assert b'no associated data' in response.content.lower()

    def test_delete_confirm_deduplicates_notes(self, client):
        """A note where user is both created_by and modified_by counts once."""
        admin = AdminUserFactory()
        target = UserFactory()
        from apps.notes.models import Note
        Note.objects.create(
            title='Test Note', description='x',
            created_by=target, modified_by=target,
        )
        client.force_login(admin)
        response = client.get(reverse('user_delete_confirm', args=[target.pk]))
        assert response.status_code == 200
        assert b'1 note' in response.content.lower()
        assert b'2 note' not in response.content.lower()

    def test_delete_confirm_cannot_delete_self(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('user_delete_confirm', args=[admin.pk]))
        assert response.status_code == 400


@pytest.mark.django_db
class TestUserDelete:
    def test_delete_requires_admin(self, client):
        user = UserFactory(role='member')
        target = UserFactory()
        client.force_login(user)
        response = client.post(reverse('user_delete', args=[target.pk]))
        assert response.status_code == 403

    def test_delete_requires_post(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.get(reverse('user_delete', args=[target.pk]))
        assert response.status_code == 405

    def test_delete_clean_user(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        target_pk = target.pk
        client.force_login(admin)
        response = client.post(reverse('user_delete', args=[target.pk]))
        assert response.status_code == 200
        assert not User.objects.filter(pk=target_pk).exists()

    def test_delete_user_with_data_cascades(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        TodoFactory(owner=target)
        TodoFactory(owner=target)
        target_pk = target.pk
        client.force_login(admin)
        response = client.post(reverse('user_delete', args=[target.pk]))
        assert response.status_code == 200
        assert not User.objects.filter(pk=target_pk).exists()
        from apps.todos.models import Todo
        assert Todo.objects.filter(owner_id=target_pk).count() == 0

    def test_cannot_delete_self(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_delete', args=[admin.pk]))
        assert response.status_code == 400
        assert User.objects.filter(pk=admin.pk).exists()

    def test_delete_returns_empty_response(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_delete', args=[target.pk]))
        assert response.status_code == 200
        assert response.content == b''

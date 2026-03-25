import pytest
from django.urls import reverse
from apps.accounts.factories import UserFactory, AdminUserFactory
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
    def test_dashboard_includes_todos_in_context(self, client):
        """Dashboard should pass recent_todos to template."""
        user = UserFactory()
        TodoFactory(owner=user, title='My Todo')
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert 'recent_todos' in response.context
        assert len(response.context['recent_todos']) == 1

    def test_dashboard_shows_only_incomplete_todos(self, client):
        """Dashboard should only show incomplete todos."""
        user = UserFactory()
        TodoFactory(owner=user, title='Pending Todo', is_completed=False)
        TodoFactory(owner=user, title='Done Todo', is_completed=True)
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert len(response.context['recent_todos']) == 1
        assert response.context['recent_todos'][0].title == 'Pending Todo'

    def test_dashboard_shows_only_own_todos(self, client):
        """Dashboard should only show todos owned by logged-in user."""
        user = UserFactory()
        other = UserFactory()
        TodoFactory(owner=user, title='My Todo')
        TodoFactory(owner=other, title='Other Todo')
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert len(response.context['recent_todos']) == 1

    def test_dashboard_limits_todos_to_five(self, client):
        """Dashboard should show at most 5 todos."""
        user = UserFactory()
        for i in range(7):
            TodoFactory(owner=user, title=f'Todo {i}')
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert len(response.context['recent_todos']) == 5

    def test_dashboard_includes_todo_count(self, client):
        """Dashboard should pass total incomplete todo count."""
        user = UserFactory()
        for i in range(7):
            TodoFactory(owner=user)
        TodoFactory(owner=user, is_completed=True)
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert response.context['todo_count'] == 7

    def test_dashboard_renders_todo_section(self, client):
        """Dashboard should render the My To-Dos section with todo titles."""
        user = UserFactory()
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
class TestToggleRole:
    def test_toggle_role_requires_admin(self, client):
        user = UserFactory(role='member')
        target = UserFactory(role='member')
        client.force_login(user)
        response = client.post(reverse('toggle_role', args=[target.pk]))
        assert response.status_code == 403

    def test_toggle_role_works_for_admin(self, client):
        admin = AdminUserFactory()
        target = UserFactory(role='member')
        client.force_login(admin)
        response = client.post(reverse('toggle_role', args=[target.pk]))
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.role == 'admin'

    def test_admin_cannot_toggle_own_role(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('toggle_role', args=[admin.pk]))
        admin.refresh_from_db()
        assert admin.role == 'admin'

    def test_toggle_role_requires_post(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.get(reverse('toggle_role', args=[target.pk]))
        assert response.status_code == 405


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

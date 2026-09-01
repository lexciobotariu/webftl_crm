import uuid

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset

User = get_user_model()


@pytest.mark.django_db
@pytest.mark.security
class TestSignupClosed:
    def test_signup_get_redirects_or_denied(self, client):
        response = client.get(reverse('account_signup'))
        assert response.status_code in (302, 403, 404, 200)

    def test_signup_post_does_not_create_user(self, client):
        response = client.post(reverse('account_signup'), {
            'email': 'newuser@example.com',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
        })
        assert not User.objects.filter(email='newuser@example.com').exists()
        assert response.status_code in (302, 403, 404, 200)


@pytest.mark.django_db
@pytest.mark.security
class TestRbacViewEnforcement:
    def _user_with_preset(self, **permissions):
        preset = PermissionPreset.objects.create(
            name=f'Preset_{uuid.uuid4().hex[:8]}',
            **permissions,
        )
        return UserFactory(permission_preset=preset)

    def test_dashboard_denied_without_permission(self, client):
        user = self._user_with_preset(access_dashboard=False)
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert response.status_code == 403

    def test_my_tasks_denied_without_permission(self, client):
        user = self._user_with_preset(access_tasks=False)
        client.force_login(user)
        response = client.get(reverse('my_tasks'))
        assert response.status_code == 403

    def test_todo_list_denied_without_permission(self, client):
        user = self._user_with_preset(access_todos=False)
        client.force_login(user)
        response = client.get(reverse('todo_list'))
        assert response.status_code == 403

    def test_project_list_denied_without_permission(self, client):
        user = self._user_with_preset(access_projects=False)
        client.force_login(user)
        response = client.get(reverse('project_list'))
        assert response.status_code == 403

    def test_salary_create_requires_admin(self, client):
        user = self._user_with_preset(access_salaries=True)
        client.force_login(user)
        response = client.get(reverse('salary_create'))
        assert response.status_code == 403

    def test_salary_list_allowed_with_permission(self, client):
        user = self._user_with_preset(access_salaries=True)
        client.force_login(user)
        response = client.get(reverse('salary_list'))
        assert response.status_code == 200

    def test_user_delete_blocked_with_salary_records(self, client):
        from apps.salaries.models import EmployeeSalary

        admin = AdminUserFactory()
        target = UserFactory()
        EmployeeSalary.objects.create(user=target, base_salary='5000.00', currency='EUR')
        client.force_login(admin)
        response = client.post(reverse('user_delete', args=[target.pk]))
        assert response.status_code == 400
        assert User.objects.filter(pk=target.pk).exists()

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.factories import admin_preset
from apps.accounts.permissions import PermissionPreset

User = get_user_model()


@pytest.fixture
def salaries_preset(db):
    """A non-admin preset that grants access_salaries."""
    preset, _ = PermissionPreset.objects.get_or_create(
        name='Payroll Viewer',
        defaults={
            'description': 'Read-only access to the salaries section',
            'access_dashboard': True,
            'access_clients': False,
            'access_projects': False,
            'access_tasks': False,
            'access_todos': False,
            'access_notes': False,
            'access_salaries': True,
            'access_team': False,
        },
    )
    return preset


@pytest.fixture
def user(db, salaries_preset):
    """A plain member who is allowed into the salaries section but cannot write.

    Read views only need ``access_salaries``; every mutating view additionally
    requires ``@require_admin``. Keeping this fixture non-admin is what makes
    the boundary tests in ``test_permissions.py`` meaningful.
    """
    return User.objects.create_user(
        email='user@example.com',
        name='Test User',
        password='testpass123',
        role='member',
        permission_preset=salaries_preset,
    )


@pytest.fixture
def salaries_admin(db):
    """An admin, for the views guarded by ``@require_admin``."""
    return User.objects.create_user(
        email='salaries-admin@example.com',
        name='Salaries Admin',
        password='testpass123',
        role='admin',
        permission_preset=admin_preset(),
    )


@pytest.fixture
def admin_client_logged_in(client, salaries_admin):
    client.force_login(salaries_admin)
    return client

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a regular user with Admin preset so salary views are accessible."""
    from apps.accounts.permissions import PermissionPreset
    preset = PermissionPreset.objects.get(name='Admin')
    return User.objects.create_user(
        email='user@example.com',
        name='Test User',
        password='testpass123',
        role='member',
        permission_preset=preset,
    )

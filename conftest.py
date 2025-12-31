import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a regular user."""
    return User.objects.create_user(
        email='user@example.com',
        name='Test User',
        password='testpass123',
        role='member'
    )


@pytest.fixture
def admin_user(db):
    """Create an admin user."""
    return User.objects.create_user(
        email='admin@example.com',
        name='Admin User',
        password='testpass123',
        role='admin'
    )


@pytest.fixture
def client_logged_in(client, user):
    """Return a logged-in test client."""
    client.force_login(user)
    return client


@pytest.fixture
def admin_client_logged_in(client, admin_user):
    """Return a logged-in admin test client."""
    client.force_login(admin_user)
    return client

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.factories import developer_preset, ensure_system_presets

User = get_user_model()

# Fixtures that mean "this test talks to the database".
_DB_FIXTURES = {'db', 'transactional_db', 'django_db_setup', 'django_db_reset_sequences'}


def _test_touches_db(request):
    if _DB_FIXTURES & set(request.fixturenames):
        return True
    # Django's own TestCase/TransactionTestCase subclasses get the DB without
    # ever naming a pytest-django fixture.
    from django.test import TransactionTestCase

    cls = request.node.cls
    return isinstance(cls, type) and issubclass(cls, TransactionTestCase)


@pytest.fixture(autouse=True)
def restore_system_presets(request, django_db_blocker):
    """Put the migration-seeded PermissionPresets back before every DB test.

    ``TransactionTestCase`` flushes every table at teardown and does not restore
    migration data, so the Admin/Developer presets vanish for the rest of the
    session — and stay gone in the reused database on the next ``--reuse-db``
    run. See ``apps.accounts.factories.ensure_system_presets``.
    """
    if _test_touches_db(request):
        request.getfixturevalue('django_db_setup')
        with django_db_blocker.unblock():
            ensure_system_presets()
    yield


@pytest.fixture
def user(db):
    """Create a regular user with Developer preset for app-level permissions."""
    return User.objects.create_user(
        email='user@example.com',
        name='Test User',
        password='testpass123',
        role='member',
        permission_preset=developer_preset(),
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

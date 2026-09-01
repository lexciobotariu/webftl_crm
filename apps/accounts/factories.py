import factory
from django.contrib.auth import get_user_model

from apps.accounts.permissions import PermissionPreset

User = get_user_model()


# Mirrors accounts migration 0005_seed_default_presets.
SYSTEM_PRESET_DEFAULTS = {
    'Admin': {
        'description': 'Full access to all sections',
        'is_system': True,
        'access_dashboard': True,
        'access_clients': True,
        'access_projects': True,
        'access_tasks': True,
        'access_todos': True,
        'access_notes': True,
        'access_salaries': True,
        'access_team': True,
    },
    'Developer': {
        'description': 'Access to assigned projects, tasks, and personal todos',
        'is_system': True,
        'access_dashboard': True,
        'access_clients': False,
        'access_projects': True,
        'access_tasks': True,
        'access_todos': True,
        'access_notes': True,
        'access_salaries': False,
        'access_team': False,
    },
}


def ensure_system_presets():
    """Recreate the presets seeded by accounts migration 0005 if they are gone.

    ``TransactionTestCase`` flushes every table at teardown and never restores
    migration-seeded rows, so any test running after a race test — and every
    test in a later ``--reuse-db`` run — would otherwise fail with
    ``PermissionPreset.DoesNotExist``.
    """
    for name, defaults in SYSTEM_PRESET_DEFAULTS.items():
        PermissionPreset.objects.get_or_create(name=name, defaults=defaults)


def system_preset(name):
    preset, _ = PermissionPreset.objects.get_or_create(
        name=name, defaults=SYSTEM_PRESET_DEFAULTS[name]
    )
    return preset


def developer_preset():
    return system_preset('Developer')


def admin_preset():
    return system_preset('Admin')


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f'user{n}@example.com')
    name = factory.Faker('name')
    role = 'member'
    github_token = ''
    is_active = True
    permission_preset = factory.LazyFunction(developer_preset)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop('password', 'testpass123')
        manager = cls._get_manager(model_class)
        return manager.create_user(**kwargs, password=password)


class AdminUserFactory(UserFactory):
    role = 'admin'
    email = factory.Sequence(lambda n: f'admin{n}@example.com')

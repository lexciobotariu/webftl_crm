import factory
from django.contrib.auth import get_user_model

from apps.accounts.permissions import PermissionPreset

User = get_user_model()


# Mirrors the seeded Admin and Developer presets (migrations 0005 through 0010).
SYSTEM_PRESET_DEFAULTS = {
    'Admin': {
        'description': 'Full access to all sections',
        'is_system': True,
        'access_dashboard': True,
        'access_clients': True,
        'clients_view_all': True,
        'clients_create': True,
        'clients_edit': True,
        'access_projects': True,
        'projects_view_all': True,
        'projects_create': True,
        'projects_edit_own': True,
        'projects_edit_all': True,
        'access_tasks': True,
        'tasks_view_all': True,
        'tasks_create': True,
        'tasks_edit_own': True,
        'tasks_edit_all': True,
        'access_todos': True,
        'access_notes': True,
        'notes_view_all': True,
        'notes_edit_public': True,
        'access_salaries': True,
        'access_team': True,
    },
    'Developer': {
        'description': 'Access to assigned projects, tasks, and personal todos',
        'is_system': True,
        'access_dashboard': True,
        'access_clients': False,
        'clients_view_all': False,
        'clients_create': False,
        'clients_edit': False,
        'access_projects': True,
        'projects_view_all': False,
        'projects_create': False,
        'projects_edit_own': False,
        'projects_edit_all': False,
        'access_tasks': True,
        'tasks_view_all': False,
        'tasks_create': False,
        'tasks_edit_own': False,
        'tasks_edit_all': False,
        'access_todos': True,
        'access_notes': True,
        'notes_view_all': False,
        'notes_edit_public': False,
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


def member_preset():
    """Developer sections plus task create and edit own.

    The seeded Developer preset leaves the task write flags off. Tests that
    create or edit a task use this preset so a project member still can.
    """
    defaults = {
        **SYSTEM_PRESET_DEFAULTS['Developer'],
        'is_system': False,
        'description': 'Assigned projects, with task create and edit own',
        'tasks_create': True,
        'tasks_edit_own': True,
    }
    preset, _ = PermissionPreset.objects.get_or_create(name='Member', defaults=defaults)
    return preset


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
    permission_preset = factory.LazyFunction(member_preset)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop('password', 'testpass123')
        manager = cls._get_manager(model_class)
        return manager.create_user(**kwargs, password=password)


class AdminUserFactory(UserFactory):
    role = 'admin'
    email = factory.Sequence(lambda n: f'admin{n}@example.com')

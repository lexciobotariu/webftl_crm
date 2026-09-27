from django.db import models

PERMISSION_KEYS = [
    'access_dashboard',
    'access_clients',
    'clients_view_all',
    'clients_create',
    'clients_edit',
    'access_projects',
    'projects_view_all',
    'projects_create',
    'projects_edit_own',
    'projects_edit_all',
    'access_tasks',
    'tasks_view_all',
    'tasks_create',
    'tasks_edit_own',
    'tasks_edit_all',
    'access_todos',
    'access_notes',
    'notes_view_all',
    'notes_edit_public',
    'access_salaries',
    'access_team',
]


class PermissionPreset(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    # App-level permissions (default True — restrictive presets set False)
    access_dashboard = models.BooleanField(default=True)
    access_clients = models.BooleanField(default=True)
    access_projects = models.BooleanField(default=True)
    access_tasks = models.BooleanField(default=True)
    access_todos = models.BooleanField(default=True)
    access_notes = models.BooleanField(default=True)
    access_salaries = models.BooleanField(default=True)
    access_team = models.BooleanField(default=True)

    # Unchecked means view own. Admins still see everything via has_app_permission.
    clients_view_all = models.BooleanField(default=False)
    projects_view_all = models.BooleanField(default=False)

    # Create and edit are separate from view. Delete stays role=admin.
    clients_create = models.BooleanField(default=False)
    clients_edit = models.BooleanField(default=False)
    projects_create = models.BooleanField(default=False)
    projects_edit_own = models.BooleanField(default=False)
    projects_edit_all = models.BooleanField(default=False)

    # View own is access_tasks plus a ProjectAccess row. There is no view-own flag.
    tasks_view_all = models.BooleanField(default=False)
    tasks_create = models.BooleanField(default=False)
    tasks_edit_own = models.BooleanField(default=False)
    tasks_edit_all = models.BooleanField(default=False)

    # View own is access_notes plus a client or project the user can already open.
    # These never reach a private note. There is no create flag.
    notes_view_all = models.BooleanField(default=False)
    notes_edit_public = models.BooleanField(default=False)

    is_system = models.BooleanField(default=False, help_text="System presets cannot be deleted")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def has_permission(self, key):
        """Check if this preset grants the given permission key."""
        if key not in PERMISSION_KEYS:
            return False
        return getattr(self, key, False)

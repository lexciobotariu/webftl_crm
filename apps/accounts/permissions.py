from django.db import models

PERMISSION_KEYS = [
    'access_dashboard',
    'access_clients',
    'access_projects',
    'access_tasks',
    'access_todos',
    'access_notes',
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

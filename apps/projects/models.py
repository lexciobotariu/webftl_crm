from django.conf import settings
from django.db import models

from apps.clients.models import Client


class Project(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    github_repo_url = models.URLField(blank=True)
    github_sync_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.client.name})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self._create_default_statuses()

    def _create_default_statuses(self):
        defaults = ['Backlog', 'To Do', 'In Progress', 'Review', 'Done']
        for i, name in enumerate(defaults):
            Status.objects.create(project=self, name=name, order=i)

    @property
    def task_count(self):
        """Return total number of tasks across all statuses."""
        from apps.tasks.models import Task
        return Task.objects.filter(project=self).count()


class Status(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='statuses')
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        verbose_name_plural = 'Statuses'

    def __str__(self):
        return self.name

    @property
    def task_count(self):
        return self.tasks.count()


class ProjectMember(models.Model):
    """
    Tracks user membership and roles within projects.
    Admins bypass this check and have access to all projects.
    """
    ROLE_CHOICES = [
        ('viewer', 'Viewer'),      # Can view project and tasks
        ('editor', 'Editor'),      # Can edit tasks, create subtasks
        ('manager', 'Manager'),    # Can manage project settings, statuses, labels
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='project_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='viewer')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['project', 'user']
        ordering = ['project', 'user__name']

    def __str__(self):
        return f"{self.user.name} - {self.project.name} ({self.role})"


def can_access_project(user, project, required_role='viewer'):
    """
    Check if user has access to a project with at least the required role.

    Admins always have full access.
    Role hierarchy: viewer < editor < manager
    """
    if user.is_admin:
        return True

    role_levels = {'viewer': 0, 'editor': 1, 'manager': 2}
    required_level = role_levels.get(required_role, 0)

    try:
        membership = ProjectMember.objects.get(project=project, user=user)
        user_level = role_levels.get(membership.role, 0)
        return user_level >= required_level
    except ProjectMember.DoesNotExist:
        return False

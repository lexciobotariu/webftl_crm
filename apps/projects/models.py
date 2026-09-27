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
            Status.objects.create(
                project=self, name=name, order=i, is_done=(name == 'Done')
            )

    @property
    def task_count(self):
        """Return total number of tasks across all statuses."""
        from apps.tasks.models import Task
        return Task.objects.filter(project=self).count()


class Status(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='statuses')
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    visible_on_board = models.BooleanField(default=True)
    is_done = models.BooleanField(default=False)

    class Meta:
        ordering = ['order']
        verbose_name_plural = 'Statuses'
        constraints = [
            models.UniqueConstraint(fields=['project', 'name'], name='unique_status_name_per_project'),
        ]

    def __str__(self):
        return self.name

    @property
    def task_count(self):
        return self.tasks.count()


class ProjectAccess(models.Model):
    """One row means this person has access to that project.

    The row opens the project and, until a later pass, allows tasks, comments,
    and the person's own time. It does not grant settings edits. Admins bypass
    the row through ``is_admin`` and ``has_app_permission``.
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='access')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='project_access'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['project', 'user']
        ordering = ['project', 'user__name']

    def __str__(self):
        return f"{self.user.name} - {self.project.name}"


def _has_access_row(user, project):
    return ProjectAccess.objects.filter(project=project, user=user).exists()


def visible_projects(user):
    """Projects this user may see on the dashboard and in the project list.

    ``projects_view_all`` is every project. Without it, projects where ``user``
    has a ProjectAccess row. ``role=admin`` bypasses the flag through
    ``User.has_app_permission``.
    """
    if user.has_app_permission('projects_view_all'):
        return Project.objects.all()
    return Project.objects.filter(access__user=user).distinct()


def can_access_project(user, project):
    """Whether the user may open this project.

    Admin, a ProjectAccess row, ``projects_view_all``, or ``projects_edit_all``.
    """
    if user.is_admin:
        return True
    if _has_access_row(user, project):
        return True
    return user.has_app_permission('projects_view_all') or user.has_app_permission(
        'projects_edit_all'
    )


def can_edit_project(user, project):
    """Settings, statuses, labels, and the GitHub repo settings.

    Admin, ``projects_edit_all``, or ``projects_edit_own`` plus a ProjectAccess row.
    A row by itself does not grant edit.
    """
    if user.is_admin:
        return True
    if user.has_app_permission('projects_edit_all'):
        return True
    return user.has_app_permission('projects_edit_own') and _has_access_row(user, project)


def can_work_on_project(user, project):
    """Tasks, comments, and the user's own time.

    What an editor could do: admin, or a ProjectAccess row. View-all alone is
    not enough, and neither edit flag adds this.
    """
    if user.is_admin:
        return True
    return _has_access_row(user, project)


def get_assignable_users(project):
    """Users who can be assigned tasks on this project (access rows + admins)."""
    from apps.accounts.models import User

    access_ids = ProjectAccess.objects.filter(project=project).values_list('user_id', flat=True)
    return User.objects.filter(is_active=True).filter(
        models.Q(pk__in=access_ids) | models.Q(role='admin')
    )

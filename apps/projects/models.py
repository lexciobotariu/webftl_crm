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

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.projects.models import Project, Status


class Label(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='labels')
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default='#6366f1')  # Hex color

    class Meta:
        unique_together = ['project', 'name']

    def __str__(self):
        return self.name


class TaskQuerySet(models.QuerySet):
    """Keeps the definitions of "done", "active" and "overdue" in one place.

    ``Task.is_overdue`` is the per-instance version of :meth:`overdue`; the two
    must agree, so anything counting overdue tasks should go through here rather
    than re-deriving the filter.
    """

    def done(self):
        return self.filter(status__is_done=True)

    def active(self):
        """Tasks in a status that does not count as done."""
        return self.exclude(status__is_done=True)

    def overdue(self, today=None):
        if today is None:
            today = timezone.now().date()
        return self.active().filter(due_date__lt=today)


class Task(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    status = models.ForeignKey(Status, on_delete=models.RESTRICT, related_name='tasks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks'
    )
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, blank=True)
    due_date = models.DateField(null=True, blank=True)
    time_estimate = models.PositiveIntegerField(null=True, blank=True, help_text='Estimated hours')
    labels = models.ManyToManyField(Label, blank=True, related_name='tasks')
    order = models.PositiveIntegerField(default=0)

    # GitHub integration
    github_issue_id = models.PositiveIntegerField(null=True, blank=True)
    github_issue_number = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TaskQuerySet.as_manager()

    class Meta:
        ordering = ['order', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'github_issue_id'],
                condition=Q(github_issue_id__isnull=False),
                name='unique_github_issue_per_project',
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        if not self.due_date:
            return False
        if self.status.is_done:
            return False
        return self.due_date < timezone.now().date()

    @property
    def subtask_progress(self):
        total = self.subtasks.count()
        if total == 0:
            return None
        completed = self.subtasks.filter(completed=True).count()
        return f"{completed}/{total}"


class Subtask(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='subtasks')
    title = models.CharField(max_length=255)
    completed = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title


class TaskActivity(models.Model):
    """Tracks activity on tasks - comments, status changes, etc."""
    ACTIVITY_TYPES = [
        ('comment', 'Comment'),
        ('status_change', 'Status Changed'),
        ('assignee_change', 'Assignee Changed'),
        ('priority_change', 'Priority Changed'),
        ('created', 'Created'),
        ('due_date_change', 'Due Date Changed'),
        ('label_added', 'Label Added'),
        ('label_removed', 'Label Removed'),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    content = models.TextField(blank=True)
    old_value = models.CharField(max_length=255, blank=True)
    new_value = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name_plural = 'Task activities'

    def __str__(self):
        return f"{self.get_activity_type_display()} on {self.task}"


class Attachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='attachments/%Y/%m/')
    filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.filename

    def save(self, *args, **kwargs):
        if not self.filename:
            self.filename = self.file.name
        super().save(*args, **kwargs)

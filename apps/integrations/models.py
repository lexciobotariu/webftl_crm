from django.db import models

from apps.tasks.models import Task


class GitHubCommit(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='commits')
    sha = models.CharField(max_length=40, unique=True)
    message = models.TextField()
    author = models.CharField(max_length=255)
    url = models.URLField()
    created_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sha[:7]} - {self.message[:50]}"


class GitHubPullRequest(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('merged', 'Merged'),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='pull_requests')
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    url = models.URLField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        ordering = ['-updated_at']
        unique_together = ['task', 'number']

    def __str__(self):
        return f"#{self.number} - {self.title}"

from django.conf import settings
from django.db import models
from django.db.models import Q


class Notification(models.Model):
    """Something on a task that one person should know about, shown in the Inbox.

    Written only where an author is known (the task signals and
    ``tasks.services.add_comment``), so imports and syncs do not flood anyone.
    Who may still see the task is checked when the Inbox is read, not here.
    There is at most one unread row per person, task and kind: a second
    comment while the first is unread moves that row up instead.
    """

    ASSIGNED = 'assigned'
    MENTIONED = 'mentioned'
    COMMENTED = 'commented'
    KIND_CHOICES = [
        (ASSIGNED, 'Assigned'),
        (MENTIONED, 'Mentioned'),
        (COMMENTED, 'Commented'),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications'
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    task = models.ForeignKey('tasks.Task', on_delete=models.CASCADE, related_name='notifications')
    # The comment, for "commented" and "mentioned"; deleting it removes this row.
    activity = models.ForeignKey(
        'tasks.TaskActivity', on_delete=models.CASCADE, null=True, blank=True, related_name='notifications'
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [
            models.Index(
                fields=['recipient', '-created_at'],
                condition=Q(read_at__isnull=True),
                name='notification_unread_idx',
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['recipient', 'task', 'kind'],
                condition=Q(read_at__isnull=True),
                name='one_unread_notification_per_kind',
            ),
        ]

    def __str__(self):
        return f'{self.get_kind_display()} for {self.recipient} on {self.task}'

    @property
    def verb(self):
        return {
            self.ASSIGNED: 'assigned you',
            self.MENTIONED: 'mentioned you',
            self.COMMENTED: 'commented on',
        }[self.kind]

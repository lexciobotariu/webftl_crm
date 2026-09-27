"""Project membership side effects."""

from django.utils import timezone

from apps.tasks.models import Task, TimeEntry
from apps.tasks.services import _close_open_entry


def handle_member_removed(project_id, user_id):
    """Close the live task when someone leaves a project.

    Clears ``assignee`` on this project's tasks so the work is not stuck
    on a person who can no longer open it. A running timer on those tasks
    is closed in place. Time entry rows stay.
    """
    Task.objects.filter(project_id=project_id, assignee_id=user_id).update(assignee=None)

    now = timezone.now()
    open_entries = TimeEntry.objects.filter(
        user_id=user_id,
        ended_at__isnull=True,
        task__project_id=project_id,
    )
    for entry in open_entries:
        _close_open_entry(entry, now)

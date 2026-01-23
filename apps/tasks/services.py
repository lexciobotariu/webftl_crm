# apps/tasks/services.py
"""
Service layer for task operations.

This module contains business logic extracted from views.py.
Views should delegate to these functions for all task-related operations.

Key patterns:
- All mutating operations require a `user` parameter for permission checks
- Functions that modify tasks should set `task._changed_by = user` before save
  to trigger activity logging via signals
- Permission errors raise PermissionDenied (caught by views as 403)
"""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max

from apps.projects.models import can_access_project

from .models import Subtask, TaskActivity


class TaskPermissionError(PermissionDenied):
    """Raised when user lacks required access level for a task operation."""
    pass


def require_access(user, project, level='editor'):
    """
    Check if user has required access level to a project.

    Args:
        user: The user attempting the action
        project: The project being accessed
        level: Required role - 'viewer', 'editor', or 'manager'

    Raises:
        TaskPermissionError: If user lacks required access
    """
    if not can_access_project(user, project, level):
        raise TaskPermissionError(f"{level.title()} access required")


def update_task_field(task, field, value, user):
    """
    Update a single field on a task with activity tracking.

    Args:
        task: Task instance to update
        field: Field name to update (e.g., 'priority', 'assignee', 'due_date')
        value: New value for the field
        user: User performing the update (for permissions and activity log)

    Returns:
        The updated task instance

    Raises:
        TaskPermissionError: If user lacks editor access
    """
    require_access(user, task.project, 'editor')

    setattr(task, field, value)
    task._changed_by = user
    task.save()
    return task


def move_task(task, new_status, user):
    """
    Move a task to a new status column.

    Args:
        task: Task instance to move
        new_status: Status instance to move to
        user: User performing the move (for permissions and activity log)

    Raises:
        TaskPermissionError: If user lacks editor access
    """
    require_access(user, task.project, 'editor')

    task.status = new_status
    task._changed_by = user
    task.save()


@transaction.atomic
def create_subtask(task, title, user):
    """
    Create a subtask with automatic ordering.

    Args:
        task: Parent task
        title: Subtask title
        user: User creating the subtask (for permissions)

    Returns:
        The created Subtask instance

    Raises:
        TaskPermissionError: If user lacks editor access
    """
    require_access(user, task.project, 'editor')

    max_order = task.subtasks.aggregate(Max('order'))['order__max']
    return Subtask.objects.create(
        task=task,
        title=title,
        order=(max_order or -1) + 1
    )


def toggle_subtask(subtask, user):
    """
    Toggle a subtask's completion status.

    Args:
        subtask: Subtask instance to toggle
        user: User performing the toggle (for permissions)

    Returns:
        The updated Subtask instance

    Raises:
        TaskPermissionError: If user lacks editor access
    """
    require_access(user, subtask.task.project, 'editor')

    subtask.completed = not subtask.completed
    subtask.save()
    return subtask


def delete_subtask(subtask, user):
    """
    Delete a subtask.

    Args:
        subtask: Subtask instance to delete
        user: User performing the deletion (for permissions)

    Raises:
        TaskPermissionError: If user lacks editor access
    """
    require_access(user, subtask.task.project, 'editor')
    subtask.delete()


def add_comment(task, content, user):
    """
    Add a comment to a task.

    Comments are stored as TaskActivity with type 'comment'.
    Viewers can add comments (lower permission than editing).

    Args:
        task: Task to comment on
        content: Comment text
        user: User making the comment

    Returns:
        The created TaskActivity instance

    Raises:
        TaskPermissionError: If user lacks viewer access
    """
    require_access(user, task.project, 'viewer')

    return TaskActivity.objects.create(
        task=task,
        user=user,
        activity_type='comment',
        content=content
    )

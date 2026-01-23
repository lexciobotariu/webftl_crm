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

from apps.projects.models import can_access_project


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

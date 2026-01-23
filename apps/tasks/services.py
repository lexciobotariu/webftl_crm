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

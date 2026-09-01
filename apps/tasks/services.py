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
import os
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max, Q
from django.utils.text import get_valid_filename

from apps.projects.models import can_access_project

from .models import Attachment, Subtask, TaskActivity

# File upload security settings
ALLOWED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
    '.png', '.jpg', '.jpeg', '.gif',
    '.txt', '.csv', '.zip'
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@dataclass
class FileValidationError:
    """Returned when file validation fails."""
    message: str


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


@transaction.atomic
def move_task(task, new_status, user, position=None):
    """
    Move a task to a new status column, optionally at a specific index.

    The destination column is renumbered so ``order`` stays a dense 0..n-1
    sequence; that is what makes both cross-column moves and intra-column
    reordering survive a page reload.

    Args:
        task: Task instance to move
        new_status: Status instance to move to
        user: User performing the move (for permissions and activity log)
        position: Zero-based index within the destination column. None appends.

    Raises:
        TaskPermissionError: If user lacks editor access
    """
    require_access(user, task.project, 'editor')

    from apps.tasks.models import Task

    # Lock the moved task and both column sets in one pk-ordered query. The
    # subquery reads status_id at lock time so a concurrent move cannot leave
    # us locking the wrong source column; a single query avoids deadlocks from
    # taking the same rows in different orders across two SELECT … FOR UPDATEs.
    _locked_tasks = list(
        Task.objects.select_for_update()
        .filter(
            Q(pk=task.pk)
            | Q(project_id=task.project_id, status_id=new_status.pk)
            | Q(
                project_id=task.project_id,
                status_id__in=Task.objects.filter(pk=task.pk).values('status_id'),
            )
        )
        .order_by('pk')
    )
    locked_task = next((t for t in _locked_tasks if t.pk == task.pk), None)
    if locked_task is None:
        # The task was deleted between the caller's fetch and our lock.
        raise Task.DoesNotExist('Task was deleted during the move.')
    old_status_id = locked_task.status_id

    locked_task.status = new_status
    locked_task._changed_by = user
    locked_task.save()

    destination = list(
        Task.objects.filter(project_id=locked_task.project_id, status=new_status)
        .exclude(pk=locked_task.pk)
        .order_by('order', '-created_at')
    )
    if position is None:
        index = len(destination)
    else:
        index = max(0, min(int(position), len(destination)))
    destination.insert(index, locked_task)

    columns = [destination]
    if old_status_id != new_status.pk:
        # Close the gap the task left behind, so `order` stays dense there too.
        columns.append(
            list(
                Task.objects.filter(project_id=locked_task.project_id, status_id=old_status_id)
                .order_by('order', '-created_at')
            )
        )

    changed = []
    for column in columns:
        for new_order, sibling in enumerate(column):
            if sibling.order != new_order:
                sibling.order = new_order
                changed.append(sibling)
    if changed:
        Task.objects.bulk_update(changed, ['order'])

    # Sync the caller's instance so views can re-render it without a stale
    # status/order (same contract as toggle_subtask).
    task.status = new_status
    task.order = locked_task.order


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
    next_order = 0 if max_order is None else max_order + 1
    return Subtask.objects.create(
        task=task,
        title=title,
        order=next_order
    )


@transaction.atomic
def toggle_subtask(subtask, user):
    """
    Toggle a subtask's completion status.

    The row is locked and re-read first, so two rapid clicks cannot both read
    the same value and land on the same result.

    Args:
        subtask: Subtask instance to toggle
        user: User performing the toggle (for permissions)

    Returns:
        The updated Subtask instance

    Raises:
        TaskPermissionError: If user lacks editor access
    """
    require_access(user, subtask.task.project, 'editor')

    locked = Subtask.objects.select_for_update().get(pk=subtask.pk)
    locked.completed = not locked.completed
    locked.save(update_fields=['completed'])

    subtask.completed = locked.completed
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


def validate_upload(file):
    """
    Validate a file for upload.

    Args:
        file: UploadedFile instance

    Returns:
        FileValidationError if validation fails, None if valid
    """
    if not file:
        return FileValidationError("No file provided")

    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return FileValidationError(
            f"File type not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if file.size > MAX_FILE_SIZE:
        return FileValidationError("File too large. Maximum size is 10MB.")

    return None


def upload_attachment(task, file, user):
    """
    Upload an attachment to a task.

    Args:
        task: Task to attach file to
        file: UploadedFile instance
        user: User uploading the file

    Returns:
        The created Attachment instance

    Raises:
        TaskPermissionError: If user lacks editor access
        ValueError: If file validation fails
    """
    require_access(user, task.project, 'editor')

    error = validate_upload(file)
    if error:
        raise ValueError(error.message)

    return Attachment.objects.create(
        task=task,
        file=file,
        filename=get_valid_filename(file.name),
        uploaded_by=user
    )


def delete_task(task, user):
    """
    Delete a task.

    Args:
        task: Task instance to delete
        user: User performing the deletion (for permissions)

    Raises:
        TaskPermissionError: If user lacks editor access
    """
    require_access(user, task.project, 'editor')
    task.delete()


def toggle_label(task, label, user):
    """
    Toggle a label on a task (add if not present, remove if present).

    Args:
        task: Task instance
        label: Label instance to toggle
        user: User performing the action (for permissions)

    Raises:
        TaskPermissionError: If user lacks editor access
    """
    require_access(user, task.project, 'editor')

    if label in task.labels.all():
        task.labels.remove(label)
    else:
        task.labels.add(label)

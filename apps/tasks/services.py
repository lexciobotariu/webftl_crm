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
from datetime import datetime, time, timedelta

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import DateTimeField, ExpressionWrapper, F, Max, Q
from django.utils import timezone
from django.utils.text import get_valid_filename

from .durations import MAX_DAY_MINUTES
from .models import (
    Attachment,
    Subtask,
    TaskActivity,
    TimeEntry,
    can_create_task,
    can_edit_task,
    can_edit_tasks_on,
    can_view_task,
)

# File upload security settings
ALLOWED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
    '.png', '.jpg', '.jpeg', '.gif',
    '.txt', '.csv', '.zip'
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
TIMER_LIMIT = timedelta(hours=12)


@dataclass
class FileValidationError:
    """Returned when file validation fails."""
    message: str


class TaskPermissionError(PermissionDenied):
    """Raised when user lacks required access level for a task operation."""
    pass


class TimeEntryValidationError(ValueError):
    """A logged time range breaks the manual-entry rules."""


def require_access(user, project):
    """Edit a task on ``project``.

    Admin, ``tasks_edit_all``, or ``tasks_edit_own`` plus a ProjectAccess row.
    Project view, project edit, and ``tasks_view_all`` do not grant this.
    """
    if not can_edit_tasks_on(user, project):
        raise TaskPermissionError('You cannot edit this task')


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
    require_access(user, task.project)

    setattr(task, field, value)
    task._changed_by = user
    task.save()
    return task


# Default for move_task's ``after_id``: no anchor given, so ``position`` decides.
AFTER_UNSET = object()


@transaction.atomic
def move_task(task, new_status, user, position=None, after_id=AFTER_UNSET):
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
        after_id: The card the task was dropped under. Use it when the client only
            shows some of the column (filters), where a visible index is not the
            column index. ``None`` drops at the top, a pk drops right after that
            card, and a card that is not in the column (deleted, moved, another
            project) appends. Wins over ``position``; left out, ``position`` decides.

    Raises:
        TaskPermissionError: If user lacks editor access
    """
    require_access(user, task.project)

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
    if after_id is not AFTER_UNSET:
        if after_id is None:
            index = 0
        else:
            anchor = next((i for i, t in enumerate(destination) if t.pk == after_id), None)
            index = len(destination) if anchor is None else anchor + 1
    elif position is None:
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
    if not can_create_task(user, task.project):
        raise TaskPermissionError('You cannot create tasks on this project')

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
    require_access(user, subtask.task.project)

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
    require_access(user, subtask.task.project)
    subtask.delete()


def add_comment(task, content, user, mentions=()):
    """
    Add a comment to a task.

    Comments are stored as TaskActivity with type 'comment'.
    Editors can add comments, same as creating a task or starting a timer.

    Args:
        task: Task to comment on
        content: Comment text
        user: User making the comment
        mentions: User ids picked in the @ menu

    Returns:
        The created TaskActivity instance

    Raises:
        TaskPermissionError: If user lacks editor access
    """
    from apps.notifications.services import notify_comment

    require_access(user, task.project)

    comment = TaskActivity.objects.create(
        task=task,
        user=user,
        activity_type='comment',
        content=content
    )
    # ``mentions`` are the ids picked in the @ menu; notify_comment keeps the
    # ones who can see the task and are still named in the text.
    notify_comment(comment, mentions)
    return comment


def can_change_comment(user, comment):
    """The author while they can still edit the task, or an admin.

    Same rule as :func:`require_entry_edit`: ``tasks_edit_all`` does not let
    anyone change someone else's words.
    """
    if user.is_admin:
        return True
    return comment.user_id == user.pk and can_edit_task(user, comment.task)


def require_comment_change(user, comment):
    if not can_change_comment(user, comment):
        raise TaskPermissionError('You can only change your own comments')


def edit_comment(comment, content, user):
    require_comment_change(user, comment)
    if content == comment.content:
        return comment
    comment.content = content
    comment.edited_at = timezone.now()
    comment.save(update_fields=['content', 'edited_at'])
    return comment


def delete_comment(comment, user):
    from apps.notifications.services import comment_deleted

    require_comment_change(user, comment)
    with transaction.atomic():
        comment_deleted(comment)
        comment.delete()


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
    require_access(user, task.project)

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
    Delete a task. ``role=admin`` only. Edit flags do not grant this.

    Args:
        task: Task instance to delete
        user: User performing the deletion (for permissions)

    Raises:
        TaskPermissionError: If the user is not an admin
    """
    if not user.is_admin:
        raise TaskPermissionError('Admin access required')
    task.delete()


def log_label_change(task, label, user, added):
    """One row per label put on or taken off a task.

    Labels are a many-to-many field, so a Task save never sees them change:
    the places that change them call this (toggle_label and the edit form).
    """
    TaskActivity.objects.create(
        task=task,
        user=user,
        activity_type='label_added' if added else 'label_removed',
        old_value='' if added else label.name,
        new_value=label.name if added else '',
        content=f'added label {label.name}' if added else f'removed label {label.name}',
    )


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
    require_access(user, task.project)

    if task.labels.filter(pk=label.pk).exists():
        task.labels.remove(label)
        log_label_change(task, label, user, added=False)
    else:
        task.labels.add(label)
        log_label_change(task, label, user, added=True)


def close_expired_timers(now=None):
    """Stop timers that have been running longer than 12 hours.

    ``ended_at`` is the start plus 12 hours, not the moment this runs.
    Already-closed rows are left alone, including manual entries longer
    than 12 hours. Returns the number of rows closed.
    """
    if now is None:
        now = timezone.now()
    cutoff = now - TIMER_LIMIT
    return TimeEntry.objects.filter(
        ended_at__isnull=True,
        started_at__lte=cutoff,
    ).update(
        ended_at=ExpressionWrapper(
            F('started_at') + TIMER_LIMIT,
            output_field=DateTimeField(),
        )
    )


def logged_seconds_on_task(task, now=None):
    """Seconds logged on ``task`` by everyone.

    Closes timers past 12 hours first. A closed row counts
    ``ended_at - started_at``. A timer that is still running counts
    elapsed time so far, and never more than 12 hours.
    """
    if now is None:
        now = timezone.now()
    close_expired_timers(now=now)
    return sum(entry_seconds(entry, now) for entry in task.time_entries.all())


def entry_seconds(entry, now):
    """Seconds one entry counts for: its span, or for a running timer the time so far, up to 12 hours."""
    if entry.ended_at is None:
        elapsed = int((now - entry.started_at).total_seconds())
        return max(min(elapsed, int(TIMER_LIMIT.total_seconds())), 0)
    return max(int((entry.ended_at - entry.started_at).total_seconds()), 0)


def _close_open_entry(entry, now):
    """Close one running row at ``now``, or at the 12-hour mark if past it."""
    cap = entry.started_at + TIMER_LIMIT
    entry.ended_at = cap if now >= cap else now
    entry.save(update_fields=['ended_at'])
    return entry


def _close_user_open_timer(user, now):
    entry = (
        TimeEntry.objects.select_for_update()
        .filter(user=user, ended_at__isnull=True)
        .first()
    )
    if entry is None:
        return None
    return _close_open_entry(entry, now)


def require_entry_edit(user, entry):
    """The owner may change their own entry when they can edit the task.

    Changing someone else's entry stays ``role=admin``. ``tasks_edit_all``
    does not grant that.
    """
    if user.is_admin:
        return
    if entry.user_id != user.pk:
        raise TaskPermissionError('You can only change your own time entries')
    if not can_edit_task(user, entry.task):
        raise TaskPermissionError('You cannot edit this task')


def _validate_closed_range(started_at, ended_at, now=None):
    if started_at is None or ended_at is None:
        raise TimeEntryValidationError('Start and end are required.')
    if timezone.is_naive(started_at) or timezone.is_naive(ended_at):
        raise TimeEntryValidationError('Start and end must include a timezone.')
    if ended_at <= started_at:
        raise TimeEntryValidationError('End must be after start.')
    if now is None:
        now = timezone.now()
    if ended_at > now:
        raise TimeEntryValidationError('End cannot be in the future.')


def _week_bounds(week_start):
    """Seven days starting at ``week_start`` (a date or datetime) in the local zone."""
    if isinstance(week_start, datetime):
        if timezone.is_aware(week_start):
            week_start = timezone.localtime(week_start).date()
        else:
            week_start = week_start.date()
    start = timezone.make_aware(datetime.combine(week_start, time.min))
    return start, start + timedelta(days=7)


@transaction.atomic
def start_timer(task, user):
    """Start a timer on ``task`` for ``user``.

    Editors only. Any other open timer for this person is closed first:
    at now, or at the 12-hour mark if that timer is already past it.
    """
    require_access(user, task.project)
    now = timezone.now()
    _close_user_open_timer(user, now)
    try:
        with transaction.atomic():
            return TimeEntry.objects.create(
                task=task,
                user=user,
                started_at=now,
            )
    except IntegrityError:
        _close_user_open_timer(user, timezone.now())
        return TimeEntry.objects.create(
            task=task,
            user=user,
            started_at=timezone.now(),
        )


@transaction.atomic
def stop_timer(user):
    """Stop the user's running timer.

    ``ended_at`` is now. If the timer has already passed 12 hours,
    ``ended_at`` is the start plus 12 hours instead. Returns the closed
    row, or None when nothing is running.
    """
    return _close_user_open_timer(user, timezone.now())


def log_manual(task, user, started_at, ended_at, note=''):
    """Log a finished block of the user's own time. Editors only.

    The span may be longer than 12 hours. It must end after it starts
    and cannot end in the future.
    """
    require_access(user, task.project)
    _validate_closed_range(started_at, ended_at)
    return TimeEntry.objects.create(
        task=task,
        user=user,
        started_at=started_at,
        ended_at=ended_at,
        note=note or '',
    )


def _validate_duration_and_day(minutes, day):
    """The rules for a logged duration: a day that is not ahead, and 1 minute to 24 hours."""
    if day is None:
        raise TimeEntryValidationError('Pick the day.')
    if day > timezone.localdate():
        raise TimeEntryValidationError('The day cannot be in the future.')
    if minutes is None or not 1 <= minutes <= MAX_DAY_MINUTES:
        raise TimeEntryValidationError('The duration must be between 1 minute and 24 hours.')


def _start_of_day(day):
    """Midnight of ``day`` in the app's time zone."""
    return timezone.make_aware(datetime.combine(day, time.min))


def log_duration(task, user, minutes, day, note=''):
    """Log ``minutes`` of the user's own time on ``day``. Editors only.

    The entry starts at midnight of that day in the app's zone and ends
    ``minutes`` later, so its day is right wherever the zone sits. The
    "end cannot be in the future" rule of :func:`log_manual` would refuse an
    ordinary morning log of a long day, so it does not apply here.
    """
    require_access(user, task.project)
    _validate_duration_and_day(minutes, day)
    started_at = _start_of_day(day)
    return TimeEntry.objects.create(
        task=task,
        user=user,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=minutes),
        note=note or '',
    )


def update_entry(entry, user, *, minutes, day, note=''):
    """Change a closed entry to ``minutes`` on ``day``.

    The owner must still be an editor; admins may change any. A timer keeps
    its real start when the day stays the same, and the end becomes start
    plus ``minutes``; a new day moves the start to that day's midnight.
    """
    require_entry_edit(user, entry)
    if entry.ended_at is None:
        raise TimeEntryValidationError('A running timer cannot be edited. Stop it first.')
    _validate_duration_and_day(minutes, day)
    if timezone.localdate(entry.started_at) != day:
        entry.started_at = _start_of_day(day)
    entry.ended_at = entry.started_at + timedelta(minutes=minutes)
    entry.note = note or ''
    entry.save(update_fields=['started_at', 'ended_at', 'note'])
    return entry


def delete_entry(entry, user):
    """Delete an entry. Same permission rule as :func:`update_entry`."""
    require_entry_edit(user, entry)
    entry.delete()


def entries_for_week(user, week_start, project=None):
    """Entries that started in the seven days from ``week_start``.

    Without a project, this is the user's own week. With a project,
    ``role=admin`` and ``tasks_view_all`` see every entry on that project.
    Everyone else still sees only their own.
    """
    start, end = _week_bounds(week_start)
    entries = (
        TimeEntry.objects.filter(started_at__gte=start, started_at__lt=end)
        .select_related('task', 'task__project', 'user')
        .order_by('started_at', 'pk')
    )
    if project is not None:
        entries = entries.filter(task__project=project)
        if user.is_admin or user.has_app_permission('tasks_view_all'):
            return entries
    return entries.filter(user=user)


def entries_on_task(user, task):
    """Entries visible on a task screen.

    You see your own time on tasks you can view. ``role=admin`` and
    ``tasks_view_all`` also see everyone else's time on those tasks.
    """
    if not can_view_task(user, task):
        return task.time_entries.none()
    entries = task.time_entries.select_related('user').order_by('-started_at', '-pk')
    if user.is_admin or user.has_app_permission('tasks_view_all'):
        return entries
    return entries.filter(user=user)

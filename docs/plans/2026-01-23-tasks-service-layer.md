# Tasks Service Layer Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract business logic from `apps/tasks/views.py` (437 lines, 24 functions) into a service layer for better testability, reusability, and maintainability.

**Architecture:** Create `apps/tasks/services.py` with domain operations (task CRUD, subtasks, comments, attachments). Views become thin HTTP handlers that delegate to services. The existing signal-based activity tracking remains unchanged - services set `_changed_by` attribute before save to trigger activity logging.

**Tech Stack:** Django 5.1, pytest, factory-boy, existing signal infrastructure

---

## Key Constraints

1. **Preserve signal-based activity tracking** - Views must continue setting `task._changed_by = request.user` before `.save()` to trigger `TaskActivity` creation via signals in `signals.py`
2. **Preserve authorization pattern** - Use `can_access_project()` from `apps/projects/models.py`
3. **Preserve HTMX response patterns** - Views still handle `HX-Trigger` headers and partial rendering
4. **GitHub integration compatibility** - `apps/integrations/github.py` directly manipulates Task objects; services should not break this
5. **All existing tests must pass** - 51 tests in `apps/tasks/tests/`

---

## Task 1: Create Service Layer Foundation with Permission Handling

**Files:**
- Create: `apps/tasks/services.py`
- Test: `apps/tasks/tests/test_services.py`

**Step 1: Write failing test for permission error**

```python
# apps/tasks/tests/test_services.py
import pytest
from django.core.exceptions import PermissionDenied

from apps.accounts.factories import UserFactory
from apps.projects.factories import ProjectFactory, ProjectMemberFactory
from apps.tasks import services


@pytest.mark.django_db
class TestPermissions:
    def test_require_access_raises_for_non_member(self):
        user = UserFactory()
        project = ProjectFactory()
        # No membership created

        with pytest.raises(PermissionDenied) as exc_info:
            services.require_access(user, project, 'editor')

        assert 'Editor access required' in str(exc_info.value)

    def test_require_access_passes_for_editor(self):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')

        # Should not raise
        services.require_access(user, project, 'editor')

    def test_require_access_passes_for_admin(self):
        from apps.accounts.factories import AdminUserFactory
        admin = AdminUserFactory()
        project = ProjectFactory()
        # No membership needed for admin

        # Should not raise
        services.require_access(admin, project, 'manager')
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py -v`

Expected: FAIL with "cannot import name 'services' from 'apps.tasks'"

**Step 3: Write minimal implementation**

```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add apps/tasks/services.py apps/tasks/tests/test_services.py
git commit -m "feat(tasks): add service layer foundation with permission handling"
```

---

## Task 2: Add Task Field Update Service

**Files:**
- Modify: `apps/tasks/services.py`
- Modify: `apps/tasks/tests/test_services.py`

**Step 1: Write failing test for field update**

```python
# Add to apps/tasks/tests/test_services.py

from apps.tasks.factories import TaskFactory
from apps.tasks.models import TaskActivity


@pytest.mark.django_db
class TestUpdateTaskField:
    def test_update_task_field_changes_value(self):
        user = UserFactory()
        task = TaskFactory(priority='low')
        ProjectMemberFactory(project=task.project, user=user, role='editor')

        result = services.update_task_field(task, 'priority', 'high', user)

        task.refresh_from_db()
        assert task.priority == 'high'
        assert result == task

    def test_update_task_field_creates_activity(self):
        user = UserFactory()
        task = TaskFactory(priority='low')
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        TaskActivity.objects.filter(task=task).delete()

        services.update_task_field(task, 'priority', 'high', user)

        activity = TaskActivity.objects.filter(task=task, activity_type='priority_change').first()
        assert activity is not None
        assert activity.user == user

    def test_update_task_field_requires_editor(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')

        with pytest.raises(PermissionDenied):
            services.update_task_field(task, 'priority', 'high', user)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestUpdateTaskField -v`

Expected: FAIL with "AttributeError: module 'apps.tasks.services' has no attribute 'update_task_field'"

**Step 3: Write minimal implementation**

```python
# Add to apps/tasks/services.py

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
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestUpdateTaskField -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add apps/tasks/services.py apps/tasks/tests/test_services.py
git commit -m "feat(tasks): add update_task_field service with activity tracking"
```

---

## Task 3: Add Task Move Service

**Files:**
- Modify: `apps/tasks/services.py`
- Modify: `apps/tasks/tests/test_services.py`

**Step 1: Write failing test for task move**

```python
# Add to apps/tasks/tests/test_services.py

from apps.projects.factories import StatusFactory


@pytest.mark.django_db
class TestMoveTask:
    def test_move_task_changes_status(self):
        user = UserFactory()
        project = ProjectFactory()
        status1 = StatusFactory(project=project, name='Backlog')
        status2 = StatusFactory(project=project, name='Done')
        task = TaskFactory(project=project, status=status1)
        ProjectMemberFactory(project=project, user=user, role='editor')

        services.move_task(task, status2, user)

        task.refresh_from_db()
        assert task.status == status2

    def test_move_task_creates_activity(self):
        user = UserFactory()
        project = ProjectFactory()
        status1 = StatusFactory(project=project, name='Backlog')
        status2 = StatusFactory(project=project, name='Done')
        task = TaskFactory(project=project, status=status1)
        ProjectMemberFactory(project=project, user=user, role='editor')
        TaskActivity.objects.filter(task=task).delete()

        services.move_task(task, status2, user)

        activity = TaskActivity.objects.filter(task=task, activity_type='status_change').first()
        assert activity is not None
        assert activity.user == user

    def test_move_task_requires_editor(self):
        user = UserFactory()
        project = ProjectFactory()
        status1 = StatusFactory(project=project, name='Backlog')
        status2 = StatusFactory(project=project, name='Done')
        task = TaskFactory(project=project, status=status1)
        ProjectMemberFactory(project=project, user=user, role='viewer')

        with pytest.raises(PermissionDenied):
            services.move_task(task, status2, user)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestMoveTask -v`

Expected: FAIL with "AttributeError: module 'apps.tasks.services' has no attribute 'move_task'"

**Step 3: Write minimal implementation**

```python
# Add to apps/tasks/services.py

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
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestMoveTask -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add apps/tasks/services.py apps/tasks/tests/test_services.py
git commit -m "feat(tasks): add move_task service"
```

---

## Task 4: Add Subtask Services

**Files:**
- Modify: `apps/tasks/services.py`
- Modify: `apps/tasks/tests/test_services.py`

**Step 1: Write failing tests for subtask operations**

```python
# Add to apps/tasks/tests/test_services.py

from apps.tasks.factories import SubtaskFactory
from apps.tasks.models import Subtask


@pytest.mark.django_db
class TestSubtaskServices:
    def test_create_subtask(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')

        subtask = services.create_subtask(task, 'New subtask', user)

        assert subtask.task == task
        assert subtask.title == 'New subtask'
        assert subtask.completed is False

    def test_create_subtask_auto_orders(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        SubtaskFactory(task=task, order=0)
        SubtaskFactory(task=task, order=1)

        subtask = services.create_subtask(task, 'Third', user)

        assert subtask.order == 2

    def test_create_subtask_requires_editor(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')

        with pytest.raises(PermissionDenied):
            services.create_subtask(task, 'Subtask', user)

    def test_toggle_subtask(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        subtask = SubtaskFactory(task=task, completed=False)

        result = services.toggle_subtask(subtask, user)

        subtask.refresh_from_db()
        assert subtask.completed is True
        assert result == subtask

    def test_toggle_subtask_again(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        subtask = SubtaskFactory(task=task, completed=True)

        services.toggle_subtask(subtask, user)

        subtask.refresh_from_db()
        assert subtask.completed is False

    def test_delete_subtask(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        subtask = SubtaskFactory(task=task)
        subtask_pk = subtask.pk

        services.delete_subtask(subtask, user)

        assert not Subtask.objects.filter(pk=subtask_pk).exists()

    def test_delete_subtask_requires_editor(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')
        subtask = SubtaskFactory(task=task)

        with pytest.raises(PermissionDenied):
            services.delete_subtask(subtask, user)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestSubtaskServices -v`

Expected: FAIL with "AttributeError: module 'apps.tasks.services' has no attribute 'create_subtask'"

**Step 3: Write minimal implementation**

```python
# Add to apps/tasks/services.py

from django.db import transaction
from django.db.models import Max

from .models import Subtask


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
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestSubtaskServices -v`

Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add apps/tasks/services.py apps/tasks/tests/test_services.py
git commit -m "feat(tasks): add subtask services (create, toggle, delete)"
```

---

## Task 5: Add Comment Service

**Files:**
- Modify: `apps/tasks/services.py`
- Modify: `apps/tasks/tests/test_services.py`

**Step 1: Write failing test for comment creation**

```python
# Add to apps/tasks/tests/test_services.py

@pytest.mark.django_db
class TestCommentService:
    def test_add_comment(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')

        activity = services.add_comment(task, 'This is a comment', user)

        assert activity.task == task
        assert activity.user == user
        assert activity.activity_type == 'comment'
        assert activity.content == 'This is a comment'

    def test_add_comment_requires_viewer(self):
        user = UserFactory()
        task = TaskFactory()
        # No membership

        with pytest.raises(PermissionDenied):
            services.add_comment(task, 'Comment', user)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestCommentService -v`

Expected: FAIL with "AttributeError: module 'apps.tasks.services' has no attribute 'add_comment'"

**Step 3: Write minimal implementation**

```python
# Add to apps/tasks/services.py

from .models import TaskActivity


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
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestCommentService -v`

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add apps/tasks/services.py apps/tasks/tests/test_services.py
git commit -m "feat(tasks): add comment service"
```

---

## Task 6: Add Attachment Upload Service

**Files:**
- Modify: `apps/tasks/services.py`
- Modify: `apps/tasks/tests/test_services.py`

**Step 1: Write failing tests for attachment upload**

```python
# Add to apps/tasks/tests/test_services.py

from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.mark.django_db
class TestAttachmentService:
    def test_validate_upload_valid_file(self):
        file = SimpleUploadedFile('test.pdf', b'content', content_type='application/pdf')

        error = services.validate_upload(file)

        assert error is None

    def test_validate_upload_no_file(self):
        error = services.validate_upload(None)

        assert error is not None
        assert 'No file provided' in error.message

    def test_validate_upload_invalid_extension(self):
        file = SimpleUploadedFile('test.exe', b'content')

        error = services.validate_upload(file)

        assert error is not None
        assert 'not allowed' in error.message

    def test_validate_upload_file_too_large(self):
        # Create file larger than 10MB
        large_content = b'x' * (11 * 1024 * 1024)
        file = SimpleUploadedFile('test.txt', large_content)

        error = services.validate_upload(file)

        assert error is not None
        assert 'too large' in error.message

    def test_upload_attachment(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        file = SimpleUploadedFile('test.txt', b'content', content_type='text/plain')

        attachment = services.upload_attachment(task, file, user)

        assert attachment.task == task
        assert attachment.uploaded_by == user
        assert attachment.filename == 'test.txt'

    def test_upload_attachment_requires_editor(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')
        file = SimpleUploadedFile('test.txt', b'content')

        with pytest.raises(PermissionDenied):
            services.upload_attachment(task, file, user)

    def test_upload_attachment_validates_file(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='editor')
        file = SimpleUploadedFile('test.exe', b'content')

        with pytest.raises(ValueError) as exc_info:
            services.upload_attachment(task, file, user)

        assert 'not allowed' in str(exc_info.value)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestAttachmentService -v`

Expected: FAIL with "AttributeError: module 'apps.tasks.services' has no attribute 'validate_upload'"

**Step 3: Write minimal implementation**

```python
# Add to apps/tasks/services.py

import os
from dataclasses import dataclass

from django.utils.text import get_valid_filename

from .models import Attachment


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
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestAttachmentService -v`

Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add apps/tasks/services.py apps/tasks/tests/test_services.py
git commit -m "feat(tasks): add attachment upload service with validation"
```

---

## Task 7: Add Task Delete Service

**Files:**
- Modify: `apps/tasks/services.py`
- Modify: `apps/tasks/tests/test_services.py`

**Step 1: Write failing test for task deletion**

```python
# Add to apps/tasks/tests/test_services.py

from apps.tasks.models import Task


@pytest.mark.django_db
class TestDeleteTask:
    def test_delete_task(self):
        user = UserFactory()
        task = TaskFactory()
        task_pk = task.pk
        ProjectMemberFactory(project=task.project, user=user, role='editor')

        services.delete_task(task, user)

        assert not Task.objects.filter(pk=task_pk).exists()

    def test_delete_task_requires_editor(self):
        user = UserFactory()
        task = TaskFactory()
        ProjectMemberFactory(project=task.project, user=user, role='viewer')

        with pytest.raises(PermissionDenied):
            services.delete_task(task, user)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestDeleteTask -v`

Expected: FAIL with "AttributeError: module 'apps.tasks.services' has no attribute 'delete_task'"

**Step 3: Write minimal implementation**

```python
# Add to apps/tasks/services.py

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
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestDeleteTask -v`

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add apps/tasks/services.py apps/tasks/tests/test_services.py
git commit -m "feat(tasks): add delete_task service"
```

---

## Task 8: Add Label Toggle Service

**Files:**
- Modify: `apps/tasks/services.py`
- Modify: `apps/tasks/tests/test_services.py`

**Step 1: Write failing tests for label toggle**

```python
# Add to apps/tasks/tests/test_services.py

from apps.tasks.factories import LabelFactory


@pytest.mark.django_db
class TestToggleLabel:
    def test_toggle_label_adds_label(self):
        user = UserFactory()
        task = TaskFactory()
        label = LabelFactory(project=task.project)
        ProjectMemberFactory(project=task.project, user=user, role='editor')

        services.toggle_label(task, label, user)

        assert label in task.labels.all()

    def test_toggle_label_removes_label(self):
        user = UserFactory()
        task = TaskFactory()
        label = LabelFactory(project=task.project)
        task.labels.add(label)
        ProjectMemberFactory(project=task.project, user=user, role='editor')

        services.toggle_label(task, label, user)

        assert label not in task.labels.all()

    def test_toggle_label_requires_editor(self):
        user = UserFactory()
        task = TaskFactory()
        label = LabelFactory(project=task.project)
        ProjectMemberFactory(project=task.project, user=user, role='viewer')

        with pytest.raises(PermissionDenied):
            services.toggle_label(task, label, user)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestToggleLabel -v`

Expected: FAIL with "AttributeError: module 'apps.tasks.services' has no attribute 'toggle_label'"

**Step 3: Write minimal implementation**

```python
# Add to apps/tasks/services.py

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
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_services.py::TestToggleLabel -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add apps/tasks/services.py apps/tasks/tests/test_services.py
git commit -m "feat(tasks): add toggle_label service"
```

---

## Task 9: Refactor Views to Use Services - Task Property Updates

**Files:**
- Modify: `apps/tasks/views.py`

**Step 1: Run existing tests to establish baseline**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_views.py -v`

Expected: All tests PASS (this is our baseline)

**Step 2: Refactor task_update_priority to use service**

Replace the `task_update_priority` function in `apps/tasks/views.py`:

```python
# In apps/tasks/views.py, replace task_update_priority (lines 340-353)

@login_required
@require_POST
def task_update_priority(request, pk):
    task = get_object_or_404(Task, pk=pk)
    try:
        from apps.tasks import services
        services.update_task_field(
            task, 'priority',
            request.POST.get('priority') or '',
            request.user
        )
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    response = render(request, 'tasks/partials/priority_dropdown.html', {
        'task': task, 'priority_choices': Task.PRIORITY_CHOICES
    })
    response['HX-Trigger'] = 'activityUpdated'
    return response
```

**Step 3: Refactor task_update_due_date to use service**

Replace the `task_update_due_date` function:

```python
# In apps/tasks/views.py, replace task_update_due_date (lines 356-368)

@login_required
@require_POST
def task_update_due_date(request, pk):
    task = get_object_or_404(Task, pk=pk)
    try:
        from apps.tasks import services
        due_date = request.POST.get('due_date')
        services.update_task_field(
            task, 'due_date',
            due_date if due_date else None,
            request.user
        )
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    response = render(request, 'tasks/partials/due_date_picker.html', {'task': task})
    response['HX-Trigger'] = 'activityUpdated'
    return response
```

**Step 4: Refactor task_update_estimate to use service**

Replace the `task_update_estimate` function:

```python
# In apps/tasks/views.py, replace task_update_estimate (lines 371-381)

@login_required
@require_POST
def task_update_estimate(request, pk):
    task = get_object_or_404(Task, pk=pk)
    try:
        from apps.tasks import services
        estimate = request.POST.get('time_estimate')
        services.update_task_field(
            task, 'time_estimate',
            int(estimate) if estimate else None,
            request.user
        )
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    return render(request, 'tasks/partials/estimate_input.html', {'task': task})
```

**Step 5: Refactor task_update_assignee to use service**

Replace the `task_update_assignee` function:

```python
# In apps/tasks/views.py, replace task_update_assignee (lines 322-337)

@login_required
@require_POST
def task_update_assignee(request, pk):
    task = get_object_or_404(Task, pk=pk)
    try:
        from apps.tasks import services
        assignee_id = request.POST.get('assignee_id')
        assignee = User.objects.get(pk=assignee_id) if assignee_id else None
        services.update_task_field(task, 'assignee', assignee, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    team_members = User.objects.all()
    response = render(request, 'tasks/partials/assignee_dropdown.html', {
        'task': task, 'team_members': team_members
    })
    response['HX-Trigger'] = 'activityUpdated'
    return response
```

**Step 6: Run tests to verify refactoring**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_views.py -v`

Expected: All tests PASS

**Step 7: Commit**

```bash
git add apps/tasks/views.py
git commit -m "refactor(tasks): use services for task property updates"
```

---

## Task 10: Refactor Views to Use Services - Task Move and Status

**Files:**
- Modify: `apps/tasks/views.py`

**Step 1: Refactor task_move to use service**

Replace the `task_move` function in `apps/tasks/views.py`:

```python
# In apps/tasks/views.py, replace task_move (lines 160-173)

@login_required
@require_POST
@transaction.atomic
def task_move(request):
    task_id = request.POST.get('task_id')
    status_id = request.POST.get('status_id')
    task = get_object_or_404(Task.objects.select_for_update(), pk=task_id)
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    try:
        from apps.tasks import services
        services.move_task(task, status, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    return HttpResponse(status=204)
```

**Step 2: Refactor task_update_status to use service**

Replace the `task_update_status` function:

```python
# In apps/tasks/views.py, replace task_update_status (lines 176-189)

@login_required
@require_POST
def task_update_status(request, pk):
    task = get_object_or_404(Task, pk=pk)
    status_id = request.POST.get('status_id')
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    try:
        from apps.tasks import services
        services.move_task(task, status, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    response = render(request, 'tasks/partials/status_dropdown.html', {'task': task})
    response['HX-Trigger'] = 'taskStatusChanged, activityUpdated'
    return response
```

**Step 3: Run tests to verify refactoring**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_views.py::TestTaskMove apps/tasks/tests/test_views.py::TestTaskUpdateStatus -v`

Expected: All tests PASS

**Step 4: Commit**

```bash
git add apps/tasks/views.py
git commit -m "refactor(tasks): use services for task move and status updates"
```

---

## Task 11: Refactor Views to Use Services - Subtasks

**Files:**
- Modify: `apps/tasks/views.py`

**Step 1: Refactor subtask_create to use service**

Replace the `subtask_create` function:

```python
# In apps/tasks/views.py, replace subtask_create (lines 192-211)

@login_required
@require_POST
@transaction.atomic
def subtask_create(request, pk):
    task = get_object_or_404(Task.objects.select_for_update(), pk=pk)
    form = SubtaskForm(request.POST)
    if not form.is_valid():
        return HttpResponse(status=400)
    try:
        from apps.tasks import services
        subtask = services.create_subtask(task, form.cleaned_data['title'], request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    html = render(request, 'tasks/partials/subtask_item.html', {'subtask': subtask}).content.decode()
    counter_html = render(request, 'tasks/partials/subtask_counter.html', {'task': task}).content.decode()
    return HttpResponse(html + counter_html)
```

**Step 2: Refactor subtask_toggle to use service**

Replace the `subtask_toggle` function:

```python
# In apps/tasks/views.py, replace subtask_toggle (lines 214-226)

@login_required
@require_POST
def subtask_toggle(request, pk, subtask_pk):
    subtask = get_object_or_404(Subtask, pk=subtask_pk, task_id=pk)
    try:
        from apps.tasks import services
        services.toggle_subtask(subtask, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    task = subtask.task
    html = render(request, 'tasks/partials/subtask_item.html', {'subtask': subtask}).content.decode()
    counter_html = render(request, 'tasks/partials/subtask_counter.html', {'task': task}).content.decode()
    return HttpResponse(html + counter_html)
```

**Step 3: Refactor subtask_delete to use service**

Replace the `subtask_delete` function:

```python
# In apps/tasks/views.py, replace subtask_delete (lines 229-239)

@login_required
@require_POST
def subtask_delete(request, pk, subtask_pk):
    subtask = get_object_or_404(Subtask, pk=subtask_pk, task_id=pk)
    task = subtask.task
    try:
        from apps.tasks import services
        services.delete_subtask(subtask, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    counter_html = render(request, 'tasks/partials/subtask_counter.html', {'task': task}).content.decode()
    return HttpResponse(counter_html)
```

**Step 4: Run tests to verify refactoring**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_views.py::TestSubtasks -v`

Expected: All tests PASS

**Step 5: Commit**

```bash
git add apps/tasks/views.py
git commit -m "refactor(tasks): use services for subtask operations"
```

---

## Task 12: Refactor Views to Use Services - Comments and Attachments

**Files:**
- Modify: `apps/tasks/views.py`

**Step 1: Refactor comment_create to use service**

Replace the `comment_create` function:

```python
# In apps/tasks/views.py, replace comment_create (lines 242-257)

@login_required
@require_POST
def comment_create(request, pk):
    task = get_object_or_404(Task, pk=pk)
    content = request.POST.get('content', '').strip()
    if not content:
        return HttpResponse(status=400)
    try:
        from apps.tasks import services
        activity = services.add_comment(task, content, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    return render(request, 'tasks/partials/activity_item.html', {'activity': activity})
```

**Step 2: Refactor attachment_upload to use service**

Replace the `attachment_upload` function:

```python
# In apps/tasks/views.py, replace attachment_upload (lines 269-298)

@login_required
@require_POST
def attachment_upload(request, pk):
    task = get_object_or_404(Task, pk=pk)
    try:
        from apps.tasks import services
        attachment = services.upload_attachment(task, request.FILES.get('file'), request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    except ValueError as e:
        return HttpResponse(str(e), status=400)
    return render(request, 'tasks/partials/attachment_item.html', {'attachment': attachment})
```

**Step 3: Run tests to verify refactoring**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_views.py::TestComments apps/tasks/tests/test_views.py::TestAttachmentUpload -v`

Expected: All tests PASS

**Step 4: Commit**

```bash
git add apps/tasks/views.py
git commit -m "refactor(tasks): use services for comments and attachments"
```

---

## Task 13: Refactor Views to Use Services - Task Delete and Label Toggle

**Files:**
- Modify: `apps/tasks/views.py`

**Step 1: Refactor task_delete to use service**

Replace the `task_delete` function:

```python
# In apps/tasks/views.py, replace task_delete (lines 147-157)

@login_required
@require_POST
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    project_pk = task.project.pk
    try:
        from apps.tasks import services
        services.delete_task(task, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    if request.htmx:
        return HttpResponse('')
    return redirect('project_board', pk=project_pk)
```

**Step 2: Refactor task_toggle_label to use service**

Replace the `task_toggle_label` function:

```python
# In apps/tasks/views.py, replace task_toggle_label (lines 384-398)

@login_required
@require_POST
def task_toggle_label(request, pk, label_pk):
    task = get_object_or_404(Task, pk=pk)
    label = get_object_or_404(Label, pk=label_pk, project=task.project)
    try:
        from apps.tasks import services
        services.toggle_label(task, label, request.user)
    except PermissionDenied as e:
        return HttpResponseForbidden(str(e))
    project_labels = task.project.labels.all()
    return render(request, 'tasks/partials/labels_selector.html', {
        'task': task, 'project_labels': project_labels
    })
```

**Step 3: Run tests to verify refactoring**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/test_views.py -v`

Expected: All tests PASS

**Step 4: Commit**

```bash
git add apps/tasks/views.py
git commit -m "refactor(tasks): use services for task delete and label toggle"
```

---

## Task 14: Clean Up Views - Remove Redundant Imports and Constants

**Files:**
- Modify: `apps/tasks/views.py`

**Step 1: Update imports at top of views.py**

The file should now have cleaner imports. Update the top of the file:

```python
# apps/tasks/views.py - updated imports

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.projects.models import Project, Status, can_access_project
from apps.tasks.models import Label
from .forms import TaskForm, SubtaskForm
from .models import Task, Subtask, Attachment, TaskActivity

TASKS_PER_PAGE = 20
```

Note: Remove `os`, `get_valid_filename`, and the file upload constants (`ALLOWED_EXTENSIONS`, `MAX_FILE_SIZE`) as they're now in services.py.

**Step 2: Run all tests to verify nothing is broken**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/ -v`

Expected: All tests PASS

**Step 3: Commit**

```bash
git add apps/tasks/views.py
git commit -m "refactor(tasks): clean up views imports after service extraction"
```

---

## Task 15: Run Full Test Suite and Verify

**Files:**
- None (verification only)

**Step 1: Run all task-related tests**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest apps/tasks/tests/ -v`

Expected: All tests PASS

**Step 2: Run full project test suite**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && pytest -v`

Expected: All tests PASS

**Step 3: Manual smoke test (optional)**

Run: `cd /Users/lexciobotariu/conductor/workspaces/webftl_crm/honolulu && source .venv/bin/activate && python manage.py runserver`

Test manually:
- Create a task
- Move a task between columns
- Add a subtask
- Toggle subtask completion
- Add a comment
- Change task priority
- Upload an attachment

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat(tasks): complete service layer refactoring

- Extract business logic from views.py to services.py
- Add 30+ new service-level unit tests
- Maintain all existing view tests passing
- Views now delegate to services for:
  - Task field updates (assignee, priority, due_date, estimate)
  - Task move/status changes
  - Subtask operations (create, toggle, delete)
  - Comments
  - Attachment uploads
  - Label toggling
  - Task deletion
- Preserve signal-based activity tracking
- Preserve HTMX response patterns"
```

---

## Summary

| Task | Description | New Tests |
|------|-------------|-----------|
| 1 | Service foundation + permissions | 3 |
| 2 | update_task_field service | 3 |
| 3 | move_task service | 3 |
| 4 | Subtask services | 7 |
| 5 | Comment service | 2 |
| 6 | Attachment service | 7 |
| 7 | delete_task service | 2 |
| 8 | toggle_label service | 3 |
| 9-14 | Refactor views to use services | 0 (existing tests) |
| 15 | Final verification | 0 |

**Total new service tests:** 30
**Existing view tests preserved:** 51

**Final structure:**
- `apps/tasks/services.py` - ~150 lines of reusable business logic
- `apps/tasks/views.py` - ~300 lines (reduced from 437, now thin HTTP handlers)
- `apps/tasks/tests/test_services.py` - 30 new unit tests

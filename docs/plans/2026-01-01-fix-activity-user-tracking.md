# Fix Activity User Tracking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix task activity to show the actual user who made changes instead of "System"

**Architecture:** The signals in `apps/tasks/signals.py` already support tracking the user via `instance._changed_by`, but several views don't set this attribute before saving. We need to update those views to set `_changed_by = request.user` before any task save operation.

**Tech Stack:** Django 5.1.4, Django signals, HTMX

---

## Problem Analysis

The `TaskActivity` model records who made changes via the `user` field. The signal `log_task_changes` in `signals.py` reads `instance._changed_by` to populate this field:

```python
user = getattr(instance, '_changed_by', None)
```

**Views that correctly set `_changed_by`:**
- `task_update_assignee` (line 300)
- `task_update_priority` (line 315)
- `task_update_due_date` (line 330)
- `task_update_estimate` (line 343)
- `task_edit_description` (line 375)
- `task_edit_title` (line 395)

**Views that are MISSING `_changed_by`:**
- `task_create` (line 67) - "created" activity shows as System
- `task_edit` (line 119) - any form-based edit shows as System
- `task_move` (line 152) - drag-drop status change shows as System
- `task_update_status` (line 165) - dropdown status change shows as System

---

### Task 1: Fix task_create to track user

**Files:**
- Modify: `apps/tasks/views.py:64-68`
- Test: `apps/tasks/tests/test_views.py`

**Step 1: Write the failing test**

Add to `apps/tasks/tests/test_views.py` in the `TestTaskCreate` class:

```python
def test_task_create_records_activity_with_user(self, client):
    """Creating a task records activity with the creating user."""
    from apps.tasks.models import TaskActivity

    user = UserFactory(is_admin=True)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=user, role='editor')
    status = StatusFactory(project=project)
    client.force_login(user)

    response = client.post(
        reverse('task_create', args=[project.pk]),
        {'title': 'New Task', 'description': 'Test'}
    )

    task = project.tasks.first()
    activity = TaskActivity.objects.filter(task=task, activity_type='created').first()
    assert activity is not None
    assert activity.user == user
```

**Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest apps/tasks/tests/test_views.py::TestTaskCreate::test_task_create_records_activity_with_user -v`
Expected: FAIL with `assert activity.user == user` failing (user is None)

**Step 3: Write minimal implementation**

In `apps/tasks/views.py`, update `task_create`:

```python
# Find this code (around line 64-68):
            task = form.save(commit=False)
            task.project = project
            task.status = status
            task.save()

# Change to:
            task = form.save(commit=False)
            task.project = project
            task.status = status
            task._changed_by = request.user
            task.save()
```

**Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest apps/tasks/tests/test_views.py::TestTaskCreate::test_task_create_records_activity_with_user -v`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/tasks/views.py apps/tasks/tests/test_views.py
git commit -m "fix: track user in task creation activity"
```

---

### Task 2: Fix task_edit to track user

**Files:**
- Modify: `apps/tasks/views.py:114-120`
- Test: `apps/tasks/tests/test_views.py`

**Step 1: Write the failing test**

Add to `apps/tasks/tests/test_views.py`:

```python
class TestTaskEdit:
    @pytest.mark.django_db
    def test_task_edit_records_activity_with_user(self, client):
        """Editing a task via form records activity with the editing user."""
        from apps.tasks.models import TaskActivity

        user = UserFactory(is_admin=True)
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')
        status1 = StatusFactory(project=project, name='Backlog')
        status2 = StatusFactory(project=project, name='In Progress')
        task = TaskFactory(project=project, status=status1)
        client.force_login(user)

        # Clear existing activities
        TaskActivity.objects.filter(task=task).delete()

        response = client.post(
            reverse('task_edit', args=[task.pk]),
            {'title': 'Updated Title', 'description': 'Updated', 'status': status2.pk}
        )

        activity = TaskActivity.objects.filter(task=task, activity_type='status_change').first()
        assert activity is not None
        assert activity.user == user
```

**Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest apps/tasks/tests/test_views.py::TestTaskEdit::test_task_edit_records_activity_with_user -v`
Expected: FAIL with `assert activity.user == user` failing

**Step 3: Write minimal implementation**

In `apps/tasks/views.py`, update `task_edit`:

```python
# Find this code (around line 117-119):
        form = TaskForm(task.project, request.POST, instance=task)
        if form.is_valid():
            form.save()

# Change to:
        form = TaskForm(task.project, request.POST, instance=task)
        if form.is_valid():
            task._changed_by = request.user
            form.save()
```

**Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest apps/tasks/tests/test_views.py::TestTaskEdit::test_task_edit_records_activity_with_user -v`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/tasks/views.py apps/tasks/tests/test_views.py
git commit -m "fix: track user in task edit activity"
```

---

### Task 3: Fix task_move to track user

**Files:**
- Modify: `apps/tasks/views.py:147-153`
- Test: `apps/tasks/tests/test_views.py`

**Step 1: Write the failing test**

Add to `apps/tasks/tests/test_views.py`:

```python
class TestTaskMove:
    @pytest.mark.django_db
    def test_task_move_records_activity_with_user(self, client):
        """Moving a task (drag-drop) records activity with the user."""
        from apps.tasks.models import TaskActivity

        user = UserFactory(is_admin=True)
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')
        status1 = StatusFactory(project=project, name='Backlog')
        status2 = StatusFactory(project=project, name='Done')
        task = TaskFactory(project=project, status=status1)
        client.force_login(user)

        # Clear existing activities
        TaskActivity.objects.filter(task=task).delete()

        response = client.post(
            reverse('task_move'),
            {'task_id': task.pk, 'status_id': status2.pk}
        )

        activity = TaskActivity.objects.filter(task=task, activity_type='status_change').first()
        assert activity is not None
        assert activity.user == user
```

**Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest apps/tasks/tests/test_views.py::TestTaskMove::test_task_move_records_activity_with_user -v`
Expected: FAIL with `assert activity.user == user` failing

**Step 3: Write minimal implementation**

In `apps/tasks/views.py`, update `task_move`:

```python
# Find this code (around line 150-152):
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    task.status = status
    task.save()

# Change to:
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    task.status = status
    task._changed_by = request.user
    task.save()
```

**Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest apps/tasks/tests/test_views.py::TestTaskMove::test_task_move_records_activity_with_user -v`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/tasks/views.py apps/tasks/tests/test_views.py
git commit -m "fix: track user in task move (drag-drop) activity"
```

---

### Task 4: Fix task_update_status to track user

**Files:**
- Modify: `apps/tasks/views.py:160-166`
- Test: `apps/tasks/tests/test_views.py`

**Step 1: Write the failing test**

Add to `apps/tasks/tests/test_views.py`:

```python
class TestTaskUpdateStatus:
    @pytest.mark.django_db
    def test_task_update_status_records_activity_with_user(self, client):
        """Changing status via dropdown records activity with the user."""
        from apps.tasks.models import TaskActivity

        user = UserFactory(is_admin=True)
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='editor')
        status1 = StatusFactory(project=project, name='Backlog')
        status2 = StatusFactory(project=project, name='In Progress')
        task = TaskFactory(project=project, status=status1)
        client.force_login(user)

        # Clear existing activities
        TaskActivity.objects.filter(task=task).delete()

        response = client.post(
            reverse('task_update_status', args=[task.pk]),
            {'status_id': status2.pk}
        )

        activity = TaskActivity.objects.filter(task=task, activity_type='status_change').first()
        assert activity is not None
        assert activity.user == user
```

**Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest apps/tasks/tests/test_views.py::TestTaskUpdateStatus::test_task_update_status_records_activity_with_user -v`
Expected: FAIL with `assert activity.user == user` failing

**Step 3: Write minimal implementation**

In `apps/tasks/views.py`, update `task_update_status`:

```python
# Find this code (around line 163-165):
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    task.status = status
    task.save()

# Change to:
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    task.status = status
    task._changed_by = request.user
    task.save()
```

**Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest apps/tasks/tests/test_views.py::TestTaskUpdateStatus::test_task_update_status_records_activity_with_user -v`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/tasks/views.py apps/tasks/tests/test_views.py
git commit -m "fix: track user in status dropdown activity"
```

---

### Task 5: Run full test suite and final commit

**Step 1: Run all tests**

Run: `./.venv/bin/pytest -v`
Expected: All tests pass

**Step 2: Final commit if needed**

If any cleanup was required, make a final commit.

---

## Summary

After implementation, all task changes will properly track the user who made them:

| View | Activity Type | Before | After |
|------|--------------|--------|-------|
| task_create | created | System | User name |
| task_edit | status_change, etc | System | User name |
| task_move | status_change | System | User name |
| task_update_status | status_change | System | User name |

The `activity_item.html` template already handles this correctly - it shows `{{ activity.user.name|default:"System" }}`, so once we populate the user field, it will display the correct name.

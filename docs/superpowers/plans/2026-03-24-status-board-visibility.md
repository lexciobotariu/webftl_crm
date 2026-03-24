# Status Board Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `visible_on_board` toggle to the Status model so managers can hide statuses (like "Done" or "Archived") from the kanban board, reducing visual clutter while preserving tasks.

**Architecture:** Add a boolean `visible_on_board` field (default `True`) to the `Status` model. Filter the kanban board query to only show visible statuses. Add a toggle button in project settings for each status. The status dropdown on task detail pages continues showing all statuses (so users can still move tasks to hidden statuses). A summary badge in the board header shows how many tasks live in hidden columns.

**Tech Stack:** Django 5.x, HTMX, Alpine.js, Tailwind CSS, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `apps/projects/models.py:40-54` | Add `visible_on_board` field to Status model |
| Create | `apps/projects/migrations/XXXX_add_visible_on_board.py` | Auto-generated migration |
| Modify | `apps/projects/views.py:118-126` | Filter board query to visible statuses; pass hidden task count |
| Modify | `apps/projects/views.py:275-288` | New `status_toggle_visibility` view |
| Modify | `apps/projects/urls.py` | Add toggle visibility URL |
| Modify | `templates/projects/project_board.html:69-73` | Filter to visible statuses; add hidden-tasks badge |
| Modify | `templates/projects/partials/kanban_board.html` | Use `visible_statuses` instead of `project.statuses.all` |
| Modify | `templates/projects/partials/status_item.html` | Add visibility toggle button |
| Modify | `apps/projects/tests/test_models.py` | Test `visible_on_board` default and filtering |
| Modify | `apps/projects/tests/test_views.py` | Test board filtering, toggle endpoint, hidden task count |

---

### Task 1: Add `visible_on_board` field to Status model

**Files:**
- Modify: `apps/projects/models.py:40-54`
- Test: `apps/projects/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

In `apps/projects/tests/test_models.py`, add to `TestStatusModel`:

```python
def test_visible_on_board_defaults_true(self):
    project = ProjectFactory()
    status = project.statuses.first()
    assert status.visible_on_board is True

def test_visible_on_board_can_be_set_false(self):
    project = ProjectFactory()
    status = project.statuses.first()
    status.visible_on_board = False
    status.save()
    status.refresh_from_db()
    assert status.visible_on_board is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest apps/projects/tests/test_models.py::TestStatusModel::test_visible_on_board_defaults_true apps/projects/tests/test_models.py::TestStatusModel::test_visible_on_board_can_be_set_false -v`
Expected: FAIL with `AttributeError: 'Status' object has no attribute 'visible_on_board'`

- [ ] **Step 3: Add the field to the Status model**

In `apps/projects/models.py`, add the field to the `Status` model (after `order`):

```python
class Status(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='statuses')
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    visible_on_board = models.BooleanField(default=True)
```

- [ ] **Step 4: Generate and apply migration**

Run: `python manage.py makemigrations projects -n add_visible_on_board && python manage.py migrate`

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest apps/projects/tests/test_models.py::TestStatusModel -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add apps/projects/models.py apps/projects/migrations/ apps/projects/tests/test_models.py
git commit -m "feat: add visible_on_board field to Status model"
```

---

### Task 2: Filter kanban board to only show visible statuses

**Files:**
- Modify: `apps/projects/views.py:118-126`
- Modify: `apps/tasks/views.py:80-83` (task_create HTMX response also renders kanban_board.html)
- Modify: `templates/projects/project_board.html:69-73`
- Modify: `templates/projects/partials/kanban_board.html`
- Test: `apps/projects/tests/test_views.py`

- [ ] **Step 1: Write the failing tests**

In `apps/projects/tests/test_views.py`, add a new test class:

```python
@pytest.mark.django_db
class TestBoardVisibility:
    def test_board_hides_invisible_statuses(self, client):
        """Statuses with visible_on_board=False should not appear on the board."""
        user = AdminUserFactory()
        project = ProjectFactory()
        hidden_status = project.statuses.filter(name='Done').first()
        hidden_status.visible_on_board = False
        hidden_status.save()
        client.force_login(user)
        response = client.get(reverse('project_board', args=[project.pk]))
        content = response.content.decode()
        assert 'Done' not in content
        # Other statuses still visible
        assert 'Backlog' in content
        assert 'In Progress' in content

    def test_board_shows_hidden_task_count(self, client):
        """Board should show count of tasks in hidden statuses."""
        user = AdminUserFactory()
        project = ProjectFactory()
        hidden_status = project.statuses.filter(name='Done').first()
        hidden_status.visible_on_board = False
        hidden_status.save()
        from apps.tasks.factories import TaskFactory
        TaskFactory(project=project, status=hidden_status)
        TaskFactory(project=project, status=hidden_status)
        client.force_login(user)
        response = client.get(reverse('project_board', args=[project.pk]))
        assert response.context['hidden_task_count'] == 2

    def test_board_no_hidden_badge_when_zero(self, client):
        """No hidden task count in context when all statuses are visible."""
        user = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(user)
        response = client.get(reverse('project_board', args=[project.pk]))
        assert response.context['hidden_task_count'] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest apps/projects/tests/test_views.py::TestBoardVisibility -v`
Expected: FAIL (no `hidden_task_count` in context, hidden status still rendered)

- [ ] **Step 3: Update the `project_board` view**

In `apps/projects/views.py`, replace the `project_board` view:

```python
@login_required
def project_board(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not can_access_project(request.user, project, 'viewer'):
        return HttpResponseForbidden("You don't have access to this project")

    visible_statuses = project.statuses.filter(visible_on_board=True)
    hidden_task_count = Task.objects.filter(
        project=project, status__visible_on_board=False
    ).count()

    context = {
        'project': project,
        'visible_statuses': visible_statuses,
        'hidden_task_count': hidden_task_count,
    }

    if request.htmx:
        return render(request, 'projects/partials/kanban_board.html', context)
    return render(request, 'projects/project_board.html', context)
```

Add `Task` to the imports at top of `views.py` if not already present (it is already imported from `apps.tasks.models`).

- [ ] **Step 4: Update `kanban_board.html` partial**

Replace the contents of `templates/projects/partials/kanban_board.html`:

```html
{% for status in visible_statuses %}
{% include "projects/partials/kanban_column.html" %}
{% endfor %}
```

- [ ] **Step 5: Update `project_board.html` template**

In `templates/projects/project_board.html`, replace the board content loop (lines 69-73):

```html
<div id="kanban-board-content" class="flex gap-3 p-4 h-full min-w-max">
    {% for status in visible_statuses %}
    {% include "projects/partials/kanban_column.html" %}
    {% endfor %}
</div>
```

Also, add the hidden tasks badge inside the header bar (after the Settings button, around line 42):

```html
{% if hidden_task_count > 0 %}
<div class="flex items-center gap-1.5 text-[11px] text-zinc-500 bg-elevated border border-border-subtle rounded-card px-2.5 py-1.5">
    <i data-lucide="eye-off" class="w-3 h-3"></i>
    <span>{{ hidden_task_count }} hidden</span>
</div>
{% endif %}
```

- [ ] **Step 6: Update `task_create` view in `apps/tasks/views.py`**

The `task_create` view also renders `kanban_board.html` after HTMX task creation (line 82-83). It must pass `visible_statuses` too. Replace lines 82-83:

```python
                # Re-render the entire kanban board after task creation
                visible_statuses = project.statuses.filter(visible_on_board=True)
                response = render(request, 'projects/partials/kanban_board.html', {
                    'project': project,
                    'visible_statuses': visible_statuses,
                })
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest apps/projects/tests/test_views.py::TestBoardVisibility -v`
Expected: All PASS

- [ ] **Step 8: Run full test suite to check for regressions**

Run: `python -m pytest apps/projects/tests/ -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add apps/projects/views.py apps/tasks/views.py templates/projects/project_board.html templates/projects/partials/kanban_board.html apps/projects/tests/test_views.py
git commit -m "feat: filter kanban board to only show visible statuses"
```

---

### Task 3: Add visibility toggle endpoint and settings UI

**Files:**
- Modify: `apps/projects/views.py` (add `status_toggle_visibility` view)
- Modify: `apps/projects/urls.py` (add URL route)
- Modify: `templates/projects/partials/status_item.html` (add toggle button)
- Test: `apps/projects/tests/test_views.py`

- [ ] **Step 1: Write the failing tests**

In `apps/projects/tests/test_views.py`, add to the new `TestBoardVisibility` class:

```python
    def test_toggle_visibility_requires_manager(self, client):
        """Only managers can toggle status visibility."""
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        status = project.statuses.first()
        client.force_login(user)
        response = client.post(
            reverse('status_toggle_visibility', args=[project.pk, status.pk])
        )
        assert response.status_code == 403

    def test_toggle_visibility_hides_status(self, client):
        """POSTing to toggle endpoint should flip visible_on_board."""
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='manager')
        status = project.statuses.first()
        assert status.visible_on_board is True
        client.force_login(user)
        response = client.post(
            reverse('status_toggle_visibility', args=[project.pk, status.pk])
        )
        assert response.status_code == 200
        status.refresh_from_db()
        assert status.visible_on_board is False

    def test_toggle_visibility_shows_status(self, client):
        """Toggling a hidden status makes it visible again."""
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='manager')
        status = project.statuses.first()
        status.visible_on_board = False
        status.save()
        client.force_login(user)
        response = client.post(
            reverse('status_toggle_visibility', args=[project.pk, status.pk])
        )
        assert response.status_code == 200
        status.refresh_from_db()
        assert status.visible_on_board is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest apps/projects/tests/test_views.py::TestBoardVisibility::test_toggle_visibility_requires_manager -v`
Expected: FAIL with `NoReverseMatch`

- [ ] **Step 3: Add the URL route**

In `apps/projects/urls.py`, add after the `status_delete` path:

```python
path('<int:pk>/statuses/<int:status_pk>/toggle-visibility/', views.status_toggle_visibility, name='status_toggle_visibility'),
```

- [ ] **Step 4: Add the view**

In `apps/projects/views.py`, add after the `status_delete` view:

```python
@login_required
@require_POST
def status_toggle_visibility(request, pk, status_pk):
    project = get_object_or_404(Project, pk=pk)
    if not can_access_project(request.user, project, 'manager'):
        return HttpResponseForbidden("Manager access required")

    status = get_object_or_404(Status, pk=status_pk, project=project)
    status.visible_on_board = not status.visible_on_board
    status.save()
    return render(request, 'projects/partials/status_item.html', {'status': status, 'project': project})
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest apps/projects/tests/test_views.py::TestBoardVisibility -v`
Expected: All PASS

- [ ] **Step 6: Update the status_item.html template**

Replace `templates/projects/partials/status_item.html` with:

```html
<div class="flex items-center justify-between p-3 bg-panel/70 rounded-card border border-border-subtle {% if not status.visible_on_board %}opacity-50{% endif %}" id="status-{{ status.pk }}">
    <div class="flex items-center gap-2">
        <span class="text-sm text-zinc-300">{{ status.name }}</span>
        {% if not status.visible_on_board %}
        <span class="text-[10px] text-zinc-500 bg-elevated border border-border-subtle rounded px-1.5 py-0.5">hidden</span>
        {% endif %}
    </div>
    <div class="flex items-center gap-3">
        <span class="text-xs text-zinc-500">{{ status.task_count }} tasks</span>
        <button hx-post="{% url 'status_toggle_visibility' project.pk status.pk %}"
                hx-target="#status-{{ status.pk }}"
                hx-swap="outerHTML"
                class="text-zinc-500 hover:text-zinc-300 transition-colors"
                title="{% if status.visible_on_board %}Hide from board{% else %}Show on board{% endif %}">
            {% if status.visible_on_board %}
            <i data-lucide="eye" class="w-4 h-4"></i>
            {% else %}
            <i data-lucide="eye-off" class="w-4 h-4"></i>
            {% endif %}
        </button>
        {% if status.task_count == 0 %}
        <button hx-post="{% url 'status_delete' project.pk status.pk %}"
                hx-target="#status-{{ status.pk }}"
                hx-swap="outerHTML"
                hx-confirm="Delete this status?"
                class="text-zinc-500 hover:text-red-400 transition-colors">
            <i data-lucide="x" class="w-4 h-4"></i>
        </button>
        {% endif %}
    </div>
</div>
```

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest apps/projects/tests/ -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add apps/projects/views.py apps/projects/urls.py templates/projects/partials/status_item.html apps/projects/tests/test_views.py
git commit -m "feat: add visibility toggle for statuses in project settings"
```

---

### Task 4: Ensure task create and status dropdown show all statuses (including hidden)

**Files:**
- Verify: `templates/tasks/partials/status_dropdown.html` (already uses `task.project.statuses.all` — no change needed)
- Verify: `apps/tasks/views.py:59-111` (`task_create` uses `project.statuses.first()` for default — should use first *visible* status)
- Test: `apps/projects/tests/test_views.py`

- [ ] **Step 1: Write the test**

In `apps/projects/tests/test_views.py`, add to `TestBoardVisibility`:

```python
    def test_task_status_dropdown_shows_all_statuses(self, client):
        """The status dropdown on task detail should show all statuses including hidden ones."""
        user = AdminUserFactory()
        project = ProjectFactory()
        hidden_status = project.statuses.filter(name='Done').first()
        hidden_status.visible_on_board = False
        hidden_status.save()
        from apps.tasks.factories import TaskFactory
        task = TaskFactory(project=project, status=project.statuses.first())
        client.force_login(user)
        response = client.get(reverse('task_detail', args=[task.pk]))
        content = response.content.decode()
        # All statuses should appear in the dropdown
        assert 'Done' in content
```

- [ ] **Step 2: Run test to verify it passes (no change needed)**

Run: `python -m pytest apps/projects/tests/test_views.py::TestBoardVisibility::test_task_status_dropdown_shows_all_statuses -v`
Expected: PASS (the dropdown already uses `task.project.statuses.all`, which includes hidden statuses)

This step is a verification that the existing behavior is correct — no code changes needed for the status dropdown.

- [ ] **Step 3: Write test for task creation default status**

In `apps/projects/tests/test_views.py`, add to `TestBoardVisibility`:

```python
    def test_task_create_defaults_to_first_visible_status(self, client):
        """When creating a task without specifying a status, use first visible status."""
        user = AdminUserFactory()
        project = ProjectFactory()
        # Hide the first status (Backlog, order=0)
        first_status = project.statuses.order_by('order').first()
        first_status.visible_on_board = False
        first_status.save()
        second_status = project.statuses.filter(visible_on_board=True).order_by('order').first()
        client.force_login(user)
        response = client.post(
            reverse('task_create', args=[project.pk]),
            {'title': 'Test Task', 'description': ''},
        )
        from apps.tasks.models import Task
        task = Task.objects.get(title='Test Task')
        assert task.status == second_status
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest apps/projects/tests/test_views.py::TestBoardVisibility::test_task_create_defaults_to_first_visible_status -v`
Expected: FAIL (task lands in hidden Backlog status)

- [ ] **Step 5: Update `task_create` view to default to first visible status**

In `apps/tasks/views.py`, in the `task_create` view, change the fallback status (around line 69):

```python
    # Replace:
    #     status = project.statuses.first()
    # With:
        status = project.statuses.filter(visible_on_board=True).first() or project.statuses.first()
```

This falls back to any status if ALL are hidden (edge case safety).

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest apps/projects/tests/test_views.py::TestBoardVisibility -v`
Expected: All PASS

- [ ] **Step 7: Run entire test suite for regressions**

Run: `python -m pytest -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add apps/tasks/views.py apps/projects/tests/test_views.py
git commit -m "feat: default new tasks to first visible status"
```

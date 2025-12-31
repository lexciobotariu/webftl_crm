# Fix Status Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix status creation in settings page to render correctly and add status deletion capability.

**Architecture:** Create a dedicated `status_item.html` partial for the settings list view (matching the `label_item.html` pattern), add a new `status_create` endpoint that returns this partial, and add a `status_delete` view with HTMX integration.

**Tech Stack:** Django views, HTMX for dynamic updates, Tailwind CSS for styling

---

## Problem Analysis

1. **Wrong template returned:** The `manage_statuses` view returns `kanban_column.html` (designed for the board view with drag-drop) instead of a simple list row for the settings page
2. **No delete functionality:** Users cannot delete statuses from the settings page
3. **Pattern mismatch:** Labels have `label_item.html` partial + `label_create`/`label_delete` views, but statuses don't follow this pattern

---

### Task 1: Create status_item.html Partial

**Files:**
- Create: `templates/projects/partials/status_item.html`

**Step 1: Create the status item partial**

Follow the `label_item.html` pattern but adapted for statuses:

```html
<div class="flex items-center justify-between p-3 bg-panel/70 rounded-card border border-border-subtle" id="status-{{ status.pk }}">
    <span class="text-sm text-zinc-300">{{ status.name }}</span>
    <div class="flex items-center gap-3">
        <span class="text-xs text-zinc-500">{{ status.task_count }} tasks</span>
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

**Note:** Delete button only shows when `task_count == 0` to prevent deleting statuses with tasks.

---

### Task 2: Add status_create View

**Files:**
- Modify: `apps/projects/views.py`

**Step 1: Add the status_create view**

Add after the existing `label_delete` view:

```python
@login_required
@require_POST
def status_create(request, pk):
    project = get_object_or_404(Project, pk=pk)
    form = StatusForm(request.POST)
    if form.is_valid():
        status = form.save(commit=False)
        status.project = project
        status.order = project.statuses.count()
        status.save()
        return render(request, 'projects/partials/status_item.html', {'status': status, 'project': project})
    return HttpResponse(status=400)
```

---

### Task 3: Add status_delete View

**Files:**
- Modify: `apps/projects/views.py`

**Step 1: Add the status_delete view**

Add after `status_create`:

```python
@login_required
@require_POST
def status_delete(request, pk, status_pk):
    project = get_object_or_404(Project, pk=pk)
    status = get_object_or_404(Status, pk=status_pk, project=project)

    # Prevent deleting status with tasks
    if status.task_count > 0:
        return HttpResponse('Cannot delete status with tasks', status=400)

    status.delete()
    return HttpResponse('')
```

---

### Task 4: Add URL Routes

**Files:**
- Modify: `apps/projects/urls.py`

**Step 1: Add the new URL patterns**

Add these routes after the existing label routes:

```python
path('<int:pk>/statuses/create/', views.status_create, name='status_create'),
path('<int:pk>/statuses/<int:status_pk>/delete/', views.status_delete, name='status_delete'),
```

Full urlpatterns should be:
```python
urlpatterns = [
    path('', views.project_list, name='project_list'),
    path('create/', views.project_create, name='project_create'),
    path('<int:pk>/', views.project_board, name='project_board'),
    path('<int:pk>/edit/', views.project_edit, name='project_edit'),
    path('<int:pk>/delete/', views.project_delete, name='project_delete'),
    path('<int:pk>/settings/', views.project_settings, name='project_settings'),
    path('<int:pk>/statuses/', views.manage_statuses, name='manage_statuses'),
    path('<int:pk>/statuses/create/', views.status_create, name='status_create'),
    path('<int:pk>/statuses/<int:status_pk>/delete/', views.status_delete, name='status_delete'),
    path('<int:pk>/statuses/reorder/', views.reorder_statuses, name='reorder_statuses'),
    path('<int:pk>/labels/create/', views.label_create, name='label_create'),
    path('<int:pk>/labels/<int:label_pk>/delete/', views.label_delete, name='label_delete'),
]
```

---

### Task 5: Update project_settings.html Template

**Files:**
- Modify: `templates/projects/project_settings.html`

**Step 1: Update the statuses section to use the new partial and endpoint**

Replace lines 53-74 (the Statuses section content) with:

```html
<div class="p-5">
    <div class="space-y-2 mb-4" id="status-list">
        {% for status in project.statuses.all %}
        {% include "projects/partials/status_item.html" %}
        {% empty %}
        <div class="text-zinc-500 text-sm" id="no-statuses">No statuses defined.</div>
        {% endfor %}
    </div>
    <form hx-post="{% url 'status_create' project.pk %}"
          hx-target="#status-list"
          hx-swap="beforeend"
          hx-on::after-request="if(event.detail.successful) { this.reset(); document.getElementById('no-statuses')?.remove(); }"
          class="flex gap-3">
        {% csrf_token %}
        <input type="text" name="name" required placeholder="New status name"
               class="flex-1 bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none">
        <button type="submit" class="bg-accent text-white px-4 py-2 rounded-card text-sm hover:bg-accent-hover transition-colors">
            Add Status
        </button>
    </form>
</div>
```

Key changes:
- Use `{% include "projects/partials/status_item.html" %}` instead of inline HTML
- Change form to use `hx-post="{% url 'status_create' project.pk %}"` instead of `manage_statuses`
- Add `hx-on::after-request` to reset form and remove "no statuses" message

---

### Task 6: Test and Verify

**Manual Testing Steps:**

1. Go to any project's settings page (`/projects/<id>/settings/`)
2. Add a new status - verify it appears with correct styling (matching existing statuses)
3. Verify the delete button appears only for statuses with 0 tasks
4. Delete an empty status - verify it's removed from the list
5. Try to delete a status with tasks - verify it's prevented
6. Refresh the page - verify all statuses still look correct

**Run Django Check:**
```bash
python manage.py check
```

---

### Task 7: Commit

```bash
git add -A
git commit -m "fix: status management in project settings

- Create status_item.html partial for settings list view
- Add status_create endpoint returning correct partial
- Add status_delete endpoint with task count protection
- Update project_settings.html to use new endpoints
- Delete button only shows for empty statuses"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Create status_item.html partial | `templates/projects/partials/status_item.html` |
| 2 | Add status_create view | `apps/projects/views.py` |
| 3 | Add status_delete view | `apps/projects/views.py` |
| 4 | Add URL routes | `apps/projects/urls.py` |
| 5 | Update settings template | `templates/projects/project_settings.html` |
| 6 | Test and verify | Manual testing |
| 7 | Commit changes | Git |

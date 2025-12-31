# Fix Drag-Drop and Status Change Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix task drag-and-drop between kanban columns using Alpine.js Sort plugin and add status change capability in task detail drawer.

**Architecture:** Use Alpine.js Sort plugin with `x-sort:group` for multi-list drag-drop. Add HTMX-powered status dropdown to task detail panel.

**Tech Stack:** Alpine.js Sort plugin (SortableJS), HTMX, Django views

---

## Problem Analysis

1. **Drag-and-drop broken:** Current implementation uses manual drag events but isn't working. Alpine.js has a dedicated Sort plugin that handles multi-list drag-and-drop elegantly.

2. **No status change in drawer:** Task detail shows status as static badge, no way to change it

3. **Drawer too narrow:** Currently `max-w-[480px]`, needs to be wider

---

### Task 1: Add Alpine.js Sort Plugin

**Files:**
- Modify: `templates/base.html`

**Step 1: Add Sort plugin CDN before Alpine core**

Add after line 64 (before alpine):
```html
<script defer src="https://cdn.jsdelivr.net/npm/@alpinejs/sort@3.x.x/dist/cdn.min.js"></script>
```

The scripts section should be:
```html
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<script defer src="https://cdn.jsdelivr.net/npm/@alpinejs/sort@3.x.x/dist/cdn.min.js"></script>
<script defer src="https://unpkg.com/@alpinejs/csp@3.14.8/dist/cdn.min.js"></script>
```

**Step 2: Widen slide-over panel**

Change line 96 from `max-w-[480px]` to `max-w-xl` (576px).

---

### Task 2: Update Kanban Column for Sort Plugin

**Files:**
- Modify: `templates/projects/partials/kanban_column.html`

**Replace entire file with:**

```html
<div class="flex-shrink-0 w-64 h-full flex flex-col bg-card/50 rounded-panel border border-border-subtle"
     id="column-{{ status.pk }}">
    <!-- Column header - fixed -->
    <div class="flex-shrink-0 flex items-center justify-between px-3 py-2.5 border-b border-border-subtle">
        <h3 class="text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-500">{{ status.name }}</h3>
        <span class="text-[10px] text-zinc-500 bg-elevated border border-border-subtle rounded px-1.5 py-0.5 tabular-nums">
            {{ status.task_count }}
        </span>
    </div>
    <!-- Tasks container - scrollable, sortable -->
    <div class="flex-1 overflow-y-auto p-2 space-y-2"
         id="column-{{ status.pk }}-tasks"
         x-sort:group="kanban"
         x-sort:config="{ animation: 150 }"
         x-sort="$ajax('/tasks/move/', { task_id: $item, status_id: {{ status.pk }} })"
         data-status-id="{{ status.pk }}">
        {% for task in status.tasks.all %}
        {% include "projects/partials/task_card.html" %}
        {% endfor %}
    </div>
</div>
```

Key changes:
- Add `x-sort:group="kanban"` to enable multi-list sorting
- Add `x-sort` handler that calls `/tasks/move/` with task_id and status_id
- Remove all manual drag event handlers

---

### Task 3: Update Task Card for Sort Plugin

**Files:**
- Modify: `templates/projects/partials/task_card.html`

**Replace entire file with:**

```html
<div class="group bg-card/90 rounded-card border border-border-subtle p-3 cursor-move transition-all duration-150 hover:bg-elevated/90 hover:border-border-strong"
     id="task-{{ task.pk }}"
     x-sort:item="{{ task.pk }}"
     hx-get="{% url 'task_detail' task.pk %}"
     hx-target="#slide-over"
     hx-swap="innerHTML"
     hx-trigger="click">
    <div class="text-sm font-medium text-zinc-100 mb-1.5">{{ task.title }}</div>
    <div class="flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
        {% if task.priority %}
        <span class="px-2 py-0.5 rounded-full text-[10px] border
            {% if task.priority == 'urgent' %}bg-red-500/15 text-red-300 border-red-500/30
            {% elif task.priority == 'high' %}bg-orange-500/15 text-orange-300 border-orange-500/30
            {% elif task.priority == 'medium' %}bg-yellow-500/15 text-yellow-300 border-yellow-500/30
            {% else %}bg-elevated text-zinc-400 border-border-subtle{% endif %}">
            {{ task.get_priority_display }}
        </span>
        {% endif %}
        {% if task.assignee %}
        <span class="flex items-center gap-1">
            <i data-lucide="user" class="w-3 h-3"></i>
            {{ task.assignee.name }}
        </span>
        {% endif %}
        {% if task.due_date %}
        <span class="flex items-center gap-1">
            <i data-lucide="calendar" class="w-3 h-3"></i>
            {{ task.due_date|date:"M d" }}
        </span>
        {% endif %}
    </div>
    {% if task.labels.exists %}
    <div class="flex flex-wrap gap-1 mt-2">
        {% for label in task.labels.all %}
        <span class="px-2 py-0.5 text-[10px] rounded-full border" style="background: {{ label.color }}20; color: {{ label.color }}; border-color: {{ label.color }}40;">
            {{ label.name }}
        </span>
        {% endfor %}
    </div>
    {% endif %}
</div>
```

Key changes:
- Replace `draggable="true"` and manual drag handlers with `x-sort:item="{{ task.pk }}"`

---

### Task 4: Add $ajax Helper and Update project_board.html

**Files:**
- Modify: `templates/projects/project_board.html`

**Add Alpine magic helper for AJAX calls. Update the file to include:**

After `<div ... id="kanban-board">` add x-data with $ajax helper:

```html
<div class="flex-1 overflow-x-auto overflow-y-hidden"
     x-data="{
         $ajax(url, data) {
             fetch(url, {
                 method: 'POST',
                 headers: {
                     'Content-Type': 'application/x-www-form-urlencoded',
                     'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '{{ csrf_token }}'
                 },
                 body: new URLSearchParams(data)
             });
         }
     }"
     id="kanban-board">
```

Also add a hidden CSRF input somewhere in the board:
```html
<input type="hidden" name="csrfmiddlewaretoken" value="{{ csrf_token }}">
```

---

### Task 5: Add Status Dropdown to Task Detail

**Files:**
- Create: `templates/tasks/partials/status_dropdown.html`
- Modify: `templates/tasks/task_detail.html`
- Modify: `apps/tasks/views.py`
- Modify: `apps/tasks/urls.py`

**Step 1: Create status dropdown partial**

```html
<div class="relative" id="status-dropdown-{{ task.pk }}" x-data="{ open: false }">
    <button x-on:click="open = !open"
            class="flex items-center gap-2 px-3 py-1.5 rounded-card bg-elevated border border-border-subtle text-sm text-zinc-300 hover:bg-hover-strong hover:border-border-strong transition-colors">
        <span>{{ task.status.name }}</span>
        <i data-lucide="chevron-down" class="w-3.5 h-3.5 text-zinc-500"></i>
    </button>
    <div x-show="open" x-on:click.away="open = false"
         class="absolute left-0 top-full mt-1 w-48 bg-elevated border border-border-subtle rounded-card shadow-lg z-10 py-1">
        {% for status in task.project.statuses.all %}
        <button hx-post="{% url 'task_update_status' task.pk %}"
                hx-vals='{"status_id": "{{ status.pk }}"}'
                hx-target="#status-dropdown-{{ task.pk }}"
                hx-swap="outerHTML"
                class="w-full text-left px-3 py-2 text-sm hover:bg-hover-strong transition-colors {% if status.pk == task.status.pk %}text-accent{% else %}text-zinc-300{% endif %}">
            {{ status.name }}
        </button>
        {% endfor %}
    </div>
</div>
```

**Step 2: Update task_detail.html lines 5-11**

Replace the static status badge with the dropdown include:
```html
            <div class="flex flex-wrap items-center gap-2 text-xs text-zinc-500 mt-2">
                {% include "tasks/partials/status_dropdown.html" %}
                <span class="text-zinc-600">&middot;</span>
                <span class="text-zinc-300">{{ task.project.name }}</span>
            </div>
```

**Step 3: Add task_update_status view**

```python
@login_required
@require_POST
def task_update_status(request, pk):
    task = get_object_or_404(Task, pk=pk)
    status_id = request.POST.get('status_id')
    status = get_object_or_404(Status, pk=status_id, project=task.project)
    task.status = status
    task.save()
    return render(request, 'tasks/partials/status_dropdown.html', {'task': task})
```

**Step 4: Add URL route**

```python
path('<int:pk>/status/', views.task_update_status, name='task_update_status'),
```

---

### Task 6: Test and Verify

1. Go to a project board with tasks
2. Drag a task from one column to another - verify it moves smoothly
3. Click a task to open the drawer - verify it's wider
4. Click the status dropdown - verify you can change status
5. Refresh the page - verify changes persisted

---

### Task 7: Commit

```bash
git add -A
git commit -m "fix: drag-drop with Alpine Sort plugin and status dropdown

- Add Alpine.js Sort plugin for smooth multi-list drag-drop
- Use x-sort:group for kanban column grouping
- Add status dropdown to task detail drawer
- Widen slide-over panel to max-w-xl"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add Alpine Sort plugin + widen panel | `templates/base.html` |
| 2 | Update kanban column for Sort | `kanban_column.html` |
| 3 | Update task card for Sort | `task_card.html` |
| 4 | Add $ajax helper to project board | `project_board.html` |
| 5 | Add status dropdown to task detail | `status_dropdown.html`, `task_detail.html`, `views.py`, `urls.py` |
| 6 | Test and verify | Manual testing |
| 7 | Commit | Git |

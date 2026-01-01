# Project Detail URL-Based Tabs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert Project Detail page tabs from Alpine.js client-side state to Django URL-based navigation, enabling browser refresh to preserve active tab.

**Architecture:** Add a new URL route for the Tasks tab. Modify the `project_detail` view to detect which URL was accessed using `request.resolver_match.url_name` and pass `active_tab` to the template. Update the template to replace Alpine.js directives with Django template conditionals and `<a href>` navigation links.

**Tech Stack:** Django 5.1, Django URL routing, Django templates

---

## Current State

**Project Detail page** (`/projects/<pk>/detail/`):
- Uses Alpine.js: `x-data="{ activeTab: 'overview' }"`
- Two active tabs: **Overview** (default), **Tasks**
- Sidebar navigation with `@click` handlers
- Refreshing resets to Overview tab

**Target State:**
- `/projects/<pk>/detail/` → Overview tab
- `/projects/<pk>/detail/tasks/` → Tasks tab
- Refreshing preserves active tab
- Browser back/forward works

---

## Task 1: Add Project Detail Tasks URL Route

**Files:**
- Modify: `apps/projects/urls.py:8`
- Modify: `apps/projects/views.py:69-105`

**Step 1: Add new URL pattern**

In `apps/projects/urls.py`, add a route for the tasks tab after the existing `project_detail` route:

```python
urlpatterns = [
    path('', views.project_list, name='project_list'),
    path('create/', views.project_create, name='project_create'),
    path('<int:pk>/detail/', views.project_detail, name='project_detail'),
    path('<int:pk>/detail/tasks/', views.project_detail, name='project_detail_tasks'),  # Add this
    path('<int:pk>/', views.project_board, name='project_board'),
    # ... rest of patterns
]
```

**Step 2: Modify view to detect active tab**

In `apps/projects/views.py`, update the `project_detail` view to detect active tab using `request.resolver_match.url_name`:

```python
@login_required
def project_detail(request, pk):
    """Project detail page with overview and tasks tabs."""
    project = get_object_or_404(Project, pk=pk)
    if not can_access_project(request.user, project, 'viewer'):
        return HttpResponseForbidden("You don't have access to this project")

    # Determine active tab from URL
    active_tab = 'tasks' if request.resolver_match.url_name == 'project_detail_tasks' else 'overview'

    # Calculate stats
    tasks = Task.objects.filter(project=project).select_related('status', 'assignee')
    total_tasks = tasks.count()

    # Get "Done" status for completed count
    done_status = project.statuses.filter(name__iexact='done').first()
    completed_tasks = tasks.filter(status=done_status).count() if done_status else 0

    # In Progress status
    in_progress_status = project.statuses.filter(name__iexact='in progress').first()
    in_progress_tasks = tasks.filter(status=in_progress_status).count() if in_progress_status else 0

    # Overdue tasks
    today = timezone.now().date()
    overdue_tasks = tasks.filter(due_date__lt=today).exclude(status=done_status).count() if done_status else tasks.filter(due_date__lt=today).count()

    # Recent activity (last 5 across all project tasks)
    recent_activities = TaskActivity.objects.filter(
        task__project=project
    ).select_related('user', 'task').order_by('-created_at')[:5]

    return render(request, 'projects/project_detail.html', {
        'project': project,
        'tasks': tasks,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'in_progress_tasks': in_progress_tasks,
        'overdue_tasks': overdue_tasks,
        'recent_activities': recent_activities,
        'now_date': today,
        'active_tab': active_tab,  # Add this
    })
```

**Step 3: Commit**

```bash
git add apps/projects/urls.py apps/projects/views.py
git commit -m "feat: add project_detail_tasks URL route with active_tab context"
```

---

## Task 2: Update Project Detail Template to Use URL-Based Tabs

**Files:**
- Modify: `templates/projects/project_detail.html`

**Step 1: Replace Alpine.js tabs with URL links and Django conditionals**

Key changes:
1. Remove `x-data="{ activeTab: 'overview' }"` from container
2. Replace `x-show="activeTab === '...'"` with `{% if active_tab == '...' %}`
3. Replace sidebar `@click` handlers with `<a href="{% url '...' %}">` links
4. Replace `:class` bindings with Django template conditionals
5. Remove `x-cloak` attributes

```html
{% extends "base.html" %}

{% block title %}{{ project.name }} - WebFTL CRM{% endblock %}

{% block full_content %}
<div class="flex flex-col h-full">
    <!-- Compact header -->
    <div class="flex-shrink-0 px-4 py-2 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <a href="{% url 'project_list' %}" class="p-1 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors" title="Back to Projects">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i>
                </a>
                <i data-lucide="folder-kanban" class="w-4 h-4 text-zinc-500"></i>
                <h1 class="text-sm font-medium text-zinc-100" id="project-name">{{ project.name }}</h1>
                <span class="text-xs text-zinc-500">{{ project.client.name }}</span>
            </div>
            <div class="flex items-center gap-2">
                <a href="{% url 'project_board' project.pk %}"
                   class="inline-flex items-center gap-1.5 bg-accent text-white px-3 py-1.5 rounded-card text-xs font-medium hover:bg-accent-hover transition-colors">
                    <i data-lucide="kanban" class="w-3.5 h-3.5"></i>
                    Open Board
                </a>
                <a href="{% url 'project_edit' project.pk %}"
                   class="inline-flex items-center gap-1.5 bg-elevated border border-border-subtle px-3 py-1.5 rounded-card text-xs text-zinc-300 hover:bg-hover transition-colors">
                    <i data-lucide="pencil" class="w-3.5 h-3.5"></i>
                    Edit
                </a>
                <a href="{% url 'project_settings' project.pk %}"
                   class="inline-flex items-center gap-1.5 bg-elevated border border-border-subtle px-3 py-1.5 rounded-card text-xs text-zinc-400 hover:text-zinc-200 hover:bg-hover-strong transition-colors">
                    <i data-lucide="settings" class="w-3.5 h-3.5"></i>
                    Settings
                </a>
                {% if request.user.is_admin %}
                <button hx-post="{% url 'project_delete' project.pk %}"
                        hx-confirm="Delete {{ project.name|escapejs }}? This will also delete all tasks."
                        hx-target="body"
                        class="inline-flex items-center gap-1.5 bg-red-500/10 border border-red-500/20 text-red-300 px-3 py-1.5 rounded-card text-xs hover:bg-red-500/20 transition-colors">
                    <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                    Delete
                </button>
                {% endif %}
            </div>
        </div>
    </div>

    <!-- Main content with right sidebar -->
    <div class="flex-1 flex overflow-hidden">
        <!-- Main content area -->
        <div class="flex-1 overflow-y-auto p-6 pb-12">
            {% if active_tab == 'overview' %}
            <!-- Overview Section -->
            <div class="space-y-6 pb-6" id="overview-content">
                {% include "projects/partials/overview_content.html" %}
            </div>
            {% elif active_tab == 'tasks' %}
            <!-- Tasks Section -->
            <div class="pb-6" id="tasks-content">
                {% include "projects/partials/tasks_content.html" %}
            </div>
            {% endif %}
        </div>

        <!-- Right sidebar navigation -->
        <div class="w-56 flex-shrink-0 border-l border-border-subtle bg-panel/50 overflow-hidden">
            <div class="p-3">
                <div class="text-[10px] uppercase tracking-wider text-zinc-600 px-2 mb-2">Navigation</div>
                <nav class="space-y-1">
                    <a href="{% url 'project_detail' project.pk %}"
                       class="w-full flex items-center gap-3 px-3 py-2 rounded-card text-sm transition-colors text-left {% if active_tab == 'overview' %}bg-elevated text-zinc-100{% else %}text-zinc-400 hover:text-zinc-200 hover:bg-elevated/50{% endif %}">
                        <i data-lucide="layout-dashboard" class="w-4 h-4"></i>
                        Overview
                    </a>
                    <a href="{% url 'project_detail_tasks' project.pk %}"
                       class="w-full flex items-center justify-between px-3 py-2 rounded-card text-sm transition-colors text-left {% if active_tab == 'tasks' %}bg-elevated text-zinc-100{% else %}text-zinc-400 hover:text-zinc-200 hover:bg-elevated/50{% endif %}">
                        <span class="flex items-center gap-3">
                            <i data-lucide="check-square" class="w-4 h-4"></i>
                            Tasks
                        </span>
                        <span class="text-xs text-zinc-500 bg-panel px-1.5 py-0.5 rounded">{{ total_tasks }}</span>
                    </a>
                </nav>

                <!-- Coming Soon placeholders -->
                <div class="text-[10px] uppercase tracking-wider text-zinc-600 px-2 mb-2 mt-6">Coming Soon</div>
                <nav class="space-y-1">
                    <div class="w-full flex items-center gap-3 px-3 py-2 rounded-card text-sm text-zinc-600 cursor-not-allowed">
                        <i data-lucide="users" class="w-4 h-4"></i>
                        Team
                    </div>
                    <div class="w-full flex items-center gap-3 px-3 py-2 rounded-card text-sm text-zinc-600 cursor-not-allowed">
                        <i data-lucide="file-text" class="w-4 h-4"></i>
                        Documents
                    </div>
                    <div class="w-full flex items-center gap-3 px-3 py-2 rounded-card text-sm text-zinc-600 cursor-not-allowed">
                        <i data-lucide="clock" class="w-4 h-4"></i>
                        Time Tracking
                    </div>
                </nav>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

**Step 2: Verify manually**

Run: `python manage.py runserver`
- Visit `/projects/1/detail/` - Overview tab should be highlighted
- Visit `/projects/1/detail/tasks/` - Tasks tab should be highlighted
- Click sidebar tabs - should navigate via URL
- Refresh page - should stay on current tab
- Browser back button - should work

**Step 3: Commit**

```bash
git add templates/projects/project_detail.html
git commit -m "feat: convert Project Detail tabs from Alpine.js to URL-based navigation"
```

---

## Task 3: Write Tests for Project Detail Tab Navigation

**Files:**
- Modify: `apps/projects/tests/test_views.py`

**Step 1: Add Project Detail tab URL tests**

Add a new test class to verify the URL-based tab navigation:

```python
@pytest.mark.django_db
class TestProjectDetailTabs:
    def test_project_detail_default_tab_is_overview(self, client):
        """GET /projects/<pk>/detail/ should set active_tab to 'overview'"""
        from apps.accounts.factories import UserFactory
        from apps.projects.factories import ProjectFactory

        user = UserFactory(is_admin=True)
        project = ProjectFactory()
        client.force_login(user)

        response = client.get(reverse('project_detail', args=[project.pk]))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'overview'

    def test_project_detail_tasks_tab(self, client):
        """GET /projects/<pk>/detail/tasks/ should set active_tab to 'tasks'"""
        from apps.accounts.factories import UserFactory
        from apps.projects.factories import ProjectFactory

        user = UserFactory(is_admin=True)
        project = ProjectFactory()
        client.force_login(user)

        response = client.get(reverse('project_detail_tasks', args=[project.pk]))
        assert response.status_code == 200
        assert response.context['active_tab'] == 'tasks'
```

**Step 2: Run tests**

Run: `./.venv/bin/pytest apps/projects/tests/test_views.py::TestProjectDetailTabs -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add apps/projects/tests/test_views.py
git commit -m "test: add Project Detail URL-based tab navigation tests"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add project_detail_tasks URL route | `urls.py`, `views.py` |
| 2 | Update Project Detail template | `project_detail.html` |
| 3 | Write tests | `test_views.py` |

**Total: 3 tasks, 3 commits**

**Result:**
- `/projects/<pk>/detail/` → Overview tab (default)
- `/projects/<pk>/detail/tasks/` → Tasks tab
- Browser refresh preserves tab
- Back/forward navigation works
- No Alpine.js for tab state

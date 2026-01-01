# Project Detail Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a project detail page with Overview and Tasks tabs, making the Kanban board accessible via button.

**Architecture:** New `project_detail` view at `/projects/{id}/` shows project metadata, stats, and task list. Kanban board moves to `/projects/{id}/board/`. Uses Alpine.js for tab switching, reuses patterns from `client_detail.html`.

**Tech Stack:** Django 5.1, HTMX, Alpine.js, Tailwind CSS

---

## Task 1: Add project_detail View with Test

**Files:**
- Modify: `apps/projects/tests/test_views.py`
- Modify: `apps/projects/views.py`
- Modify: `apps/projects/urls.py`

**Step 1: Write the failing test**

Add to `apps/projects/tests/test_views.py`:

```python
@pytest.mark.django_db
class TestProjectDetail:
    def test_project_detail_requires_login(self, client):
        project = ProjectFactory()
        response = client.get(reverse('project_detail', args=[project.pk]))
        assert response.status_code == 302

    def test_project_detail_shows_project_info(self, client):
        user = UserFactory()
        project = ProjectFactory(name='Test Project', description='Test description')
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.get(reverse('project_detail', args=[project.pk]))
        assert response.status_code == 200
        assert 'Test Project' in response.content.decode()

    def test_project_detail_denied_without_membership(self, client):
        user = UserFactory()
        project = ProjectFactory()
        client.force_login(user)
        response = client.get(reverse('project_detail', args=[project.pk]))
        assert response.status_code == 403

    def test_project_detail_shows_task_count(self, client):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        from apps.tasks.factories import TaskFactory
        status = project.statuses.first()
        TaskFactory(project=project, status=status)
        TaskFactory(project=project, status=status)
        client.force_login(user)
        response = client.get(reverse('project_detail', args=[project.pk]))
        assert response.status_code == 200
        content = response.content.decode()
        # Should show task count in stats
        assert '2' in content
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest apps/projects/tests/test_views.py::TestProjectDetail -v`
Expected: FAIL with "NoReverseMatch: 'project_detail' is not a registered namespace"

**Step 3: Add URL route and view**

Add to `apps/projects/urls.py` (after `path('create/', ...)`):

```python
path('<int:pk>/detail/', views.project_detail, name='project_detail'),
```

Add to `apps/projects/views.py`:

```python
@login_required
def project_detail(request, pk):
    """Project detail page with overview and tasks tabs."""
    project = get_object_or_404(Project, pk=pk)
    if not can_access_project(request.user, project, 'viewer'):
        return HttpResponseForbidden("You don't have access to this project")

    # Calculate stats
    from apps.tasks.models import Task, TaskActivity
    from django.db.models import Count, Q
    from django.utils import timezone

    tasks = Task.objects.filter(project=project)
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
    })
```

**Step 4: Create minimal template**

Create `templates/projects/project_detail.html`:

```html
{% extends "base.html" %}

{% block title %}{{ project.name }} - WebFTL CRM{% endblock %}

{% block full_content %}
<div class="flex flex-col h-full" x-data="{ activeTab: 'overview' }">
    <!-- Header -->
    <div class="flex-shrink-0 px-4 py-2 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <a href="{% url 'project_list' %}" class="p-1 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors" title="Back to Projects">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i>
                </a>
                <i data-lucide="folder" class="w-4 h-4 text-zinc-500"></i>
                <h1 class="text-sm font-medium text-zinc-100">{{ project.name }}</h1>
                <a href="{% url 'client_detail' project.client.pk %}" class="text-xs text-zinc-500 hover:text-zinc-300">{{ project.client.name }}</a>
            </div>
            <div class="flex items-center gap-2">
                <a href="{% url 'project_board' project.pk %}"
                   class="inline-flex items-center gap-1.5 bg-accent text-white px-3 py-1.5 rounded-card text-xs font-medium hover:bg-accent-hover transition-colors">
                    <i data-lucide="kanban" class="w-3.5 h-3.5"></i>
                    Open Board
                </a>
                <a href="{% url 'project_settings' project.pk %}"
                   class="inline-flex items-center gap-1.5 bg-elevated border border-border-subtle px-3 py-1.5 rounded-card text-xs text-zinc-300 hover:bg-hover transition-colors">
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
        <div class="flex-1 overflow-y-auto p-6">
            <!-- Overview Section -->
            <div x-show="activeTab === 'overview'" x-cloak>
                {% include "projects/partials/overview_content.html" %}
            </div>

            <!-- Tasks Section -->
            <div x-show="activeTab === 'tasks'" x-cloak>
                {% include "projects/partials/tasks_content.html" %}
            </div>
        </div>

        <!-- Right sidebar navigation -->
        <div class="w-56 flex-shrink-0 border-l border-border-subtle bg-panel/50 overflow-y-auto">
            <div class="p-3">
                <div class="text-[10px] uppercase tracking-wider text-zinc-600 px-2 mb-2">Navigation</div>
                <nav class="space-y-1">
                    <button @click="activeTab = 'overview'"
                            :class="activeTab === 'overview' ? 'bg-elevated text-zinc-100' : 'text-zinc-400 hover:text-zinc-200 hover:bg-elevated/50'"
                            class="w-full flex items-center gap-3 px-3 py-2 rounded-card text-sm transition-colors text-left">
                        <i data-lucide="folder" class="w-4 h-4"></i>
                        Overview
                    </button>
                    <button @click="activeTab = 'tasks'"
                            :class="activeTab === 'tasks' ? 'bg-elevated text-zinc-100' : 'text-zinc-400 hover:text-zinc-200 hover:bg-elevated/50'"
                            class="w-full flex items-center justify-between px-3 py-2 rounded-card text-sm transition-colors text-left">
                        <span class="flex items-center gap-3">
                            <i data-lucide="list" class="w-4 h-4"></i>
                            Tasks
                        </span>
                        <span class="text-xs text-zinc-500 bg-panel px-1.5 py-0.5 rounded">{{ total_tasks }}</span>
                    </button>
                </nav>

                <!-- Coming Soon section -->
                <div class="text-[10px] uppercase tracking-wider text-zinc-600 px-2 mt-4 mb-2">Coming Soon</div>
                <nav class="space-y-1">
                    <div class="flex items-center gap-3 px-3 py-2 text-zinc-600 text-sm cursor-not-allowed">
                        <i data-lucide="message-circle" class="w-4 h-4"></i>
                        Discussions
                    </div>
                    <div class="flex items-center gap-3 px-3 py-2 text-zinc-600 text-sm cursor-not-allowed">
                        <i data-lucide="ticket" class="w-4 h-4"></i>
                        Tickets
                    </div>
                    <div class="flex items-center gap-3 px-3 py-2 text-zinc-600 text-sm cursor-not-allowed">
                        <i data-lucide="file-text" class="w-4 h-4"></i>
                        Notes
                    </div>
                    <div class="flex items-center gap-3 px-3 py-2 text-zinc-600 text-sm cursor-not-allowed">
                        <i data-lucide="activity" class="w-4 h-4"></i>
                        Activity
                    </div>
                </nav>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

**Step 5: Create overview partial**

Create `templates/projects/partials/overview_content.html`:

```html
<div class="space-y-6">
    <!-- Project Info -->
    <div class="border border-border-subtle rounded-card overflow-hidden">
        <div class="px-4 py-2 border-b border-border-subtle bg-panel/80">
            <div class="flex items-center gap-3">
                <i data-lucide="info" class="w-4 h-4 text-zinc-500"></i>
                <h2 class="text-sm font-medium text-zinc-100">Project Information</h2>
            </div>
        </div>
        <div class="p-4">
            <dl class="space-y-4 text-sm">
                <div>
                    <dt class="text-xs uppercase tracking-wide text-zinc-500 mb-1">Description</dt>
                    <dd class="text-zinc-300">
                        {% if project.description %}
                        {{ project.description|linebreaks }}
                        {% else %}
                        <span class="text-zinc-600 italic">No description</span>
                        {% endif %}
                    </dd>
                </div>
                {% if project.github_repo_url %}
                <div>
                    <dt class="text-xs uppercase tracking-wide text-zinc-500 mb-1">GitHub Repository</dt>
                    <dd>
                        <a href="{{ project.github_repo_url }}" target="_blank" rel="noopener"
                           class="inline-flex items-center gap-1.5 text-accent hover:text-accent-hover transition-colors">
                            <i data-lucide="github" class="w-4 h-4"></i>
                            {{ project.github_repo_url }}
                            <i data-lucide="external-link" class="w-3 h-3"></i>
                        </a>
                    </dd>
                </div>
                {% endif %}
                <div>
                    <dt class="text-xs uppercase tracking-wide text-zinc-500 mb-1">Created</dt>
                    <dd class="text-zinc-300">{{ project.created_at|date:"F j, Y" }}</dd>
                </div>
            </dl>
        </div>
    </div>

    <!-- Stats Cards -->
    <div class="grid grid-cols-4 gap-4">
        <div class="border border-border-subtle rounded-card p-4 bg-panel/50">
            <div class="text-2xl font-semibold text-zinc-100">{{ total_tasks }}</div>
            <div class="text-xs text-zinc-500 uppercase tracking-wide mt-1">Total Tasks</div>
        </div>
        <div class="border border-border-subtle rounded-card p-4 bg-panel/50">
            <div class="text-2xl font-semibold text-green-400">{{ completed_tasks }}</div>
            <div class="text-xs text-zinc-500 uppercase tracking-wide mt-1">Completed</div>
        </div>
        <div class="border border-border-subtle rounded-card p-4 bg-panel/50">
            <div class="text-2xl font-semibold text-blue-400">{{ in_progress_tasks }}</div>
            <div class="text-xs text-zinc-500 uppercase tracking-wide mt-1">In Progress</div>
        </div>
        <div class="border border-border-subtle rounded-card p-4 bg-panel/50 {% if overdue_tasks > 0 %}border-amber-500/30{% endif %}">
            <div class="text-2xl font-semibold {% if overdue_tasks > 0 %}text-amber-400{% else %}text-zinc-100{% endif %}">{{ overdue_tasks }}</div>
            <div class="text-xs text-zinc-500 uppercase tracking-wide mt-1">Overdue</div>
        </div>
    </div>

    <!-- Recent Activity Preview -->
    <div class="border border-border-subtle rounded-card overflow-hidden">
        <div class="px-4 py-2 border-b border-border-subtle bg-panel/80">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-3">
                    <i data-lucide="activity" class="w-4 h-4 text-zinc-500"></i>
                    <h2 class="text-sm font-medium text-zinc-100">Recent Activity</h2>
                </div>
                <span class="text-xs text-zinc-600 cursor-not-allowed">View all</span>
            </div>
        </div>
        <div class="p-4">
            {% if recent_activities %}
            <div class="space-y-3">
                {% for activity in recent_activities %}
                <div class="flex items-start gap-3 text-sm">
                    <div class="flex-shrink-0 w-6 h-6 rounded-full bg-panel border border-border-subtle flex items-center justify-center">
                        {% if activity.activity_type == 'comment' %}
                        <i data-lucide="message-square" class="w-3 h-3 text-zinc-500"></i>
                        {% elif activity.activity_type == 'created' %}
                        <i data-lucide="circle-dot" class="w-3 h-3 text-zinc-500"></i>
                        {% elif activity.activity_type == 'status_change' %}
                        <i data-lucide="circle" class="w-3 h-3 text-zinc-500"></i>
                        {% else %}
                        <i data-lucide="edit-3" class="w-3 h-3 text-zinc-500"></i>
                        {% endif %}
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-1.5 flex-wrap">
                            <span class="font-medium text-zinc-200">{{ activity.user.name|default:"System" }}</span>
                            <span class="text-zinc-400">{{ activity.content }}</span>
                            <span class="text-zinc-600">on</span>
                            <span class="text-zinc-300">{{ activity.task.title|truncatechars:30 }}</span>
                        </div>
                        <div class="text-xs text-zinc-500 mt-0.5">{{ activity.created_at|timesince }} ago</div>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <p class="text-sm text-zinc-500">No activity yet.</p>
            {% endif %}
        </div>
    </div>
</div>
```

**Step 6: Create tasks partial**

Create `templates/projects/partials/tasks_content.html`:

```html
<div>
    <!-- Header Row -->
    <div class="flex items-center justify-between mb-4">
        <h2 class="text-sm font-medium text-zinc-100">Tasks</h2>
        <div class="flex items-center gap-2">
            <button hx-get="{% url 'task_create' project.pk %}"
                    hx-target="#slide-over"
                    hx-swap="innerHTML"
                    hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                    class="inline-flex items-center gap-1.5 bg-elevated border border-border-subtle px-3 py-1.5 rounded-card text-xs text-zinc-300 hover:bg-hover transition-colors">
                <i data-lucide="plus" class="w-3.5 h-3.5"></i>
                New Task
            </button>
            <a href="{% url 'project_board' project.pk %}"
               class="inline-flex items-center gap-1.5 bg-accent text-white px-3 py-1.5 rounded-card text-xs font-medium hover:bg-accent-hover transition-colors">
                <i data-lucide="kanban" class="w-3.5 h-3.5"></i>
                Open Kanban Board
                <i data-lucide="arrow-right" class="w-3 h-3"></i>
            </a>
        </div>
    </div>

    {% if tasks %}
    <!-- Task Table -->
    <div class="border border-border-subtle rounded-card overflow-hidden">
        <table class="w-full">
            <thead class="bg-panel border-b border-border-subtle">
                <tr class="text-left text-xs text-zinc-500 uppercase tracking-wider">
                    <th class="px-4 py-3 font-medium">Title</th>
                    <th class="px-4 py-3 font-medium">Status</th>
                    <th class="px-4 py-3 font-medium">Priority</th>
                    <th class="px-4 py-3 font-medium">Assignee</th>
                    <th class="px-4 py-3 font-medium">Due Date</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-border-subtle">
                {% for task in tasks %}
                <tr class="hover:bg-elevated/50 transition-colors cursor-pointer"
                    hx-get="{% url 'task_detail' task.pk %}"
                    hx-target="#slide-over"
                    hx-swap="innerHTML"
                    hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();">
                    <td class="px-4 py-3">
                        <span class="text-sm text-zinc-100">{{ task.title }}</span>
                    </td>
                    <td class="px-4 py-3">
                        <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-zinc-700 text-zinc-300">
                            {{ task.status.name }}
                        </span>
                    </td>
                    <td class="px-4 py-3">
                        {% if task.priority %}
                        <span class="inline-flex items-center gap-1 text-xs
                            {% if task.priority == 'urgent' %}text-red-400
                            {% elif task.priority == 'high' %}text-orange-400
                            {% elif task.priority == 'medium' %}text-yellow-400
                            {% else %}text-zinc-500{% endif %}">
                            <i data-lucide="signal" class="w-3 h-3"></i>
                            {{ task.get_priority_display }}
                        </span>
                        {% else %}
                        <span class="text-zinc-600">—</span>
                        {% endif %}
                    </td>
                    <td class="px-4 py-3">
                        {% if task.assignee %}
                        <div class="flex items-center gap-2">
                            <span class="w-5 h-5 rounded-full bg-accent/30 flex items-center justify-center text-[10px] text-accent font-medium">
                                {{ task.assignee.name|slice:":1"|upper }}
                            </span>
                            <span class="text-sm text-zinc-400">{{ task.assignee.name }}</span>
                        </div>
                        {% else %}
                        <span class="text-zinc-600">—</span>
                        {% endif %}
                    </td>
                    <td class="px-4 py-3">
                        {% if task.due_date %}
                        <span class="text-sm text-zinc-400">{{ task.due_date|date:"M j, Y" }}</span>
                        {% else %}
                        <span class="text-zinc-600">—</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <!-- Empty State -->
    <div class="border border-border-subtle rounded-card p-8 text-center">
        <i data-lucide="list-checks" class="w-12 h-12 mx-auto mb-4 text-zinc-600"></i>
        <p class="text-zinc-400 mb-4">No tasks yet</p>
        <p class="text-sm text-zinc-500 mb-4">Create your first task or open the Kanban board</p>
        <div class="flex items-center justify-center gap-3">
            <button hx-get="{% url 'task_create' project.pk %}"
                    hx-target="#slide-over"
                    hx-swap="innerHTML"
                    hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                    class="inline-flex items-center gap-1.5 bg-elevated border border-border-subtle px-3 py-1.5 rounded-card text-xs text-zinc-300 hover:bg-hover transition-colors">
                <i data-lucide="plus" class="w-3.5 h-3.5"></i>
                New Task
            </button>
            <a href="{% url 'project_board' project.pk %}"
               class="inline-flex items-center gap-1.5 bg-accent text-white px-3 py-1.5 rounded-card text-xs font-medium hover:bg-accent-hover transition-colors">
                <i data-lucide="kanban" class="w-3.5 h-3.5"></i>
                Open Kanban Board
            </a>
        </div>
    </div>
    {% endif %}
</div>
```

**Step 7: Run test to verify it passes**

Run: `.venv/bin/pytest apps/projects/tests/test_views.py::TestProjectDetail -v`
Expected: 4 tests PASS

**Step 8: Commit**

```bash
git add apps/projects/tests/test_views.py apps/projects/views.py apps/projects/urls.py templates/projects/project_detail.html templates/projects/partials/overview_content.html templates/projects/partials/tasks_content.html
git commit -m "feat: add project detail page with overview and tasks tabs"
```

---

## Task 2: Update Navigation Links

**Files:**
- Modify: `templates/projects/partials/project_row.html`
- Modify: `templates/projects/project_board.html`

**Step 1: Update project_row.html to link to detail page**

Change line 3 in `templates/projects/partials/project_row.html`:

```html
<a href="{% url 'project_detail' project.pk %}" class="font-medium text-sm text-zinc-100 hover:text-accent transition-colors">
```

Keep the kanban icon link on line 28 as a direct board link (it already points to `project_board`).

**Step 2: Update project_board.html back arrow to point to detail page**

Change line 11 in `templates/projects/project_board.html`:

```html
<a href="{% url 'project_detail' project.pk %}" class="text-zinc-500 hover:text-zinc-300 transition-colors">
```

**Step 3: Verify manually**

1. Visit `/projects/`
2. Click a project name → should go to detail page
3. Click "Open Board" → should go to Kanban
4. In Kanban, click back arrow → should go back to detail page

**Step 4: Commit**

```bash
git add templates/projects/partials/project_row.html templates/projects/project_board.html
git commit -m "feat: update navigation to use project detail page as default"
```

---

## Task 3: Run Full Test Suite

**Step 1: Run all project tests**

Run: `.venv/bin/pytest apps/projects/tests/ -v`
Expected: All tests PASS

**Step 2: Run full test suite**

Run: `.venv/bin/pytest -v`
Expected: All tests PASS (98 passed, 2 xfailed)

---

## Summary

After completing these tasks:
- `/projects/` list links to project detail page
- `/projects/{id}/detail/` shows project overview and tasks
- `/projects/{id}/` (board) accessible via "Open Board" button
- Back arrow in Kanban returns to detail page
- Overview tab shows: description, GitHub link, created date, stats cards, recent activity
- Tasks tab shows: task list table with status/priority/assignee/due date, "New Task" and "Open Kanban Board" buttons
- Sidebar has placeholder tabs for future features (Discussions, Tickets, Notes, Activity)

# URL-Based Tab Persistence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make tab navigation URL-based so browser refresh preserves the active tab, enabling bookmarking and proper browser history.

**Architecture:** Convert Alpine.js client-side tabs to separate Django URL routes. Each tab gets its own URL path (e.g., `/tasks/my/todos/` instead of just `/tasks/my/`). Templates will be refactored to use `<a href>` links instead of `@click` handlers, with an `active_tab` context variable to highlight the current tab.

**Tech Stack:** Django 5.1, Django URL routing, Jinja2 templates

---

## Scope

**Pages affected:**
1. **My Tasks** (`/tasks/my/`) - Add `/tasks/my/todos/` route
2. **Client Detail** (`/clients/<id>/`) - Add `/clients/<id>/projects/` and `/clients/<id>/todos/` routes

**Current behavior:** Tabs use Alpine.js `x-data="{ activeTab: 'tasks' }"` - URL never changes, refresh resets to default.

**Target behavior:** Each tab has a distinct URL. Refresh stays on current tab. Browser back/forward works.

---

## Task 1: Add My Tasks Todos URL Route

**Files:**
- Modify: `apps/tasks/urls.py:6`
- Modify: `apps/tasks/views.py:27-58`

**Step 1: Add new URL pattern**

In `apps/tasks/urls.py`, add a new route for the todos tab:

```python
urlpatterns = [
    path('my/', views.my_tasks, name='my_tasks'),
    path('my/todos/', views.my_tasks, name='my_tasks_todos'),  # Add this line
    # ... rest of patterns
]
```

**Step 2: Modify view to detect active tab**

In `apps/tasks/views.py`, update the `my_tasks` view to pass `active_tab` to context:

```python
@login_required
def my_tasks(request):
    # Determine active tab from URL
    active_tab = 'todos' if request.path.endswith('/todos/') else 'tasks'

    tasks_qs = Task.objects.filter(assignee=request.user).select_related('project', 'status').order_by('-created_at')
    priority = request.GET.get('priority')
    if priority:
        tasks_qs = tasks_qs.filter(priority=priority)
    status_filter = request.GET.get('status')
    if status_filter:
        tasks_qs = tasks_qs.filter(status__name=status_filter)

    paginator = Paginator(tasks_qs, TASKS_PER_PAGE)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get user's todos
    from apps.todos.models import Todo
    show_completed_todos = request.GET.get('show_completed', '').lower() == 'true'
    todos_qs = Todo.objects.filter(owner=request.user).select_related('client')
    todo_count = todos_qs.filter(is_completed=False).count()
    if not show_completed_todos:
        todos_qs = todos_qs.filter(is_completed=False)

    return render(request, 'tasks/my_tasks.html', {
        'tasks': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
        'priority_filter': priority,
        'status_filter': status_filter,
        'todos': todos_qs,
        'show_completed': show_completed_todos,
        'todo_count': todo_count,
        'today': timezone.now().date(),
        'active_tab': active_tab,  # Add this
    })
```

**Step 3: Verify manually**

Run: `python manage.py runserver`
- Visit `/tasks/my/` - should work
- Visit `/tasks/my/todos/` - should work (same page for now)

**Step 4: Commit**

```bash
git add apps/tasks/urls.py apps/tasks/views.py
git commit -m "feat: add my_tasks_todos URL route with active_tab context"
```

---

## Task 2: Update My Tasks Template to Use URL-Based Tabs

**Files:**
- Modify: `templates/tasks/my_tasks.html`

**Step 1: Replace Alpine.js tabs with URL links**

Replace the entire template content. Key changes:
- Remove `x-data="{ activeTab: 'tasks' }"` from container
- Replace `@click="activeTab = 'tasks'"` with `href="{% url 'my_tasks' %}"`
- Replace `@click="activeTab = 'todos'"` with `href="{% url 'my_tasks_todos' %}"`
- Replace `x-show="activeTab === 'tasks'"` with `{% if active_tab == 'tasks' %}`
- Replace `:class` bindings with Django template conditionals

```html
{% extends "base.html" %}

{% block title %}My Tasks - WebFTL CRM{% endblock %}

{% block full_content %}
<div class="flex flex-col h-full">
    <!-- Compact header -->
    <div class="flex-shrink-0 px-4 py-2 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <i data-lucide="check-square" class="w-4 h-4 text-zinc-500"></i>
                <h1 class="text-sm font-medium text-zinc-100">My Tasks</h1>
            </div>
        </div>

        <!-- Tabs -->
        <div class="flex items-center gap-6 mt-3">
            <a href="{% url 'my_tasks' %}"
               class="pb-2 px-1 text-sm font-medium transition-colors {% if active_tab == 'tasks' %}text-zinc-100 border-b-2 border-accent{% else %}text-zinc-400 hover:text-zinc-200{% endif %}">
                Assigned Tasks
                <span class="ml-2 text-xs text-zinc-500 bg-elevated px-1.5 py-0.5 rounded">{{ total_count }}</span>
            </a>
            <a href="{% url 'my_tasks_todos' %}"
               class="pb-2 px-1 text-sm font-medium transition-colors {% if active_tab == 'todos' %}text-zinc-100 border-b-2 border-accent{% else %}text-zinc-400 hover:text-zinc-200{% endif %}">
                To-Dos
                <span class="ml-2 text-xs text-zinc-500 bg-elevated px-1.5 py-0.5 rounded">{{ todo_count }}</span>
            </a>
        </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-hidden">
        {% if active_tab == 'tasks' %}
        <!-- Assigned Tasks Tab -->
        <div class="h-full flex flex-col">
            <!-- Filters -->
            <div class="flex-shrink-0 px-4 py-2 border-b border-border-subtle bg-panel/40">
                <div class="flex items-center gap-4">
                    <select onchange="window.location.href='?priority=' + this.value"
                            class="bg-elevated border border-border-subtle rounded px-2 py-1 text-xs text-zinc-400 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none">
                        <option value="">All Priorities</option>
                        <option value="urgent" {% if priority_filter == "urgent" %}selected{% endif %}>Urgent</option>
                        <option value="high" {% if priority_filter == "high" %}selected{% endif %}>High</option>
                        <option value="medium" {% if priority_filter == "medium" %}selected{% endif %}>Medium</option>
                        <option value="low" {% if priority_filter == "low" %}selected{% endif %}>Low</option>
                    </select>
                </div>
            </div>

            <!-- Table content -->
            <div class="flex-1 overflow-auto">
                {% if tasks %}
                <table class="w-full">
                    <thead class="sticky top-0 bg-panel border-b border-border-subtle">
                        <tr class="text-left text-xs text-zinc-500 uppercase tracking-wider">
                            <th class="px-4 py-3 font-medium">Task</th>
                            <th class="px-4 py-3 font-medium">Project</th>
                            <th class="px-4 py-3 font-medium">Status</th>
                            <th class="px-4 py-3 font-medium">Priority</th>
                            <th class="px-4 py-3 font-medium">Due</th>
                            <th class="px-4 py-3 font-medium w-10">Actions</th>
                        </tr>
                    </thead>
                    <tbody id="my-tasks-list" class="divide-y divide-border-subtle">
                        {% for task in tasks %}
                        {% include "tasks/partials/my_task_row.html" %}
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <div class="flex flex-col items-center justify-center py-16 text-zinc-500">
                    <i data-lucide="check-square" class="w-12 h-12 mb-4 opacity-30"></i>
                    <p class="mb-2">No tasks assigned to you yet</p>
                </div>
                {% endif %}
            </div>

            <!-- Pagination -->
            <div class="flex-shrink-0">
                {% include "components/pagination.html" %}
            </div>
        </div>
        {% else %}
        <!-- To-Dos Tab -->
        <div class="h-full">
            {% include 'todos/partials/todos_section.html' %}
        </div>
        {% endif %}
    </div>
</div>

<script>
    // Initialize today's date for comparison
    window.today = new Date().toISOString().split('T')[0];
</script>
{% endblock %}
```

**Step 2: Verify manually**

Run: `python manage.py runserver`
- Visit `/tasks/my/` - should show Assigned Tasks tab highlighted
- Visit `/tasks/my/todos/` - should show To-Dos tab highlighted
- Click tabs - should navigate via URL (page refresh is expected)
- Refresh page - should stay on current tab

**Step 3: Commit**

```bash
git add templates/tasks/my_tasks.html
git commit -m "feat: convert My Tasks tabs from Alpine.js to URL-based navigation"
```

---

## Task 3: Add Client Detail Tab URL Routes

**Files:**
- Modify: `apps/clients/urls.py`
- Modify: `apps/clients/views.py:65-76`

**Step 1: Add new URL patterns**

In `apps/clients/urls.py`, add routes for projects and todos tabs:

```python
urlpatterns = [
    path('', views.client_list, name='client_list'),
    path('create/', views.client_create, name='client_create'),
    path('create/drawer/', views.client_create_drawer, name='client_create_drawer'),
    path('<int:pk>/', views.client_detail, name='client_detail'),
    path('<int:pk>/projects/', views.client_detail, name='client_detail_projects'),  # Add
    path('<int:pk>/todos/', views.client_detail, name='client_detail_todos'),  # Add
    path('<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('<int:pk>/edit/drawer/', views.client_edit_drawer, name='client_edit_drawer'),
    path('<int:pk>/notes/', views.client_notes_display, name='client_notes_display'),
    path('<int:pk>/notes/edit/', views.client_edit_notes, name='client_edit_notes'),
    path('<int:pk>/projects/create/', views.client_create_project, name='client_create_project'),
    path('<int:pk>/delete/', views.client_delete, name='client_delete'),
]
```

**Step 2: Modify view to detect active tab**

In `apps/clients/views.py`, update the `client_detail` view:

```python
@login_required
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)

    # Determine active tab from URL
    if request.path.endswith('/todos/'):
        active_tab = 'todos'
    elif request.path.endswith('/projects/'):
        active_tab = 'projects'
    else:
        active_tab = 'profile'

    from apps.todos.models import Todo
    todos_qs = Todo.objects.filter(owner=request.user, client=client, is_completed=False).select_related('client')
    todo_count = todos_qs.count()
    return render(request, 'clients/client_detail.html', {
        'client': client,
        'todo_count': todo_count,
        'todos': todos_qs,
        'show_completed': False,
        'today': timezone.now().date(),
        'active_tab': active_tab,  # Add this
    })
```

**Step 3: Verify manually**

Run: `python manage.py runserver`
- Visit `/clients/1/` - should work
- Visit `/clients/1/projects/` - should work
- Visit `/clients/1/todos/` - should work

**Step 4: Commit**

```bash
git add apps/clients/urls.py apps/clients/views.py
git commit -m "feat: add client detail tab URL routes with active_tab context"
```

---

## Task 4: Update Client Detail Template to Use URL-Based Tabs

**Files:**
- Modify: `templates/clients/client_detail.html`

**Step 1: Replace Alpine.js tabs with URL links**

Key changes:
- Remove `x-data="{ activeTab: 'profile' }"` from container
- Replace sidebar `@click` handlers with `href` links
- Replace `x-show` with Django `{% if %}` conditionals
- Replace `:class` bindings with Django template conditionals

```html
{% extends "base.html" %}

{% block title %}{{ client.name }} - WebFTL CRM{% endblock %}

{% block full_content %}
<div class="flex flex-col h-full">
    <!-- Compact header -->
    <div class="flex-shrink-0 px-4 py-2 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <a href="{% url 'client_list' %}" class="p-1 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors" title="Back to Clients">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i>
                </a>
                <i data-lucide="building-2" class="w-4 h-4 text-zinc-500"></i>
                <h1 class="text-sm font-medium text-zinc-100" id="client-name">{{ client.name }}</h1>
            </div>
            <div class="flex items-center gap-2">
                <button hx-get="{% url 'client_edit_drawer' client.pk %}"
                        hx-target="#slide-over"
                        hx-swap="innerHTML"
                        hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                        class="inline-flex items-center gap-1.5 bg-elevated border border-border-subtle px-3 py-1.5 rounded-card text-xs text-zinc-300 hover:bg-hover transition-colors">
                    <i data-lucide="pencil" class="w-3.5 h-3.5"></i>
                    Edit
                </button>
                {% if request.user.is_admin %}
                <button hx-post="{% url 'client_delete' client.pk %}"
                        hx-confirm="Delete {{ client.name|escapejs }}? This will also delete all projects and tasks."
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
            {% if active_tab == 'profile' %}
            <!-- Profile Section -->
            <div class="h-full">
                <div class="space-y-6" id="profile-content">
                    {% include "clients/partials/profile_content.html" %}
                </div>
            </div>
            {% elif active_tab == 'projects' %}
            <!-- Projects Section -->
            <div class="h-full">
                <div id="projects-content">
                    {% include "clients/partials/projects_content.html" %}
                </div>
            </div>
            {% elif active_tab == 'todos' %}
            <!-- To-Dos Section -->
            <div class="h-full">
                <div id="todos-content">
                    {% include "clients/partials/todos_content.html" %}
                </div>
            </div>
            {% endif %}
        </div>

        <!-- Right sidebar navigation -->
        <div class="w-56 flex-shrink-0 border-l border-border-subtle bg-panel/50 overflow-hidden">
            <div class="p-3">
                <div class="text-[10px] uppercase tracking-wider text-zinc-600 px-2 mb-2">Navigation</div>
                <nav class="space-y-1">
                    <a href="{% url 'client_detail' client.pk %}"
                       class="w-full flex items-center gap-3 px-3 py-2 rounded-card text-sm transition-colors text-left {% if active_tab == 'profile' %}bg-elevated text-zinc-100{% else %}text-zinc-400 hover:text-zinc-200 hover:bg-elevated/50{% endif %}">
                        <i data-lucide="user" class="w-4 h-4"></i>
                        Profile
                    </a>
                    <a href="{% url 'client_detail_projects' client.pk %}"
                       class="w-full flex items-center justify-between px-3 py-2 rounded-card text-sm transition-colors text-left {% if active_tab == 'projects' %}bg-elevated text-zinc-100{% else %}text-zinc-400 hover:text-zinc-200 hover:bg-elevated/50{% endif %}">
                        <span class="flex items-center gap-3">
                            <i data-lucide="folder-kanban" class="w-4 h-4"></i>
                            Projects
                        </span>
                        <span class="text-xs text-zinc-500 bg-panel px-1.5 py-0.5 rounded">{{ client.projects.count }}</span>
                    </a>
                    <a href="{% url 'client_detail_todos' client.pk %}"
                       class="w-full flex items-center justify-between px-3 py-2 rounded-card text-sm transition-colors text-left {% if active_tab == 'todos' %}bg-elevated text-zinc-100{% else %}text-zinc-400 hover:text-zinc-200 hover:bg-elevated/50{% endif %}">
                        <span class="flex items-center gap-3">
                            <i data-lucide="check-square" class="w-4 h-4"></i>
                            To-Dos
                        </span>
                        <span class="text-xs text-zinc-500 bg-panel px-1.5 py-0.5 rounded">{{ todo_count }}</span>
                    </a>
                </nav>
            </div>
        </div>
    </div>
</div>

<script>
    // Listen for client name update from drawer
    document.body.addEventListener('updateClientName', () => {
        // The profile content has been updated, refresh the page title if needed
        htmx.ajax('GET', window.location.href, {target: '#client-name', select: '#client-name'});
    });

    // Listen for project count update
    document.body.addEventListener('updateProjectCount', () => {
        // Refresh the sidebar project count
        location.reload();
    });
</script>
{% endblock %}
```

**Step 2: Verify manually**

Run: `python manage.py runserver`
- Visit `/clients/1/` - Profile tab should be highlighted
- Visit `/clients/1/projects/` - Projects tab should be highlighted
- Visit `/clients/1/todos/` - To-Dos tab should be highlighted
- Click sidebar tabs - should navigate via URL
- Refresh page - should stay on current tab
- Browser back button - should work

**Step 3: Commit**

```bash
git add templates/clients/client_detail.html
git commit -m "feat: convert Client Detail tabs from Alpine.js to URL-based navigation"
```

---

## Task 5: Write Tests for URL-Based Tab Navigation

**Files:**
- Modify: `apps/tasks/tests/test_views.py` (add tests)
- Modify: `apps/clients/tests/test_views.py` (add tests)

**Step 1: Add My Tasks tab URL tests**

In `apps/tasks/tests/test_views.py`, add:

```python
class MyTasksTabsTest(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.client_http = Client()
        self.client_http.force_login(self.user)

    def test_my_tasks_default_tab_is_tasks(self):
        """GET /tasks/my/ should set active_tab to 'tasks'"""
        response = self.client_http.get(reverse('my_tasks'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_tab'], 'tasks')

    def test_my_tasks_todos_tab(self):
        """GET /tasks/my/todos/ should set active_tab to 'todos'"""
        response = self.client_http.get(reverse('my_tasks_todos'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_tab'], 'todos')
```

**Step 2: Add Client Detail tab URL tests**

In `apps/clients/tests/test_views.py`, add:

```python
class ClientDetailTabsTest(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.client_obj = ClientFactory()
        self.client_http = Client()
        self.client_http.force_login(self.user)

    def test_client_detail_default_tab_is_profile(self):
        """GET /clients/<pk>/ should set active_tab to 'profile'"""
        response = self.client_http.get(reverse('client_detail', args=[self.client_obj.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_tab'], 'profile')

    def test_client_detail_projects_tab(self):
        """GET /clients/<pk>/projects/ should set active_tab to 'projects'"""
        response = self.client_http.get(reverse('client_detail_projects', args=[self.client_obj.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_tab'], 'projects')

    def test_client_detail_todos_tab(self):
        """GET /clients/<pk>/todos/ should set active_tab to 'todos'"""
        response = self.client_http.get(reverse('client_detail_todos', args=[self.client_obj.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_tab'], 'todos')
```

**Step 3: Run tests**

Run: `./.venv/bin/pytest apps/tasks/tests/test_views.py::MyTasksTabsTest -v`
Run: `./.venv/bin/pytest apps/clients/tests/test_views.py::ClientDetailTabsTest -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add apps/tasks/tests/test_views.py apps/clients/tests/test_views.py
git commit -m "test: add URL-based tab navigation tests"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add My Tasks todos URL route | `urls.py`, `views.py` |
| 2 | Update My Tasks template | `my_tasks.html` |
| 3 | Add Client Detail tab URL routes | `urls.py`, `views.py` |
| 4 | Update Client Detail template | `client_detail.html` |
| 5 | Write tests | `test_views.py` x2 |

**Total: 5 tasks, ~5 commits**

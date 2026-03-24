# Dashboard Todos Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "My To-Dos" section to the dashboard below the existing "My Recent Tasks" section, showing the user's incomplete todos in a matching table design.

**Architecture:** Query the user's incomplete todos in the dashboard view, pass them to the template, and render a new section that mirrors the "My Recent Tasks" design. Todos are clickable (open detail drawer via HTMX) and show title, client, due date, and status. The "View all" link points to the todos tab on My Tasks page.

**Tech Stack:** Django 5.x, HTMX, Tailwind CSS, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `apps/accounts/views.py:12-38` | Add `recent_todos` and `todo_count` to dashboard context |
| Modify | `templates/accounts/dashboard.html:113` | Add "My To-Dos" section after "My Recent Tasks" |
| Modify | `apps/accounts/tests/test_views.py` | Test todos appear in dashboard context and template |

---

### Task 1: Add todos query to dashboard view and render section

**Files:**
- Modify: `apps/accounts/views.py:12-38`
- Modify: `templates/accounts/dashboard.html:113`
- Test: `apps/accounts/tests/test_views.py`

- [ ] **Step 1: Write the failing tests**

In `apps/accounts/tests/test_views.py`, add a new test class. Add these imports at the top (alongside existing ones):

```python
from apps.todos.factories import TodoFactory
```

Then add the test class:

```python
@pytest.mark.django_db
class TestDashboardTodos:
    def test_dashboard_includes_todos_in_context(self, client):
        """Dashboard should pass recent_todos to template."""
        user = UserFactory()
        TodoFactory(owner=user, title='My Todo')
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert 'recent_todos' in response.context
        assert len(response.context['recent_todos']) == 1

    def test_dashboard_shows_only_incomplete_todos(self, client):
        """Dashboard should only show incomplete todos."""
        user = UserFactory()
        TodoFactory(owner=user, title='Pending Todo', is_completed=False)
        TodoFactory(owner=user, title='Done Todo', is_completed=True)
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert len(response.context['recent_todos']) == 1
        assert response.context['recent_todos'][0].title == 'Pending Todo'

    def test_dashboard_shows_only_own_todos(self, client):
        """Dashboard should only show todos owned by logged-in user."""
        user = UserFactory()
        other = UserFactory()
        TodoFactory(owner=user, title='My Todo')
        TodoFactory(owner=other, title='Other Todo')
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert len(response.context['recent_todos']) == 1

    def test_dashboard_limits_todos_to_five(self, client):
        """Dashboard should show at most 5 todos."""
        user = UserFactory()
        for i in range(7):
            TodoFactory(owner=user, title=f'Todo {i}')
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert len(response.context['recent_todos']) == 5

    def test_dashboard_includes_todo_count(self, client):
        """Dashboard should pass total incomplete todo count."""
        user = UserFactory()
        for i in range(7):
            TodoFactory(owner=user)
        TodoFactory(owner=user, is_completed=True)
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert response.context['todo_count'] == 7

    def test_dashboard_renders_todo_section(self, client):
        """Dashboard should render the My To-Dos section with todo titles."""
        user = UserFactory()
        TodoFactory(owner=user, title='Buy groceries')
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        content = response.content.decode()
        assert 'My To-Dos' in content
        assert 'Buy groceries' in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_views.py::TestDashboardTodos -v`
Expected: FAIL — `recent_todos` not in context

- [ ] **Step 3: Add todos query to dashboard view**

In `apps/accounts/views.py`, add a new try/except block after the tasks block (after line 37, before the return). The view currently has try/except blocks for clients, projects, and tasks. Add one for todos:

```python
    try:
        from apps.todos.models import Todo
        context['recent_todos'] = Todo.objects.filter(
            owner=request.user, is_completed=False
        ).select_related('client')[:5]
        context['todo_count'] = Todo.objects.filter(
            owner=request.user, is_completed=False
        ).count()
    except (ImportError, Exception):
        pass
```

Also update the defaults dict (line 15-20) to include:

```python
        'recent_todos': [],
        'todo_count': 0,
```

- [ ] **Step 4: Run tests to verify the context tests pass**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_views.py::TestDashboardTodos -v -k "not renders"`
Expected: 5 PASS, the render test still fails (template not updated yet)

- [ ] **Step 5: Add the My To-Dos section to the dashboard template**

In `templates/accounts/dashboard.html`, add the following after the closing `</div>` of the "Recent Tasks Section" (after line 113, before the closing content divs):

```html

        <!-- My To-Dos Section -->
        <div class="border border-border-subtle rounded-card overflow-hidden mt-6">
            <div class="px-4 py-2 border-b border-border-subtle bg-panel/80">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-3">
                        <i data-lucide="circle-check" class="w-4 h-4 text-zinc-500"></i>
                        <h2 class="text-sm font-medium text-zinc-100">My To-Dos</h2>
                        <span class="text-xs text-zinc-500 bg-elevated px-1.5 py-0.5 rounded">{{ todo_count }}</span>
                    </div>
                    <a href="{% url 'my_tasks_todos' %}" class="text-xs text-accent hover:text-accent-hover transition-colors">
                        View all
                    </a>
                </div>
            </div>
            {% if recent_todos %}
            <table class="w-full">
                <thead class="bg-panel border-b border-border-subtle">
                    <tr class="text-left text-xs text-zinc-500 uppercase tracking-wider">
                        <th class="px-4 py-2 font-medium">To-Do</th>
                        <th class="px-4 py-2 font-medium">Client</th>
                        <th class="px-4 py-2 font-medium">Due Date</th>
                        <th class="px-4 py-2 font-medium w-10">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-border-subtle">
                    {% for todo in recent_todos %}
                    <tr class="hover:bg-elevated/50 transition-colors cursor-pointer"
                        hx-get="{% url 'todo_detail' todo.pk %}" hx-target="#slide-over" hx-swap="innerHTML"
                        hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();">
                        <td class="px-4 py-3">
                            <span class="font-medium text-sm text-zinc-100">{{ todo.title }}</span>
                        </td>
                        <td class="px-4 py-3">
                            {% if todo.client %}
                            <span class="text-sm text-zinc-400">{{ todo.client.name }}</span>
                            {% else %}
                            <span class="text-sm text-zinc-600">—</span>
                            {% endif %}
                        </td>
                        <td class="px-4 py-3">
                            {% if todo.due_date %}
                            <span class="text-sm text-zinc-500">{{ todo.due_date|date:"M d" }}</span>
                            {% else %}
                            <span class="text-sm text-zinc-600">—</span>
                            {% endif %}
                        </td>
                        <td class="px-4 py-3">
                            <div class="flex items-center justify-end gap-1">
                                <button hx-get="{% url 'todo_detail' todo.pk %}"
                                        hx-target="#slide-over"
                                        hx-swap="innerHTML"
                                        hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                                        class="p-1.5 text-zinc-500 hover:text-zinc-200 hover:bg-elevated rounded transition-colors"
                                        title="Edit"
                                        onclick="event.stopPropagation()">
                                    <i data-lucide="edit-2" class="w-4 h-4"></i>
                                </button>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="flex flex-col items-center justify-center py-12 text-zinc-500">
                <i data-lucide="circle-check" class="w-10 h-10 mb-3 opacity-30"></i>
                <p class="text-sm">No to-dos yet</p>
            </div>
            {% endif %}
        </div>
```

- [ ] **Step 6: Run all tests to verify they pass**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_views.py -v`
Expected: All PASS (existing + 6 new)

- [ ] **Step 7: Commit**

```bash
git add apps/accounts/views.py templates/accounts/dashboard.html apps/accounts/tests/test_views.py
git commit -m "feat: add My To-Dos section to dashboard"
```

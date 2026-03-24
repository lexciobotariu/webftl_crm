# RBAC Phase 4: Client Name Visibility in Project Context

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show client names as non-clickable text (instead of links to client detail) for users without `access_clients` permission, so contractors see which client a project belongs to without being able to navigate to client pages.

**Architecture:** Wrap every `<a href="{% url 'client_detail' ... %}">` referencing a client in project templates with `{% if perms_map.access_clients %}...link...{% else %}...plain text...{% endif %}`. The `perms_map` context variable is already available in all templates from Phase 1. The back arrow in project detail/board/settings headers changes from linking to client detail to linking to the project list for users without client access. No backend changes needed — this is purely template logic.

**Tech Stack:** Django templates, Tailwind CSS, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `templates/projects/project_list.html:14-23` | Hide client filter dropdown for users without client access |
| Modify | `templates/projects/partials/project_row.html:8-11` | Client name link in project list table |
| Modify | `templates/projects/project_detail.html:11-18` | Back arrow + breadcrumb client link |
| Modify | `templates/projects/project_board.html:11-18` | Back arrow + breadcrumb client link |
| Modify | `templates/projects/project_settings.html:10-18` | Breadcrumb client link |
| Modify | `templates/projects/partials/overview_content.html:23-26` | Client field in overview section |
| Modify | `templates/projects/partials/settings_general_form.html:31` | Client name in settings (already read-only text, no change needed) |
| Test | `apps/projects/tests/test_views.py` | Test client link visibility per permission |

---

### Task 1: Make client name links permission-aware across all project templates

**Files:**
- Modify: `templates/projects/project_list.html`
- Modify: `templates/projects/partials/project_row.html`
- Modify: `templates/projects/project_detail.html`
- Modify: `templates/projects/project_board.html`
- Modify: `templates/projects/project_settings.html`
- Modify: `templates/projects/partials/overview_content.html`
- Test: `apps/projects/tests/test_views.py`

- [ ] **Step 1: Write the failing tests**

Add to `apps/projects/tests/test_views.py`. Add these imports at the top if not present:

```python
from apps.accounts.permissions import PermissionPreset
```

Add new test class:

```python
@pytest.mark.django_db
class TestClientNameVisibility:
    def test_project_list_shows_client_link_for_admin(self, client):
        """Admin should see client name as a clickable link."""
        admin = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(admin)
        response = client.get(reverse('project_list'))
        content = response.content.decode()
        assert f'/clients/{project.client.pk}/' in content

    def test_project_list_hides_client_link_for_developer(self, client):
        """Developer should see client name as plain text, not a link."""
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.get(reverse('project_list'))
        content = response.content.decode()
        # Client name should appear but NOT as a link to client_detail
        assert project.client.name in content
        assert f'/clients/{project.client.pk}/' not in content

    def test_project_detail_shows_client_breadcrumb_link_for_admin(self, client):
        """Admin should see clickable client breadcrumb."""
        admin = AdminUserFactory()
        project = ProjectFactory()
        client.force_login(admin)
        response = client.get(reverse('project_detail', args=[project.pk]))
        content = response.content.decode()
        assert f'/clients/{project.client.pk}/' in content

    def test_project_detail_hides_client_breadcrumb_link_for_developer(self, client):
        """Developer should see client name in breadcrumb but not as link."""
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.get(reverse('project_detail', args=[project.pk]))
        content = response.content.decode()
        assert project.client.name in content
        assert f'/clients/{project.client.pk}/' not in content

    def test_project_list_hides_client_filter_for_developer(self, client):
        """Developer should not see the client filter dropdown."""
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.get(reverse('project_list'))
        content = response.content.decode()
        assert 'All Clients' not in content

    def test_project_board_hides_client_link_for_developer(self, client):
        """Developer should see client name in board breadcrumb but not as link."""
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=user, role='viewer')
        client.force_login(user)
        response = client.get(reverse('project_board', args=[project.pk]))
        content = response.content.decode()
        assert project.client.name in content
        assert f'/clients/{project.client.pk}/' not in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest apps/projects/tests/test_views.py::TestClientNameVisibility -v`
Expected: FAIL (client links appear for developer users)

- [ ] **Step 3: Update `project_row.html`**

In `templates/projects/partials/project_row.html`, replace the client cell (lines 7-14):

Find:
```html
    <td class="px-4 py-3">
        {% if project.client %}
        <a href="{% url 'client_detail' project.client.pk %}" class="text-sm text-zinc-400 hover:text-zinc-200 transition-colors">
            {{ project.client.name }}
        </a>
        {% else %}
        <span class="text-sm text-zinc-600">—</span>
        {% endif %}
    </td>
```

Replace with:
```html
    <td class="px-4 py-3">
        {% if project.client %}
            {% if perms_map.access_clients %}
            <a href="{% url 'client_detail' project.client.pk %}" class="text-sm text-zinc-400 hover:text-zinc-200 transition-colors">
                {{ project.client.name }}
            </a>
            {% else %}
            <span class="text-sm text-zinc-400">{{ project.client.name }}</span>
            {% endif %}
        {% else %}
        <span class="text-sm text-zinc-600">—</span>
        {% endif %}
    </td>
```

- [ ] **Step 4: Hide client filter dropdown in `project_list.html`**

In `templates/projects/project_list.html`, wrap the client filter (lines 14-23) with a permission check:

Find:
```html
                <!-- Client filter -->
                <select onchange="window.location.href='?client=' + this.value"
                        class="ml-4 bg-elevated border border-border-subtle rounded px-2 py-1 text-xs text-zinc-400 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none">
                    <option value="">All Clients</option>
                    {% for client in clients %}
                    <option value="{{ client.pk }}" {% if client_filter == client.pk|stringformat:"s" %}selected{% endif %}>
                        {{ client.name }}
                    </option>
                    {% endfor %}
                </select>
```

Replace with:
```html
                {% if perms_map.access_clients %}
                <!-- Client filter -->
                <select onchange="window.location.href='?client=' + this.value"
                        class="ml-4 bg-elevated border border-border-subtle rounded px-2 py-1 text-xs text-zinc-400 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none">
                    <option value="">All Clients</option>
                    {% for client in clients %}
                    <option value="{{ client.pk }}" {% if client_filter == client.pk|stringformat:"s" %}selected{% endif %}>
                        {{ client.name }}
                    </option>
                    {% endfor %}
                </select>
                {% endif %}
```

- [ ] **Step 5: Update `project_detail.html` header/breadcrumb**

In `templates/projects/project_detail.html`, replace the back arrow and breadcrumb (lines 11-18):

Find:
```html
                <a href="{% url 'client_detail' project.client.pk %}" class="p-1 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors" title="Back to Client">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i>
                </a>
                <div class="flex items-center gap-2 text-sm">
                    <a href="{% url 'client_detail' project.client.pk %}" class="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 transition-colors">
                        <i data-lucide="building-2" class="w-3.5 h-3.5"></i>
                        <span>{{ project.client.name }}</span>
                    </a>
```

Replace with:
```html
                {% if perms_map.access_clients %}
                <a href="{% url 'client_detail' project.client.pk %}" class="p-1 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors" title="Back to Client">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i>
                </a>
                {% else %}
                <a href="{% url 'project_list' %}" class="p-1 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors" title="Back to Projects">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i>
                </a>
                {% endif %}
                <div class="flex items-center gap-2 text-sm">
                    {% if perms_map.access_clients %}
                    <a href="{% url 'client_detail' project.client.pk %}" class="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 transition-colors">
                        <i data-lucide="building-2" class="w-3.5 h-3.5"></i>
                        <span>{{ project.client.name }}</span>
                    </a>
                    {% else %}
                    <span class="flex items-center gap-1.5 text-zinc-500">
                        <i data-lucide="building-2" class="w-3.5 h-3.5"></i>
                        <span>{{ project.client.name }}</span>
                    </span>
                    {% endif %}
```

- [ ] **Step 6: Update `project_board.html` header/breadcrumb**

In `templates/projects/project_board.html`, replace the back arrow and breadcrumb (lines 11-18). Same pattern as project_detail:

Find:
```html
                <a href="{% url 'project_detail' project.pk %}" class="p-1 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors" title="Back to Project">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i>
                </a>
                <div class="flex items-center gap-2 text-sm">
                    <a href="{% url 'client_detail' project.client.pk %}" class="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 transition-colors">
                        <i data-lucide="building-2" class="w-3.5 h-3.5"></i>
                        <span>{{ project.client.name }}</span>
                    </a>
```

Replace with:
```html
                <a href="{% url 'project_detail' project.pk %}" class="p-1 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors" title="Back to Project">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i>
                </a>
                <div class="flex items-center gap-2 text-sm">
                    {% if perms_map.access_clients %}
                    <a href="{% url 'client_detail' project.client.pk %}" class="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 transition-colors">
                        <i data-lucide="building-2" class="w-3.5 h-3.5"></i>
                        <span>{{ project.client.name }}</span>
                    </a>
                    {% else %}
                    <span class="flex items-center gap-1.5 text-zinc-500">
                        <i data-lucide="building-2" class="w-3.5 h-3.5"></i>
                        <span>{{ project.client.name }}</span>
                    </span>
                    {% endif %}
```

Note: The board's back arrow stays pointing to project_detail (not client) — this is already correct for all users.

- [ ] **Step 7: Update `project_settings.html` breadcrumb**

In `templates/projects/project_settings.html`, replace the client breadcrumb link (lines 15-18):

Find:
```html
                <a href="{% url 'client_detail' project.client.pk %}" class="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 transition-colors">
                    <i data-lucide="building-2" class="w-3.5 h-3.5"></i>
                    <span>{{ project.client.name }}</span>
                </a>
```

Replace with:
```html
                {% if perms_map.access_clients %}
                <a href="{% url 'client_detail' project.client.pk %}" class="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 transition-colors">
                    <i data-lucide="building-2" class="w-3.5 h-3.5"></i>
                    <span>{{ project.client.name }}</span>
                </a>
                {% else %}
                <span class="flex items-center gap-1.5 text-zinc-500">
                    <i data-lucide="building-2" class="w-3.5 h-3.5"></i>
                    <span>{{ project.client.name }}</span>
                </span>
                {% endif %}
```

- [ ] **Step 8: Update `overview_content.html` client field**

In `templates/projects/partials/overview_content.html`, replace the client link (lines 23-26):

Find:
```html
                <dd class="text-zinc-300">
                    <a href="{% url 'client_detail' project.client.pk %}" class="hover:text-accent transition-colors">
                        {{ project.client.name }}
                    </a>
                </dd>
```

Replace with:
```html
                <dd class="text-zinc-300">
                    {% if perms_map.access_clients %}
                    <a href="{% url 'client_detail' project.client.pk %}" class="hover:text-accent transition-colors">
                        {{ project.client.name }}
                    </a>
                    {% else %}
                    {{ project.client.name }}
                    {% endif %}
                </dd>
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest apps/projects/tests/test_views.py::TestClientNameVisibility -v`
Expected: All PASS

- [ ] **Step 10: Run full project tests for regressions**

Run: `.venv/bin/python -m pytest apps/projects/tests/ -v`
Expected: All PASS

- [ ] **Step 11: Commit**

```bash
git add templates/projects/project_list.html templates/projects/partials/project_row.html templates/projects/project_detail.html templates/projects/project_board.html templates/projects/project_settings.html templates/projects/partials/overview_content.html apps/projects/tests/test_views.py
git commit -m "feat: show client names as plain text for users without client access"
```

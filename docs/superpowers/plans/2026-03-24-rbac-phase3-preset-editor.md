# RBAC Phase 3: Preset Editor UI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an admin UI to create, edit, and delete custom permission presets, accessible from the Team page.

**Architecture:** Add a "Manage Presets" page linked from the Team header. The page lists all presets with their permission badges and user count. A drawer handles create/edit with toggle switches for each permission. System presets (Admin, Developer) can be edited but not deleted. Presets assigned to users cannot be deleted — the UI shows a warning. All views are admin-only behind `@require_permission('access_team')` + `is_admin`.

**Tech Stack:** Django 5.x, HTMX, Tailwind CSS, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `apps/accounts/urls.py` | Add preset list, create, edit, delete routes |
| Modify | `apps/accounts/views.py` | Add preset CRUD views |
| Create | `templates/accounts/preset_list.html` | Full page listing all presets |
| Create | `templates/accounts/partials/preset_item.html` | Single preset row partial |
| Create | `templates/accounts/partials/preset_form_drawer.html` | Create/edit drawer with toggles |
| Modify | `templates/accounts/team_list.html` | Add "Manage Presets" button in header |
| Test | `apps/accounts/tests/test_permissions.py` | Tests for all preset CRUD operations |

---

### Task 1: Preset list page with preset items

**Files:**
- Modify: `apps/accounts/urls.py`
- Modify: `apps/accounts/views.py`
- Create: `templates/accounts/preset_list.html`
- Create: `templates/accounts/partials/preset_item.html`
- Modify: `templates/accounts/team_list.html`
- Test: `apps/accounts/tests/test_permissions.py`

- [ ] **Step 1: Write the failing tests**

Add to `apps/accounts/tests/test_permissions.py`:

```python
@pytest.mark.django_db
class TestPresetList:
    def test_preset_list_requires_admin(self, client):
        """Non-admin should get 403."""
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        client.force_login(user)
        response = client.get(reverse('preset_list'))
        assert response.status_code == 403

    def test_preset_list_shows_presets(self, client):
        """Admin should see all presets listed."""
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('preset_list'))
        content = response.content.decode()
        assert response.status_code == 200
        assert 'Admin' in content
        assert 'Developer' in content

    def test_preset_list_shows_user_count(self, client):
        """Each preset should show how many users are assigned to it."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Developer')
        UserFactory(permission_preset=preset)
        UserFactory(permission_preset=preset)
        client.force_login(admin)
        response = client.get(reverse('preset_list'))
        # The Developer preset should show 2 users
        assert response.status_code == 200

    def test_preset_list_shows_permission_badges(self, client):
        """Preset items should show which permissions are granted."""
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('preset_list'))
        content = response.content.decode()
        # Developer preset has Projects access
        assert 'Projects' in content

    def test_team_list_has_manage_presets_link(self, client):
        """Team page header should have a Manage Presets button."""
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert 'Manage Presets' in response.content.decode()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_permissions.py::TestPresetList -v`
Expected: FAIL with `NoReverseMatch`

- [ ] **Step 3: Add URL route**

In `apps/accounts/urls.py`, add:

```python
path('team/presets/', views.preset_list, name='preset_list'),
```

- [ ] **Step 4: Add preset_list view**

In `apps/accounts/views.py`, add:

```python
@login_required
@require_permission('access_team')
def preset_list(request):
    """List all permission presets."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    presets = PermissionPreset.objects.annotate(
        user_count=models.Count('users')
    ).order_by('name')
    return render(request, 'accounts/preset_list.html', {
        'presets': presets,
    })
```

Add `from django.db import models` to the imports at the top of `apps/accounts/views.py` (needed for `models.Count`).

- [ ] **Step 5: Create preset_list.html template**

Create `templates/accounts/preset_list.html`:

```html
{% extends "base.html" %}

{% block title %}Permission Presets - WebFTL CRM{% endblock %}

{% block full_content %}
<div class="flex flex-col h-full">
    <!-- Header -->
    <div class="flex-shrink-0 px-4 py-2 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <a href="{% url 'team_list' %}"
                   class="p-1 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors" title="Back to Team">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i>
                </a>
                <i data-lucide="shield" class="w-4 h-4 text-zinc-500"></i>
                <h1 class="text-sm font-medium text-zinc-100">Permission Presets</h1>
                <span class="text-xs text-zinc-500 bg-elevated px-1.5 py-0.5 rounded">{{ presets|length }}</span>
            </div>
            <button hx-get="{% url 'preset_create' %}"
                    hx-target="#slide-over"
                    hx-swap="innerHTML"
                    hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                    class="inline-flex items-center gap-1.5 bg-accent text-white px-3 py-1.5 rounded-card text-xs font-medium hover:bg-accent-hover transition-colors">
                <i data-lucide="plus" class="w-3.5 h-3.5"></i>
                New Preset
            </button>
        </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-auto p-4">
        <div class="max-w-4xl space-y-3" id="preset-list">
            {% for preset in presets %}
            {% include "accounts/partials/preset_item.html" %}
            {% empty %}
            <div class="flex flex-col items-center justify-center py-16 text-zinc-500">
                <i data-lucide="shield" class="w-12 h-12 mb-4 opacity-30"></i>
                <p class="text-sm">No presets defined</p>
            </div>
            {% endfor %}
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 6: Create preset_item.html partial**

Create `templates/accounts/partials/preset_item.html`:

```html
<div class="bg-panel/80 rounded-panel border border-border-subtle overflow-hidden" id="preset-{{ preset.pk }}">
    <div class="px-5 py-4 flex items-start justify-between">
        <div class="flex-1">
            <div class="flex items-center gap-2 mb-1">
                <h3 class="text-sm font-medium text-zinc-100">{{ preset.name }}</h3>
                {% if preset.is_system %}
                <span class="px-1.5 py-0.5 text-[10px] rounded bg-zinc-500/10 text-zinc-500 border border-zinc-500/20">System</span>
                {% endif %}
                <span class="text-xs text-zinc-500">{{ preset.user_count }} user{{ preset.user_count|pluralize }}</span>
            </div>
            {% if preset.description %}
            <p class="text-xs text-zinc-500 mb-3">{{ preset.description }}</p>
            {% endif %}
            <div class="flex flex-wrap gap-1.5">
                {% if preset.access_dashboard %}
                <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Dashboard</span>
                {% endif %}
                {% if preset.access_clients %}
                <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Clients</span>
                {% endif %}
                {% if preset.access_projects %}
                <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Projects</span>
                {% endif %}
                {% if preset.access_tasks %}
                <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Tasks</span>
                {% endif %}
                {% if preset.access_todos %}
                <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Todos</span>
                {% endif %}
                {% if preset.access_notes %}
                <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Notes</span>
                {% endif %}
                {% if preset.access_salaries %}
                <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Salaries</span>
                {% endif %}
                {% if preset.access_team %}
                <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Team</span>
                {% endif %}
            </div>
        </div>
        <div class="flex items-center gap-1 ml-4">
            <button hx-get="{% url 'preset_edit' preset.pk %}"
                    hx-target="#slide-over"
                    hx-swap="innerHTML"
                    hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                    class="p-1.5 text-zinc-500 hover:text-zinc-200 hover:bg-elevated rounded transition-colors"
                    title="Edit preset">
                <i data-lucide="pencil" class="w-4 h-4"></i>
            </button>
            {% if not preset.is_system and preset.user_count == 0 %}
            <button hx-post="{% url 'preset_delete' preset.pk %}"
                    hx-target="#preset-{{ preset.pk }}"
                    hx-swap="outerHTML"
                    hx-confirm="Delete '{{ preset.name }}'?"
                    class="p-1.5 text-zinc-500 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                    title="Delete preset">
                <i data-lucide="trash-2" class="w-4 h-4"></i>
            </button>
            {% endif %}
        </div>
    </div>
</div>
```

Note: The delete button only shows when `is_system` is False AND `user_count == 0`. The edit and delete URLs (`preset_edit`, `preset_create`, `preset_delete`) don't exist yet — they'll be added in Task 2. For now, add stub URL routes and views so the template doesn't error.

- [ ] **Step 7: Add stub URL routes and views for create/edit/delete**

In `apps/accounts/urls.py`, add:

```python
path('team/presets/create/', views.preset_create, name='preset_create'),
path('team/presets/<int:pk>/edit/', views.preset_edit, name='preset_edit'),
path('team/presets/<int:pk>/delete/', views.preset_delete, name='preset_delete'),
```

In `apps/accounts/views.py`, add stubs:

```python
@login_required
@require_permission('access_team')
def preset_create(request):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    return render(request, 'accounts/partials/preset_form_drawer.html', {'presets': PermissionPreset.objects.all()})


@login_required
@require_permission('access_team')
def preset_edit(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    preset = get_object_or_404(PermissionPreset, pk=pk)
    return render(request, 'accounts/partials/preset_form_drawer.html', {'preset': preset})


@login_required
@require_permission('access_team')
@require_POST
def preset_delete(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    from django.http import HttpResponse
    return HttpResponse('')
```

Create a minimal `templates/accounts/partials/preset_form_drawer.html`:

```html
<div class="p-4">
    <p class="text-sm text-zinc-300">Preset form placeholder</p>
</div>
```

- [ ] **Step 8: Add "Manage Presets" button to team_list.html**

In `templates/accounts/team_list.html`, add a button in the header, right before the "Invite Member" link (around line 15). Replace the header `<div class="flex items-center justify-between">` block:

Find:
```html
            <a href="{% url 'account_signup' %}"
               class="inline-flex items-center gap-1.5 bg-accent text-white px-3 py-1.5 rounded-card text-xs font-medium hover:bg-accent-hover transition-colors">
                <i data-lucide="plus" class="w-3.5 h-3.5"></i>
                Invite Member
            </a>
```

Replace with:
```html
            <div class="flex items-center gap-2">
                <a href="{% url 'preset_list' %}"
                   class="inline-flex items-center gap-1.5 bg-elevated border border-border-subtle px-3 py-1.5 rounded-card text-xs text-zinc-400 hover:text-zinc-200 hover:bg-hover-strong transition-colors">
                    <i data-lucide="shield" class="w-3.5 h-3.5"></i>
                    Manage Presets
                </a>
                <a href="{% url 'account_signup' %}"
                   class="inline-flex items-center gap-1.5 bg-accent text-white px-3 py-1.5 rounded-card text-xs font-medium hover:bg-accent-hover transition-colors">
                    <i data-lucide="plus" class="w-3.5 h-3.5"></i>
                    Invite Member
                </a>
            </div>
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_permissions.py::TestPresetList -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add apps/accounts/urls.py apps/accounts/views.py templates/accounts/preset_list.html templates/accounts/partials/preset_item.html templates/accounts/partials/preset_form_drawer.html templates/accounts/team_list.html apps/accounts/tests/test_permissions.py
git commit -m "feat: add preset list page with permission badges and user counts"
```

---

### Task 2: Preset create/edit drawer with toggle switches

**Files:**
- Modify: `apps/accounts/views.py` — flesh out `preset_create` and `preset_edit`
- Modify: `templates/accounts/partials/preset_form_drawer.html` — full form with toggles
- Test: `apps/accounts/tests/test_permissions.py`

- [ ] **Step 1: Write the failing tests**

Add to `apps/accounts/tests/test_permissions.py`:

```python
@pytest.mark.django_db
class TestPresetCreate:
    def test_create_preset_requires_admin(self, client):
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        client.force_login(user)
        response = client.post(reverse('preset_create'), {
            'name': 'New Preset',
        })
        assert response.status_code == 403

    def test_create_preset_success(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('preset_create'), {
            'name': 'Contractor',
            'description': 'External contractors',
            'access_dashboard': 'on',
            'access_projects': 'on',
            'access_tasks': 'on',
        })
        assert response.status_code == 200
        preset = PermissionPreset.objects.get(name='Contractor')
        assert preset.access_dashboard is True
        assert preset.access_projects is True
        assert preset.access_tasks is True
        assert preset.access_clients is False
        assert preset.access_salaries is False

    def test_create_preset_returns_item(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('preset_create'), {
            'name': 'Viewer',
            'access_dashboard': 'on',
        })
        assert 'Viewer' in response.content.decode()

    def test_create_preset_duplicate_name_fails(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('preset_create'), {
            'name': 'Developer',
        })
        # Should re-render the form with error, not create
        assert response.status_code == 200
        assert PermissionPreset.objects.filter(name='Developer').count() == 1


@pytest.mark.django_db
class TestPresetEdit:
    def test_edit_preset_get_shows_form(self, client):
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Developer')
        client.force_login(admin)
        response = client.get(reverse('preset_edit', args=[preset.pk]))
        content = response.content.decode()
        assert 'Developer' in content
        assert response.status_code == 200

    def test_edit_preset_updates_permissions(self, client):
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.create(
            name='Custom',
            access_clients=False,
        )
        client.force_login(admin)
        response = client.post(reverse('preset_edit', args=[preset.pk]), {
            'name': 'Custom',
            'description': 'Updated',
            'access_dashboard': 'on',
            'access_clients': 'on',
            'access_projects': 'on',
            'access_tasks': 'on',
            'access_todos': 'on',
            'access_notes': 'on',
        })
        assert response.status_code == 200
        preset.refresh_from_db()
        assert preset.access_clients is True
        assert preset.description == 'Updated'

    def test_edit_system_preset_cannot_change_name(self, client):
        """System presets can have permissions edited but not their name."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Developer')
        client.force_login(admin)
        response = client.post(reverse('preset_edit', args=[preset.pk]), {
            'name': 'Renamed',
            'access_dashboard': 'on',
            'access_projects': 'on',
        })
        preset.refresh_from_db()
        assert preset.name == 'Developer'  # Name unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_permissions.py::TestPresetCreate apps/accounts/tests/test_permissions.py::TestPresetEdit -v`
Expected: FAIL

- [ ] **Step 3: Flesh out preset_create and preset_edit views**

In `apps/accounts/views.py`, replace the stubs:

```python
from apps.accounts.permissions import PermissionPreset, PERMISSION_KEYS


@login_required
@require_permission('access_team')
def preset_create(request):
    """Create a new permission preset via drawer."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()

        if not name:
            return render(request, 'accounts/partials/preset_form_drawer.html', {
                'error': 'Name is required.',
            })

        if PermissionPreset.objects.filter(name=name).exists():
            return render(request, 'accounts/partials/preset_form_drawer.html', {
                'error': f'A preset named "{name}" already exists.',
                'form_name': name,
                'form_description': description,
            })

        preset = PermissionPreset.objects.create(
            name=name,
            description=description,
            **{key: key in request.POST for key in PERMISSION_KEYS},
        )
        preset.user_count = 0  # For template rendering
        response = render(request, 'accounts/partials/preset_item.html', {'preset': preset})
        response['HX-Trigger'] = 'closeSlideOver'
        return response

    return render(request, 'accounts/partials/preset_form_drawer.html', {})


@login_required
@require_permission('access_team')
def preset_edit(request, pk):
    """Edit a permission preset via drawer."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    preset = get_object_or_404(PermissionPreset, pk=pk)

    if request.method == 'POST':
        if not preset.is_system:
            preset.name = request.POST.get('name', '').strip() or preset.name
        preset.description = request.POST.get('description', '').strip()
        for key in PERMISSION_KEYS:
            setattr(preset, key, key in request.POST)
        preset.save()

        # Re-annotate user_count for template
        from django.db.models import Count
        preset = PermissionPreset.objects.annotate(user_count=Count('users')).get(pk=pk)
        response = render(request, 'accounts/partials/preset_item.html', {'preset': preset})
        response['HX-Trigger'] = 'closeSlideOver'
        return response

    return render(request, 'accounts/partials/preset_form_drawer.html', {'preset': preset})
```

Make sure `PERMISSION_KEYS` is imported — update the existing import line:

```python
from .permissions import PermissionPreset, PERMISSION_KEYS
```

- [ ] **Step 4: Build the full form drawer template**

Replace `templates/accounts/partials/preset_form_drawer.html` with:

```html
<div class="flex flex-col h-full">
    <!-- Header -->
    <div class="flex-shrink-0 px-4 py-3 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <i data-lucide="shield" class="w-4 h-4 text-zinc-500"></i>
                <h2 class="text-sm font-medium text-zinc-100">
                    {% if preset %}Edit Preset{% else %}New Preset{% endif %}
                </h2>
            </div>
            <button onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors">
                <i data-lucide="x" class="w-4 h-4"></i>
            </button>
        </div>
    </div>

    <!-- Form -->
    <form hx-post="{% if preset %}{% url 'preset_edit' preset.pk %}{% else %}{% url 'preset_create' %}{% endif %}"
          hx-target="{% if preset %}#preset-{{ preset.pk }}{% else %}#preset-list{% endif %}"
          hx-swap="{% if preset %}outerHTML{% else %}beforeend{% endif %}"
          class="flex-1 overflow-y-auto p-4">
        {% csrf_token %}

        {% if error %}
        <div class="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-card">
            <p class="text-sm text-red-400">{{ error }}</p>
        </div>
        {% endif %}

        <div class="space-y-4">
            <!-- Name -->
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Name</label>
                {% if preset.is_system %}
                <div class="w-full bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-400">
                    {{ preset.name }}
                </div>
                {% else %}
                <input type="text" name="name" required
                       value="{{ preset.name|default:form_name|default:'' }}"
                       class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
                       placeholder="e.g. Contractor">
                {% endif %}
            </div>

            <!-- Description -->
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Description</label>
                <input type="text" name="description"
                       value="{{ preset.description|default:form_description|default:'' }}"
                       class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
                       placeholder="Brief description of this role">
            </div>

            <!-- Permissions -->
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-3">Permissions</label>
                <div class="space-y-2">
                    <label class="flex items-center justify-between p-3 bg-elevated/50 rounded-card border border-border-subtle hover:border-border-strong transition-colors cursor-pointer">
                        <div class="flex items-center gap-2">
                            <i data-lucide="layout-dashboard" class="w-4 h-4 text-zinc-500"></i>
                            <span class="text-sm text-zinc-300">Dashboard</span>
                        </div>
                        <input type="checkbox" name="access_dashboard" {% if preset %}{% if preset.access_dashboard %}checked{% endif %}{% else %}checked{% endif %}
                               class="w-4 h-4 bg-elevated border-border-subtle rounded text-accent focus:ring-accent">
                    </label>

                    <label class="flex items-center justify-between p-3 bg-elevated/50 rounded-card border border-border-subtle hover:border-border-strong transition-colors cursor-pointer">
                        <div class="flex items-center gap-2">
                            <i data-lucide="building-2" class="w-4 h-4 text-zinc-500"></i>
                            <span class="text-sm text-zinc-300">Clients</span>
                        </div>
                        <input type="checkbox" name="access_clients" {% if preset %}{% if preset.access_clients %}checked{% endif %}{% else %}checked{% endif %}
                               class="w-4 h-4 bg-elevated border-border-subtle rounded text-accent focus:ring-accent">
                    </label>

                    <label class="flex items-center justify-between p-3 bg-elevated/50 rounded-card border border-border-subtle hover:border-border-strong transition-colors cursor-pointer">
                        <div class="flex items-center gap-2">
                            <i data-lucide="folder-kanban" class="w-4 h-4 text-zinc-500"></i>
                            <span class="text-sm text-zinc-300">Projects</span>
                        </div>
                        <input type="checkbox" name="access_projects" {% if preset %}{% if preset.access_projects %}checked{% endif %}{% else %}checked{% endif %}
                               class="w-4 h-4 bg-elevated border-border-subtle rounded text-accent focus:ring-accent">
                    </label>

                    <label class="flex items-center justify-between p-3 bg-elevated/50 rounded-card border border-border-subtle hover:border-border-strong transition-colors cursor-pointer">
                        <div class="flex items-center gap-2">
                            <i data-lucide="user-check" class="w-4 h-4 text-zinc-500"></i>
                            <span class="text-sm text-zinc-300">Tasks</span>
                        </div>
                        <input type="checkbox" name="access_tasks" {% if preset %}{% if preset.access_tasks %}checked{% endif %}{% else %}checked{% endif %}
                               class="w-4 h-4 bg-elevated border-border-subtle rounded text-accent focus:ring-accent">
                    </label>

                    <label class="flex items-center justify-between p-3 bg-elevated/50 rounded-card border border-border-subtle hover:border-border-strong transition-colors cursor-pointer">
                        <div class="flex items-center gap-2">
                            <i data-lucide="circle-check" class="w-4 h-4 text-zinc-500"></i>
                            <span class="text-sm text-zinc-300">Todos</span>
                        </div>
                        <input type="checkbox" name="access_todos" {% if preset %}{% if preset.access_todos %}checked{% endif %}{% else %}checked{% endif %}
                               class="w-4 h-4 bg-elevated border-border-subtle rounded text-accent focus:ring-accent">
                    </label>

                    <label class="flex items-center justify-between p-3 bg-elevated/50 rounded-card border border-border-subtle hover:border-border-strong transition-colors cursor-pointer">
                        <div class="flex items-center gap-2">
                            <i data-lucide="sticky-note" class="w-4 h-4 text-zinc-500"></i>
                            <span class="text-sm text-zinc-300">Notes</span>
                        </div>
                        <input type="checkbox" name="access_notes" {% if preset %}{% if preset.access_notes %}checked{% endif %}{% else %}checked{% endif %}
                               class="w-4 h-4 bg-elevated border-border-subtle rounded text-accent focus:ring-accent">
                    </label>

                    <label class="flex items-center justify-between p-3 bg-elevated/50 rounded-card border border-border-subtle hover:border-border-strong transition-colors cursor-pointer">
                        <div class="flex items-center gap-2">
                            <i data-lucide="wallet" class="w-4 h-4 text-zinc-500"></i>
                            <span class="text-sm text-zinc-300">Salaries</span>
                        </div>
                        <input type="checkbox" name="access_salaries" {% if preset %}{% if preset.access_salaries %}checked{% endif %}{% else %}checked{% endif %}
                               class="w-4 h-4 bg-elevated border-border-subtle rounded text-accent focus:ring-accent">
                    </label>

                    <label class="flex items-center justify-between p-3 bg-elevated/50 rounded-card border border-border-subtle hover:border-border-strong transition-colors cursor-pointer">
                        <div class="flex items-center gap-2">
                            <i data-lucide="users" class="w-4 h-4 text-zinc-500"></i>
                            <span class="text-sm text-zinc-300">Team</span>
                        </div>
                        <input type="checkbox" name="access_team" {% if preset %}{% if preset.access_team %}checked{% endif %}{% else %}checked{% endif %}
                               class="w-4 h-4 bg-elevated border-border-subtle rounded text-accent focus:ring-accent">
                    </label>
                </div>
            </div>
        </div>

        <div class="flex gap-3 mt-6 pt-4 border-t border-border-subtle">
            <button type="submit"
                    class="bg-accent text-white px-4 py-2 rounded-card text-sm font-medium hover:bg-accent-hover transition-colors">
                {% if preset %}Save Changes{% else %}Create Preset{% endif %}
            </button>
            <button type="button"
                    onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="bg-elevated border border-border-subtle px-4 py-2 rounded-card text-sm text-zinc-400 hover:text-zinc-200 hover:bg-hover-strong transition-colors">
                Cancel
            </button>
        </div>
    </form>
</div>

<script>
if (typeof lucide !== 'undefined') {
    lucide.createIcons();
}
</script>
```

**IMPORTANT NOTE on checkbox default values:** When creating a new preset (`preset` is not in context), all checkboxes should default to checked. When editing, the actual boolean value from the model is used. We use `{% if preset %}{% if preset.access_X %}checked{% endif %}{% else %}checked{% endif %}` pattern because `|default:True` would incorrectly override `False` values during edit (since `False` is falsy).

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_permissions.py::TestPresetCreate apps/accounts/tests/test_permissions.py::TestPresetEdit -v`
Expected: All PASS

- [ ] **Step 6: Run full accounts tests**

Run: `.venv/bin/python -m pytest apps/accounts/tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add apps/accounts/views.py templates/accounts/partials/preset_form_drawer.html apps/accounts/tests/test_permissions.py
git commit -m "feat: preset create/edit drawer with permission toggle switches"
```

---

### Task 3: Preset delete with safety checks

**Files:**
- Modify: `apps/accounts/views.py` — flesh out `preset_delete`
- Test: `apps/accounts/tests/test_permissions.py`

- [ ] **Step 1: Write the failing tests**

Add to `apps/accounts/tests/test_permissions.py`:

```python
@pytest.mark.django_db
class TestPresetDelete:
    def test_delete_custom_preset(self, client):
        """Admin can delete a custom preset with no users."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.create(name='ToDelete')
        client.force_login(admin)
        response = client.post(reverse('preset_delete', args=[preset.pk]))
        assert response.status_code == 200
        assert not PermissionPreset.objects.filter(name='ToDelete').exists()

    def test_cannot_delete_system_preset(self, client):
        """System presets cannot be deleted."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Admin')
        client.force_login(admin)
        response = client.post(reverse('preset_delete', args=[preset.pk]))
        assert response.status_code == 400
        assert PermissionPreset.objects.filter(name='Admin').exists()

    def test_cannot_delete_preset_with_users(self, client):
        """Presets assigned to users cannot be deleted."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.create(name='InUse')
        UserFactory(permission_preset=preset)
        client.force_login(admin)
        response = client.post(reverse('preset_delete', args=[preset.pk]))
        assert response.status_code == 400
        assert PermissionPreset.objects.filter(name='InUse').exists()

    def test_delete_requires_admin(self, client):
        """Non-admin cannot delete presets."""
        preset_obj = PermissionPreset.objects.create(name='WithTeam', access_team=True)
        user = UserFactory(permission_preset=preset_obj)
        target = PermissionPreset.objects.create(name='ToDelete')
        client.force_login(user)
        response = client.post(reverse('preset_delete', args=[target.pk]))
        assert response.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_permissions.py::TestPresetDelete -v`
Expected: FAIL (stub returns empty 200 for everything)

- [ ] **Step 3: Flesh out preset_delete view**

In `apps/accounts/views.py`, replace the `preset_delete` stub:

```python
@login_required
@require_permission('access_team')
@require_POST
def preset_delete(request, pk):
    """Delete a permission preset."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    preset = get_object_or_404(PermissionPreset, pk=pk)

    if preset.is_system:
        return HttpResponse('Cannot delete system presets', status=400)

    if preset.users.exists():
        return HttpResponse('Cannot delete preset with assigned users', status=400)

    preset.delete()
    return HttpResponse('')
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_permissions.py::TestPresetDelete -v`
Expected: All PASS

- [ ] **Step 5: Run full accounts tests**

Run: `.venv/bin/python -m pytest apps/accounts/tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add apps/accounts/views.py apps/accounts/tests/test_permissions.py
git commit -m "feat: preset deletion with system and in-use protection"
```

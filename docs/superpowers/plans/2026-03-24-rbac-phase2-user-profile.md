# RBAC Phase 2: User Profile Page with Preset Assignment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a user profile detail page accessible from the Team list, where admins can view user info and assign a permission preset via a drawer.

**Architecture:** Add a "Preset" column to the Team table showing the assigned preset (or "No preset"). Each user row gets a clickable preset badge that opens a drawer with a dropdown to assign/change the preset. A new `user_detail` view serves the drawer. The existing `user_row.html` partial is updated to show the preset and link to the drawer. An `update_preset` POST endpoint handles the assignment.

**Tech Stack:** Django 5.x, HTMX, Tailwind CSS, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `apps/accounts/urls.py` | Add user detail drawer and preset update routes |
| Modify | `apps/accounts/views.py` | Add `user_detail_drawer` and `update_preset` views |
| Create | `templates/accounts/partials/user_detail_drawer.html` | User profile drawer with info + preset selector |
| Modify | `templates/accounts/partials/user_row.html` | Add Preset column, make row clickable for drawer |
| Modify | `templates/accounts/team_list.html` | Add Preset column header |
| Test | `apps/accounts/tests/test_permissions.py` | Tests for new views and preset assignment |

---

### Task 1: Add Preset column to Team table and user row

**Files:**
- Modify: `templates/accounts/team_list.html`
- Modify: `templates/accounts/partials/user_row.html`
- Test: `apps/accounts/tests/test_permissions.py`

- [ ] **Step 1: Write the failing test**

Add to `apps/accounts/tests/test_permissions.py`:

```python
@pytest.mark.django_db
class TestTeamPresetDisplay:
    def test_team_list_shows_preset_column(self, client):
        """Team list should show a Preset column header."""
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert 'Preset' in response.content.decode()

    def test_team_list_shows_user_preset_name(self, client):
        """Team list should show the assigned preset name for each user."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Developer')
        dev = UserFactory(name='Dev User', permission_preset=preset)
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        content = response.content.decode()
        assert 'Developer' in content

    def test_team_list_shows_no_preset_label(self, client):
        """Users without a preset should show 'No preset' label."""
        admin = AdminUserFactory()
        member = UserFactory(name='New User', permission_preset=None)
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert 'No preset' in response.content.decode()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_permissions.py::TestTeamPresetDisplay -v`
Expected: FAIL

- [ ] **Step 3: Add Preset column header to team_list.html**

In `templates/accounts/team_list.html`, add a Preset column header after Role (line 31):

```html
<th class="px-4 py-3 font-medium">Role</th>
<th class="px-4 py-3 font-medium">Preset</th>
<th class="px-4 py-3 font-medium w-10">Actions</th>
```

- [ ] **Step 4: Add Preset column to user_row.html**

Replace `templates/accounts/partials/user_row.html` with:

```html
<tr id="user-{{ user.pk }}" class="hover:bg-elevated/50 transition-colors">
    <td class="px-4 py-3">
        <span class="font-medium text-sm text-zinc-100">{{ user.name }}</span>
    </td>
    <td class="px-4 py-3">
        <span class="text-sm text-zinc-400">{{ user.email }}</span>
    </td>
    <td class="px-4 py-3">
        <span class="px-2 py-0.5 text-xs rounded-full border {% if user.role == 'admin' %}bg-accent/15 text-accent border-accent/30{% else %}bg-elevated text-zinc-300 border-border-subtle{% endif %}">
            {{ user.get_role_display }}
        </span>
    </td>
    <td class="px-4 py-3">
        {% if user.permission_preset %}
        <span class="px-2 py-0.5 text-xs rounded-full border bg-elevated text-zinc-300 border-border-subtle">
            {{ user.permission_preset.name }}
        </span>
        {% else %}
        <span class="text-xs text-zinc-600">No preset</span>
        {% endif %}
    </td>
    <td class="px-4 py-3">
        <div class="flex items-center justify-end gap-1">
            {% if user != request.user %}
            <button hx-get="{% url 'user_detail_drawer' user.pk %}"
                    hx-target="#slide-over"
                    hx-swap="innerHTML"
                    hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                    class="p-1.5 text-zinc-500 hover:text-zinc-200 hover:bg-elevated rounded transition-colors"
                    title="Edit user">
                <i data-lucide="pencil" class="w-4 h-4"></i>
            </button>
            {% endif %}
        </div>
    </td>
</tr>
```

Note: This replaces the old toggle_role button with a pencil icon that opens the user detail drawer. The role toggle will move into the drawer.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_permissions.py::TestTeamPresetDisplay -v`
Expected: All PASS (the URL `user_detail_drawer` doesn't exist yet but the template won't error since the page renders without clicking)

Actually — the `{% url 'user_detail_drawer' user.pk %}` tag WILL cause a `NoReverseMatch` error when rendering the page. We need to add a dummy URL first, OR we can add the URL and a stub view together. Let's add them in this task to keep the template rendering clean.

- [ ] **Step 5b: Add URL and stub view**

In `apps/accounts/urls.py`, add:

```python
path('team/<int:pk>/detail/', views.user_detail_drawer, name='user_detail_drawer'),
```

In `apps/accounts/views.py`, add a stub view:

```python
@login_required
@require_permission('access_team')
def user_detail_drawer(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    return render(request, 'accounts/partials/user_detail_drawer.html', {'user_obj': user_obj})
```

Create a minimal `templates/accounts/partials/user_detail_drawer.html`:

```html
<div class="p-4">
    <p class="text-sm text-zinc-300">{{ user_obj.name }}</p>
</div>
```

Note: We use `user_obj` as the context variable (not `user`) to avoid clashing with the template context `user` which is the logged-in user.

Also update the `team_list` view's queryset to avoid N+1 queries. In `apps/accounts/views.py`, change:

```python
users_qs = User.objects.all().order_by('name')
```
to:
```python
users_qs = User.objects.select_related('permission_preset').order_by('name')
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_permissions.py::TestTeamPresetDisplay apps/accounts/tests/test_views.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add templates/accounts/team_list.html templates/accounts/partials/user_row.html templates/accounts/partials/user_detail_drawer.html apps/accounts/views.py apps/accounts/urls.py apps/accounts/tests/test_permissions.py
git commit -m "feat: add Preset column to team list and stub user detail drawer"
```

---

### Task 2: Build user detail drawer with preset assignment

**Files:**
- Modify: `apps/accounts/views.py` (flesh out `user_detail_drawer`, add `update_preset`)
- Modify: `apps/accounts/urls.py` (add `update_preset` route)
- Modify: `templates/accounts/partials/user_detail_drawer.html` (full drawer UI)
- Test: `apps/accounts/tests/test_permissions.py`

- [ ] **Step 1: Write the failing tests**

Add to `apps/accounts/tests/test_permissions.py`:

```python
@pytest.mark.django_db
class TestUserDetailDrawer:
    def test_drawer_requires_team_permission(self, client):
        """Non-admin without team access should get 403."""
        preset = PermissionPreset.objects.get(name='Developer')
        user = UserFactory(permission_preset=preset)
        target = UserFactory()
        client.force_login(user)
        response = client.get(reverse('user_detail_drawer', args=[target.pk]))
        assert response.status_code == 403

    def test_drawer_requires_admin_role(self, client):
        """Non-admin user with access_team permission should still get 403."""
        preset = PermissionPreset.objects.create(name='TeamViewer', access_team=True)
        user = UserFactory(permission_preset=preset)
        target = UserFactory()
        client.force_login(user)
        response = client.get(reverse('user_detail_drawer', args=[target.pk]))
        assert response.status_code == 403

    def test_drawer_shows_user_info(self, client):
        """Drawer should display user name, email, role, and current preset."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Developer')
        target = UserFactory(name='John Doe', email='john@test.com', permission_preset=preset)
        client.force_login(admin)
        response = client.get(reverse('user_detail_drawer', args=[target.pk]))
        content = response.content.decode()
        assert 'John Doe' in content
        assert 'john@test.com' in content
        assert response.status_code == 200

    def test_drawer_lists_all_presets(self, client):
        """Drawer should list all available presets in a dropdown."""
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.get(reverse('user_detail_drawer', args=[target.pk]))
        content = response.content.decode()
        assert 'Admin' in content
        assert 'Developer' in content


@pytest.mark.django_db
class TestUpdatePreset:
    def test_assign_preset_to_user(self, client):
        """Admin can assign a preset to a user."""
        admin = AdminUserFactory()
        target = UserFactory(permission_preset=None)
        preset = PermissionPreset.objects.get(name='Developer')
        client.force_login(admin)
        response = client.post(
            reverse('update_preset', args=[target.pk]),
            {'preset_id': preset.pk},
        )
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.permission_preset == preset

    def test_clear_preset_from_user(self, client):
        """Admin can clear a user's preset by sending empty preset_id."""
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.get(name='Developer')
        target = UserFactory(permission_preset=preset)
        client.force_login(admin)
        response = client.post(
            reverse('update_preset', args=[target.pk]),
            {'preset_id': ''},
        )
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.permission_preset is None

    def test_update_preset_requires_admin(self, client):
        """Only admins can update presets (team permission alone is not enough)."""
        preset = PermissionPreset.objects.create(name='WithTeam', access_team=True)
        user = UserFactory(permission_preset=preset)
        target = UserFactory()
        dev_preset = PermissionPreset.objects.get(name='Developer')
        client.force_login(user)
        response = client.post(
            reverse('update_preset', args=[target.pk]),
            {'preset_id': dev_preset.pk},
        )
        assert response.status_code == 403

    def test_update_preset_returns_updated_row(self, client):
        """After updating preset, response should contain the new preset name."""
        admin = AdminUserFactory()
        target = UserFactory(permission_preset=None)
        preset = PermissionPreset.objects.get(name='Developer')
        client.force_login(admin)
        response = client.post(
            reverse('update_preset', args=[target.pk]),
            {'preset_id': preset.pk},
        )
        assert 'Developer' in response.content.decode()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_permissions.py::TestUserDetailDrawer apps/accounts/tests/test_permissions.py::TestUpdatePreset -v`
Expected: FAIL

- [ ] **Step 3: Add URL route for update_preset**

In `apps/accounts/urls.py`, add:

```python
path('team/<int:pk>/update-preset/', views.update_preset, name='update_preset'),
```

Full file should be:

```python
from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('team/', views.team_list, name='team_list'),
    path('team/<int:pk>/toggle-role/', views.toggle_role, name='toggle_role'),
    path('team/<int:pk>/detail/', views.user_detail_drawer, name='user_detail_drawer'),
    path('team/<int:pk>/update-preset/', views.update_preset, name='update_preset'),
]
```

- [ ] **Step 4: Flesh out user_detail_drawer view and add update_preset view**

In `apps/accounts/views.py`, add the import at the top of the file (alongside existing imports):

```python
from .permissions import PermissionPreset
```

Then update the `user_detail_drawer` view and add `update_preset`:

```python
@login_required
@require_permission('access_team')
def user_detail_drawer(request, pk):
    """User detail drawer with preset assignment."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    user_obj = get_object_or_404(User, pk=pk)
    presets = PermissionPreset.objects.all()
    return render(request, 'accounts/partials/user_detail_drawer.html', {
        'user_obj': user_obj,
        'presets': presets,
    })


@login_required
@require_permission('access_team')
@require_POST
def update_preset(request, pk):
    """Update a user's permission preset."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    user_obj = get_object_or_404(User, pk=pk)
    preset_id = request.POST.get('preset_id', '').strip()
    if preset_id:
        preset = get_object_or_404(PermissionPreset, pk=preset_id)
        user_obj.permission_preset = preset
    else:
        user_obj.permission_preset = None
    user_obj.save()
    return render(request, 'accounts/partials/user_row.html', {'user': user_obj})
```

- [ ] **Step 5: Build the full drawer template**

Replace `templates/accounts/partials/user_detail_drawer.html` with:

```html
<div class="flex flex-col h-full">
    <!-- Drawer header -->
    <div class="flex-shrink-0 px-4 py-3 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <i data-lucide="user" class="w-4 h-4 text-zinc-500"></i>
                <h2 class="text-sm font-medium text-zinc-100">{{ user_obj.name }}</h2>
            </div>
            <button onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors">
                <i data-lucide="x" class="w-4 h-4"></i>
            </button>
        </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-4">
        <!-- User Info -->
        <div class="space-y-4 mb-6">
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Email</label>
                <div class="text-sm text-zinc-300">{{ user_obj.email }}</div>
            </div>
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Role</label>
                <span class="px-2 py-0.5 text-xs rounded-full border {% if user_obj.role == 'admin' %}bg-accent/15 text-accent border-accent/30{% else %}bg-elevated text-zinc-300 border-border-subtle{% endif %}">
                    {{ user_obj.get_role_display }}
                </span>
            </div>
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Member Since</label>
                <div class="text-sm text-zinc-300">{{ user_obj.created_at|date:"M d, Y" }}</div>
            </div>
        </div>

        <!-- Preset Assignment -->
        <div class="pt-4 border-t border-border-subtle">
            <h3 class="text-xs uppercase tracking-wide text-zinc-500 mb-3">Permission Preset</h3>
            <form hx-post="{% url 'update_preset' user_obj.pk %}"
                  hx-target="#user-{{ user_obj.pk }}"
                  hx-swap="outerHTML"
                  hx-on::after-request="document.getElementById('slide-over').classList.add('hidden');">
                {% csrf_token %}
                <select name="preset_id"
                        class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none mb-3">
                    <option value="" {% if not user_obj.permission_preset %}selected{% endif %}>No preset</option>
                    {% for preset in presets %}
                    <option value="{{ preset.pk }}" {% if user_obj.permission_preset_id == preset.pk %}selected{% endif %}>
                        {{ preset.name }}{% if preset.description %} — {{ preset.description }}{% endif %}
                    </option>
                    {% endfor %}
                </select>
                {% if user_obj.permission_preset %}
                <div class="mb-3 p-3 bg-elevated/50 rounded-card border border-border-subtle">
                    <div class="text-xs uppercase tracking-wide text-zinc-500 mb-2">Current Access</div>
                    <div class="flex flex-wrap gap-1.5">
                        {% if user_obj.permission_preset.access_dashboard %}
                        <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Dashboard</span>
                        {% endif %}
                        {% if user_obj.permission_preset.access_clients %}
                        <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Clients</span>
                        {% endif %}
                        {% if user_obj.permission_preset.access_projects %}
                        <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Projects</span>
                        {% endif %}
                        {% if user_obj.permission_preset.access_tasks %}
                        <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Tasks</span>
                        {% endif %}
                        {% if user_obj.permission_preset.access_todos %}
                        <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Todos</span>
                        {% endif %}
                        {% if user_obj.permission_preset.access_notes %}
                        <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Notes</span>
                        {% endif %}
                        {% if user_obj.permission_preset.access_salaries %}
                        <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Salaries</span>
                        {% endif %}
                        {% if user_obj.permission_preset.access_team %}
                        <span class="px-2 py-0.5 text-[10px] rounded bg-green-500/10 text-green-400 border border-green-500/20">Team</span>
                        {% endif %}
                    </div>
                </div>
                {% endif %}
                <button type="submit"
                        class="w-full bg-accent text-white px-4 py-2 rounded-card text-sm font-medium hover:bg-accent-hover transition-colors">
                    Save Preset
                </button>
            </form>
        </div>
    </div>

    <!-- Footer: Role toggle -->
    {% if user_obj != request.user %}
    <div class="flex-shrink-0 px-4 py-3 border-t border-border-subtle bg-panel/50">
        <button hx-post="{% url 'toggle_role' user_obj.pk %}"
                hx-target="#user-{{ user_obj.pk }}"
                hx-swap="outerHTML"
                hx-on::after-request="document.getElementById('slide-over').classList.add('hidden');"
                class="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-card text-sm transition-colors
                       {% if user_obj.role == 'admin' %}text-zinc-400 hover:bg-elevated{% else %}text-accent hover:bg-accent/10{% endif %}">
            <i data-lucide="{% if user_obj.role == 'admin' %}user-minus{% else %}user-plus{% endif %}" class="w-4 h-4"></i>
            Make {% if user_obj.role == 'admin' %}Member{% else %}Admin{% endif %}
        </button>
    </div>
    {% endif %}
</div>

<script>
if (typeof lucide !== 'undefined') {
    lucide.createIcons();
}
</script>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest apps/accounts/tests/test_permissions.py::TestUserDetailDrawer apps/accounts/tests/test_permissions.py::TestUpdatePreset -v`
Expected: All PASS

- [ ] **Step 7: Run full accounts test suite**

Run: `.venv/bin/python -m pytest apps/accounts/tests/ -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add apps/accounts/views.py apps/accounts/urls.py templates/accounts/partials/user_detail_drawer.html apps/accounts/tests/test_permissions.py
git commit -m "feat: user detail drawer with preset assignment and access preview"
```

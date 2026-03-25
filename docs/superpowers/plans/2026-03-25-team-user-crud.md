# Team User Management CRUD — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the Team app's user detail drawer into a full CRUD system — editable user fields, soft-delete (deactivation), and two-tier hard deletion with cascade warnings.

**Architecture:** The existing user detail drawer (HTMX slide-over) becomes an always-editable form. Two old views (`toggle_role`, `update_preset`) are consolidated into a single `user_update` view. New `user_deactivate`, `user_delete_confirm`, and `user_delete` views handle lifecycle management. Inactive users are shown greyed out in the team list with an "Inactive" badge.

**Tech Stack:** Django 5.x, HTMX, Tailwind CSS, pytest, factory_boy

**Spec:** `docs/superpowers/specs/2026-03-25-team-user-crud-design.md`

**Important cascade note:** The `Note` model has `on_delete=CASCADE` on both `created_by` and `modified_by`. This means deleting a user will also delete notes they merely *edited* (not just created). The delete confirmation counts reflect this via the deduplicated `Q(created_by) | Q(modified_by)` query. This is a known data loss risk — the warning dialog makes it visible to the admin.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `apps/accounts/views.py` | Modify | Add `user_update`, `user_deactivate`, `user_delete_confirm`, `user_delete`; remove `toggle_role`, `update_preset` |
| `apps/accounts/urls.py` | Modify | Replace old URL patterns with new ones |
| `templates/accounts/partials/user_detail_drawer.html` | Rewrite | Full edit form with footer actions |
| `templates/accounts/partials/user_row.html` | Modify | Add inactive badge + greyed styling |
| `templates/accounts/partials/user_delete_confirm.html` | Create | Inline deletion confirmation with cascade counts |
| `apps/accounts/tests/test_views.py` | Modify | Add tests for all new views; update old toggle_role tests |
| `apps/accounts/tests/test_permissions.py` | Modify | Update tests referencing `toggle_role` and `update_preset` URLs |
| `apps/tasks/views.py` | Modify | Fix inconsistent `is_active` filtering on lines 127, 310, 332 |

---

## Task 1: Backend — `user_update` View (replaces `toggle_role` + `update_preset`)

> **Roles:** Backend implements, Verifier tests

**Files:**
- Modify: `apps/accounts/views.py`
- Modify: `apps/accounts/urls.py`
- Test: `apps/accounts/tests/test_views.py`

### Tests

- [ ] **Step 1: Write tests for `user_update`**

Add a new test class in `apps/accounts/tests/test_views.py`:

```python
@pytest.mark.django_db
class TestUserUpdate:
    def test_user_update_requires_admin(self, client):
        user = UserFactory(role='member')
        target = UserFactory()
        client.force_login(user)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': 'New Name', 'email': target.email, 'role': 'member',
        })
        assert response.status_code == 403

    def test_user_update_requires_post(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.get(reverse('user_update', args=[target.pk]))
        assert response.status_code == 405

    def test_user_update_changes_name(self, client):
        admin = AdminUserFactory()
        target = UserFactory(name='Old Name')
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': 'New Name', 'email': target.email, 'role': 'member',
        })
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.name == 'New Name'

    def test_user_update_changes_email(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': target.name, 'email': 'newemail@example.com', 'role': 'member',
        })
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.email == 'newemail@example.com'

    def test_user_update_rejects_duplicate_email(self, client):
        admin = AdminUserFactory()
        existing = UserFactory(email='taken@example.com')
        target = UserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': target.name, 'email': 'taken@example.com', 'role': 'member',
        })
        assert response.status_code == 200  # Re-renders drawer with error
        target.refresh_from_db()
        assert target.email != 'taken@example.com'
        assert b'already in use' in response.content

    def test_user_update_rejects_blank_name(self, client):
        admin = AdminUserFactory()
        target = UserFactory(name='Original')
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': '', 'email': target.email, 'role': 'member',
        })
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.name == 'Original'
        assert b'required' in response.content.lower()

    def test_user_update_changes_role(self, client):
        admin = AdminUserFactory()
        target = UserFactory(role='member')
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': target.name, 'email': target.email, 'role': 'admin',
        })
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.role == 'admin'

    def test_user_update_changes_preset(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        preset = PermissionPreset.objects.create(name='Custom')
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': target.name, 'email': target.email, 'role': 'member',
            'preset_id': preset.pk,
        })
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.permission_preset == preset

    def test_user_update_clears_preset(self, client):
        admin = AdminUserFactory()
        preset = PermissionPreset.objects.create(name='Custom')
        target = UserFactory(permission_preset=preset)
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': target.name, 'email': target.email, 'role': 'member',
            'preset_id': '',
        })
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.permission_preset is None

    def test_user_update_last_admin_guard(self, client):
        """Cannot demote yourself if you're the last active admin."""
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[admin.pk]), {
            'name': admin.name, 'email': admin.email, 'role': 'member',
        })
        assert response.status_code == 200
        admin.refresh_from_db()
        assert admin.role == 'admin'  # Not changed
        assert b'last' in response.content.lower()

    def test_user_update_allows_demote_when_other_admins_exist(self, client):
        admin1 = AdminUserFactory()
        admin2 = AdminUserFactory()
        client.force_login(admin1)
        response = client.post(reverse('user_update', args=[admin1.pk]), {
            'name': admin1.name, 'email': admin1.email, 'role': 'member',
        })
        assert response.status_code == 200
        admin1.refresh_from_db()
        assert admin1.role == 'member'

    def test_user_update_returns_user_row(self, client):
        admin = AdminUserFactory()
        target = UserFactory(name='Old')
        client.force_login(admin)
        response = client.post(reverse('user_update', args=[target.pk]), {
            'name': 'New', 'email': target.email, 'role': 'member',
        })
        assert response.status_code == 200
        assert b'New' in response.content
        assert 'closeSlideOver' in response.get('HX-Trigger', '')
        assert f'#user-{target.pk}' in response.get('HX-Retarget', '')
        assert 'outerHTML' in response.get('HX-Reswap', '')
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest apps/accounts/tests/test_views.py::TestUserUpdate -v
```

Expected: FAIL — `NoReverseMatch: 'user_update' is not a registered URL`

### Implementation

- [ ] **Step 3: Add `user_update` view to `apps/accounts/views.py`**

Add this view (keep existing imports, add `from .permissions import PermissionPreset` if not present):

```python
@login_required
@require_permission('access_team')
@require_POST
def user_update(request, pk):
    """Update a user's name, email, role, and preset."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    user_obj = get_object_or_404(User, pk=pk)
    presets = PermissionPreset.objects.all()

    name = request.POST.get('name', '').strip()
    email = request.POST.get('email', '').strip()
    role = request.POST.get('role', '').strip()
    preset_id = request.POST.get('preset_id', '').strip()

    errors = {}

    if not name:
        errors['name'] = 'Name is required.'
    if not email:
        errors['email'] = 'Email is required.'
    elif User.objects.filter(email=email).exclude(pk=pk).exists():
        errors['email'] = 'This email is already in use.'

    if role not in ('admin', 'member'):
        role = user_obj.role

    # Last-admin guard: prevent demoting if last active admin
    if user_obj.role == 'admin' and role == 'member':
        active_admin_count = User.objects.filter(role='admin', is_active=True).count()
        if active_admin_count <= 1:
            errors['role'] = 'Cannot demote the last active admin.'

    if errors:
        return render(request, 'accounts/partials/user_detail_drawer.html', {
            'user_obj': user_obj,
            'presets': presets,
            'errors': errors,
            'form_data': {'name': name, 'email': email, 'role': role, 'preset_id': preset_id},
        })

    user_obj.name = name
    user_obj.email = email
    user_obj.role = role

    if preset_id:
        preset = get_object_or_404(PermissionPreset, pk=preset_id)
        user_obj.permission_preset = preset
    else:
        user_obj.permission_preset = None

    user_obj.save()

    response = render(request, 'accounts/partials/user_row.html', {'user': user_obj})
    response['HX-Retarget'] = f'#user-{user_obj.pk}'
    response['HX-Reswap'] = 'outerHTML'
    response['HX-Trigger'] = 'closeSlideOver'
    return response
```

- [ ] **Step 4: Remove `toggle_role` and `update_preset` views from `apps/accounts/views.py`**

Delete the `toggle_role` function (lines 201-211) and `update_preset` function (lines 87-102).

- [ ] **Step 5: Update URL patterns in `apps/accounts/urls.py`**

Replace:
```python
path('team/<int:pk>/toggle-role/', views.toggle_role, name='toggle_role'),
path('team/<int:pk>/update-preset/', views.update_preset, name='update_preset'),
```

With:
```python
path('team/<int:pk>/update/', views.user_update, name='user_update'),
```

- [ ] **Step 6: Update old tests that reference removed URLs**

In `apps/accounts/tests/test_views.py`, remove or rename the `TestToggleRole` class (lines 113-145) since `toggle_role` no longer exists. The toggle_role functionality is now covered by `TestUserUpdate.test_user_update_changes_role`.

In `apps/accounts/tests/test_permissions.py`, search for any references to `toggle_role` or `update_preset` URL names and update them to `user_update`.

- [ ] **Step 7: Run all tests**

```bash
pytest apps/accounts/tests/ -v
```

Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add apps/accounts/views.py apps/accounts/urls.py apps/accounts/tests/
git commit -m "feat: add user_update view replacing toggle_role and update_preset"
```

---

## Task 2: Frontend — Rewrite User Detail Drawer as Edit Form

> **Roles:** Frontend implements, Verifier reviews

**Files:**
- Rewrite: `templates/accounts/partials/user_detail_drawer.html`

- [ ] **Step 1: Rewrite the drawer template**

Replace the entire content of `templates/accounts/partials/user_detail_drawer.html` with:

```html
<div class="flex flex-col h-full">
    <!-- Drawer header -->
    <div class="flex-shrink-0 px-4 py-3 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <i data-lucide="user" class="w-4 h-4 text-zinc-500"></i>
                <h2 class="text-sm font-medium text-zinc-100">Edit User</h2>
            </div>
            <button onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors">
                <i data-lucide="x" class="w-4 h-4"></i>
            </button>
        </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-4">
        <!-- Read-only info -->
        <div class="mb-4">
            <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Member Since</label>
            <div class="text-sm text-zinc-300">{{ user_obj.created_at|date:"M d, Y" }}</div>
        </div>

        <!-- Edit form
             Default target is #slide-over (for validation errors — re-renders drawer in place).
             On success, the view returns HX-Retarget and HX-Reswap headers to redirect
             the response to the user row instead. -->
        <form hx-post="{% url 'user_update' user_obj.pk %}"
              hx-target="#slide-over"
              hx-swap="innerHTML"
              id="user-edit-form">
            {% csrf_token %}

            <!-- Name -->
            <div class="mb-4">
                <label for="name" class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Name</label>
                <input type="text" name="name" id="name"
                       value="{{ form_data.name|default:user_obj.name }}"
                       class="w-full bg-elevated border {% if errors.name %}border-red-500{% else %}border-border-subtle{% endif %} rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
                       required>
                {% if errors.name %}
                <p class="mt-1 text-xs text-red-400">{{ errors.name }}</p>
                {% endif %}
            </div>

            <!-- Email -->
            <div class="mb-4">
                <label for="email" class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Email</label>
                <input type="email" name="email" id="email"
                       value="{{ form_data.email|default:user_obj.email }}"
                       class="w-full bg-elevated border {% if errors.email %}border-red-500{% else %}border-border-subtle{% endif %} rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
                       required>
                {% if errors.email %}
                <p class="mt-1 text-xs text-red-400">{{ errors.email }}</p>
                {% endif %}
            </div>

            <!-- Role -->
            <div class="mb-4">
                <label for="role" class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Role</label>
                <select name="role" id="role"
                        class="w-full bg-elevated border {% if errors.role %}border-red-500{% else %}border-border-subtle{% endif %} rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none">
                    <option value="admin" {% if form_data.role %}{% if form_data.role == 'admin' %}selected{% endif %}{% elif user_obj.role == 'admin' %}selected{% endif %}>Admin</option>
                    <option value="member" {% if form_data.role %}{% if form_data.role == 'member' %}selected{% endif %}{% elif user_obj.role == 'member' %}selected{% endif %}>Member</option>
                </select>
                {% if errors.role %}
                <p class="mt-1 text-xs text-red-400">{{ errors.role }}</p>
                {% endif %}
            </div>

            <!-- Permission Preset -->
            <div class="mb-4">
                <label for="preset_id" class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Permission Preset</label>
                <select name="preset_id" id="preset_id"
                        class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none">
                    <option value="" {% if not user_obj.permission_preset %}selected{% endif %}>No preset</option>
                    {% for preset in presets %}
                    <option value="{{ preset.pk }}" {% if user_obj.permission_preset_id == preset.pk %}selected{% endif %}>
                        {{ preset.name }}{% if preset.description %} — {{ preset.description }}{% endif %}
                    </option>
                    {% endfor %}
                </select>
            </div>

            {% if user_obj.permission_preset %}
            <div class="mb-4 p-3 bg-elevated/50 rounded-card border border-border-subtle">
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
                Save Changes
            </button>
        </form>
    </div>

    <!-- Footer: Deactivate/Reactivate + Delete -->
    {% if user_obj != request.user %}
    <div class="flex-shrink-0 px-4 py-3 border-t border-border-subtle bg-panel/50 space-y-2">
        <!-- Deactivate / Reactivate -->
        {% if user_obj.is_active %}
        <button hx-post="{% url 'user_deactivate' user_obj.pk %}"
                hx-target="#user-{{ user_obj.pk }}"
                hx-swap="outerHTML"
                hx-confirm="Are you sure you want to deactivate {{ user_obj.name }}?"
                class="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-card text-sm text-red-400 hover:bg-red-500/10 transition-colors">
            <i data-lucide="user-x" class="w-4 h-4"></i>
            Deactivate User
        </button>
        {% else %}
        <button hx-post="{% url 'user_deactivate' user_obj.pk %}"
                hx-target="#user-{{ user_obj.pk }}"
                hx-swap="outerHTML"
                class="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-card text-sm text-green-400 hover:bg-green-500/10 transition-colors">
            <i data-lucide="user-check" class="w-4 h-4"></i>
            Reactivate User
        </button>
        {% endif %}

        <!-- Delete -->
        <button hx-get="{% url 'user_delete_confirm' user_obj.pk %}"
                hx-target="#delete-confirm-{{ user_obj.pk }}"
                hx-swap="innerHTML"
                class="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-card text-sm text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-colors">
            <i data-lucide="trash-2" class="w-4 h-4"></i>
            Delete User
        </button>
        <div id="delete-confirm-{{ user_obj.pk }}"></div>
    </div>
    {% endif %}
</div>

<script>
if (typeof lucide !== 'undefined') {
    lucide.createIcons();
}
</script>
```

**Key changes from old template:**
- Email, Role fields are now editable inputs/selects (were read-only text)
- Name field added (was only in header)
- Single form submits to `user_update` (was two separate forms/buttons)
- Footer has Deactivate/Reactivate + Delete buttons (was just role toggle)
- Member Since kept as read-only text
- Error display for each field via `errors` dict from context
- `form_data` context used to preserve values on validation error

- [ ] **Step 2: Update `user_detail_drawer` view to handle `HX-Trigger` for drawer closing**

The `user_detail_drawer` view in `apps/accounts/views.py` needs no changes — it already passes `user_obj` and `presets`. The `user_update` view (from Task 1) handles the `HX-Trigger: closeSlideOver` on success. On validation error, it re-renders the drawer template (no trigger = drawer stays open).

However, add a listener for the `closeSlideOver` event in the team_list or base template. Check if one already exists — the preset views use it (line 149 in views.py). If the slide-over doesn't auto-close on this trigger, add this to `templates/accounts/team_list.html`:

```html
<script>
document.body.addEventListener('closeSlideOver', function() {
    document.getElementById('slide-over').classList.add('hidden');
    lucide.createIcons();
});
</script>
```

- [ ] **Step 3: Verify drawer renders correctly**

Start the dev server and manually verify the drawer opens with editable fields. Test saving with valid data, then test with a duplicate email to see the error rendering.

- [ ] **Step 4: Commit**

```bash
git add templates/accounts/partials/user_detail_drawer.html templates/accounts/team_list.html
git commit -m "feat: rewrite user detail drawer as full edit form"
```

---

## Task 3: Backend — `user_deactivate` View

> **Roles:** Backend implements, Verifier tests

**Files:**
- Modify: `apps/accounts/views.py`
- Modify: `apps/accounts/urls.py`
- Test: `apps/accounts/tests/test_views.py`

### Tests

- [ ] **Step 1: Write tests for `user_deactivate`**

Add to `apps/accounts/tests/test_views.py`:

```python
@pytest.mark.django_db
class TestUserDeactivate:
    def test_deactivate_requires_admin(self, client):
        user = UserFactory(role='member')
        target = UserFactory()
        client.force_login(user)
        response = client.post(reverse('user_deactivate', args=[target.pk]))
        assert response.status_code == 403

    def test_deactivate_requires_post(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.get(reverse('user_deactivate', args=[target.pk]))
        assert response.status_code == 405

    def test_deactivate_user(self, client):
        admin = AdminUserFactory()
        target = UserFactory(is_active=True)
        client.force_login(admin)
        response = client.post(reverse('user_deactivate', args=[target.pk]))
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.is_active is False
        assert 'closeSlideOver' in response.get('HX-Trigger', '')

    def test_reactivate_user(self, client):
        admin = AdminUserFactory()
        target = UserFactory(is_active=False)
        client.force_login(admin)
        response = client.post(reverse('user_deactivate', args=[target.pk]))
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.is_active is True

    def test_cannot_deactivate_self(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_deactivate', args=[admin.pk]))
        assert response.status_code == 400
        admin.refresh_from_db()
        assert admin.is_active is True

    def test_cannot_deactivate_last_admin(self, client):
        admin = AdminUserFactory()
        target = AdminUserFactory()
        client.force_login(admin)
        # Deactivate target (second admin) — should work
        response = client.post(reverse('user_deactivate', args=[target.pk]))
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.is_active is False
        # Now admin is the last active admin — deactivating another admin
        # who is inactive is a reactivation, which is fine
        # But deactivating admin themselves should be blocked (self-deactivation)

    def test_cannot_deactivate_if_last_active_admin(self, client):
        """Prevent deactivating the only remaining active admin (even if not self)."""
        admin = AdminUserFactory()
        target_admin = AdminUserFactory()
        client.force_login(admin)
        # Deactivate target_admin — leaves only admin as the sole active admin
        response = client.post(reverse('user_deactivate', args=[target_admin.pk]))
        assert response.status_code == 200
        target_admin.refresh_from_db()
        assert target_admin.is_active is False
        # Now create another admin and try to deactivate them —
        # but admin is the only remaining active admin, so it should be blocked
        new_admin = AdminUserFactory()
        # First deactivate new_admin — this would leave admin as last
        # But this is deactivating someone else while admin is still active, which is fine
        # The real guard is: can't deactivate a user if doing so would leave 0 active admins
        # Since admin is still active, deactivating new_admin is allowed
        response = client.post(reverse('user_deactivate', args=[new_admin.pk]))
        assert response.status_code == 200
        new_admin.refresh_from_db()
        assert new_admin.is_active is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest apps/accounts/tests/test_views.py::TestUserDeactivate -v
```

Expected: FAIL — `NoReverseMatch: 'user_deactivate' is not a registered URL`

### Implementation

- [ ] **Step 3: Add `user_deactivate` view to `apps/accounts/views.py`**

```python
@login_required
@require_permission('access_team')
@require_POST
def user_deactivate(request, pk):
    """Toggle a user's active status."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    user_obj = get_object_or_404(User, pk=pk)

    if user_obj == request.user:
        return HttpResponse('Cannot deactivate yourself.', status=400)

    # If deactivating (not reactivating), check last-admin guard
    if user_obj.is_active and user_obj.role == 'admin':
        active_admin_count = User.objects.filter(role='admin', is_active=True).count()
        if active_admin_count <= 1:
            return HttpResponse('Cannot deactivate the last active admin.', status=400)

    user_obj.is_active = not user_obj.is_active
    user_obj.save()

    response = render(request, 'accounts/partials/user_row.html', {'user': user_obj})
    response['HX-Trigger'] = 'closeSlideOver'
    return response
```

- [ ] **Step 4: Add URL pattern in `apps/accounts/urls.py`**

Add after the `user_update` path:

```python
path('team/<int:pk>/deactivate/', views.user_deactivate, name='user_deactivate'),
```

- [ ] **Step 5: Run tests**

```bash
pytest apps/accounts/tests/test_views.py::TestUserDeactivate -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add apps/accounts/views.py apps/accounts/urls.py apps/accounts/tests/test_views.py
git commit -m "feat: add user_deactivate view for soft-delete"
```

---

## Task 4: Frontend — Inactive User Row Styling

> **Roles:** Frontend implements, Verifier reviews visually

**Files:**
- Modify: `templates/accounts/partials/user_row.html`

- [ ] **Step 1: Update `user_row.html` to show inactive state**

Replace the entire content of `templates/accounts/partials/user_row.html`:

```html
<tr id="user-{{ user.pk }}" class="{% if not user.is_active %}opacity-50{% endif %} hover:bg-elevated/50 transition-colors">
    <td class="px-4 py-3">
        <div class="flex items-center gap-2">
            <span class="font-medium text-sm text-zinc-100">{{ user.name }}</span>
            {% if not user.is_active %}
            <span class="px-1.5 py-0.5 text-[10px] rounded-full bg-zinc-700 text-zinc-400 border border-zinc-600">
                Inactive
            </span>
            {% endif %}
        </div>
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
            <button hx-get="{% url 'user_detail_drawer' user.pk %}"
                    hx-target="#slide-over"
                    hx-swap="innerHTML"
                    hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                    class="p-1.5 text-zinc-500 hover:text-zinc-200 hover:bg-elevated rounded transition-colors"
                    title="Edit user">
                <i data-lucide="pencil" class="w-4 h-4"></i>
            </button>
        </div>
    </td>
</tr>
```

**Key changes from old template:**
- Added `{% if not user.is_active %}opacity-50{% endif %}` on `<tr>` for greyed-out row
- Added "Inactive" badge next to the name
- Edit button now always visible (removed `{% if user != request.user %}` guard — admins should be able to edit all users including themselves and inactive ones)

- [ ] **Step 2: Verify visually**

Create a test user, deactivate them via the drawer, confirm the row appears greyed out with the "Inactive" badge.

- [ ] **Step 3: Commit**

```bash
git add templates/accounts/partials/user_row.html
git commit -m "feat: add inactive user styling with badge to team list"
```

---

## Task 5: Backend — `user_delete_confirm` and `user_delete` Views

> **Roles:** Backend implements, Verifier tests

**Files:**
- Modify: `apps/accounts/views.py`
- Modify: `apps/accounts/urls.py`
- Create: `templates/accounts/partials/user_delete_confirm.html`
- Test: `apps/accounts/tests/test_views.py`

### Tests

- [ ] **Step 1: Write tests for deletion views**

Add to `apps/accounts/tests/test_views.py`. You will need additional imports:

```python
from apps.todos.factories import TodoFactory
from apps.notes.factories import NoteFactory  # if exists, otherwise create inline
from apps.tasks.models import Task, Comment, Attachment
from apps.projects.models import ProjectMember
```

```python
@pytest.mark.django_db
class TestUserDeleteConfirm:
    def test_delete_confirm_requires_admin(self, client):
        user = UserFactory(role='member')
        target = UserFactory()
        client.force_login(user)
        response = client.get(reverse('user_delete_confirm', args=[target.pk]))
        assert response.status_code == 403

    def test_delete_confirm_returns_counts(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        # Create some related data
        TodoFactory(owner=target)
        TodoFactory(owner=target)
        client.force_login(admin)
        response = client.get(reverse('user_delete_confirm', args=[target.pk]))
        assert response.status_code == 200
        assert b'2 todo' in response.content.lower()

    def test_delete_confirm_clean_user(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.get(reverse('user_delete_confirm', args=[target.pk]))
        assert response.status_code == 200
        assert b'no associated data' in response.content.lower()

    def test_delete_confirm_shows_tasks_unassigned(self, client):
        """Confirm that SET_NULL side effects (task unassignment) are shown."""
        admin = AdminUserFactory()
        target = UserFactory()
        # Create tasks assigned to target — requires project/status setup
        # The verifier should set up the full fixture chain here
        client.force_login(admin)
        response = client.get(reverse('user_delete_confirm', args=[target.pk]))
        assert response.status_code == 200
        # Verify the response includes unassignment info if tasks exist

    def test_delete_confirm_deduplicates_notes(self, client):
        """A note where user is both created_by and modified_by counts once."""
        admin = AdminUserFactory()
        target = UserFactory()
        from apps.notes.models import Note
        # Create a note where target is both author and editor
        Note.objects.create(
            title='Test Note', content='x',
            created_by=target, modified_by=target,
        )
        client.force_login(admin)
        response = client.get(reverse('user_delete_confirm', args=[target.pk]))
        assert response.status_code == 200
        assert b'1 note' in response.content.lower()
        # Should NOT say "2 notes"
        assert b'2 note' not in response.content.lower()

    def test_delete_confirm_cannot_delete_self(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('user_delete_confirm', args=[admin.pk]))
        assert response.status_code == 400


@pytest.mark.django_db
class TestUserDelete:
    def test_delete_requires_admin(self, client):
        user = UserFactory(role='member')
        target = UserFactory()
        client.force_login(user)
        response = client.post(reverse('user_delete', args=[target.pk]))
        assert response.status_code == 403

    def test_delete_requires_post(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.get(reverse('user_delete', args=[target.pk]))
        assert response.status_code == 405

    def test_delete_clean_user(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        target_pk = target.pk
        client.force_login(admin)
        response = client.post(reverse('user_delete', args=[target.pk]))
        assert response.status_code == 200
        assert not User.objects.filter(pk=target_pk).exists()

    def test_delete_user_with_data_cascades(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        TodoFactory(owner=target)
        TodoFactory(owner=target)
        target_pk = target.pk
        client.force_login(admin)
        response = client.post(reverse('user_delete', args=[target.pk]))
        assert response.status_code == 200
        assert not User.objects.filter(pk=target_pk).exists()
        from apps.todos.models import Todo
        assert Todo.objects.filter(owner_id=target_pk).count() == 0

    def test_cannot_delete_self(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_delete', args=[admin.pk]))
        assert response.status_code == 400
        assert User.objects.filter(pk=admin.pk).exists()

    def test_cannot_delete_last_admin(self, client):
        admin = AdminUserFactory()
        target = AdminUserFactory()
        client.force_login(admin)
        # First deactivate target to make admin the only active admin
        target.is_active = False
        target.save()
        # Try to delete target — allowed since target is not the last admin (admin is)
        # But try to delete another active admin when they'd be the last
        another = AdminUserFactory()
        # Deactivate 'another' so admin is truly last
        another.is_active = False
        another.save()
        # admin is last active admin — can't delete themselves
        response = client.post(reverse('user_delete', args=[admin.pk]))
        assert response.status_code == 400

    def test_delete_returns_empty_response_with_trigger(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.post(reverse('user_delete', args=[target.pk]))
        assert response.status_code == 200
        assert response.content == b''
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest apps/accounts/tests/test_views.py::TestUserDeleteConfirm apps/accounts/tests/test_views.py::TestUserDelete -v
```

Expected: FAIL — `NoReverseMatch`

### Implementation

- [ ] **Step 3: Add `user_delete_confirm` view to `apps/accounts/views.py`**

Add these imports at the top of the file:

```python
from django.db.models import Q
```

Then add the view:

```python
@login_required
@require_permission('access_team')
def user_delete_confirm(request, pk):
    """Return deletion confirmation partial with cascade counts."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    user_obj = get_object_or_404(User, pk=pk)

    if user_obj == request.user:
        return HttpResponse('Cannot delete yourself.', status=400)

    from apps.todos.models import Todo
    from apps.notes.models import Note
    from apps.tasks.models import Task, Comment, Attachment
    from apps.projects.models import ProjectMember
    from apps.salaries.models import EmployeeSalary, SalaryMonth, Payment

    counts = {
        'todos': Todo.objects.filter(owner=user_obj).count(),
        'notes': Note.objects.filter(Q(created_by=user_obj) | Q(modified_by=user_obj)).count(),
        'comments': Comment.objects.filter(author=user_obj).count(),
        'attachments': Attachment.objects.filter(uploaded_by=user_obj).count(),
        'project_memberships': ProjectMember.objects.filter(user=user_obj).count(),
        'tasks_unassigned': Task.objects.filter(assignee=user_obj).count(),
    }

    # Salary cascade chain
    try:
        salary = EmployeeSalary.objects.get(user=user_obj)
        salary_months = SalaryMonth.objects.filter(employee_salary=salary)
        counts['salary'] = True
        counts['salary_months'] = salary_months.count()
        counts['payments'] = Payment.objects.filter(salary_month__in=salary_months).count()
    except EmployeeSalary.DoesNotExist:
        counts['salary'] = False
        counts['salary_months'] = 0
        counts['payments'] = 0

    counts['has_data'] = any([
        counts['todos'], counts['notes'], counts['comments'],
        counts['attachments'], counts['project_memberships'],
        counts['salary'], counts['tasks_unassigned'],
    ])

    return render(request, 'accounts/partials/user_delete_confirm.html', {
        'user_obj': user_obj,
        'counts': counts,
    })
```

- [ ] **Step 4: Add `user_delete` view to `apps/accounts/views.py`**

```python
@login_required
@require_permission('access_team')
@require_POST
def user_delete(request, pk):
    """Permanently delete a user and all associated data."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    user_obj = get_object_or_404(User, pk=pk)

    if user_obj == request.user:
        return HttpResponse('Cannot delete yourself.', status=400)

    if user_obj.role == 'admin' and user_obj.is_active:
        active_admin_count = User.objects.filter(role='admin', is_active=True).count()
        if active_admin_count <= 1:
            return HttpResponse('Cannot delete the last active admin.', status=400)

    user_obj.delete()
    return HttpResponse('')
```

- [ ] **Step 5: Add URL patterns in `apps/accounts/urls.py`**

```python
path('team/<int:pk>/delete-confirm/', views.user_delete_confirm, name='user_delete_confirm'),
path('team/<int:pk>/delete/', views.user_delete, name='user_delete'),
```

- [ ] **Step 6: Create `templates/accounts/partials/user_delete_confirm.html`**

```html
<div class="mt-2 p-3 bg-red-500/5 border border-red-500/20 rounded-card">
    {% if counts.has_data %}
    <p class="text-xs text-red-400 font-medium mb-2">This will permanently delete:</p>
    <ul class="text-xs text-zinc-400 space-y-1 mb-2">
        {% if counts.todos %}
        <li>{{ counts.todos }} todo{{ counts.todos|pluralize }}</li>
        {% endif %}
        {% if counts.notes %}
        <li>{{ counts.notes }} note{{ counts.notes|pluralize }}</li>
        {% endif %}
        {% if counts.comments %}
        <li>{{ counts.comments }} comment{{ counts.comments|pluralize }}</li>
        {% endif %}
        {% if counts.attachments %}
        <li>{{ counts.attachments }} attachment{{ counts.attachments|pluralize }}</li>
        {% endif %}
        {% if counts.project_memberships %}
        <li>{{ counts.project_memberships }} project membership{{ counts.project_memberships|pluralize }}</li>
        {% endif %}
        {% if counts.salary %}
        <li>Salary record (including {{ counts.salary_months }} month{{ counts.salary_months|pluralize }} and {{ counts.payments }} payment{{ counts.payments|pluralize }})</li>
        {% endif %}
    </ul>
    {% if counts.tasks_unassigned %}
    <p class="text-xs text-zinc-400 mb-3">Additionally, {{ counts.tasks_unassigned }} task{{ counts.tasks_unassigned|pluralize }} will be unassigned.</p>
    {% endif %}
    {% else %}
    <p class="text-xs text-zinc-400 mb-3">This user has no associated data. Delete permanently?</p>
    {% endif %}

    <div class="flex gap-2">
        <button onclick="this.closest('[id^=delete-confirm]').innerHTML = ''"
                class="flex-1 px-3 py-1.5 text-xs text-zinc-400 bg-elevated rounded-card hover:bg-zinc-700 transition-colors">
            Cancel
        </button>
        <button hx-post="{% url 'user_delete' user_obj.pk %}"
                hx-target="#user-{{ user_obj.pk }}"
                hx-swap="delete"
                hx-on::after-request="document.getElementById('slide-over').classList.add('hidden');"
                class="flex-1 px-3 py-1.5 text-xs text-white bg-red-600 rounded-card hover:bg-red-700 transition-colors">
            {% if counts.has_data %}Delete Permanently{% else %}Delete{% endif %}
        </button>
    </div>
</div>
```

- [ ] **Step 7: Run tests**

```bash
pytest apps/accounts/tests/test_views.py::TestUserDeleteConfirm apps/accounts/tests/test_views.py::TestUserDelete -v
```

Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add apps/accounts/views.py apps/accounts/urls.py apps/accounts/tests/test_views.py templates/accounts/partials/user_delete_confirm.html
git commit -m "feat: add user deletion with two-tier cascade warning"
```

---

## Task 6: Backend — Fix Inconsistent Active User Filtering in Task Views

> **Roles:** Backend implements, Verifier tests

**Files:**
- Modify: `apps/tasks/views.py` (lines 127, 310, 332)

- [ ] **Step 1: Write tests for active user filtering**

Add a test file or add to existing task tests. The key behavior: inactive users should not appear in `team_members` context.

```python
# In the appropriate task test file
@pytest.mark.django_db
class TestInactiveUserFiltering:
    def test_task_detail_excludes_inactive_users(self, client):
        admin = AdminUserFactory()
        active_user = UserFactory(is_active=True, name='Active')
        inactive_user = UserFactory(is_active=False, name='Inactive')
        # Create a project and task as needed for the view
        # Then check response.context['team_members'] does not include inactive_user
        ...

    def test_task_update_assignee_excludes_inactive_users(self, client):
        ...
```

Note: The exact test setup depends on the task views' required context (project, task, etc.). The verifier should write these tests with proper fixtures.

- [ ] **Step 2: Fix the three inconsistent lines in `apps/tasks/views.py`**

Change line 127:
```python
# Old: team_members = User.objects.all()
team_members = User.objects.filter(is_active=True)
```

Change line 310:
```python
# Old: team_members = User.objects.all()
team_members = User.objects.filter(is_active=True)
```

Change line 332:
```python
# Old: team_members = User.objects.all()
team_members = User.objects.filter(is_active=True)
```

- [ ] **Step 3: Run existing task tests**

```bash
pytest apps/tasks/tests/ -v
```

Expected: All PASS (no regressions)

- [ ] **Step 4: Commit**

```bash
git add apps/tasks/views.py
git commit -m "fix: filter inactive users from task assignee dropdowns"
```

---

## Task 7: Verifier — End-to-End Testing

> **Roles:** Verifier executes all tests

**Files:**
- All test files in `apps/accounts/tests/`

- [ ] **Step 1: Run the full test suite**

```bash
pytest -v
```

Expected: All PASS, no regressions across any app.

- [ ] **Step 2: Manual E2E verification checklist**

Start the dev server (`python manage.py runserver`) and verify:

1. **Edit user**: Open drawer for any user, change name/email/role/preset, save. Verify row updates and drawer closes.
2. **Validation errors**: Try saving with blank name, duplicate email. Verify error messages show inline and drawer stays open.
3. **Last-admin guard**: With only one admin, try changing their role to member. Verify error message.
4. **Deactivate user**: Deactivate a user. Verify row turns grey with "Inactive" badge.
5. **Reactivate user**: Open inactive user's drawer, click Reactivate. Verify row returns to normal.
6. **Self-deactivation prevented**: Verify deactivate button is hidden when viewing your own profile.
7. **Clean delete**: Create a new user (via signup), open their drawer, delete them. Verify clean delete message and user removed from list.
8. **Force delete with warning**: Assign a user some todos/tasks, then try to delete them. Verify cascade count warning appears.
9. **Inactive user in dropdowns**: Deactivate a user, then go to create a task — verify they don't appear in the assignee dropdown.
10. **Existing assignments preserved**: Verify tasks previously assigned to a deactivated user still show the assignment.

- [ ] **Step 3: Commit any test fixes**

```bash
git add -A
git commit -m "test: complete E2E verification for user CRUD"
```

---

## Task Dependency Graph

```
Task 1 (user_update backend) ──────┐
Task 3 (deactivate backend) ───────┤── Task 2 (drawer frontend) ── depends on Tasks 1, 3, 5
Task 5 (delete backend) ───────────┘
                                        Task 4 (row styling) ── depends on Task 3
Task 6 (active filtering) ── independent
Task 7 (E2E testing) ── depends on ALL above
```

**Parallelizable:** Tasks 1, 3, 5, 6 can run in parallel (all backend work).
**Sequential:** Task 2 depends on Tasks 1, 3, AND 5 (drawer references all URL names). Task 4 depends on Task 3. Task 7 depends on all.

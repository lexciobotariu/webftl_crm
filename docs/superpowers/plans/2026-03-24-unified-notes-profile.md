# Unified Notes on Client Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the plain-text notes section on the client profile tab with a unified table showing all Note objects (from both the client and its projects), with Title, Description, and Type columns.

**Architecture:** Add a new view that queries Note objects for the client AND all its projects, merges them into a single list, and renders a read-only table on the profile. The old `client.notes` TextField section (with its edit button) is replaced entirely. The existing Notes tab in the sidebar continues to work as-is for full CRUD.

**Tech Stack:** Django views, Django templates (HTMX partials), Tailwind CSS

---

## Current State

- **Client profile** (`templates/clients/partials/profile_content.html`) has two sections:
  1. Contact Information card
  2. Notes card — renders `client.notes` TextField via `notes_display.html` partial, with inline edit via `notes_edit.html`
- **Notes tab** (`client_detail.html` line 73-81) loads `client_notes_list` via HTMX — shows only client-attached Note objects in a full table with Title, Created By, Last Modified, Modified By, Privacy columns
- **Note model** (`apps/notes/models.py`) — polymorphic, attaches to client XOR project
- **Project model** (`apps/projects/models.py`) — has `client` FK, so `client.projects.all()` gives all projects for a client

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `templates/clients/partials/profile_notes_table.html` | New partial: unified notes table (read-only, 3 columns) |
| Modify | `apps/clients/views.py` | Add `client_profile_notes` view to query & merge notes |
| Modify | `apps/clients/urls.py` | Add URL for the new HTMX partial endpoint |
| Modify | `templates/clients/partials/profile_content.html` | Replace old notes section with HTMX-loaded table |
| Create | `apps/clients/tests/test_profile_notes.py` | Tests for the new view |

### Files NOT modified (left as-is)

- `templates/clients/partials/notes_display.html` — kept for now (unused on profile, but harmless)
- `templates/clients/partials/notes_edit.html` — kept for now (unused on profile, but harmless)
- `apps/clients/views.py` `client_edit_notes`, `client_notes_display` — kept (may be removed in a future cleanup)
- `apps/notes/` — no changes to the Notes app
- `apps/clients/models.py` — `client.notes` TextField stays in DB (no migration needed), just not shown on profile anymore

---

## Tasks

### Task 1: Create the unified notes view

**Files:**
- Create: `apps/clients/tests/test_profile_notes.py`
- Modify: `apps/clients/views.py`
- Modify: `apps/clients/urls.py`

- [ ] **Step 1: Write the failing test**

Create `apps/clients/tests/test_profile_notes.py`:

```python
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

from apps.clients.models import Client
from apps.projects.models import Project
from apps.notes.models import Note

User = get_user_model()


class ClientProfileNotesViewTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_user(
            email='admin@test.com', password='test', role='admin'
        )
        self.client_obj = Client.objects.create(name='Test Client')
        self.project = Project.objects.create(
            client=self.client_obj, name='Test Project'
        )

    def test_returns_client_and_project_notes(self):
        """Profile notes table shows notes from client AND its projects."""
        client_note = Note.objects.create(
            client=self.client_obj,
            title='Client Note',
            description='About the client',
            created_by=self.admin,
            modified_by=self.admin,
        )
        project_note = Note.objects.create(
            project=self.project,
            title='Project Note',
            description='About the project',
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            f'/clients/{self.client_obj.pk}/profile-notes/'
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Client Note')
        self.assertContains(response, 'Project Note')

    def test_type_column_shows_client_or_project_name(self):
        """Type column shows 'Client' for client notes and project name for project notes."""
        Note.objects.create(
            client=self.client_obj,
            title='A Client Note',
            created_by=self.admin,
            modified_by=self.admin,
        )
        Note.objects.create(
            project=self.project,
            title='A Project Note',
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            f'/clients/{self.client_obj.pk}/profile-notes/'
        )

        self.assertContains(response, 'Client')
        self.assertContains(response, 'Test Project')

    def test_requires_login(self):
        """Unauthenticated users are redirected."""
        response = self.client.get(
            f'/clients/{self.client_obj.pk}/profile-notes/'
        )
        self.assertEqual(response.status_code, 302)

    def test_non_admin_forbidden(self):
        """Non-admin users get 403."""
        regular_user = User.objects.create_user(
            email='user@test.com', password='test', role='member'
        )
        self.client.force_login(regular_user)
        response = self.client.get(
            f'/clients/{self.client_obj.pk}/profile-notes/'
        )
        self.assertEqual(response.status_code, 403)

    def test_respects_note_visibility(self):
        """Private notes from other users are not shown."""
        other_admin = User.objects.create_user(
            email='other@test.com', password='test', role='admin'
        )
        # Private note by other user — should still show for admin
        Note.objects.create(
            client=self.client_obj,
            title='Private Note',
            is_private=True,
            created_by=other_admin,
            modified_by=other_admin,
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            f'/clients/{self.client_obj.pk}/profile-notes/'
        )
        # Admins can see all notes
        self.assertContains(response, 'Private Note')

    def test_empty_state(self):
        """Shows empty message when no notes exist."""
        self.client.force_login(self.admin)
        response = self.client.get(
            f'/clients/{self.client_obj.pk}/profile-notes/'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No notes yet')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.clients.tests.test_profile_notes -v 2`
Expected: FAIL — URL not found / view not defined

- [ ] **Step 3: Add the URL route**

In `apps/clients/urls.py`, add after line 12 (`client_detail_notes`):

```python
    path('<int:pk>/profile-notes/', views.client_profile_notes, name='client_profile_notes'),
```

- [ ] **Step 4: Write the view**

In `apps/clients/views.py`, add this new view:

```python
@login_required
def client_profile_notes(request, pk):
    """Return unified notes table for client profile (client + project notes)."""
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    client = get_object_or_404(Client, pk=pk)

    from apps.notes.models import Note, can_view_note

    # Get client notes
    client_notes = list(
        Note.objects.filter(client=client)
        .select_related('created_by', 'modified_by')
    )

    # Get notes from all client's projects
    project_ids = client.projects.values_list('pk', flat=True)
    project_notes = list(
        Note.objects.filter(project_id__in=project_ids)
        .select_related('created_by', 'modified_by', 'project')
    )

    # Merge, filter visibility, sort by most recent
    all_notes = [n for n in client_notes + project_notes if can_view_note(request.user, n)]
    all_notes.sort(key=lambda n: n.updated_at, reverse=True)

    # Annotate each note with its type label
    for note in all_notes:
        if note.client_id:
            note.type_label = 'Client'
        else:
            note.type_label = 'Project'
            note.type_name = note.project.name

    return render(request, 'clients/partials/profile_notes_table.html', {
        'notes': all_notes,
        'client': client,
    })
```

- [ ] **Step 5: Run tests to verify they fail on missing template**

Run: `python manage.py test apps.clients.tests.test_profile_notes -v 2`
Expected: FAIL — template not found

- [ ] **Step 6: Commit view + URL + test skeleton**

```bash
git add apps/clients/views.py apps/clients/urls.py apps/clients/tests/test_profile_notes.py
git commit -m "feat(clients): add unified profile notes view and tests (no template yet)"
```

---

### Task 2: Create the unified notes table template

**Files:**
- Create: `templates/clients/partials/profile_notes_table.html`

- [ ] **Step 1: Create the template**

Create `templates/clients/partials/profile_notes_table.html`:

```html
{% if notes %}
<table class="w-full">
    <thead class="bg-panel border-b border-border-subtle">
        <tr class="text-left text-xs text-zinc-500 uppercase tracking-wider">
            <th class="px-4 py-2 font-medium">Title</th>
            <th class="px-4 py-2 font-medium">Description</th>
            <th class="px-4 py-2 font-medium">Type</th>
        </tr>
    </thead>
    <tbody class="divide-y divide-border-subtle">
        {% for note in notes %}
        <tr hx-get="{% url 'note_detail_drawer' note.pk %}"
            hx-target="#slide-over"
            hx-swap="innerHTML"
            hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
            class="hover:bg-elevated/50 cursor-pointer transition-colors">
            <td class="px-4 py-3">
                <span class="font-medium text-sm text-zinc-100">{{ note.title }}</span>
            </td>
            <td class="px-4 py-3">
                <span class="text-sm text-zinc-400 line-clamp-2">{{ note.description|default:"—"|truncatewords:20 }}</span>
            </td>
            <td class="px-4 py-3">
                {% if note.type_label == 'Project' %}
                <span class="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-elevated rounded-card text-zinc-400">
                    <i data-lucide="folder-kanban" class="w-3 h-3"></i>
                    {{ note.type_name }}
                </span>
                {% else %}
                <span class="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-elevated rounded-card text-zinc-400">
                    <i data-lucide="building-2" class="w-3 h-3"></i>
                    Client
                </span>
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% else %}
<div class="flex flex-col items-center justify-center py-8 text-zinc-500">
    <i data-lucide="sticky-note" class="w-8 h-8 mb-2 opacity-30"></i>
    <p class="text-sm">No notes yet</p>
</div>
{% endif %}

<script>
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
</script>
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python manage.py test apps.clients.tests.test_profile_notes -v 2`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add templates/clients/partials/profile_notes_table.html
git commit -m "feat(clients): add unified notes table template"
```

---

### Task 3: Replace old notes section on profile with unified table

**Files:**
- Modify: `templates/clients/partials/profile_content.html:45-48`

- [ ] **Step 1: Replace the old notes section**

In `templates/clients/partials/profile_content.html`, replace lines 45-48:

```html
<!-- Notes -->
<div class="border border-border-subtle rounded-card overflow-hidden mt-6" id="notes-section">
    {% include "clients/partials/notes_display.html" %}
</div>
```

With:

```html
<!-- Notes (unified: client + project notes) -->
<div class="border border-border-subtle rounded-card overflow-hidden mt-6" id="notes-section">
    <div class="px-4 py-2 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center gap-3">
            <i data-lucide="file-text" class="w-4 h-4 text-zinc-500"></i>
            <h2 class="text-sm font-medium text-zinc-100">Notes</h2>
        </div>
    </div>
    <div hx-get="{% url 'client_profile_notes' client.pk %}"
         hx-trigger="load"
         hx-swap="innerHTML">
        <div class="flex items-center justify-center py-8">
            <span class="text-sm text-zinc-500">Loading notes...</span>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Verify in browser**

1. Start the dev server: `python manage.py runserver`
2. Navigate to a client profile page
3. Confirm: old plain-text notes section is gone, replaced by a table with Title / Description / Type columns
4. Confirm: clicking a note row opens the detail drawer
5. Confirm: notes from projects show the project name badge, client notes show "Client" badge

- [ ] **Step 3: Run full test suite**

Run: `python manage.py test -v 2`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add templates/clients/partials/profile_content.html
git commit -m "feat(clients): replace profile notes section with unified notes table"
```

---

### Task 4: Fix duplicate URL route in clients/urls.py

**Files:**
- Modify: `apps/clients/urls.py:15-16`

**Context:** Lines 12 and 15 both map `<int:pk>/notes/` — line 12 goes to `client_detail` (notes tab), line 15 goes to `client_notes_display`. The duplicate means line 15 is unreachable. Since we're no longer using `notes_display` on the profile, clean this up.

- [ ] **Step 1: Remove the dead route**

In `apps/clients/urls.py`, remove line 15:

```python
    path('<int:pk>/notes/', views.client_notes_display, name='client_notes_display'),
```

- [ ] **Step 2: Run full test suite**

Run: `python manage.py test -v 2`
Expected: ALL PASS (if any test references `client_notes_display` URL by name, it will fail — fix accordingly)

- [ ] **Step 3: Commit**

```bash
git add apps/clients/urls.py
git commit -m "fix(clients): remove unreachable duplicate notes URL route"
```

---

## Summary of Changes

| What changes | Before | After |
|---|---|---|
| Profile notes section | Plain-text `client.notes` TextField with Edit button | Read-only table of Note objects from client + all projects |
| Columns | N/A (free-form text) | Title, Description, Type (Client / Project name) |
| Edit button on profile notes | Yes (inline textarea) | Removed — editing happens via Notes tab or note detail drawer |
| Notes tab in sidebar | Shows only client-attached notes | Unchanged |
| `client.notes` TextField | Displayed on profile | Still in DB, no migration, just not rendered on profile |
| Note detail drawer | Accessible from Notes tab | Also accessible by clicking any row in the profile table |

## Not In Scope

- Removing the `client.notes` TextField from the model (would require a migration — do separately if desired)
- Removing `client_edit_notes` / `client_notes_display` views (harmless dead code, clean up later)
- Changing the Notes tab behavior
- Adding create/edit/delete from the profile notes table (use the Notes tab for that)

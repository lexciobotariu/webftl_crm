# Notes App Design Document

**Date:** 2026-01-01
**Feature:** Notes functionality for Clients and Projects
**Status:** Design Complete - Ready for Implementation

---

## Overview

The Notes app allows users to create, view, edit, and delete notes attached to either clients or projects. Notes can be marked as private (visible only to creator and admins) or public (visible to all users with access to the parent entity).

---

## Data Model & Database Schema

### Note Model

**Location:** `apps/notes/models.py`

```python
class Note(models.Model):
    # Polymorphic relationship - exactly one must be set
    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE,
                               null=True, blank=True, related_name='notes')
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE,
                                null=True, blank=True, related_name='notes')

    # Content fields
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Privacy
    is_private = models.BooleanField(default=False)

    # Ownership & tracking
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                   on_delete=models.CASCADE,
                                   related_name='notes_created')
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                    on_delete=models.CASCADE,
                                    related_name='notes_modified')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']  # Most recently modified first

    def clean(self):
        # Ensure exactly one parent is set
        if not (bool(self.client) ^ bool(self.project)):
            raise ValidationError("Note must belong to either a client or project")
```

### Design Decisions

- **Single polymorphic model** for both client and project notes
- **Activity-based sorting** (most recently modified first)
- **Simple boolean privacy flag** (private vs public)
- **Dual user tracking** (created_by and modified_by)
- **Auto timestamps** for maintenance-free tracking

---

## Authorization & Access Control

### Permission Rules

**Client Notes:**
- **Private notes:** Only creator and admins can view
- **Public notes:** Only admins can view (client pages are admin-only)
- **Create/Edit/Delete:** Admins can do anything; creators can edit/delete their own notes

**Project Notes:**
- **Private notes:** Only creator and admins can view
- **Public notes:** Anyone with project access (any ProjectMember) can view
- **Create:** Any ProjectMember with 'editor' role or higher can create notes
- **Edit/Delete:** Admins can do anything; creators can edit/delete their own notes

### Authorization Helper Functions

**Location:** `apps/notes/models.py`

```python
def can_view_note(user, note):
    """Check if user can view this note"""
    if user.is_admin:
        return True

    # Private notes: only creator
    if note.is_private:
        return note.created_by == user

    # Public client notes: admin-only (already handled above)
    if note.client:
        return False

    # Public project notes: any project member
    if note.project:
        return can_access_project(user, note.project, 'viewer')

    return False

def can_create_note(user, project=None, client=None):
    """Check if user can create notes"""
    if user.is_admin:
        return True

    if client:
        return False  # Only admins can create client notes

    if project:
        return can_access_project(user, project, 'editor')

    return False

def can_modify_note(user, note):
    """Check if user can edit/delete this note"""
    if user.is_admin:
        return True

    # Only creator can modify their own notes
    return note.created_by == user
```

---

## URL Structure & Routing

### Notes App URLs

**Location:** `apps/notes/urls.py`

```python
from django.urls import path
from . import views

urlpatterns = [
    # Client notes
    path('client/<int:client_pk>/create/drawer/', views.note_create_drawer, name='client_note_create_drawer'),
    path('client/<int:client_pk>/list/', views.client_notes_list, name='client_notes_list'),

    # Project notes
    path('project/<int:project_pk>/create/drawer/', views.note_create_drawer, name='project_note_create_drawer'),
    path('project/<int:project_pk>/list/', views.project_notes_list, name='project_notes_list'),

    # Note operations (works for both client and project notes)
    path('<int:pk>/', views.note_detail_drawer, name='note_detail_drawer'),
    path('<int:pk>/edit/', views.note_edit_drawer, name='note_edit_drawer'),
    path('<int:pk>/delete/', views.note_delete, name='note_delete'),
]
```

### Integration URLs

**Client URLs** (`apps/clients/urls.py`):
```python
path('<int:pk>/notes/', views.client_detail, name='client_detail_notes'),
```

**Project URLs** (`apps/projects/urls.py`):
```python
path('<int:pk>/detail/notes/', views.project_detail, name='project_detail_notes'),
```

**Main URLs** (`config/urls.py`):
```python
path('notes/', include('apps.notes.urls')),
```

### Navigation Flow

1. User visits client/project detail page → Clicks "Notes" tab in right sidebar
2. Notes tab loads → Shows table list via `client_notes_list` or `project_notes_list` partial
3. User clicks note row → Opens read-only drawer via `note_detail_drawer`
4. User clicks "Edit" in drawer → Swaps drawer content to edit mode via `note_edit_drawer`
5. User clicks "Add Note" → Opens create drawer via `note_create_drawer`
6. On save → HTMX partial updates table list without page refresh

---

## View Layer & HTMX Integration

### View Functions

**Location:** `apps/notes/views.py`

#### List Views (HTMX Partials)

```python
@login_required
def client_notes_list(request, client_pk):
    """Render notes table for client detail page"""
    client = get_object_or_404(Client, pk=client_pk)

    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    notes = client.notes.select_related('created_by', 'modified_by').all()
    notes = [n for n in notes if can_view_note(request.user, n)]

    return render(request, 'notes/partials/notes_list.html', {
        'notes': notes,
        'parent': client,
        'parent_type': 'client'
    })

@login_required
def project_notes_list(request, project_pk):
    """Render notes table for project detail page"""
    project = get_object_or_404(Project, pk=project_pk)

    if not can_access_project(request.user, project, 'viewer'):
        return HttpResponseForbidden("Access denied")

    notes = project.notes.select_related('created_by', 'modified_by').all()
    notes = [n for n in notes if can_view_note(request.user, n)]

    return render(request, 'notes/partials/notes_list.html', {
        'notes': notes,
        'parent': project,
        'parent_type': 'project'
    })
```

#### Create Note Drawer

```python
@login_required
def note_create_drawer(request, client_pk=None, project_pk=None):
    """Create new note drawer"""
    parent = None
    parent_type = None

    if client_pk:
        parent = get_object_or_404(Client, pk=client_pk)
        parent_type = 'client'
        if not request.user.is_admin:
            return HttpResponseForbidden("Admin access required")
    elif project_pk:
        parent = get_object_or_404(Project, pk=project_pk)
        parent_type = 'project'
        if not can_create_note(request.user, project=parent):
            return HttpResponseForbidden("Access denied")

    if request.method == 'POST':
        note = Note(
            title=request.POST.get('title'),
            description=request.POST.get('description', ''),
            is_private=request.POST.get('is_private') == 'on',
            created_by=request.user,
            modified_by=request.user
        )

        if parent_type == 'client':
            note.client = parent
        else:
            note.project = parent

        note.save()

        # Return updated list partial
        notes = parent.notes.select_related('created_by', 'modified_by').all()
        notes = [n for n in notes if can_view_note(request.user, n)]

        response = render(request, 'notes/partials/notes_list.html', {
            'notes': notes,
            'parent': parent,
            'parent_type': parent_type
        })
        response['HX-Trigger'] = 'closeSlideOver'
        return response

    return render(request, 'notes/partials/note_create_drawer.html', {
        'parent': parent,
        'parent_type': parent_type
    })
```

#### Detail & Edit Drawers

```python
@login_required
def note_detail_drawer(request, pk):
    """Read-only note view"""
    note = get_object_or_404(Note.objects.select_related('created_by', 'modified_by'), pk=pk)

    if not can_view_note(request.user, note):
        return HttpResponseForbidden("Access denied")

    return render(request, 'notes/partials/note_detail_drawer.html', {
        'note': note,
        'can_modify': can_modify_note(request.user, note)
    })

@login_required
def note_edit_drawer(request, pk):
    """Edit existing note"""
    note = get_object_or_404(Note, pk=pk)

    if not can_modify_note(request.user, note):
        return HttpResponseForbidden("Access denied")

    if request.method == 'POST':
        note.title = request.POST.get('title')
        note.description = request.POST.get('description', '')
        note.is_private = request.POST.get('is_private') == 'on'
        note.modified_by = request.user
        note.save()

        # Return to read-only view
        response = render(request, 'notes/partials/note_detail_drawer.html', {
            'note': note,
            'can_modify': True
        })

        # Also update the list
        parent = note.client or note.project
        notes = parent.notes.select_related('created_by', 'modified_by').all()
        notes = [n for n in notes if can_view_note(request.user, n)]

        list_html = render(request, 'notes/partials/notes_list.html', {
            'notes': notes,
            'parent': parent,
            'parent_type': 'client' if note.client else 'project'
        }).content.decode()

        # Use out-of-band swap to update both drawer and list
        response['HX-Trigger'] = 'noteUpdated'
        return HttpResponse(
            response.content.decode() +
            f'<div id="notes-list" hx-swap-oob="true">{list_html}</div>'
        )

    return render(request, 'notes/partials/note_edit_drawer.html', {'note': note})

@login_required
@require_POST
def note_delete(request, pk):
    """Delete a note"""
    note = get_object_or_404(Note, pk=pk)

    if not can_modify_note(request.user, note):
        return HttpResponseForbidden("Access denied")

    parent = note.client or note.project
    parent_type = 'client' if note.client else 'project'
    note.delete()

    # Return updated list
    notes = parent.notes.select_related('created_by', 'modified_by').all()
    notes = [n for n in notes if can_view_note(request.user, n)]

    response = render(request, 'notes/partials/notes_list.html', {
        'notes': notes,
        'parent': parent,
        'parent_type': parent_type
    })
    response['HX-Trigger'] = 'closeSlideOver'
    return response
```

### HTMX Integration Points

1. **Notes tab loads** → `hx-get` to list view, targets content area
2. **Click note row** → `hx-get` to detail drawer, targets `#slide-over`
3. **Click Edit** → `hx-get` to edit drawer, swaps drawer content
4. **Submit create/edit form** → `hx-post`, updates list via OOB swap
5. **Delete note** → `hx-post`, returns updated list and closes drawer

---

## Template Structure

### Directory Structure

```
/templates/notes/
└── partials/
    ├── notes_list.html           # Table of notes (HTMX partial)
    ├── note_create_drawer.html   # Create form in drawer
    ├── note_detail_drawer.html   # Read-only view in drawer
    └── note_edit_drawer.html     # Edit form in drawer
```

### Key Template Features

**Notes List (`notes_list.html`):**
- Sticky header with "Add Note" button
- Table with columns: Title, Created By, Last Modified, Modified By, Privacy
- Clickable rows open detail drawer
- Empty state for no notes
- Privacy badges (lock icon for private, globe for public)

**Detail Drawer (`note_detail_drawer.html`):**
- Read-only display of title and description
- Privacy indicator
- Metadata section (created by, created date, modified by, modified date)
- Edit and Delete buttons (if user has permission)

**Create/Edit Drawers:**
- Title input (required)
- Description textarea
- Privacy checkbox with explanation
- Save/Cancel buttons
- Form validation

### Integration into Client/Project Pages

**Sidebar Navigation:**
```html
<a href="{% url 'client_detail_notes' client.pk %}"
   class="w-full flex items-center gap-3 px-3 py-2 rounded-card text-sm transition-colors
          {% if active_tab == 'notes' %}bg-elevated text-zinc-100{% else %}text-zinc-400 hover:bg-elevated/50{% endif %}">
    <i data-lucide="sticky-note" class="w-4 h-4"></i>
    Notes
</a>
```

**Content Area:**
```html
{% if active_tab == 'notes' %}
    <div hx-get="{% url 'client_notes_list' client.pk %}"
         hx-trigger="load"
         hx-swap="innerHTML"
         class="h-full">
        <div class="flex items-center justify-center h-full">
            <div class="text-zinc-500">Loading notes...</div>
        </div>
    </div>
{% endif %}
```

---

## Implementation Steps

1. **Activate virtual environment** - Run `source .venv/bin/activate`
2. **Create notes app structure** - Run `python manage.py startapp notes apps/notes`
3. **Define Note model** - Add model, helper functions in `models.py`
4. **Create migrations** - Run `python manage.py makemigrations` and `python manage.py migrate`
5. **Register admin** - Add basic admin interface for debugging
6. **Create view functions** - Implement all 5 views with authorization
7. **Set up URL routing** - Configure app URLs and integrate into main URLs
8. **Build templates** - Create all 4 partial templates
9. **Integrate into client detail** - Add tab to sidebar and content handling
10. **Integrate into project detail** - Add tab to sidebar and content handling
11. **Test HTMX flow** - Verify create, read, edit, delete operations
12. **Test permissions** - Verify private/public access controls work correctly

---

## Files to Create

### New Django App
```
apps/notes/
├── __init__.py
├── admin.py                    # Register Note model
├── apps.py                     # App config
├── models.py                   # Note model
├── views.py                    # All view functions
├── urls.py                     # URL routing
└── migrations/
    └── 0001_initial.py         # Auto-generated
```

### Templates
```
templates/notes/partials/
├── notes_list.html
├── note_create_drawer.html
├── note_detail_drawer.html
└── note_edit_drawer.html
```

---

## Files to Modify

1. **`apps/clients/urls.py`** - Add notes tab URL
2. **`apps/clients/views.py`** - Add 'notes' tab handling to `client_detail` view
3. **`templates/clients/client_detail.html`** - Add notes tab to sidebar and content area
4. **`apps/projects/urls.py`** - Add notes tab URL
5. **`apps/projects/views.py`** - Add 'notes' tab handling to `project_detail` view
6. **`templates/projects/project_detail.html`** - Add notes tab to sidebar and content area
7. **`config/urls.py`** (or main `urls.py`) - Include notes app URLs
8. **`config/settings.py`** - Add 'apps.notes' to `INSTALLED_APPS`

---

## Design Patterns Used

- **Polymorphic model** - Single Note model for both clients and projects
- **Permission helpers** - Reusable functions for authorization checks
- **HTMX partials** - No page refreshes for CRUD operations
- **Out-of-band swaps** - Update multiple page sections simultaneously
- **Drawer UI pattern** - Consistent with existing task and todo drawers
- **Activity-based sorting** - Most recently modified notes first
- **Select related optimization** - Minimize database queries

---

## Future Enhancements (Out of Scope)

- Rich text editor for description
- Note attachments/files
- Note comments/threads
- Note tags/categories
- Note search and filtering
- Note activity history/audit log
- Email notifications on note creation/updates
- Note mentions (@user)

---

## Testing Checklist

- [ ] Admin can create notes on clients
- [ ] Admin can create notes on projects
- [ ] Project editor can create notes on projects
- [ ] Project viewer cannot create notes
- [ ] Private notes only visible to creator and admins
- [ ] Public client notes only visible to admins
- [ ] Public project notes visible to all project members
- [ ] Note creator can edit their own notes
- [ ] Note creator can delete their own notes
- [ ] Admin can edit/delete any note
- [ ] HTMX updates list without page refresh on create
- [ ] HTMX updates list without page refresh on edit
- [ ] HTMX updates list without page refresh on delete
- [ ] Notes sorted by most recently modified first
- [ ] Empty state displays when no notes exist
- [ ] Privacy toggle works correctly
- [ ] Modified by field updates on edit

---

**End of Design Document**

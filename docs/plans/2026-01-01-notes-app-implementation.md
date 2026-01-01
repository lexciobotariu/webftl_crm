# Notes App Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a Notes app for clients and projects with private/public visibility and HTMX-powered UI

**Architecture:** Single polymorphic Note model with helper functions for authorization, HTMX partials for all CRUD operations, drawer UI pattern for create/edit/detail views

**Tech Stack:** Django 5.x, HTMX, TailwindCSS, Lucide icons

---

## Task 1: Create Notes Django App

**Files:**
- Create: `apps/notes/__init__.py`
- Create: `apps/notes/apps.py`
- Create: `apps/notes/models.py`
- Create: `apps/notes/views.py`
- Create: `apps/notes/urls.py`
- Create: `apps/notes/admin.py`

**Step 1: Activate virtual environment**

Run: `source .venv/bin/activate`
Expected: Virtual environment activated

**Step 2: Create Django app structure**

Run: `python manage.py startapp notes apps/notes`
Expected: Directory `apps/notes/` created with default structure

**Step 3: Configure app config**

Edit `apps/notes/apps.py`:
```python
from django.apps import AppConfig


class NotesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.notes'
```

**Step 4: Verify app structure**

Run: `ls -la apps/notes/`
Expected: See `__init__.py`, `apps.py`, `models.py`, `views.py`, `admin.py`, etc.

**Step 5: Commit**

```bash
git add apps/notes/
git commit -m "feat: create notes django app structure

Initialize notes app for client and project notes functionality.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Define Note Model and Permission Helpers

**Files:**
- Modify: `apps/notes/models.py`

**Step 1: Write Note model**

Replace contents of `apps/notes/models.py`:
```python
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.projects.models import can_access_project


class Note(models.Model):
    """
    Notes attached to clients or projects.
    Supports private (creator-only) and public (shared with team) visibility.
    """
    # Polymorphic relationship - exactly one must be set
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notes'
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notes'
    )

    # Content fields
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Privacy
    is_private = models.BooleanField(default=False)

    # Ownership & tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notes_created'
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notes_modified'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']  # Most recently modified first

    def __str__(self):
        parent = self.client or self.project
        return f"{self.title} ({parent})"

    def clean(self):
        """Ensure exactly one parent is set"""
        if not (bool(self.client) ^ bool(self.project)):
            raise ValidationError("Note must belong to either a client or project")


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

**Step 2: Verify model syntax**

Run: `python -m py_compile apps/notes/models.py`
Expected: No output (clean compile)

**Step 3: Commit**

```bash
git add apps/notes/models.py
git commit -m "feat: add Note model and permission helpers

- Polymorphic Note model for clients and projects
- Private/public visibility flag
- Permission helpers: can_view_note, can_create_note, can_modify_note
- Activity-based sorting (most recently modified first)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Register Notes in Settings and Create Migrations

**Files:**
- Modify: `config/settings.py`

**Step 1: Add notes to INSTALLED_APPS**

Find the `INSTALLED_APPS` list in `config/settings.py` and add `'apps.notes',` after the other apps (e.g., after `'apps.todos',`):

```python
INSTALLED_APPS = [
    # ... existing apps ...
    'apps.clients',
    'apps.projects',
    'apps.tasks',
    'apps.todos',
    'apps.notes',  # Add this line
    'apps.integrations',
    # ... rest of apps ...
]
```

**Step 2: Verify settings syntax**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

**Step 3: Create migrations**

Run: `python manage.py makemigrations notes`
Expected: `Migrations for 'notes':` followed by migration file path

**Step 4: Apply migrations**

Run: `python manage.py migrate notes`
Expected: `Running migrations:` followed by `Applying notes.0001_initial... OK`

**Step 5: Commit**

```bash
git add config/settings.py apps/notes/migrations/
git commit -m "feat: register notes app and create database migration

Add notes to INSTALLED_APPS and apply initial migration.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Register Notes in Admin

**Files:**
- Modify: `apps/notes/admin.py`

**Step 1: Write admin configuration**

Replace contents of `apps/notes/admin.py`:
```python
from django.contrib import admin
from .models import Note


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ['title', 'get_parent', 'is_private', 'created_by', 'updated_at']
    list_filter = ['is_private', 'created_at', 'updated_at']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at', 'updated_at']

    def get_parent(self, obj):
        return obj.client or obj.project
    get_parent.short_description = 'Parent'
```

**Step 2: Verify admin syntax**

Run: `python -m py_compile apps/notes/admin.py`
Expected: No output (clean compile)

**Step 3: Commit**

```bash
git add apps/notes/admin.py
git commit -m "feat: add admin interface for notes

Register Note model with list display and filters.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Create Notes Views

**Files:**
- Modify: `apps/notes/views.py`

**Step 1: Write all view functions**

Replace contents of `apps/notes/views.py`:
```python
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST

from apps.clients.models import Client
from apps.projects.models import Project, can_access_project
from .models import Note, can_view_note, can_create_note, can_modify_note


@login_required
def client_notes_list(request, client_pk):
    """Render notes table for client detail page"""
    client = get_object_or_404(Client, pk=client_pk)

    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")

    notes = client.notes.select_related('created_by', 'modified_by').all()
    notes = [n for n in notes if can_view_note(request.user, n)]

    can_create = can_create_note(request.user, client=client)

    return render(request, 'notes/partials/notes_list.html', {
        'notes': notes,
        'parent': client,
        'parent_type': 'client',
        'can_create_note': can_create,
    })


@login_required
def project_notes_list(request, project_pk):
    """Render notes table for project detail page"""
    project = get_object_or_404(Project, pk=project_pk)

    if not can_access_project(request.user, project, 'viewer'):
        return HttpResponseForbidden("Access denied")

    notes = project.notes.select_related('created_by', 'modified_by').all()
    notes = [n for n in notes if can_view_note(request.user, n)]

    can_create = can_create_note(request.user, project=project)

    return render(request, 'notes/partials/notes_list.html', {
        'notes': notes,
        'parent': project,
        'parent_type': 'project',
        'can_create_note': can_create,
    })


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

        can_create = can_create_note(
            request.user,
            client=parent if parent_type == 'client' else None,
            project=parent if parent_type == 'project' else None
        )

        response = render(request, 'notes/partials/notes_list.html', {
            'notes': notes,
            'parent': parent,
            'parent_type': parent_type,
            'can_create_note': can_create,
        })
        response['HX-Trigger'] = 'closeSlideOver'
        return response

    return render(request, 'notes/partials/note_create_drawer.html', {
        'parent': parent,
        'parent_type': parent_type
    })


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

        parent_type = 'client' if note.client else 'project'
        can_create = can_create_note(
            request.user,
            client=parent if parent_type == 'client' else None,
            project=parent if parent_type == 'project' else None
        )

        list_html = render(request, 'notes/partials/notes_list.html', {
            'notes': notes,
            'parent': parent,
            'parent_type': parent_type,
            'can_create_note': can_create,
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

    can_create = can_create_note(
        request.user,
        client=parent if parent_type == 'client' else None,
        project=parent if parent_type == 'project' else None
    )

    response = render(request, 'notes/partials/notes_list.html', {
        'notes': notes,
        'parent': parent,
        'parent_type': parent_type,
        'can_create_note': can_create,
    })
    response['HX-Trigger'] = 'closeSlideOver'
    return response
```

**Step 2: Verify views syntax**

Run: `python -m py_compile apps/notes/views.py`
Expected: No output (clean compile)

**Step 3: Commit**

```bash
git add apps/notes/views.py
git commit -m "feat: implement notes views with HTMX support

- List views for client and project notes
- Create/detail/edit drawers
- Delete endpoint
- Authorization checks on all views
- Out-of-band swaps for real-time updates

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Create Notes URL Configuration

**Files:**
- Modify: `apps/notes/urls.py`

**Step 1: Write URL patterns**

Replace contents of `apps/notes/urls.py`:
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

**Step 2: Include in main URLs**

Find `config/urls.py` and add notes URLs to the urlpatterns list:
```python
urlpatterns = [
    # ... existing patterns ...
    path('notes/', include('apps.notes.urls')),
]
```

**Step 3: Verify URL configuration**

Run: `python manage.py show_urls | grep notes`
Expected: List of notes URLs displayed

**Step 4: Commit**

```bash
git add apps/notes/urls.py config/urls.py
git commit -m "feat: configure notes URL routing

Add URL patterns for notes CRUD operations and integrate with main URLs.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Create Notes List Template

**Files:**
- Create: `templates/notes/partials/notes_list.html`

**Step 1: Create template directory**

Run: `mkdir -p templates/notes/partials`
Expected: Directory created

**Step 2: Write notes list template**

Create `templates/notes/partials/notes_list.html`:
```html
<div id="notes-list" class="flex flex-col h-full">
    <!-- Header with Add button -->
    <div class="flex-shrink-0 px-4 py-3 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <h2 class="text-sm font-medium text-zinc-100">Notes</h2>
            {% if can_create_note %}
            <button hx-get="{% url parent_type|add:'_note_create_drawer' parent.pk %}"
                    hx-target="#slide-over"
                    hx-swap="innerHTML"
                    hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                    class="flex items-center gap-2 px-3 py-1.5 text-sm bg-elevated hover:bg-elevated/80 rounded-card transition-colors">
                <i data-lucide="plus" class="w-4 h-4"></i>
                Add Note
            </button>
            {% endif %}
        </div>
    </div>

    <!-- Notes table -->
    <div class="flex-1 overflow-y-auto">
        {% if notes %}
        <table class="w-full text-sm">
            <thead class="sticky top-0 bg-panel/95 border-b border-border-subtle">
                <tr class="text-left text-zinc-400">
                    <th class="px-4 py-2 font-medium">Title</th>
                    <th class="px-4 py-2 font-medium">Created By</th>
                    <th class="px-4 py-2 font-medium">Last Modified</th>
                    <th class="px-4 py-2 font-medium">Modified By</th>
                    <th class="px-4 py-2 font-medium w-20">Privacy</th>
                </tr>
            </thead>
            <tbody>
                {% for note in notes %}
                <tr hx-get="{% url 'note_detail_drawer' note.pk %}"
                    hx-target="#slide-over"
                    hx-swap="innerHTML"
                    hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                    class="border-b border-border-subtle hover:bg-elevated/30 cursor-pointer transition-colors">
                    <td class="px-4 py-3 text-zinc-100">
                        {{ note.title }}
                    </td>
                    <td class="px-4 py-3 text-zinc-300">
                        {{ note.created_by.get_full_name|default:note.created_by.username }}
                    </td>
                    <td class="px-4 py-3 text-zinc-400">
                        {{ note.updated_at|date:"M d, Y g:i A" }}
                    </td>
                    <td class="px-4 py-3 text-zinc-300">
                        {{ note.modified_by.get_full_name|default:note.modified_by.username }}
                    </td>
                    <td class="px-4 py-3">
                        {% if note.is_private %}
                        <span class="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-elevated rounded-card text-zinc-400">
                            <i data-lucide="lock" class="w-3 h-3"></i>
                            Private
                        </span>
                        {% else %}
                        <span class="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-elevated rounded-card text-zinc-400">
                            <i data-lucide="globe" class="w-3 h-3"></i>
                            Public
                        </span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="p-8 text-center text-zinc-500">
            <i data-lucide="sticky-note" class="w-12 h-12 mx-auto mb-3 opacity-50"></i>
            <p>No notes yet</p>
        </div>
        {% endif %}
    </div>
</div>
```

**Step 3: Verify template syntax**

Run: `python manage.py check --deploy`
Expected: No template errors

**Step 4: Commit**

```bash
git add templates/notes/
git commit -m "feat: add notes list template

Table view with activity-based sorting and privacy indicators.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Create Note Detail Drawer Template

**Files:**
- Create: `templates/notes/partials/note_detail_drawer.html`

**Step 1: Write detail drawer template**

Create `templates/notes/partials/note_detail_drawer.html`:
```html
<div class="flex flex-col h-full">
    <!-- Header -->
    <div class="flex-shrink-0 px-4 py-3 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <i data-lucide="sticky-note" class="w-4 h-4"></i>
                <h2 class="text-sm font-medium text-zinc-100">Note Details</h2>
            </div>
            <button onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="text-zinc-400 hover:text-zinc-100">
                <i data-lucide="x" class="w-4 h-4"></i>
            </button>
        </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-4 space-y-4">
        <!-- Title -->
        <div>
            <div class="flex items-center justify-between mb-2">
                <label class="text-xs text-zinc-500 uppercase tracking-wide">Title</label>
                {% if note.is_private %}
                <span class="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-elevated rounded-card text-zinc-400">
                    <i data-lucide="lock" class="w-3 h-3"></i>
                    Private
                </span>
                {% endif %}
            </div>
            <p class="text-sm text-zinc-100">{{ note.title }}</p>
        </div>

        <!-- Description -->
        <div>
            <label class="text-xs text-zinc-500 uppercase tracking-wide mb-2 block">Description</label>
            <div class="text-sm text-zinc-300 whitespace-pre-wrap">{{ note.description|default:"No description" }}</div>
        </div>

        <!-- Metadata -->
        <div class="pt-4 border-t border-border-subtle space-y-2 text-xs text-zinc-500">
            <div class="flex justify-between">
                <span>Created by:</span>
                <span class="text-zinc-300">{{ note.created_by.get_full_name|default:note.created_by.username }}</span>
            </div>
            <div class="flex justify-between">
                <span>Created:</span>
                <span class="text-zinc-300">{{ note.created_at|date:"M d, Y g:i A" }}</span>
            </div>
            <div class="flex justify-between">
                <span>Last modified by:</span>
                <span class="text-zinc-300">{{ note.modified_by.get_full_name|default:note.modified_by.username }}</span>
            </div>
            <div class="flex justify-between">
                <span>Last modified:</span>
                <span class="text-zinc-300">{{ note.updated_at|date:"M d, Y g:i A" }}</span>
            </div>
        </div>
    </div>

    <!-- Footer Actions -->
    <div class="flex-shrink-0 px-4 py-3 border-t border-border-subtle bg-panel/80">
        <div class="flex gap-3">
            {% if can_modify %}
            <button hx-get="{% url 'note_edit_drawer' note.pk %}"
                    hx-target="#slide-over"
                    hx-swap="innerHTML"
                    class="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-card text-sm transition-colors">
                <i data-lucide="pencil" class="w-4 h-4"></i>
                Edit
            </button>
            <button hx-post="{% url 'note_delete' note.pk %}"
                    hx-target="#notes-list"
                    hx-swap="innerHTML"
                    hx-confirm="Are you sure you want to delete this note?"
                    class="px-4 py-2 bg-elevated hover:bg-red-600/20 text-red-400 hover:text-red-300 rounded-card text-sm transition-colors">
                Delete
            </button>
            {% endif %}
        </div>
    </div>
</div>
```

**Step 2: Commit**

```bash
git add templates/notes/partials/note_detail_drawer.html
git commit -m "feat: add note detail drawer template

Read-only view with metadata and edit/delete actions.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Create Note Create Drawer Template

**Files:**
- Create: `templates/notes/partials/note_create_drawer.html`

**Step 1: Write create drawer template**

Create `templates/notes/partials/note_create_drawer.html`:
```html
<div class="flex flex-col h-full">
    <!-- Header -->
    <div class="flex-shrink-0 px-4 py-3 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <i data-lucide="plus" class="w-4 h-4"></i>
                <h2 class="text-sm font-medium text-zinc-100">Create Note</h2>
            </div>
            <button onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="text-zinc-400 hover:text-zinc-100">
                <i data-lucide="x" class="w-4 h-4"></i>
            </button>
        </div>
    </div>

    <!-- Form -->
    <form hx-post="{% url parent_type|add:'_note_create_drawer' parent.pk %}"
          hx-target="#notes-list"
          hx-swap="innerHTML"
          class="flex-1 flex flex-col overflow-hidden">
        {% csrf_token %}

        <div class="flex-1 overflow-y-auto p-4 space-y-4">
            <!-- Title -->
            <div>
                <label for="title" class="text-xs text-zinc-500 uppercase tracking-wide mb-2 block">
                    Title <span class="text-red-400">*</span>
                </label>
                <input type="text"
                       id="title"
                       name="title"
                       required
                       class="w-full px-3 py-2 bg-elevated border border-border-subtle rounded-card text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                       placeholder="Enter note title">
            </div>

            <!-- Description -->
            <div>
                <label for="description" class="text-xs text-zinc-500 uppercase tracking-wide mb-2 block">
                    Description
                </label>
                <textarea id="description"
                          name="description"
                          rows="8"
                          class="w-full px-3 py-2 bg-elevated border border-border-subtle rounded-card text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                          placeholder="Enter note description..."></textarea>
            </div>

            <!-- Privacy Toggle -->
            <div class="flex items-center gap-3 p-3 bg-elevated/50 rounded-card border border-border-subtle">
                <input type="checkbox"
                       id="is_private"
                       name="is_private"
                       class="w-4 h-4 bg-elevated border-border-subtle rounded text-purple-600 focus:ring-2 focus:ring-purple-500">
                <label for="is_private" class="text-sm text-zinc-300 flex items-center gap-2">
                    <i data-lucide="lock" class="w-4 h-4"></i>
                    Make this note private
                    <span class="text-xs text-zinc-500">(Only you and admins can view)</span>
                </label>
            </div>
        </div>

        <!-- Footer Actions -->
        <div class="flex-shrink-0 px-4 py-3 border-t border-border-subtle bg-panel/80">
            <div class="flex gap-3">
                <button type="submit"
                        class="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-card text-sm transition-colors">
                    <i data-lucide="check" class="w-4 h-4"></i>
                    Create Note
                </button>
                <button type="button"
                        onclick="document.getElementById('slide-over').classList.add('hidden')"
                        class="px-4 py-2 bg-elevated hover:bg-elevated/80 text-zinc-300 rounded-card text-sm transition-colors">
                    Cancel
                </button>
            </div>
        </div>
    </form>
</div>
```

**Step 2: Commit**

```bash
git add templates/notes/partials/note_create_drawer.html
git commit -m "feat: add note create drawer template

Form with title, description, and privacy toggle.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Create Note Edit Drawer Template

**Files:**
- Create: `templates/notes/partials/note_edit_drawer.html`

**Step 1: Write edit drawer template**

Create `templates/notes/partials/note_edit_drawer.html`:
```html
<div class="flex flex-col h-full">
    <!-- Header -->
    <div class="flex-shrink-0 px-4 py-3 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <i data-lucide="pencil" class="w-4 h-4"></i>
                <h2 class="text-sm font-medium text-zinc-100">Edit Note</h2>
            </div>
            <button onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="text-zinc-400 hover:text-zinc-100">
                <i data-lucide="x" class="w-4 h-4"></i>
            </button>
        </div>
    </div>

    <!-- Form -->
    <form hx-post="{% url 'note_edit_drawer' note.pk %}"
          hx-target="#slide-over"
          hx-swap="innerHTML"
          class="flex-1 flex flex-col overflow-hidden">
        {% csrf_token %}

        <div class="flex-1 overflow-y-auto p-4 space-y-4">
            <!-- Title -->
            <div>
                <label for="title" class="text-xs text-zinc-500 uppercase tracking-wide mb-2 block">
                    Title <span class="text-red-400">*</span>
                </label>
                <input type="text"
                       id="title"
                       name="title"
                       value="{{ note.title }}"
                       required
                       class="w-full px-3 py-2 bg-elevated border border-border-subtle rounded-card text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                       placeholder="Enter note title">
            </div>

            <!-- Description -->
            <div>
                <label for="description" class="text-xs text-zinc-500 uppercase tracking-wide mb-2 block">
                    Description
                </label>
                <textarea id="description"
                          name="description"
                          rows="8"
                          class="w-full px-3 py-2 bg-elevated border border-border-subtle rounded-card text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                          placeholder="Enter note description...">{{ note.description }}</textarea>
            </div>

            <!-- Privacy Toggle -->
            <div class="flex items-center gap-3 p-3 bg-elevated/50 rounded-card border border-border-subtle">
                <input type="checkbox"
                       id="is_private"
                       name="is_private"
                       {% if note.is_private %}checked{% endif %}
                       class="w-4 h-4 bg-elevated border-border-subtle rounded text-purple-600 focus:ring-2 focus:ring-purple-500">
                <label for="is_private" class="text-sm text-zinc-300 flex items-center gap-2">
                    <i data-lucide="lock" class="w-4 h-4"></i>
                    Make this note private
                    <span class="text-xs text-zinc-500">(Only you and admins can view)</span>
                </label>
            </div>
        </div>

        <!-- Footer Actions -->
        <div class="flex-shrink-0 px-4 py-3 border-t border-border-subtle bg-panel/80">
            <div class="flex gap-3">
                <button type="submit"
                        class="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-card text-sm transition-colors">
                    <i data-lucide="check" class="w-4 h-4"></i>
                    Save Changes
                </button>
                <button type="button"
                        hx-get="{% url 'note_detail_drawer' note.pk %}"
                        hx-target="#slide-over"
                        hx-swap="innerHTML"
                        class="px-4 py-2 bg-elevated hover:bg-elevated/80 text-zinc-300 rounded-card text-sm transition-colors">
                    Cancel
                </button>
            </div>
        </div>
    </form>
</div>
```

**Step 2: Commit**

```bash
git add templates/notes/partials/note_edit_drawer.html
git commit -m "feat: add note edit drawer template

Edit form with pre-filled values and cancel to detail view.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Integrate Notes Tab into Client Detail

**Files:**
- Modify: `apps/clients/urls.py`
- Modify: `apps/clients/views.py`
- Modify: `templates/clients/client_detail.html`

**Step 1: Add notes URL to clients**

Edit `apps/clients/urls.py`, add this line to the urlpatterns list:
```python
path('<int:pk>/notes/', views.client_detail, name='client_detail_notes'),
```

**Step 2: Update client_detail view to handle notes tab**

Edit `apps/clients/views.py`, find the `client_detail` function and update the tab detection:
```python
# Determine active tab from URL
url_name = request.resolver_match.url_name
if url_name == 'client_detail_todos':
    active_tab = 'todos'
elif url_name == 'client_detail_projects':
    active_tab = 'projects'
elif url_name == 'client_detail_notes':
    active_tab = 'notes'
else:
    active_tab = 'profile'
```

**Step 3: Add notes tab to client_detail.html sidebar**

Find the right sidebar navigation in `templates/clients/client_detail.html` and add the notes tab link (after the todos link):
```html
<a href="{% url 'client_detail_notes' client.pk %}"
   class="w-full flex items-center gap-3 px-3 py-2 rounded-card text-sm transition-colors {% if active_tab == 'notes' %}bg-elevated text-zinc-100{% else %}text-zinc-400 hover:bg-elevated/50{% endif %}">
    <i data-lucide="sticky-note" class="w-4 h-4"></i>
    Notes
</a>
```

**Step 4: Add notes tab content area**

Find the main content section and add notes tab content (after the todos section):
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

**Step 5: Verify changes compile**

Run: `python manage.py check`
Expected: No issues

**Step 6: Commit**

```bash
git add apps/clients/urls.py apps/clients/views.py templates/clients/client_detail.html
git commit -m "feat: integrate notes tab into client detail page

Add notes navigation and content area to client detail view.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 12: Integrate Notes Tab into Project Detail

**Files:**
- Modify: `apps/projects/urls.py`
- Modify: `apps/projects/views.py`
- Modify: `templates/projects/project_detail.html`

**Step 1: Add notes URL to projects**

Edit `apps/projects/urls.py`, add this line to the urlpatterns list:
```python
path('<int:pk>/detail/notes/', views.project_detail, name='project_detail_notes'),
```

**Step 2: Update project_detail view to handle notes tab**

Edit `apps/projects/views.py`, find the `project_detail` function and update the tab detection to include notes (similar pattern to clients):
```python
# Determine active tab from URL
url_name = request.resolver_match.url_name
if url_name == 'project_detail_tasks':
    active_tab = 'tasks'
elif url_name == 'project_detail_notes':
    active_tab = 'notes'
else:
    active_tab = 'overview'
```

**Step 3: Add notes tab to project_detail.html sidebar**

Find the right sidebar navigation in `templates/projects/project_detail.html` and add the notes tab link:
```html
<a href="{% url 'project_detail_notes' project.pk %}"
   class="w-full flex items-center gap-3 px-3 py-2 rounded-card text-sm transition-colors {% if active_tab == 'notes' %}bg-elevated text-zinc-100{% else %}text-zinc-400 hover:bg-elevated/50{% endif %}">
    <i data-lucide="sticky-note" class="w-4 h-4"></i>
    Notes
</a>
```

**Step 4: Add notes tab content area**

Find the main content section and add notes tab content:
```html
{% if active_tab == 'notes' %}
    <div hx-get="{% url 'project_notes_list' project.pk %}"
         hx-trigger="load"
         hx-swap="innerHTML"
         class="h-full">
        <div class="flex items-center justify-center h-full">
            <div class="text-zinc-500">Loading notes...</div>
        </div>
    </div>
{% endif %}
```

**Step 5: Verify changes compile**

Run: `python manage.py check`
Expected: No issues

**Step 6: Commit**

```bash
git add apps/projects/urls.py apps/projects/views.py templates/projects/project_detail.html
git commit -m "feat: integrate notes tab into project detail page

Add notes navigation and content area to project detail view.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 13: Manual Testing

**Files:**
- None (testing only)

**Step 1: Start development server**

Run: `python manage.py runserver`
Expected: Server starts on `http://127.0.0.1:8000/`

**Step 2: Test client notes (admin user)**

1. Navigate to a client detail page
2. Click "Notes" tab
3. Click "Add Note"
4. Fill in title, description, toggle privacy
5. Submit form
6. Verify note appears in list
7. Click note row to view details
8. Click "Edit" button
9. Modify note and save
10. Verify updates appear in list (real-time)
11. Delete the note
12. Verify it disappears from list

**Step 3: Test project notes (editor user)**

1. Create a test project with ProjectMember as 'editor'
2. Login as that user
3. Navigate to project detail page
4. Click "Notes" tab
5. Repeat create/edit/delete flow
6. Verify permissions work correctly

**Step 4: Test privacy controls**

1. Create a private note
2. Log in as different user (non-admin, project member)
3. Verify they cannot see the private note
4. Create a public note
5. Verify other project members can see it

**Step 5: Test permission boundaries**

1. As project viewer, verify "Add Note" button is hidden
2. As non-member, verify 403 on notes list access
3. As note creator, verify can edit own notes
4. As admin, verify can edit any notes

**Step 6: Stop development server**

Press: `Ctrl+C`

---

## Completion Checklist

After all tasks complete, verify:

- [ ] Notes app appears in Django admin
- [ ] Client notes tab displays and loads notes
- [ ] Project notes tab displays and loads notes
- [ ] Create note drawer opens and saves notes
- [ ] Detail drawer displays note information
- [ ] Edit drawer updates notes in real-time
- [ ] Delete removes notes and updates list
- [ ] Privacy toggle works (private vs public)
- [ ] Permissions enforce correctly
- [ ] HTMX updates happen without page refresh
- [ ] Out-of-band swaps update both drawer and list
- [ ] Notes sorted by most recently modified first
- [ ] Empty state shows when no notes exist
- [ ] Icons render correctly (Lucide)
- [ ] No console errors in browser
- [ ] No server errors in Django logs

---

**Implementation Complete!**

All tasks implement the Notes app according to the design document. The app provides full CRUD functionality with authorization, HTMX-powered UI, and seamless integration into client and project detail pages.

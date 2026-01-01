# To-Dos App Design

**Goal:** Create a lightweight to-do system for quick action items and client relationship tasks, separate from project tasks.

**Date:** 2026-01-01

**Environment:** Use `.venv` for all Python commands (e.g., `.venv/bin/python manage.py makemigrations`)

---

## Overview

To-Dos are simple, personal tasks that can be:
- **Personal** - General work tasks not tied to any client
- **Client-linked** - Action items related to a specific client

They are intentionally lightweight compared to project tasks - no workflow, no statuses, just done/not done.

---

## Key Decisions

| Decision | Choice |
|----------|--------|
| Complexity | Simple: title, description, due date, completed |
| Client linking | Separate flows: client profile vs My Tasks |
| Naming | "To-Dos" |
| Visibility | Private - each user sees only their own |
| Completion | Hidden by default, show with filter toggle |
| Architecture | New `todos` app (separate from `tasks`) |

---

## Data Model

**Todo Model** (`apps/todos/models.py`):

```python
from django.conf import settings
from django.db import models
from apps.clients.models import Client


class Todo(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='todos'
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='todos'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['is_completed', 'due_date', '-created_at']

    def __str__(self):
        return self.title
```

**Fields:**
- `owner` - User who created the to-do (enforces privacy)
- `client` - Optional. If null = personal to-do. If set = client to-do.
- `title` - Required, what needs to be done
- `description` - Optional, additional details
- `due_date` - Optional, when it's due
- `is_completed` - Checkbox state
- `completed_at` - When it was marked done (for "completed today" filtering)

---

## URLs & Views

**URL Structure** (`apps/todos/urls.py`):

| URL | View | Method | Purpose |
|-----|------|--------|---------|
| `/todos/` | `todo_list` | GET | Personal to-dos list (HTMX partial) |
| `/todos/create/` | `todo_create` | GET/POST | Create personal to-do (drawer) |
| `/todos/<pk>/` | `todo_detail` | GET | View/edit to-do (drawer) |
| `/todos/<pk>/edit/` | `todo_edit` | POST | Update to-do |
| `/todos/<pk>/toggle/` | `todo_toggle` | POST | Toggle completed (HTMX) |
| `/todos/<pk>/delete/` | `todo_delete` | POST | Delete to-do |
| `/clients/<pk>/todos/` | `client_todo_list` | GET | Client's to-dos (HTMX partial) |
| `/clients/<pk>/todos/create/` | `client_todo_create` | GET/POST | Create client to-do (drawer) |

**Privacy:** All views filter by `owner=request.user`. Users can only see/edit their own to-dos.

---

## UI Components

### Client Profile - To-Dos Tab

**Sidebar Navigation:**
```
Navigation
─────────────────
[user] Profile
[folder] Projects     [3]
[check-square] To-Dos [5]  ← NEW
```

**Tab Content:**
- Header: "To-Dos" + "Add To-Do" button
- Filter toggle: "Show completed" (off by default)
- List of to-dos (owner's only, for this client)

### My Tasks Page - To-Dos Section

**Tab Structure:**
```
[Assigned Tasks] [To-Dos]  ← NEW TAB
```

**To-Dos Tab Content:**
- "Add To-Do" button
- Filter toggle: "Show completed"
- List of personal to-dos (no client) + all client to-dos

### To-Do List Item

```
┌─────────────────────────────────────────────────────────┐
│ [○] Call John about renewal                    Jan 5   │
│     Test1111                                           │
└─────────────────────────────────────────────────────────┘
```

- Checkbox on left (click to toggle)
- Title (click to open drawer)
- Due date on right (colored if overdue)
- Client name below title (muted, only if client-linked)
- Completed items: strikethrough title, muted styling

### To-Do Drawer

**Create Mode:**
- Title input (required)
- Description textarea
- Due date picker
- Client dropdown (only from My Tasks; hidden/pre-filled from client profile)
- "Create" button

**Edit Mode:**
- Same fields as create
- Completed checkbox
- "Save" and "Delete" buttons

---

## Files to Create

```
apps/todos/
├── __init__.py
├── admin.py
├── apps.py
├── models.py
├── views.py
├── urls.py
├── forms.py
└── factories.py

apps/todos/tests/
├── __init__.py
├── test_models.py
└── test_views.py

templates/todos/
└── partials/
    ├── todo_item.html
    ├── todo_list.html
    └── todo_drawer.html

templates/clients/partials/
└── todos_content.html
```

## Files to Modify

| File | Change |
|------|--------|
| `config/settings.py` | Add `'apps.todos'` to INSTALLED_APPS |
| `config/urls.py` | Include `apps.todos.urls` |
| `templates/clients/client_detail.html` | Add To-Dos tab to sidebar navigation |
| `apps/clients/views.py` | Add `todo_count` to client_detail context |
| `templates/tasks/my_tasks.html` | Add To-Dos tab/section |
| `apps/tasks/views.py` | Add user's todos to my_tasks context |

---

## Out of Scope (YAGNI)

These features are intentionally excluded to keep to-dos lightweight:

- Priority levels
- Assignee (owner is always creator)
- Labels/tags
- Subtasks
- Comments
- Activity tracking
- Attachments
- Recurring to-dos
- Reminders/notifications

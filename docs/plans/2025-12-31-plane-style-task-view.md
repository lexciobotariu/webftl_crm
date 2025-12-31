# Plane.so Style Task View Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign task detail view with Plane.so/Notion-style properties panel, drawer + full page views, and activity log.

**Architecture:** Shared components between drawer and full page views. TaskActivity model for auto-tracking changes. Inline dropdowns for property editing.

**Tech Stack:** Django models + signals, HTMX for inline editing, Alpine.js for dropdowns, Tailwind CSS

---

## Design Overview

**Drawer View (quick peek):**
```
┌─────────────────────────────────────┐
│ ← PROJ-123  test task    [↗] [×]   │  <- Header with expand button
├─────────────────────────────────────┤
│ Click to add description...         │  <- Editable description
│                                     │
│ ─────────────────────────────────── │
│ Properties                          │
│ ○ State      │ Backlog        [▼]  │  <- Inline dropdowns
│ 👤 Assignee  │ Add assignee   [▼]  │
│ ⚡ Priority  │ None           [▼]  │
│ 📅 Due date  │ Add due date   [▼]  │
│ 🏷 Labels    │ + Add labels        │
│ ⏱ Estimate  │ Add estimate        │
│ ─────────────────────────────────── │
│ Activity                            │
│ • John changed status: Todo → Done  │  <- Activity log
│ • Jane commented: "Looks good!"     │
│ [Add comment...]                    │
└─────────────────────────────────────┘
```

**Full Page View (deep dive):**
```
┌──────────────────────────────────────────────────────────────┐
│ Projects > Project Name > PROJ-123                           │  <- Breadcrumb
├────────────────────────────────────────┬─────────────────────┤
│                                        │ Properties          │
│ PROJ-123                               │ ○ State    Backlog  │
│ test task                              │ 👤 Assignee  -      │
│ Click to add description...            │ ⚡ Priority  None   │
│                                        │ 📅 Due date  -      │
│ ─────────────────────────             │ 🏷 Labels    -      │
│ Subtasks (2/5)                         │ ⏱ Estimate  -      │
│ ☑ Do thing 1                          │                     │
│ ☐ Do thing 2                          ├─────────────────────┤
│                                        │ Activity            │
│ ─────────────────────────             │ • Status changed    │
│ Activity                               │ • Comment added     │
│ [Comment input with rich formatting]   │                     │
└────────────────────────────────────────┴─────────────────────┘
```

---

### Task 1: Create TaskActivity Model

**Files:**
- Modify: `apps/tasks/models.py`
- Create migration

**Step 1: Add TaskActivity model**

```python
class TaskActivity(models.Model):
    """Tracks activity on tasks - comments, status changes, etc."""
    ACTIVITY_TYPES = [
        ('comment', 'Comment'),
        ('status_change', 'Status Changed'),
        ('assignee_change', 'Assignee Changed'),
        ('priority_change', 'Priority Changed'),
        ('created', 'Created'),
        ('due_date_change', 'Due Date Changed'),
        ('label_added', 'Label Added'),
        ('label_removed', 'Label Removed'),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    content = models.TextField(blank=True)  # For comments or description of change
    old_value = models.CharField(max_length=255, blank=True)  # e.g., "Todo"
    new_value = models.CharField(max_length=255, blank=True)  # e.g., "In Progress"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_activity_type_display()} on {self.task}"
```

**Step 2: Run migration**

```bash
python manage.py makemigrations tasks
python manage.py migrate
```

---

### Task 2: Add Django Signals for Activity Tracking

**Files:**
- Create: `apps/tasks/signals.py`
- Modify: `apps/tasks/apps.py`

**Step 1: Create signals.py**

```python
from django.db.models.signals import pre_save, post_save, m2m_changed
from django.dispatch import receiver
from .models import Task, TaskActivity


@receiver(pre_save, sender=Task)
def track_task_changes(sender, instance, **kwargs):
    """Store old values before save for comparison."""
    if instance.pk:
        try:
            old_task = Task.objects.get(pk=instance.pk)
            instance._old_status = old_task.status
            instance._old_assignee = old_task.assignee
            instance._old_priority = old_task.priority
            instance._old_due_date = old_task.due_date
        except Task.DoesNotExist:
            pass


@receiver(post_save, sender=Task)
def log_task_changes(sender, instance, created, **kwargs):
    """Log changes to TaskActivity after save."""
    user = getattr(instance, '_changed_by', None)

    if created:
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='created',
            content='created this task'
        )
        return

    # Check what changed
    if hasattr(instance, '_old_status') and instance._old_status != instance.status:
        old_name = instance._old_status.name if instance._old_status else 'None'
        new_name = instance.status.name if instance.status else 'None'
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='status_change',
            old_value=old_name,
            new_value=new_name,
            content=f'changed status from {old_name} to {new_name}'
        )

    if hasattr(instance, '_old_assignee') and instance._old_assignee != instance.assignee:
        old_name = instance._old_assignee.name if instance._old_assignee else 'Unassigned'
        new_name = instance.assignee.name if instance.assignee else 'Unassigned'
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='assignee_change',
            old_value=old_name,
            new_value=new_name,
            content=f'changed assignee from {old_name} to {new_name}'
        )

    if hasattr(instance, '_old_priority') and instance._old_priority != instance.priority:
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='priority_change',
            old_value=instance._old_priority or 'None',
            new_value=instance.priority or 'None',
            content=f'changed priority to {instance.get_priority_display() or "None"}'
        )

    if hasattr(instance, '_old_due_date') and instance._old_due_date != instance.due_date:
        old_date = instance._old_due_date.strftime('%b %d') if instance._old_due_date else 'None'
        new_date = instance.due_date.strftime('%b %d') if instance.due_date else 'None'
        TaskActivity.objects.create(
            task=instance,
            user=user,
            activity_type='due_date_change',
            old_value=old_date,
            new_value=new_date,
            content=f'changed due date to {new_date}'
        )
```

**Step 2: Register signals in apps.py**

```python
class TasksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.tasks'

    def ready(self):
        import apps.tasks.signals  # noqa
```

---

### Task 3: Create Shared Property Components

**Files:**
- Create: `templates/tasks/partials/property_row.html`
- Create: `templates/tasks/partials/properties_panel.html`

**Step 1: Create property_row.html (single property row)**

```html
{# Usage: {% include "tasks/partials/property_row.html" with icon="circle" label="State" value=task.status.name field="status" %} #}
<div class="flex items-center py-2 hover:bg-hover rounded-card group">
    <div class="flex items-center gap-2 w-32 text-zinc-500 text-sm">
        <i data-lucide="{{ icon }}" class="w-4 h-4"></i>
        <span>{{ label }}</span>
    </div>
    <div class="flex-1">
        {% block property_value %}
        <button class="text-sm text-zinc-300 hover:text-zinc-100 hover:bg-elevated px-2 py-1 rounded-card transition-colors"
                hx-get="{% url 'task_property_edit' task.pk field %}"
                hx-target="closest div"
                hx-swap="innerHTML">
            {{ value|default:placeholder }}
        </button>
        {% endblock %}
    </div>
</div>
```

**Step 2: Create properties_panel.html**

```html
<div class="space-y-1">
    <h3 class="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">Properties</h3>

    <!-- Status -->
    <div class="flex items-center py-2 hover:bg-hover rounded-card" id="prop-status-{{ task.pk }}">
        <div class="flex items-center gap-2 w-32 text-zinc-500 text-sm">
            <i data-lucide="circle" class="w-4 h-4"></i>
            <span>State</span>
        </div>
        <div class="flex-1" id="status-value-{{ task.pk }}">
            {% include "tasks/partials/status_dropdown.html" %}
        </div>
    </div>

    <!-- Assignee -->
    <div class="flex items-center py-2 hover:bg-hover rounded-card" id="prop-assignee-{{ task.pk }}">
        <div class="flex items-center gap-2 w-32 text-zinc-500 text-sm">
            <i data-lucide="user" class="w-4 h-4"></i>
            <span>Assignee</span>
        </div>
        <div class="flex-1" id="assignee-value-{{ task.pk }}">
            {% include "tasks/partials/assignee_dropdown.html" %}
        </div>
    </div>

    <!-- Priority -->
    <div class="flex items-center py-2 hover:bg-hover rounded-card" id="prop-priority-{{ task.pk }}">
        <div class="flex items-center gap-2 w-32 text-zinc-500 text-sm">
            <i data-lucide="signal" class="w-4 h-4"></i>
            <span>Priority</span>
        </div>
        <div class="flex-1" id="priority-value-{{ task.pk }}">
            {% include "tasks/partials/priority_dropdown.html" %}
        </div>
    </div>

    <!-- Due Date -->
    <div class="flex items-center py-2 hover:bg-hover rounded-card" id="prop-due-date-{{ task.pk }}">
        <div class="flex items-center gap-2 w-32 text-zinc-500 text-sm">
            <i data-lucide="calendar" class="w-4 h-4"></i>
            <span>Due date</span>
        </div>
        <div class="flex-1" id="due-date-value-{{ task.pk }}">
            {% include "tasks/partials/due_date_picker.html" %}
        </div>
    </div>

    <!-- Time Estimate -->
    <div class="flex items-center py-2 hover:bg-hover rounded-card" id="prop-estimate-{{ task.pk }}">
        <div class="flex items-center gap-2 w-32 text-zinc-500 text-sm">
            <i data-lucide="clock" class="w-4 h-4"></i>
            <span>Estimate</span>
        </div>
        <div class="flex-1" id="estimate-value-{{ task.pk }}">
            {% include "tasks/partials/estimate_input.html" %}
        </div>
    </div>

    <!-- Labels -->
    <div class="flex items-center py-2 hover:bg-hover rounded-card" id="prop-labels-{{ task.pk }}">
        <div class="flex items-center gap-2 w-32 text-zinc-500 text-sm">
            <i data-lucide="tag" class="w-4 h-4"></i>
            <span>Labels</span>
        </div>
        <div class="flex-1" id="labels-value-{{ task.pk }}">
            {% include "tasks/partials/labels_selector.html" %}
        </div>
    </div>
</div>
```

---

### Task 4: Create Property Dropdown Components

**Files:**
- Update: `templates/tasks/partials/status_dropdown.html` (already exists, update styling)
- Create: `templates/tasks/partials/assignee_dropdown.html`
- Create: `templates/tasks/partials/priority_dropdown.html`
- Create: `templates/tasks/partials/due_date_picker.html`
- Create: `templates/tasks/partials/estimate_input.html`
- Create: `templates/tasks/partials/labels_selector.html`

**Step 1: Create assignee_dropdown.html**

```html
<div class="relative" x-data="{ open: false }">
    <button @click="open = !open"
            class="flex items-center gap-2 px-2 py-1 rounded-card text-sm text-zinc-300 hover:bg-elevated transition-colors">
        {% if task.assignee %}
        <span class="w-5 h-5 rounded-full bg-accent/30 flex items-center justify-center text-[10px] text-accent">
            {{ task.assignee.name|slice:":1"|upper }}
        </span>
        <span>{{ task.assignee.name }}</span>
        {% else %}
        <span class="text-zinc-500">Add assignee</span>
        {% endif %}
    </button>
    <div x-show="open" @click.away="open = false"
         x-transition
         class="absolute left-0 top-full mt-1 w-56 bg-elevated border border-border-subtle rounded-card shadow-lg z-20 py-1">
        <button hx-post="{% url 'task_update_assignee' task.pk %}"
                hx-vals='{"assignee_id": ""}'
                hx-target="#assignee-value-{{ task.pk }}"
                hx-swap="innerHTML"
                class="w-full text-left px-3 py-2 text-sm text-zinc-400 hover:bg-hover-strong transition-colors">
            Unassigned
        </button>
        {% for user in team_members %}
        <button hx-post="{% url 'task_update_assignee' task.pk %}"
                hx-vals='{"assignee_id": "{{ user.pk }}"}'
                hx-target="#assignee-value-{{ task.pk }}"
                hx-swap="innerHTML"
                class="w-full text-left px-3 py-2 text-sm hover:bg-hover-strong transition-colors flex items-center gap-2 {% if user.pk == task.assignee_id %}text-accent{% else %}text-zinc-300{% endif %}">
            <span class="w-5 h-5 rounded-full bg-accent/30 flex items-center justify-center text-[10px] text-accent">
                {{ user.name|slice:":1"|upper }}
            </span>
            {{ user.name }}
        </button>
        {% endfor %}
    </div>
</div>
```

**Step 2: Create priority_dropdown.html**

```html
<div class="relative" x-data="{ open: false }">
    <button @click="open = !open"
            class="flex items-center gap-2 px-2 py-1 rounded-card text-sm hover:bg-elevated transition-colors
                   {% if task.priority == 'urgent' %}text-red-400
                   {% elif task.priority == 'high' %}text-orange-400
                   {% elif task.priority == 'medium' %}text-yellow-400
                   {% else %}text-zinc-400{% endif %}">
        {% if task.priority %}
        <i data-lucide="signal" class="w-3.5 h-3.5"></i>
        {{ task.get_priority_display }}
        {% else %}
        <span class="text-zinc-500">None</span>
        {% endif %}
    </button>
    <div x-show="open" @click.away="open = false"
         x-transition
         class="absolute left-0 top-full mt-1 w-40 bg-elevated border border-border-subtle rounded-card shadow-lg z-20 py-1">
        {% for value, label in priority_choices %}
        <button hx-post="{% url 'task_update_priority' task.pk %}"
                hx-vals='{"priority": "{{ value }}"}'
                hx-target="#priority-value-{{ task.pk }}"
                hx-swap="innerHTML"
                class="w-full text-left px-3 py-2 text-sm hover:bg-hover-strong transition-colors
                       {% if value == task.priority %}text-accent{% else %}text-zinc-300{% endif %}">
            {{ label }}
        </button>
        {% endfor %}
    </div>
</div>
```

**Step 3: Create due_date_picker.html**

```html
<div class="relative" x-data="{ open: false }">
    <button @click="open = !open"
            class="flex items-center gap-2 px-2 py-1 rounded-card text-sm text-zinc-300 hover:bg-elevated transition-colors">
        {% if task.due_date %}
        <i data-lucide="calendar" class="w-3.5 h-3.5 text-zinc-500"></i>
        {{ task.due_date|date:"M d, Y" }}
        {% else %}
        <span class="text-zinc-500">Add due date</span>
        {% endif %}
    </button>
    <div x-show="open" @click.away="open = false"
         x-transition
         class="absolute left-0 top-full mt-1 bg-elevated border border-border-subtle rounded-card shadow-lg z-20 p-3">
        <form hx-post="{% url 'task_update_due_date' task.pk %}"
              hx-target="#due-date-value-{{ task.pk }}"
              hx-swap="innerHTML"
              @submit="open = false">
            {% csrf_token %}
            <input type="date" name="due_date" value="{{ task.due_date|date:'Y-m-d' }}"
                   class="bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:outline-none">
            <div class="flex gap-2 mt-2">
                <button type="submit" class="bg-accent text-white px-3 py-1 rounded-card text-xs">Save</button>
                {% if task.due_date %}
                <button type="button"
                        hx-post="{% url 'task_update_due_date' task.pk %}"
                        hx-vals='{"due_date": ""}'
                        hx-target="#due-date-value-{{ task.pk }}"
                        hx-swap="innerHTML"
                        class="text-zinc-400 hover:text-red-400 px-3 py-1 text-xs">Clear</button>
                {% endif %}
            </div>
        </form>
    </div>
</div>
```

**Step 4: Create estimate_input.html**

```html
<div class="relative" x-data="{ open: false }">
    <button @click="open = !open"
            class="flex items-center gap-2 px-2 py-1 rounded-card text-sm text-zinc-300 hover:bg-elevated transition-colors">
        {% if task.time_estimate %}
        {{ task.time_estimate }}h
        {% else %}
        <span class="text-zinc-500">Add estimate</span>
        {% endif %}
    </button>
    <div x-show="open" @click.away="open = false"
         x-transition
         class="absolute left-0 top-full mt-1 bg-elevated border border-border-subtle rounded-card shadow-lg z-20 p-3">
        <form hx-post="{% url 'task_update_estimate' task.pk %}"
              hx-target="#estimate-value-{{ task.pk }}"
              hx-swap="innerHTML"
              @submit="open = false">
            {% csrf_token %}
            <input type="number" name="time_estimate" value="{{ task.time_estimate }}" step="0.5" min="0"
                   placeholder="Hours"
                   class="w-24 bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:outline-none">
            <button type="submit" class="bg-accent text-white px-3 py-1 rounded-card text-xs ml-2">Save</button>
        </form>
    </div>
</div>
```

**Step 5: Create labels_selector.html**

```html
<div class="relative" x-data="{ open: false }">
    <button @click="open = !open"
            class="flex items-center gap-1 px-2 py-1 rounded-card text-sm hover:bg-elevated transition-colors">
        {% if task.labels.exists %}
        {% for label in task.labels.all %}
        <span class="px-2 py-0.5 text-[10px] rounded-full border"
              style="background: {{ label.color }}20; color: {{ label.color }}; border-color: {{ label.color }}40;">
            {{ label.name }}
        </span>
        {% endfor %}
        {% else %}
        <span class="text-zinc-500 flex items-center gap-1">
            <i data-lucide="plus" class="w-3 h-3"></i>
            Add labels
        </span>
        {% endif %}
    </button>
    <div x-show="open" @click.away="open = false"
         x-transition
         class="absolute left-0 top-full mt-1 w-56 bg-elevated border border-border-subtle rounded-card shadow-lg z-20 py-1 max-h-64 overflow-y-auto">
        {% for label in project_labels %}
        <button hx-post="{% url 'task_toggle_label' task.pk label.pk %}"
                hx-target="#labels-value-{{ task.pk }}"
                hx-swap="innerHTML"
                class="w-full text-left px-3 py-2 text-sm hover:bg-hover-strong transition-colors flex items-center gap-2">
            <span class="w-3 h-3 rounded" style="background-color: {{ label.color }}"></span>
            <span class="{% if label in task.labels.all %}text-accent{% else %}text-zinc-300{% endif %}">{{ label.name }}</span>
            {% if label in task.labels.all %}
            <i data-lucide="check" class="w-3 h-3 text-accent ml-auto"></i>
            {% endif %}
        </button>
        {% endfor %}
    </div>
</div>
```

---

### Task 5: Create Activity Component

**Files:**
- Create: `templates/tasks/partials/activity_panel.html`
- Create: `templates/tasks/partials/activity_item.html`

**Step 1: Create activity_item.html**

```html
<div class="flex gap-3 py-3">
    <div class="flex-shrink-0">
        {% if activity.activity_type == 'comment' %}
        <span class="w-6 h-6 rounded-full bg-accent/30 flex items-center justify-center text-[10px] text-accent">
            {{ activity.user.name|slice:":1"|upper }}
        </span>
        {% else %}
        <span class="w-6 h-6 rounded-full bg-elevated flex items-center justify-center">
            <i data-lucide="{% if activity.activity_type == 'status_change' %}circle{% elif activity.activity_type == 'assignee_change' %}user{% elif activity.activity_type == 'priority_change' %}signal{% elif activity.activity_type == 'created' %}plus{% else %}edit{% endif %}"
               class="w-3 h-3 text-zinc-500"></i>
        </span>
        {% endif %}
    </div>
    <div class="flex-1 min-w-0">
        {% if activity.activity_type == 'comment' %}
        <div class="flex items-center gap-2 mb-1">
            <span class="text-sm font-medium text-zinc-200">{{ activity.user.name }}</span>
            <span class="text-xs text-zinc-500">{{ activity.created_at|timesince }} ago</span>
        </div>
        <div class="text-sm text-zinc-300">{{ activity.content|linebreaks }}</div>
        {% else %}
        <div class="flex items-center gap-2">
            <span class="text-sm text-zinc-400">
                <span class="text-zinc-300">{{ activity.user.name|default:"System" }}</span>
                {{ activity.content }}
            </span>
            <span class="text-xs text-zinc-500">{{ activity.created_at|timesince }} ago</span>
        </div>
        {% endif %}
    </div>
</div>
```

**Step 2: Create activity_panel.html**

```html
<div class="space-y-1">
    <h3 class="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">Activity</h3>

    <div id="activity-list-{{ task.pk }}" class="divide-y divide-border-subtle">
        {% for activity in task.activities.all %}
        {% include "tasks/partials/activity_item.html" %}
        {% empty %}
        <p class="text-sm text-zinc-500 py-3">No activity yet.</p>
        {% endfor %}
    </div>

    <!-- Comment input -->
    <form hx-post="{% url 'comment_create' task.pk %}"
          hx-target="#activity-list-{{ task.pk }}"
          hx-swap="afterbegin"
          hx-on::after-request="this.reset()"
          class="mt-4">
        {% csrf_token %}
        <textarea name="content" rows="2" placeholder="Add a comment..."
                  class="w-full bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-accent focus:outline-none resize-none"></textarea>
        <div class="flex justify-end mt-2">
            <button type="submit" class="bg-accent text-white px-3 py-1.5 rounded-card text-xs font-medium hover:bg-accent-hover transition-colors">
                Comment
            </button>
        </div>
    </form>
</div>
```

---

### Task 6: Create Drawer View Template

**Files:**
- Rewrite: `templates/tasks/task_detail.html`

**Full template:**

```html
<div class="flex flex-col h-full">
    <!-- Header -->
    <div class="flex-shrink-0 flex items-center justify-between px-4 py-3 border-b border-border-subtle">
        <div class="flex items-center gap-3">
            <button onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="text-zinc-500 hover:text-zinc-300 transition-colors">
                <i data-lucide="arrow-left" class="w-4 h-4"></i>
            </button>
            <span class="text-xs text-zinc-500 bg-elevated px-2 py-0.5 rounded border border-border-subtle">
                {{ task.project.name|slice:":4"|upper }}-{{ task.pk }}
            </span>
        </div>
        <div class="flex items-center gap-2">
            <a href="{% url 'task_full_page' task.project.pk task.pk %}"
               class="text-zinc-500 hover:text-zinc-300 transition-colors p-1.5 hover:bg-elevated rounded-card"
               title="Open full page">
                <i data-lucide="maximize-2" class="w-4 h-4"></i>
            </a>
            <button onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="text-zinc-500 hover:text-zinc-300 transition-colors p-1.5 hover:bg-elevated rounded-card">
                <i data-lucide="x" class="w-4 h-4"></i>
            </button>
        </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-4 space-y-6">
        <!-- Title -->
        <div>
            <h2 class="text-lg font-semibold text-zinc-100"
                contenteditable="true"
                hx-post="{% url 'task_update_title' task.pk %}"
                hx-trigger="blur"
                hx-vals="js:{title: event.target.innerText}"
                hx-swap="none">{{ task.title }}</h2>
        </div>

        <!-- Description -->
        <div class="text-sm text-zinc-400 cursor-pointer hover:text-zinc-300"
             hx-get="{% url 'task_edit_description' task.pk %}"
             hx-target="this"
             hx-swap="outerHTML">
            {% if task.description %}
            {{ task.description|linebreaks }}
            {% else %}
            <span class="italic">Click to add description...</span>
            {% endif %}
        </div>

        <!-- Properties -->
        <div class="border-t border-border-subtle pt-4">
            {% include "tasks/partials/properties_panel.html" %}
        </div>

        <!-- Subtasks -->
        {% if task.subtasks.exists or True %}
        <div class="border-t border-border-subtle pt-4">
            <h3 class="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">
                Subtasks {% if task.subtask_progress %}({{ task.subtask_progress }}){% endif %}
            </h3>
            <div id="subtask-list" class="space-y-2 mb-3">
                {% for subtask in task.subtasks.all %}
                {% include "tasks/partials/subtask_item.html" %}
                {% endfor %}
            </div>
            <form hx-post="{% url 'subtask_create' task.pk %}" hx-target="#subtask-list" hx-swap="beforeend"
                  hx-on::after-request="this.reset()"
                  class="flex items-center gap-2">
                {% csrf_token %}
                <i data-lucide="plus" class="w-4 h-4 text-zinc-500"></i>
                <input type="text" name="title" placeholder="Add subtask..."
                       class="flex-1 bg-transparent text-sm text-zinc-300 placeholder-zinc-500 focus:outline-none">
            </form>
        </div>
        {% endif %}

        <!-- Activity -->
        <div class="border-t border-border-subtle pt-4">
            {% include "tasks/partials/activity_panel.html" %}
        </div>
    </div>
</div>
<script>document.getElementById('slide-over').classList.remove('hidden');</script>
```

---

### Task 7: Create Full Page View Template

**Files:**
- Create: `templates/tasks/task_full_page.html`

**Full template:**

```html
{% extends "base.html" %}

{% block title %}{{ task.title }} - {{ task.project.name }}{% endblock %}

{% block full_content %}
<div class="flex flex-col h-full">
    <!-- Breadcrumb header -->
    <div class="flex-shrink-0 px-4 py-2 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-2 text-sm">
                <a href="{% url 'project_list' %}" class="text-zinc-500 hover:text-zinc-300">Projects</a>
                <i data-lucide="chevron-right" class="w-3 h-3 text-zinc-600"></i>
                <a href="{% url 'project_board' task.project.pk %}" class="text-zinc-500 hover:text-zinc-300">{{ task.project.name }}</a>
                <i data-lucide="chevron-right" class="w-3 h-3 text-zinc-600"></i>
                <span class="text-zinc-300">{{ task.project.name|slice:":4"|upper }}-{{ task.pk }}</span>
            </div>
            <div class="flex items-center gap-2">
                <button class="text-zinc-500 hover:text-zinc-300 p-1.5 hover:bg-elevated rounded-card">
                    <i data-lucide="link" class="w-4 h-4"></i>
                </button>
                <button hx-post="{% url 'task_delete' task.pk %}"
                        hx-confirm="Delete this task?"
                        class="text-zinc-500 hover:text-red-400 p-1.5 hover:bg-elevated rounded-card">
                    <i data-lucide="trash-2" class="w-4 h-4"></i>
                </button>
            </div>
        </div>
    </div>

    <!-- Main content with sidebar -->
    <div class="flex-1 flex overflow-hidden">
        <!-- Main content area -->
        <div class="flex-1 overflow-y-auto p-6">
            <div class="max-w-3xl">
                <!-- Task ID -->
                <div class="text-xs text-zinc-500 mb-2">
                    {{ task.project.name|slice:":4"|upper }}-{{ task.pk }}
                </div>

                <!-- Title -->
                <h1 class="text-2xl font-semibold text-zinc-100 mb-4"
                    contenteditable="true"
                    hx-post="{% url 'task_update_title' task.pk %}"
                    hx-trigger="blur"
                    hx-vals="js:{title: event.target.innerText}"
                    hx-swap="none">{{ task.title }}</h1>

                <!-- Description -->
                <div class="text-zinc-400 mb-6 cursor-pointer hover:text-zinc-300 min-h-[60px]"
                     hx-get="{% url 'task_edit_description' task.pk %}"
                     hx-target="this"
                     hx-swap="outerHTML">
                    {% if task.description %}
                    {{ task.description|linebreaks }}
                    {% else %}
                    <span class="italic text-zinc-500">Click to add description...</span>
                    {% endif %}
                </div>

                <!-- Subtasks -->
                <div class="mb-6">
                    <h3 class="text-sm font-semibold text-zinc-300 mb-3">
                        Subtasks {% if task.subtask_progress %}({{ task.subtask_progress }}){% endif %}
                    </h3>
                    <div id="subtask-list" class="space-y-2 mb-3">
                        {% for subtask in task.subtasks.all %}
                        {% include "tasks/partials/subtask_item.html" %}
                        {% endfor %}
                    </div>
                    <form hx-post="{% url 'subtask_create' task.pk %}" hx-target="#subtask-list" hx-swap="beforeend"
                          hx-on::after-request="this.reset()"
                          class="flex items-center gap-2 text-zinc-500 hover:text-zinc-300">
                        {% csrf_token %}
                        <i data-lucide="plus" class="w-4 h-4"></i>
                        <input type="text" name="title" placeholder="Add subtask..."
                               class="flex-1 bg-transparent text-sm placeholder-zinc-500 focus:outline-none">
                    </form>
                </div>

                <!-- Activity -->
                <div class="border-t border-border-subtle pt-6">
                    {% include "tasks/partials/activity_panel.html" %}
                </div>
            </div>
        </div>

        <!-- Properties sidebar -->
        <div class="w-72 flex-shrink-0 border-l border-border-subtle bg-card/50 p-4 overflow-y-auto">
            {% include "tasks/partials/properties_panel.html" %}
        </div>
    </div>
</div>
{% endblock %}
```

---

### Task 8: Add New Views and URLs

**Files:**
- Modify: `apps/tasks/views.py`
- Modify: `apps/tasks/urls.py`

**Step 1: Add new views**

```python
@login_required
def task_full_page(request, project_pk, task_pk):
    """Full page task view with properties sidebar."""
    task = get_object_or_404(
        Task.objects.select_related('project', 'status', 'assignee')
        .prefetch_related('subtasks', 'activities__user', 'labels'),
        pk=task_pk, project_id=project_pk
    )
    team_members = User.objects.all()
    project_labels = task.project.labels.all()
    priority_choices = Task.PRIORITY_CHOICES
    return render(request, 'tasks/task_full_page.html', {
        'task': task,
        'team_members': team_members,
        'project_labels': project_labels,
        'priority_choices': priority_choices,
    })


@login_required
@require_POST
def task_update_title(request, pk):
    task = get_object_or_404(Task, pk=pk)
    task.title = request.POST.get('title', task.title)
    task._changed_by = request.user
    task.save()
    return HttpResponse(status=204)


@login_required
@require_POST
def task_update_assignee(request, pk):
    task = get_object_or_404(Task, pk=pk)
    assignee_id = request.POST.get('assignee_id')
    task.assignee = User.objects.get(pk=assignee_id) if assignee_id else None
    task._changed_by = request.user
    task.save()
    team_members = User.objects.all()
    return render(request, 'tasks/partials/assignee_dropdown.html', {
        'task': task, 'team_members': team_members
    })


@login_required
@require_POST
def task_update_priority(request, pk):
    task = get_object_or_404(Task, pk=pk)
    task.priority = request.POST.get('priority') or None
    task._changed_by = request.user
    task.save()
    return render(request, 'tasks/partials/priority_dropdown.html', {
        'task': task, 'priority_choices': Task.PRIORITY_CHOICES
    })


@login_required
@require_POST
def task_update_due_date(request, pk):
    task = get_object_or_404(Task, pk=pk)
    due_date = request.POST.get('due_date')
    task.due_date = due_date if due_date else None
    task._changed_by = request.user
    task.save()
    return render(request, 'tasks/partials/due_date_picker.html', {'task': task})


@login_required
@require_POST
def task_update_estimate(request, pk):
    task = get_object_or_404(Task, pk=pk)
    estimate = request.POST.get('time_estimate')
    task.time_estimate = float(estimate) if estimate else None
    task._changed_by = request.user
    task.save()
    return render(request, 'tasks/partials/estimate_input.html', {'task': task})


@login_required
@require_POST
def task_toggle_label(request, pk, label_pk):
    task = get_object_or_404(Task, pk=pk)
    label = get_object_or_404(Label, pk=label_pk, project=task.project)
    if label in task.labels.all():
        task.labels.remove(label)
    else:
        task.labels.add(label)
    project_labels = task.project.labels.all()
    return render(request, 'tasks/partials/labels_selector.html', {
        'task': task, 'project_labels': project_labels
    })


@login_required
def task_edit_description(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == 'POST':
        task.description = request.POST.get('description', '')
        task._changed_by = request.user
        task.save()
        return render(request, 'tasks/partials/description_display.html', {'task': task})
    return render(request, 'tasks/partials/description_edit.html', {'task': task})
```

**Step 2: Add URL routes**

```python
# Add to urlpatterns
path('project/<int:project_pk>/<int:task_pk>/', views.task_full_page, name='task_full_page'),
path('<int:pk>/title/', views.task_update_title, name='task_update_title'),
path('<int:pk>/assignee/', views.task_update_assignee, name='task_update_assignee'),
path('<int:pk>/priority/', views.task_update_priority, name='task_update_priority'),
path('<int:pk>/due-date/', views.task_update_due_date, name='task_update_due_date'),
path('<int:pk>/estimate/', views.task_update_estimate, name='task_update_estimate'),
path('<int:pk>/labels/<int:label_pk>/toggle/', views.task_toggle_label, name='task_toggle_label'),
path('<int:pk>/description/', views.task_edit_description, name='task_edit_description'),
```

---

### Task 9: Update task_detail View to Pass Required Context

**Files:**
- Modify: `apps/tasks/views.py`

Update the existing `task_detail` view:

```python
@login_required
def task_detail(request, pk):
    task = get_object_or_404(
        Task.objects.select_related('project', 'status', 'assignee')
        .prefetch_related('subtasks', 'activities__user', 'labels', 'project__labels'),
        pk=pk
    )
    team_members = User.objects.all()
    project_labels = task.project.labels.all()
    priority_choices = Task.PRIORITY_CHOICES
    return render(request, 'tasks/task_detail.html', {
        'task': task,
        'team_members': team_members,
        'project_labels': project_labels,
        'priority_choices': priority_choices,
    })
```

---

### Task 10: Create Description Edit Partial

**Files:**
- Create: `templates/tasks/partials/description_display.html`
- Create: `templates/tasks/partials/description_edit.html`

**description_display.html:**

```html
<div class="text-sm text-zinc-400 cursor-pointer hover:text-zinc-300"
     hx-get="{% url 'task_edit_description' task.pk %}"
     hx-target="this"
     hx-swap="outerHTML">
    {% if task.description %}
    {{ task.description|linebreaks }}
    {% else %}
    <span class="italic">Click to add description...</span>
    {% endif %}
</div>
```

**description_edit.html:**

```html
<form hx-post="{% url 'task_edit_description' task.pk %}"
      hx-target="this"
      hx-swap="outerHTML"
      class="space-y-2">
    {% csrf_token %}
    <textarea name="description" rows="4"
              class="w-full bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:outline-none resize-none"
              autofocus>{{ task.description }}</textarea>
    <div class="flex gap-2">
        <button type="submit" class="bg-accent text-white px-3 py-1 rounded-card text-xs">Save</button>
        <button type="button"
                hx-get="{% url 'task_edit_description' task.pk %}"
                hx-target="closest form"
                hx-swap="outerHTML"
                hx-vals='{"cancel": "1"}'
                class="text-zinc-400 hover:text-zinc-200 px-3 py-1 text-xs">Cancel</button>
    </div>
</form>
```

---

### Task 11: Update Comment Create to Use TaskActivity

**Files:**
- Modify: `apps/tasks/views.py`

Update comment_create view to create TaskActivity instead:

```python
@login_required
@require_POST
def comment_create(request, pk):
    task = get_object_or_404(Task, pk=pk)
    content = request.POST.get('content', '').strip()
    if content:
        activity = TaskActivity.objects.create(
            task=task,
            user=request.user,
            activity_type='comment',
            content=content
        )
        return render(request, 'tasks/partials/activity_item.html', {'activity': activity})
    return HttpResponse(status=400)
```

---

### Task 12: Test and Verify

**Manual Testing:**
1. Open drawer - verify new layout with properties panel
2. Click "expand" button - verify full page opens
3. Change status via dropdown - verify activity logs it
4. Change assignee - verify activity logs it
5. Add a comment - verify it appears in activity
6. Edit description inline - verify it saves
7. Check activity shows all changes

**Run Django Check:**
```bash
python manage.py check
```

---

### Task 13: Commit

```bash
git add -A
git commit -m "feat: Plane.so style task view with drawer and full page

- Add TaskActivity model for activity tracking
- Add Django signals to auto-log task changes
- Create shared property components (status, assignee, priority, etc.)
- Redesign drawer with Notion-style properties panel
- Add full page task view with properties sidebar
- Add inline editing for all properties
- Activity section shows comments + auto-logged changes"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Create TaskActivity model | `models.py`, migration |
| 2 | Add Django signals for tracking | `signals.py`, `apps.py` |
| 3 | Create property components | `properties_panel.html`, `property_row.html` |
| 4 | Create dropdown components | 6 partial templates |
| 5 | Create activity component | `activity_panel.html`, `activity_item.html` |
| 6 | Rewrite drawer template | `task_detail.html` |
| 7 | Create full page template | `task_full_page.html` |
| 8 | Add new views and URLs | `views.py`, `urls.py` |
| 9 | Update task_detail context | `views.py` |
| 10 | Create description edit partial | 2 templates |
| 11 | Update comment_create | `views.py` |
| 12 | Test and verify | Manual testing |
| 13 | Commit | Git |

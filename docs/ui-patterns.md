# WebFTL CRM UI/UX Patterns Documentation

This document describes the UI/UX patterns used throughout the WebFTL CRM application to ensure consistency and provide guidance for future development.

## Design System Overview

The application uses a **Linear-style dark theme** with the following core design tokens:

### Colors (Tailwind Config)
```css
/* Background colors */
--color-bg: #0A0A0A;
--color-sidebar: #0A0A0A;
--color-panel: #0E0F0F;
--color-card: #1B1C20;
--color-elevated: #1E1F22;

/* Border colors */
--color-border: rgba(255, 255, 255, 0.08);
--color-border-subtle: rgba(255, 255, 255, 0.05);
--color-border-strong: rgba(255, 255, 255, 0.12);

/* Interactive states */
--color-hover: rgba(255, 255, 255, 0.05);
--color-hover-strong: rgba(255, 255, 255, 0.08);

/* Accent (purple) */
--color-accent: #8b5cf6;
--color-accent-hover: #a78bfa;
--color-accent-muted: rgba(139, 92, 246, 0.16);
```

### Border Radius
- `rounded-card`: 4px (for buttons, inputs, small elements)
- `rounded-panel`: 6px (for larger panels and containers)

---

## Page Layout Patterns

### 1. Compact Header Pattern

Used for list pages and detail pages. Provides a consistent header with icon, title, count badge, and actions.

**Structure:**
```html
<div class="flex-shrink-0 px-4 py-2 border-b border-border-subtle bg-panel/80">
    <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
            <i data-lucide="[icon-name]" class="w-4 h-4 text-zinc-500"></i>
            <h1 class="text-sm font-medium text-zinc-100">[Title]</h1>
            <span class="text-xs text-zinc-500 bg-elevated px-1.5 py-0.5 rounded">[count]</span>
        </div>
        <!-- Actions go here -->
    </div>
</div>
```

**Usage examples:**
- `templates/clients/client_list.html` - Clients list with "Add Client" button
- `templates/projects/project_list.html` - Projects list with filter and "Add Project" button
- `templates/tasks/my_tasks.html` - My tasks with priority filter

### 2. Full-Height Layout (`{% block full_content %}`)

Used for pages that need to fill the entire viewport height (list pages, kanban boards, detail pages).

**Structure:**
```html
{% extends "base.html" %}

{% block full_content %}
<div class="flex flex-col h-full">
    <!-- Compact header -->
    <div class="flex-shrink-0 ...">...</div>

    <!-- Scrollable content area -->
    <div class="flex-1 overflow-auto">...</div>

    <!-- Optional: Pagination -->
    {% include "components/pagination.html" %}
</div>
{% endblock %}
```

**Used in:**
- `templates/clients/client_list.html`
- `templates/clients/client_detail.html`
- `templates/projects/project_list.html`
- `templates/projects/project_board.html`
- `templates/projects/project_settings.html`
- `templates/tasks/my_tasks.html`
- `templates/tasks/task_full_page.html`
- `templates/accounts/dashboard.html`
- `templates/accounts/team_list.html`

### 3. Padded Content Layout (`{% block content %}`)

Used for form pages and simpler content. Automatically wrapped in padding and panel styling by base.html.

**Structure:**
```html
{% extends "base.html" %}

{% block content %}
<div class="max-w-2xl">
    <!-- Form content here -->
</div>
{% endblock %}
```

**Used in:**
- `templates/clients/client_form.html`
- `templates/tasks/task_form.html`
- `templates/projects/project_form.html`
- `templates/projects/manage_statuses.html`

### 4. Right Sidebar Navigation Pattern

Used for detail pages with multiple sections or tabs.

**Structure:**
```html
<div class="flex-1 flex overflow-hidden">
    <!-- Main content area -->
    <div class="flex-1 overflow-y-auto p-6">
        <!-- Tab/section content -->
    </div>

    <!-- Right sidebar navigation -->
    <div class="w-56 flex-shrink-0 border-l border-border-subtle bg-panel/50 overflow-y-auto">
        <div class="p-3">
            <div class="text-[10px] uppercase tracking-wider text-zinc-600 px-2 mb-2">Navigation</div>
            <nav class="space-y-1">
                <!-- Navigation buttons/links -->
            </nav>
        </div>
    </div>
</div>
```

**Variations:**
- **Client Detail** (`w-56`): Uses Alpine.js `x-data` with `activeTab` for tab switching
- **Project Settings** (`w-48`, `hidden lg:block`): Uses anchor links with responsive visibility

---

## Form Input Classes

### INPUT_CLASSES Constants

Each app defines an `INPUT_CLASSES` constant in its `forms.py` file. Currently there are slight inconsistencies:

#### `apps/clients/forms.py`
```python
INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'
```

#### `apps/projects/forms.py`
```python
INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'
```
*(Same as clients)*

#### `apps/tasks/forms.py`
```python
INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-card px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none transition-colors'
```

### Differences Between Apps

| Property | clients/projects | tasks |
|----------|-----------------|-------|
| Vertical padding | `py-2` | `py-2.5` |
| Placeholder color | (not set) | `placeholder-zinc-600` |
| Transitions | (not set) | `transition-colors` |

### Form Label Pattern

```html
<label class="block text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-2">[Label]</label>
```

### Form Widget Usage

```python
class MyForm(forms.ModelForm):
    class Meta:
        widgets = {
            'field_name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'textarea_field': forms.Textarea(attrs={'class': INPUT_CLASSES, 'rows': 4}),
            'select_field': forms.Select(attrs={'class': INPUT_CLASSES}),
            'date_field': forms.DateInput(attrs={'class': INPUT_CLASSES, 'type': 'date'}),
        }
```

---

## Table Styling

### Standard Table Structure

```html
<table class="w-full">
    <thead class="sticky top-0 bg-panel border-b border-border-subtle">
        <tr class="text-left text-xs text-zinc-500 uppercase tracking-wider">
            <th class="px-4 py-3 font-medium">Column</th>
            <!-- More columns -->
        </tr>
    </thead>
    <tbody id="[list-id]" class="divide-y divide-border-subtle">
        {% for item in items %}
        {% include "[app]/partials/[item]_row.html" %}
        {% endfor %}
    </tbody>
</table>
```

### Table Row Pattern (from partials)

Rows are typically included from partial templates (e.g., `client_row.html`, `project_row.html`) with hover effects applied via Tailwind CSS.

### Empty State Pattern

```html
<div class="flex flex-col items-center justify-center py-16 text-zinc-500">
    <i data-lucide="[icon]" class="w-12 h-12 mb-4 opacity-30"></i>
    <p class="mb-2">[Empty message]</p>
    <a href="{% url '[create_url]' %}" class="text-accent hover:text-accent-hover text-sm">
        [Call to action]
    </a>
</div>
```

---

## Pagination Component

Reusable pagination component at `templates/components/pagination.html`.

**Include in templates:**
```html
{% include "components/pagination.html" %}
```

**Features:**
- Shows "Showing X-Y of Z" count
- First/Previous/Next/Last navigation with Lucide icons
- Page number links with ellipsis for large page counts
- Active page highlighted with accent color
- Disabled states for unavailable navigation

---

## Button Patterns

### Primary Action Button
```html
<button class="bg-accent text-white px-4 py-2 rounded-card text-sm hover:bg-accent-hover transition-colors">
    Action
</button>
```

### Compact Header Button (Add New)
```html
<a href="[url]" class="inline-flex items-center gap-1.5 bg-accent text-white px-3 py-1.5 rounded-card text-xs font-medium hover:bg-accent-hover transition-colors">
    <i data-lucide="plus" class="w-3.5 h-3.5"></i>
    Add [Item]
</a>
```

### Secondary Button
```html
<button class="bg-elevated border border-border-subtle text-zinc-300 px-4 py-2 rounded-card text-sm hover:bg-hover hover:border-border-strong transition-colors">
    Secondary Action
</button>
```

### Danger Button
```html
<button class="bg-red-500/10 border border-red-500/20 text-red-300 px-3 py-1.5 rounded-card text-xs hover:bg-red-500/20 transition-colors">
    <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
    Delete
</button>
```

---

## Slide-Over (Drawer) Pattern

A slide-over panel for editing content without leaving the current page.

**Container (in base.html):**
```html
<div id="slide-over" class="fixed inset-y-0 right-0 w-full max-w-xl bg-panel border-l border-border-subtle z-50 overflow-y-auto hidden animate-slide-in-right"></div>
```

**HTMX Trigger:**
```html
<button hx-get="{% url 'item_edit_drawer' item.pk %}"
        hx-target="#slide-over"
        hx-swap="innerHTML"
        hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();">
    Edit
</button>
```

**Close event:**
```javascript
document.body.addEventListener('closeSlideOver', () => {
    document.getElementById('slide-over').classList.add('hidden');
});
```

---

## Inconsistencies Found

### 1. INPUT_CLASSES Differences

**Issue:** The tasks app has slightly different INPUT_CLASSES than clients/projects:
- `py-2.5` vs `py-2` (extra 0.5 padding)
- Includes `placeholder-zinc-600` and `transition-colors`

**Recommendation:** Standardize INPUT_CLASSES across all apps. Consider creating a shared module:
```python
# apps/core/form_utils.py
INPUT_CLASSES = 'w-full bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none transition-colors'
```

### 2. Block Usage Inconsistency

**Issue:** Some pages use `{% block content %}` while others use `{% block full_content %}`:
- Form pages use `{% block content %}` (wrapped with padding)
- List/detail pages use `{% block full_content %}` (full height)

**Status:** This is intentional design - form pages benefit from centered, padded layout while list pages need full-height scrolling. Document this pattern for consistency.

### 3. LabelForm Custom Classes

**Issue:** In `apps/projects/forms.py`, `LabelForm` uses inline classes instead of INPUT_CLASSES:
```python
'name': forms.TextInput(attrs={
    'class': 'flex-1 bg-panel border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none',
    ...
}),
```

**Recommendation:** Use INPUT_CLASSES constant for consistency, or create a variant constant for special layouts.

### 4. Right Sidebar Width Variations

**Issue:** Different sidebar widths used:
- Client detail: `w-56` (224px)
- Project settings: `w-48` (192px)

**Recommendation:** Standardize on one width or document when to use each.

### 5. Drawer vs Redirect Pattern

**Issue:** Some edit actions use the slide-over drawer while others redirect to a form page:
- Client edit: Uses drawer (`client_edit_drawer`)
- Client create: Redirects to form page (`client_form.html`)

**Recommendation:** Document when to use each pattern:
- **Drawer**: Quick edits on detail pages
- **Redirect**: Complex forms or create operations

---

## Icon Library

The application uses **Lucide Icons** (loaded via CDN).

**Initialization:**
```javascript
lucide.createIcons();
// Re-init after HTMX swaps
document.body.addEventListener('htmx:afterSwap', () => {
    lucide.createIcons();
});
```

**Usage:**
```html
<i data-lucide="icon-name" class="w-4 h-4"></i>
```

**Common icons used:**
- `users` - Clients
- `folder-kanban` - Projects
- `check-square` - Tasks
- `settings` - Settings
- `plus` - Add/Create
- `pencil` - Edit
- `trash-2` - Delete
- `arrow-left` - Back navigation
- `chevron-left/right` - Pagination

---

## JavaScript Libraries

- **HTMX 2.0.4** - Dynamic HTML updates
- **Alpine.js 3.x** - Reactive UI components
- **Alpine.js Sort Plugin** - Drag and drop functionality
- **Lucide** - Icon library
- **Tailwind CSS** (via CDN) - Utility-first CSS

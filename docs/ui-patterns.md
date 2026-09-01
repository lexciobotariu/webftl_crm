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

Use the shared component rather than repeating the markup:

```html
{% url 'client_create_drawer' as create_url %}
{% include "components/empty_state.html" with icon="users" message="No clients yet" action_hx_get=create_url action_label="Add your first client" %}
```

`action_url` renders a link; `action_hx_get` renders a button that loads the URL
into the drawer. Omit both for a message-only state.

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

Destructive actions live in the settings page's Danger Zone, not in a page header —
a Delete sitting next to Settings/Open Board is one mis-click away from wiping a
record. See `project_settings.html` for the reference Danger Zone.

---

## Slide-Over (Drawer) Pattern

The **salaries app** is the reference implementation. All drawer forms should follow this contract.

**Container (in base.html):**
```html
<div id="slide-over" class="fixed inset-y-0 right-0 w-full max-w-xl ..."></div>
```

**Form target — always the drawer:**
```html
<form hx-post="{% url 'salary_create' %}"
      hx-target="#slide-over"
      hx-swap="innerHTML">
```

**Success response (view):** empty body + `HX-Trigger` JSON:
```python
response = HttpResponse('')
response['HX-Trigger'] = json.dumps({'closeSlideOver': True, 'refreshSalaryList': True})
```

**Validation error (view):** re-render the drawer partial into `#slide-over` (no trigger headers).

**List refresh listener:** listen for the trigger and re-fetch the current URL,
so an active filter or page number is not silently dropped. Keep the count pill
and pagination inside the refreshed container so they cannot go stale.

```html
<div id="client-list-content"> ... table ... {% include "components/pagination.html" %} </div>

<script>
    document.body.addEventListener('refreshClientList', () => {
        refreshFragment('#client-list-content');
        refreshFragment('#client-count');
    });
</script>
```

The salaries app still uses the older `hx-get`/`hx-select` form; it has no
filters or pagination, so nothing is lost there.

**Row update variant (accounts user edit):** on success only, use `HX-Retarget` + `HX-Reswap` to update a table row outside the drawer.

**Global utilities (base.html):**
- `openSlideOver(event)` / `closeSlideOver()` — use these from `hx-on::after-request`
  instead of hand-writing `document.getElementById('slide-over')...`. `openSlideOver`
  is a no-op when the request failed, so an error never opens an empty drawer.
- `closeSlideOver` event listener closes the drawer
- **Click-outside close** — one global `click` listener closes the drawer when the
  click lands outside `#slide-over`. It covers every opener because closing is
  centralized in `closeSlideOver()`; nothing per-drawer is needed. The opening
  click is safe: it bubbles while the panel is still `hidden`, so the guard
  short-circuits before the HTMX response un-hides it.
- `refreshFragment(selector)` — re-fetches the *current* URL and swaps that
  fragment, so filters and `?page=` survive. Prefer this over a bare
  `hx-get="{% url ... %}"` refresh, which drops the query string.
- `showErrorToast(message)` — shared toast
- `#htmx-indicator` shows loading state (`hx-indicator="#htmx-indicator"` on body)
- `htmx:responseError` / `htmx:sendError` / `htmx:targetError` show a toast;
  5xx bodies are replaced with a generic message rather than shown raw.
- `Alpine.data('dropdown')` — shared `{ open, toggle(), close() }` used by the
  task property dropdowns.
- Any `x-show` panel whose expression is false at load must carry `x-cloak`; the
  global `[x-cloak]` rule lives in `base.html` `<head>`.

**Deprecated:** POSTing into list containers (`#client-list`, `#notes-list`, `#preset-list`) — causes broken empty states and nested IDs.

---

## Kanban Board

**Top-nav actions** (`project_board.html`): Add Task (accent) then Task List and
Settings (secondary). "Task List" is the way back to `project_detail_tasks` — the
board is a peer view of the task list, not a dead end.

**Card drag handle** (`partials/task_card.html`): the `x-sort:handle` grip is
always visible and sits to the *right* of the title block, as the last child of
the card's `flex items-start gap-2` row. It is not hover-revealed — a handle you
cannot see is a handle you do not know exists. The title block keeps
`flex-1 min-w-0` so it shrinks instead of pushing the grip out.

**URLs:** `/projects/<pk>/overview/`, `/tasks/`, `/notes/` for the detail tabs and
`/projects/<pk>/kanban/` for the board. A bare `/projects/<pk>/` redirects to the
overview tab. Always link by URL *name*, never by literal path.

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

### 6. Salaries layout divergence

The salaries pages do not use the right-sidebar navigation pattern; `salary_detail.html`
is a single scrolling column of month/payment cards with drawers for every mutation.
This is deliberate — there are no tabs to navigate — but it means the salaries app is
the reference for the *drawer* contract and not for page layout.

### Resolved

- **Alpine sort buttons in `activity_panel.html`** — the `sortAsc` toggle was never
  wired to the list; removed.
- **`manage_statuses.html`** — folded into `project_settings.html`; template deleted.
- **Duplicated drawer-open handlers** — replaced by `openSlideOver(event)`.
- **Duplicated permission badge markup** — extracted to
  `templates/components/permission_badges.html`.
- **Duplicate kanban entry point** — the tasks tab had its own "Open Kanban Board"
  button next to the header's "Open Board"; the tab-local one was removed.
- **Delete button in the project header** — moved to the settings Danger Zone only.

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

All are loaded from a CDN, pinned to an exact version and checked with Subresource
Integrity. Bumping a version means recomputing its `integrity` hash.

- **HTMX 2.0.4** — dynamic HTML updates
- **Alpine.js 3.17.1** — reactive UI components
- **@alpinejs/sort 3.17.1** — kanban drag and drop
- **@alpinejs/collapse 3.17.1** — `x-collapse` (used by the salary month list)
- **Lucide 1.38.0** — icon library
- **Iconify 2.3.0** — supplementary icons
- **Tailwind CSS** (`cdn.tailwindcss.com`) — the one unpinned, unhashed dependency;
  it is a JIT build with no versioned URL. See the README for the tradeoff.

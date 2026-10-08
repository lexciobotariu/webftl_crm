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
- `templates/tasks/my_tasks.html` - My tasks: toolbar plus grouped list (`tasks/view/`), driven by the URL

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
- `templates/tasks/view/project_tasks.html`
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

Task lists (the project Tasks page and My Tasks) do not page: they load the first
`limit` rows and offer "Show more" (`?limit=`), see `apps/tasks/viewspec.py`.

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
- **Closing empties the drawer, a moment later.** `closeSlideOver()` hides the panel at once
  and removes its content only when the response being handled has dispatched all its
  `HX-Trigger` events and no request sent from inside the drawer is still in flight. Emptying
  detaches the element that sent the request, and an event dispatched on a detached element
  never reaches `<body>`; a response of `{"closeSlideOver": true, "taskStatusChanged": true}`
  would otherwise close the drawer and lose the list refresh.
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

### Time on a task

- **One "Time" property** (`tasks/partials/time_property.html`) reads `logged / estimate` with a thin
  bar (`role="progressbar"`); going over is written out ("Over by 15m"), not only coloured, and there is
  no bar without an estimate. Start/Stop, "Log time" and the estimate popover live in it.
- **Durations are text.** The estimate and the log form take `1h 30m`, `45m`, `1.5h`, `1:30`
  (`apps/tasks/durations.py`); a bare number is hours in the estimate and refused when logging. Time is
  logged as **duration + date**, never start and end, and shown as date + duration.
- **`timerChanged`** (an `HX-Trigger`, sent by start, stop, log, edit and delete) is the one event for
  time. Listeners: the running-timer bar, the activity list (see below), and `#time-logged-<pk>` — the single listener
  of the Time property. Its answer (`task_time_property`) replaces itself and brings the bar, the
  Start/Stop button and the task header's Start/Stop button along with `hx-swap-oob`, so nothing
  listens twice. Changing the estimate sends `taskUpdated-<pk>`, which the same element hears.
- **Popovers are never part of a refresh.** Each one is its own `x-data="dropdown"` with
  `@click.away`, so Escape closes it and not the drawer (see Escape above), and a half-typed log
  survives `timerChanged`. Anchor a popover to the property row (`left-0 right-0` / `left-2 right-2`
  on a `relative` parent), not to its button: the sidebar is `overflow-hidden` and clips anything wider.
- **Logging answers with an empty body**; anything else is the reason, swapped into the popover's
  error line. The popover does not close the drawer.

### Activity: comments, events and the Work log

- **One list, three tabs** (All / Comments / Work log, `static/js/activity-filter.js`). The list is
  always rendered whole; every row carries `data-kind` (`comment`, `event`, `work`, plus the Work
  log's `summary`) and `custom.css` hides what the open tab does not match, so a refresh or a new
  comment never needs to know the tab. Empty states are `data-empty` lines the CSS shows when a tab
  has nothing. The tabs copy the Write/Preview tablist (roving `tabindex`, arrow keys, wrapping).
  Each opening starts on **All**, so a notification that leads to a comment is not behind a tab that
  hides it, and a comment written from Work log sends the tab back to All.
- **`task_activities` merges at read time.** It returns activities plus the time entries the viewer
  may see (`entries_on_task`), ordered by `created_at` (for time that is when it was logged, not the
  day it is for), each marked `item_type` and `can_change`. Nothing is written to the activity
  table for time, so editing or deleting an entry has nothing to sync and time stays out of the
  project's activity. The query count does not grow with the rows (tested).
- **A time row has its own ids** (`time-entry-<pk>`), reads "Lex logged 1h 30m — note", and edits in
  place like a comment (the refresh guard `#activity-items-<pk> form` covers it). Delete answers an
  empty 200 so the row goes. A running timer reads "timer running" and can only be deleted.
- **Subscribe / Unsubscribe** (`TaskSubscription`, `notifications.services.follower_ids`):
  without a row, followers are the assignee, the creator and commenters; a row with
  `subscribed=False` takes someone out, `True` puts them in. Mentions ignore it.
- **Sub-tasks** rename in place (click the title, Enter saves, Escape cancels) and reorder
  by drag (`x-sort` on the list, `subtask_reorder` takes the ids in their new order).
- **Who may comment.** Anyone who can open the task, editor or not (`services.add_comment`).
  Changing or deleting a comment stays with its author (while they can still see the task)
  or an admin (`can_change_comment`).
- **Work log totals** per person come from the rows already read. What the viewer cannot see is one
  "Others" line, taken from the task's full total, so the sum matches the Time property.

**Deprecated:** POSTing into list containers (`#client-list`, `#notes-list`, `#preset-list`) — causes broken empty states and nested IDs.

---

## Project Tasks page

`/projects/<pk>/tasks/` (`project_tasks`, `templates/tasks/view/`) is one full-width
page whose state lives in the URL. `apps/tasks/viewspec.py` (`TaskViewSpec`) is the only
code that reads and validates the query parameters; unknown values are ignored, never a 400.
`layout` is always in the canonical URL, so only a bare query string means "restore the view
this person last used" (`ProjectTaskView`, unique per user and project; search text and
paging are never saved).

- **Always a full page.** The toolbar and "Show more" request the page and the client keeps
  `#task-view` (`hx-select`, `outerHTML`); the filter badge and checkboxes are refreshed out
  of band (`hx-select-oob`). The OOB elements carry no Alpine state. The server sets the
  URL with `push_url` (toolbar) or `replace_url` (search, "Show more", refreshes).
- **Only the toolbar form saves the view.** It is `<form id="task-toolbar">`, so its
  requests arrive with `HX-Trigger: task-toolbar`. A shared link, a refresh after a drawer
  edit, search-as-you-type and "Show more" never overwrite what someone chose.
- **Statuses are stored as the ones hidden** (`hide_status=<id>`), so a status added later
  shows up by itself. The filter form posts the checked ones (`shown_status` + `filter=1`)
  and the spec translates them.
- **Rows go stale otherwise.** The drawer's property views emit `taskChanged` (plus
  `taskUpdated-<pk>`); the page answers with `refreshFragment('#task-view')`.
- **Order by "Manual"** is the board's order (`order`, newest first on a tie). It is the
  default when grouping by status, so the list and the board agree; any other grouping
  defaults to Priority. Only a sort that differs from the grouping's default goes in the
  URL (`viewspec.default_sort`). My Tasks does not offer it: the order is per project column.
  Changing "Group by" in the menu moves a sort still at the old default to the new one;
  a sort someone picked stays.
- **Show empty groups** (`empty=1`/`0`) lists the groups with no task too, with a count of 0
  (`listview.group_slots`). On by default when grouping by status, off otherwise. Filters
  still apply: a hidden status or an unchecked priority is not listed. When only a page of
  rows is loaded, empty groups after the last loaded one wait for "Show more".
- **Search** matches the title, or a task id: `CUST-12` (key in any case), `12` or `#12`.
  A bare number matches that number in every project the page covers.
- **Row properties** (`col=`, the Display menu's Properties) choose the optional row
  columns: `id`, `project` (My Tasks), `labels`, `due`, `estimate`. The form always sends
  `cols=1`, so none checked means none (`col=none` in the URL).
- **One row, not the whole view, after a quick edit.** `task-view.js` posts the edit, then
  GETs the page URL plus `row=<pk>` (`listview.render_task_row`): the row or card alone, or
  204 when it left the view. Every row carries `data-keys` (`listview.row_keys`: its group
  and sort key); the new row is swapped in only when they match, otherwise the whole view
  is fetched. Status changes always fetch the whole view (counts and badges move). The page
  ignores `taskChanged` from elements marked `data-row-refresh` (the quick menu).
- **Labels** show at most 3 on a row, then `+N`; a card shows every label. A row is one
  line and must not wrap, a card has room to wrap. The drawer always shows them all.

### Quick edit on rows and cards

Priority, status and assignee change from the row (cards: priority and assignee, since the
column is the status) without opening the drawer.

- **One floating menu per page.** `#task-quick-menu` sits in `_view_scripts.html`, outside
  `#task-view`, and `static/js/task-view.js` opens it from a delegated click on any
  `[data-quick="priority|status|assignee"]` button. Never add a dropdown per row: a page of
  rows would carry hundreds of htmx nodes that every swap re-processes.
- **Options.** Priority is a `<template>` rendered once in the page. Status and assignee come
  from `GET /tasks/<pk>/quick/<field>/` (`task_quick_menu`), rendered without the request so
  no context processor runs. The current value is `aria-checked` and choosing it does nothing.
- **Saving reuses the drawer's endpoints** (`task_update_status/priority/assignee`). The POST
  goes out with `htmx.ajax(..., {source: '#task-quick-menu', swap: 'none'})`, so
  `taskChanged` / `taskStatusChanged` reach `body` and the page re-fetches the view, even
  though the pressed option is gone by then.
- **The click does not also open the drawer.** Rows use `hx-trigger="click[!event.target.closest('[data-quick]')]"`,
  and the card's `onclick` has the same guard. Don't use `click consume`: it would also stop
  click-outside listeners. Opening a menu closes the drawer.
- **Who gets buttons.** The page works out edit rights once (`quick_edit`, plus
  `quick_edit_projects` on My Tasks, from `editable_scope`); rows only read them. Anyone
  else sees the plain icons.
- **Scroll survives the refresh.** Elements marked `data-keep-scroll="<key>"` (the list, the
  board, each column) are saved before `#task-view` is swapped and restored after: the
  refresh after an edit, "Show more", and the board's refresh after a drag. Only a request
  sent from the toolbar (filter, layout, search) is a different view and starts from the top.
- **Escape.** `static/js/keys.js` is the one Escape handler. It walks palette, shortcut
  help, quick menu, dropdown, drawer, selection and stops at the first that closes something; new layers
  register with `registerEscLayer(name, fn)`. A field that handles Escape itself must
  `preventDefault()`. The dropdown layer closes an Alpine component only when it has `open`
  *and* a panel with `@click.away` (or `.outside`); a collapsible section that also uses `open`
  is left alone.

### Selection and keyboard shortcuts

Every row and card carries `data-task-row`; `static/js/task-view.js` keeps one of them
selected (`.task-selected`, defined in `custom.css` from the theme tokens, plus `tabindex="0"`,
`aria-current` and real focus).

- **Move:** `J` / `K` or `↓` / `↑` through the visible rows (rows in a collapsed group are
  skipped). On the board they stay in the column, and `H` / `L` or `←` / `→` jump to the nearest
  column that has cards, keeping the position.
- **Act:** `Enter` opens the drawer, `/` focuses the search box (`Esc` leaves it), `C` clicks
  `#task-new` (project page only), `S` / `P` / `A` open the quick menu on the selected row
  (a card has no status trigger, so `S` does nothing there), `D` opens the due date menu and
  `Shift+L` the labels menu (both placed under the row, for editors only; plain `L` stays a
  board move), `I` assigns the task to the viewer (`data-me` on the quick menu), `?` lists them
  in `#task-shortcuts`. A click on a row or card selects it too.
- **Copy:** `Ctrl/Cmd+.` copies the selected task's id, `Ctrl/Cmd+Shift+,` its full-page link
  (`data-identifier`, `data-link` on rows and cards). Matched by `event.code`, so the layout
  does not matter; `showInfoToast` confirms.
- **When keys count.** Only with focus on `body` or inside `#task-view`; never in a field,
  with Ctrl / Cmd / Alt held (except the copy keys), during IME composition, or while the
  drawer, quick menu or help is open. Shift does not matter, except for `Shift+L`. `Enter` on a focused button stays that button's click.
- **Refresh.** The selection is put back at `htmx:afterSettle`. If its row is gone (a filter
  now hides it) the row at the same position is selected. Focus only moves back when nothing
  else has it, so a refresh never pulls it out of the search box or the drawer. Closing the
  drawer returns focus to the selected row (`slideover:closed`).

### Creating a task

The create drawer (`task_create_slideover.html`) is one form that is the whole panel: a
compact header (project, "New task", the **status picker**), a scrolling body, and a footer
with "Create more", Cancel and Create.

- **Fast entry.** The title takes focus when the drawer opens (and again after "Create more");
  `Enter` in the title submits natively and `Ctrl` / `Cmd` + `Enter` submits from any field;
  `hx-sync="this:drop"` ignores a second submit while one is in flight.
- **Status picker.** `partials/status_dropdown_create.html`, after `priority_dropdown_create.html`,
  posts `status_id`. It lives in the slide-over template, not in `task_form_fields.html`, which
  the full-page form shares and which has no status.
- **Create more.** The checkbox is remembered in `localStorage` (`taskCreateMore`). On success the
  view returns a fresh form with the same status, assignee and priority (so a run started from a
  group "+" stays in that group), a "Created <title>" line, and fires only
  `taskStatusChanged`, so the drawer stays open while the list behind it refreshes.
- **Prefill.** `?status=`, `?assignee=` and `?priority=` open the drawer with that value. A status
  or assignee that is not a number, or a priority that is not a choice, is ignored; a status from
  another project is a 404; a non-numeric `status_id` on submit is a 400. The prefilled assignee's
  name is resolved from the team list (`selected_assignee`).
- **Where "+" is.** Board column headers (status), and list group headers when grouped by status,
  priority or assignee. The group buttons show only with `can_create_task and project`, so not
  on My Tasks.

## Inbox (split view)

The Inbox is a stream of events, not a work list, so it deliberately does not
look like My Tasks. It reads like a mail client (`templates/notifications/inbox.html`):

- **Left column** (`w-[380px]`, full width below `lg`): header, an All / Unread /
  Mentions segmented control, and `#inbox-list` (`role="listbox"`). Rows
  (`partials/item.html`) are real links (`?show=…&n=<pk>`) on three lines: who and
  when, the task (status, ID, title), and what happened. Sticky day separators
  (Today / Yesterday / This week / Older) do not fold.
- **Right pane** `#inbox-pane`: a context bar (who did what, position, previous /
  next, read toggle, delete) above the task drawer's content rendered with
  `render_task_drawer(..., embedded=True)`, which leaves out the back and close
  buttons and does not call `openSlideOver()`. Below `lg` the pane covers the
  list while something is selected (`data-selected` on `#inbox`).
- **Opening** posts to `notification_open`: the pane, the row and the Unread count
  come back in one response, the notification is marked read and the address is
  replaced (`HX-Replace-Url`), so moving does not fill the history. A GET with
  `?n=` shows the pane without changing anything; the pane then posts its own
  read.
- **Keyboard** (`static/js/inbox.js`, not `task-view.js`): J / K open the next or
  previous one, Enter opens the selected one, E toggles read, Backspace / Delete
  deletes and opens the next, ? lists the keys, Esc closes the pane (after the
  palette, dialogs and menus). The comment that raised a notification is scrolled
  to and briefly highlighted (`.inbox-flash`).
- **The open notification stays in the list.** Every request that redraws the list
  (the refresh after a task change, "Show more", "Mark all read") names the open
  one (`n=<pk>`), and the Unread tab keeps it although opening marked it read;
  otherwise the pane's buttons would have no row to act on. Such a request also
  sends `list=1`, so the view does not render the pane (a whole task) for it.
- **Replacing the pane asks first when something is being written in it**
  (`mayLeavePane()` in `inbox.js`): J / K, a click on another row, Esc and delete
  all go through it, whatever has the focus.
- **Requests that change one notification** (read, unread, delete) are sent with
  `#inbox-opener` as target, not the pane: htmx fires `afterSwap` on the target even
  for a swap of "none", and that would scroll the pane back to the comment.
- **A task embedded in a page shares no ids with the drawer.** The sub-task and
  attachment lists are named per task (`subtask-list-<pk>`), so a drawer opened
  over the Inbox for another task appends to its own lists.

## Command palette (Ctrl/Cmd+K)

Search and jump, no actions. `Cmd+K` on a Mac, `Ctrl+K` elsewhere (or the Search button at the top
of the sidebar, which works without a keyboard) opens `#palette` from `base.html`;
`static/js/keys.js` runs it. On a Mac `Ctrl+K` is left alone: it deletes to the end of the line in
a text field.

- **What it finds.** `apps/search` (no models): `services.search(user, q)` and `GET /search/?q=`.
  Tasks match the title or the id (a number, or `CUST-19`, where the prefix is only how an id is
  shown and is ignored, whatever characters it holds; an exact id comes first). A single digit is
  searched as a task id only. Projects and clients match the name. Pages match
  the label. Five results per section, newest tasks first.
- **Visibility.** Each section uses the helper the list page uses (`visible_tasks`,
  `visible_projects`, `visible_clients`) **and** only appears if the person has the module
  (`access_tasks`, `access_projects`, `access_clients`); the helpers do not check the module.
- **Pages** are `apps/search/pages.py`, the sidebar's list with the sidebar's conditions. Add a
  sidebar entry there too; `TestPages.test_the_page_list_is_the_sidebars_...` renders the sidebar for
  several kinds of user and fails when the two drift.
- **The query** is trimmed and cut to `MAX_QUERY_LENGTH` (`apps/tasks/viewspec.py`); under 2
  characters it only shows the hint, unless it is a digit. The view renders `search/results.html` without the request, so
  the context processors (permissions, timers) do not run on every keystroke.
- **Markup.** A modal `role="dialog"` with a `role="combobox"` input and a `role="listbox"` whose
  options are real `<a href>` links; focus stays in the input and `aria-activedescendant` follows
  the arrow keys. `Tab` keeps focus in the dialog. The input has `hx-trigger="input delay:200ms"`,
  `hx-sync="this:replace"` (a newer keystroke cancels the older request) and its own spinner, so the
  global "Loading…" stays quiet.
- **Choosing.** `Enter` or a click on a task loads the drawer into `#slide-over` on the current page
  (`data-detail-url`); everything else navigates. `Ctrl/Cmd`-click or `Ctrl/Cmd+Enter` opens the link
  in a new tab. `Esc` closes the palette before anything else. On the task's own full page the
  link is followed instead: the drawer would repeat that page's element ids.
- **Only the answer to what is typed is shown.** An answer to an earlier query is dropped, a
  search still running when the palette closes is aborted, and `Enter` pressed before the results
  arrive waits for them and opens the first. A redirect instead of results means the session
  ended, and the page reloads to the login.
- **Over the drawer.** A click inside the palette (or the shortcut list) does not count as a click
  outside the drawer, so a half-filled drawer under it stays open.

## Kanban Board

The board is the `board` layout of the Tasks page above (`tasks/view/_board.html`), not a
page of its own. `/projects/<pk>/kanban/` (`project_board`) only redirects to
`/projects/<pk>/tasks/?layout=board`; link to `project_tasks` with no parameters so the
layout a person last chose wins.

- **Columns** are the statuses with `visible_on_board=True`, minus any the filter hides.
  The filters apply to the cards; order is always the manual one (grouping and sorting
  belong to the list). Every card is loaded; there is no paging on the board.
- **Drag and drop** lives in `Alpine.store('kanban')` in the page shell, outside
  `#task-view`, so it survives every swap. A drop sends `after_id` (the card it landed
  under; empty for the top of the column) because with filters on, `$position` is an index
  among the visible cards only. `task_move` passes it to `services.move_task(after_id=...)`:
  absent keeps the old `position`/append behaviour, empty is first, a pk is right after
  that card, and an anchor no longer in the column appends. After a move the page calls
  `refreshFragment('#task-view')`, so filters stay.
- Known limit: with filters on, dropping above the first visible card puts the task first
  in the whole column, even if hidden cards sit above it.
- **A task that arrives in a column lands at the top**, whether it was just created
  (`order=0`, newest first on a tie) or moved there from the drawer or the quick menu
  (`task_update_status` passes `after_id=None`). Only a drag picks another place.
- **Column headers** carry the status type icon (`components/status_icon.html`), as the
  list's group headers do.
- **Hidden columns:** the strip above the board counts filtered tasks that sit in statuses
  hidden from the board (`hidden_task_count`).

**Card drag handle** (`partials/task_card.html`): the `x-sort:handle` grip is
always visible and sits to the *right* of the title block, as the last child of
the card's `flex items-start gap-2` row. It is not hover-revealed — a handle you
cannot see is a handle you do not know exists. The title block keeps
`flex-1 min-w-0` so it shrinks instead of pushing the grip out.

**URLs:** `/projects/<pk>/overview/`, `/notes/`, `/team/` for the detail tabs,
`/projects/<pk>/tasks/` for the Tasks page (list and board layouts). A bare
`/projects/<pk>/` redirects to the overview tab. Always link by URL *name*, never by
literal path.

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

### Inline SVG icons (status, priority, unassigned)

Status types, priorities and the unassigned avatar use SVGs downloaded from
[Iconify](https://icon-sets.iconify.design/) and stored in `templates/components/icons/`,
named `<set>-<icon>.svg`. They are inlined by `components/status_icon.html`,
`priority_icon.html` and `avatar.html` (no CDN request, no `lucide.createIcons()` rescan
on every htmx swap). They use `currentColor` and size with `1em`, so colour and size
come from the wrapper.

To add or change one: `curl https://api.iconify.design/<set>/<icon>.svg -o templates/components/icons/<set>-<icon>.svg`.

| Icon set | Used for | License |
| --- | --- | --- |
| Tabler Icons (`tabler`) | backlog, unstarted, completed, canceled, urgent, no priority, unassigned, check mark in the quick menu | MIT |
| Material Design Icons (`mdi`) | started (half circle), low / medium / high signal bars | Apache-2.0 |

---

## JavaScript Libraries

The libraries below are loaded from a CDN, pinned to an exact version and checked with Subresource
Integrity. Bumping a version means recomputing its `integrity` hash.

- **HTMX 2.0.4** — dynamic HTML updates
- **Alpine.js 3.17.1** — reactive UI components
- **@alpinejs/sort 3.17.1** — kanban drag and drop
- **@alpinejs/collapse 3.17.1** — `x-collapse` (used by the salary month list)
- **Lucide 1.38.0** — icon library
- **Iconify 2.3.0** — supplementary icons
- **Own scripts** (`static/js/`, served from the app, not the CDN): `keys.js` (the Escape
  dispatcher and the command palette, loaded by `base.html`) and `task-view.js` (quick-edit menu, loaded by the Tasks
  pages). With `DEBUG` off, run `collectstatic` after adding or changing one; CI and Docker do.
- **Tailwind CSS** (`cdn.tailwindcss.com`) — the one unpinned, unhashed dependency;
  it is a JIT build with no versioned URL. See the README for the tradeoff.

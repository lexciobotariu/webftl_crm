# Project Detail Page Design

**Goal:** Create a project detail page similar to the client profile, providing an overview before diving into the Kanban board.

**Date:** 2026-01-01

---

## Overview

Currently, clicking a project goes directly to the Kanban board. This design adds an intermediate project detail page that shows project metadata, stats, and a task list, with the Kanban board accessible via button.

---

## Page Structure

### Header (compact, consistent with other pages)
- Back arrow → Project list (`/projects/`)
- Folder icon + Project name
- Client name as subtitle/badge
- Action buttons:
  - "Open Board" (primary accent button) → `/projects/{id}/board/`
  - "Settings" → `/projects/{id}/settings/`
  - "Delete" (admin only, red)

### Main Layout (two columns)
- **Left:** Content area (switches based on active tab)
- **Right:** Navigation sidebar (w-56, matches client page)

### Sidebar Navigation
```
Navigation
─────────────────
[folder] Overview        ← active by default
[list] Tasks        [12] ← count badge
─────────────────
Coming Soon
─────────────────
[message-circle] Discussions  ← disabled/muted
[ticket] Tickets
[file-text] Notes
[activity] Activity
```

The "Coming Soon" section uses muted styling to indicate planned but not yet functional features.

---

## Overview Tab

### Project Info Section
- **Description:** Editable inline (like client notes), or empty state "Add a description..."
- **GitHub repo:** Clickable link with external icon (if set)
- **Created date:** Formatted date

### Stats Cards (horizontal row, 4 cards)
| Total Tasks | Completed | In Progress | Overdue |
|-------------|-----------|-------------|---------|
| 24          | 12        | 8           | 2       |

- Compact cards matching the dark theme
- Overdue card uses warning color if count > 0

### Recent Activity Preview
- Shows last 5 task activities across the project
- Each item: icon, user name, action, timestamp
- "View all" link (disabled, points to future Activity tab)

---

## Tasks Tab

### Header Row
```
Tasks                                    [+ New Task] [Open Kanban Board →]
```
- "New Task" opens task create drawer (existing behavior)
- "Open Kanban Board" navigates to `/projects/{id}/board/`

### Task Table
| Column | Description |
|--------|-------------|
| Title | Task title, clickable to open slide-over |
| Status | Colored badge with status name |
| Priority | Icon or badge (urgent/high/medium/low) |
| Assignee | User avatar/name or dash |
| Due Date | Formatted date or dash |

- Clicking a row opens task detail slide-over (same as Kanban)
- Table uses existing dark theme styling

### Empty State
```
No tasks yet
Create your first task or open the Kanban board
[+ New Task]  [Open Kanban Board]
```

---

## URL Structure

| URL | View Name | Description |
|-----|-----------|-------------|
| `/projects/` | `project_list` | Project list (unchanged) |
| `/projects/{id}/` | `project_detail` | **NEW** - Project detail page |
| `/projects/{id}/board/` | `project_board` | Kanban board (unchanged) |
| `/projects/{id}/settings/` | `project_settings` | Settings (unchanged) |

---

## Navigation Changes

1. **Project list:** Click project name → `/projects/{id}/` (detail page, not board)
2. **Project detail:** "Open Kanban Board" button → `/projects/{id}/board/`
3. **Kanban board header:** Add back arrow → `/projects/{id}/` (detail page)
4. **Breadcrumbs in Kanban:** `Projects > Project Name > Board`

This keeps existing Kanban bookmarks working while making detail page the natural entry point.

---

## Future Tabs (Hardcoded Placeholders)

These tabs appear in sidebar but show "Coming Soon" when clicked:

- **Discussions:** Team conversations about the project
- **Tickets:** External tickets/issues linked to project
- **Notes:** Project documentation and notes
- **Activity:** Combined timeline of project + task events

---

## Technical Notes

### Files to Create/Modify
- `templates/projects/project_detail.html` - New detail page template
- `templates/projects/partials/overview_content.html` - Overview tab content
- `templates/projects/partials/tasks_content.html` - Tasks tab content
- `apps/projects/views.py` - Add `project_detail` view
- `apps/projects/urls.py` - Add route, update project list link
- `templates/projects/project_list.html` - Update link targets
- `templates/projects/project_board.html` - Add back navigation

### Reusable Patterns
- Header layout from `client_detail.html`
- Sidebar navigation from `client_detail.html`
- Tab switching with Alpine.js `x-data="{ activeTab: 'overview' }"`
- Task slide-over from existing Kanban implementation

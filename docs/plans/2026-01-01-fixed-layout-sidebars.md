# Fixed Layout: Sidebars and Header

**Goal:** Make the left sidebar, header, and right sidebar fixed/sticky while only the main content area scrolls.

**Date:** 2026-01-01

---

## Current Layout Analysis

### Structure Overview

```
+------------------+----------------------------------------+
|                  |  Header (flex-shrink-0)                |
|    Left          +---------------------------+------------+
|    Sidebar       |                           |   Right    |
|    (w-60)        |  Main Content             |   Sidebar  |
|                  |  (overflow-y-auto)        |   (w-56)   |
|  min-h-screen    |                           |            |
+------------------+---------------------------+------------+
```

### Current Behavior

| Component | Current | Desired |
|-----------|---------|---------|
| Left Sidebar | Fixed (min-h-screen) | Fixed |
| Header | Fixed (flex-shrink-0) | Fixed |
| Right Sidebar | Scrollable (overflow-y-auto) | Fixed |
| Main Content | Scrollable (overflow-y-auto) | Scrollable |

### Files with Right Sidebar

| File | Right Sidebar Class |
|------|---------------------|
| `templates/clients/client_detail.html` | `w-56 flex-shrink-0 border-l border-border-subtle bg-panel/50 overflow-y-auto` |
| `templates/projects/project_detail.html` | `w-56 flex-shrink-0 border-l border-border-subtle bg-panel/50 overflow-y-auto` |
| `templates/tasks/task_full_page.html` | `w-72 flex-shrink-0 border-l border-border-subtle p-4 overflow-y-auto` |

---

## Solution

### The Fix

Remove `overflow-y-auto` from the right sidebar in all affected templates. This prevents the sidebar from scrolling independently while the main content remains scrollable.

**Before:**
```html
<div class="w-56 flex-shrink-0 border-l border-border-subtle bg-panel/50 overflow-y-auto">
```

**After:**
```html
<div class="w-56 flex-shrink-0 border-l border-border-subtle bg-panel/50">
```

### Why This Works

The current layout structure already has the correct flex containment:

1. **base.html**: Outer container is `min-h-full flex` with `overflow-hidden` on main
2. **Detail pages**: Use `flex flex-col h-full` → `flex-1 flex overflow-hidden`
3. **Left sidebar**: Already fixed via `min-h-screen` in flex container
4. **Header**: Already fixed via `flex-shrink-0`
5. **Main content**: Already scrollable via `overflow-y-auto`

The only issue is the right sidebar has `overflow-y-auto` making it independently scrollable.

---

## Files to Modify

### 1. templates/clients/client_detail.html (Line 59)

Change:
```html
<div class="w-56 flex-shrink-0 border-l border-border-subtle bg-panel/50 overflow-y-auto">
```
To:
```html
<div class="w-56 flex-shrink-0 border-l border-border-subtle bg-panel/50 overflow-hidden">
```

### 2. templates/projects/project_detail.html (Line 67)

Change:
```html
<div class="w-56 flex-shrink-0 border-l border-border-subtle bg-panel/50 overflow-y-auto">
```
To:
```html
<div class="w-56 flex-shrink-0 border-l border-border-subtle bg-panel/50 overflow-hidden">
```

### 3. templates/tasks/task_full_page.html (Line 121)

Change:
```html
<div class="w-72 flex-shrink-0 border-l border-border-subtle p-4 overflow-y-auto">
```
To:
```html
<div class="w-72 flex-shrink-0 border-l border-border-subtle p-4 overflow-hidden">
```

---

## Considerations

### Sidebar Content Height

The right sidebar contains navigation items that should fit within the viewport:
- **client_detail.html**: Profile, Projects (2 items)
- **project_detail.html**: Overview, Tasks + Coming Soon section (~6 items)
- **task_full_page.html**: Properties panel (status, assignee, priority, etc.)

If sidebar content exceeds viewport height in the future, consider:
1. Using `overflow-y-auto` with a max-height
2. Adding a scroll container inside the sidebar for specific sections
3. Collapsible sections for "Coming Soon" items

### Alternative: Sticky Positioning

An alternative approach would be using `position: sticky` on the header and sidebar:

```html
<div class="sticky top-0 ...">
```

However, this requires restructuring the flex layout and may cause z-index issues. The current approach (removing `overflow-y-auto`) is simpler and maintains the existing structure.

---

## Testing Checklist

After implementation, verify:

- [ ] **Client Detail Page**: Scroll main content, header and right sidebar stay fixed
- [ ] **Project Detail Page**: Scroll main content, header and right sidebar stay fixed
- [ ] **Task Full Page**: Scroll main content, header and right sidebar stay fixed
- [ ] **Left Sidebar**: Stays fixed on all pages (already working)
- [ ] **Mobile/Small Viewport**: Layout doesn't break on smaller screens
- [ ] **Long Content**: Main content scrolls properly with lots of tasks/activity

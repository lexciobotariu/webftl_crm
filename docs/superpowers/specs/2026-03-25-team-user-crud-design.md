# Team User Management CRUD — Design Spec

**Date:** 2026-03-25
**Status:** Approved
**Scope:** Expand the Team app's user detail drawer into a full CRUD system for superusers/admins.

## Context

The Team page currently has a user detail drawer that displays user info as read-only text and only allows changing the permission preset. This spec expands the drawer into a full user management interface — editable fields, soft-delete (deactivation), and two-tier hard deletion with cascade warnings.

User creation remains via allauth self-signup (unchanged).

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| User creation flow | Keep allauth self-signup | Sufficient for current needs |
| Deactivation behavior | Set `is_active=False`, leave all assignments intact | Simple, preserves historical data |
| Inactive user visibility | Always shown, greyed out with "Inactive" badge | No hidden state, easy to reactivate |
| Self-deactivation | Prevented | Avoid admin lockout |
| Last-admin guard | Prevent deactivating/deleting the last active admin | System must always have at least one admin |
| Deletion strategy | Two-tier: clean delete (no data) or force delete with warning | Allows cleanup of test users while protecting real data |
| Edit form UX | Always-editable form in drawer | Drawer is admin-only, edit is its primary purpose |
| Editable fields | Name, email, role, preset | GitHub token excluded (sensitive) |

## 1. User Detail Drawer — Edit Form

The drawer becomes an always-editable form with all fields submitting together.

### Form Fields (top to bottom)

| Field | Type | Constraints |
|-------|------|-------------|
| Name | Text input | Required, max 255 chars |
| Email | Email input | Required, unique across users |
| Role | Dropdown select | Choices: Admin, Member |
| Permission Preset | Dropdown select | All presets + "No preset" option |

Below the preset dropdown, keep the existing permission badges display showing the selected preset's permissions.

**Read-only info** displayed above the form (not editable):
- **Member Since** — `created_at` date, displayed as static text

### Save Behavior

- Single "Save Changes" button submits all fields via HTMX POST to `user_update`
- On success: replaces the user's table row via `hx-target="#user-{pk}"` with `hx-swap="outerHTML"`, closes drawer via `HX-Trigger: closeSlideOver` response header
- On validation error: re-renders the full drawer with inline error messages (email uniqueness, required fields). Drawer stays open — no `HX-Trigger` header sent on error.

### Validation Rules

- **Email uniqueness**: Server-side check, return error in drawer if duplicate
- **Name required**: Server-side, return error if blank
- **Last-admin guard**: If changing own role from admin to member, verify at least one other active admin exists

## 2. Deactivation / Reactivation

Located in the drawer footer, below the save button.

### Active Users

- **"Deactivate User" button** — red/danger styling
- On click: HTMX POST to `user_deactivate`
- Returns updated user row (now shows inactive styling) and closes drawer

### Inactive Users

- **"Reactivate User" button** — green styling
- On click: HTMX POST to `user_deactivate` (same endpoint, toggles state)
- Returns updated user row (active styling restored) and closes drawer

### Guards

- **Can't deactivate yourself** — button hidden or disabled with tooltip
- **Can't deactivate the last active admin** — server-side check, return inline error
- Show clear error message in drawer if action is blocked

### Effects of Deactivation

- `is_active = False` on the User model
- Django's authentication backend natively rejects login for inactive users
- **Active sessions are NOT invalidated** — deactivated users with existing sessions can continue until session expires. This is accepted as out of scope for now; session flushing can be added later if needed.
- User excluded from assignee/member dropdowns across the app (filter `is_active=True`)
- Existing assignments, todos, notes, comments remain unchanged

## 3. Team List — Inactive User Display

### Row Styling

- Inactive users: greyed-out row (reduced opacity or muted text color)
- **"Inactive" badge** next to the user's name — grey background, similar to the role badge styling
- Edit button (pencil) still available — opens drawer with reactivate option

### No Filtering

All users (active and inactive) shown in the same list. No tabs or filters needed at this stage.

## 4. Deletion — Two-Tier

Located in the drawer footer, below the deactivate/reactivate button.

### Trigger

- **"Delete User"** text button — subtle, danger-colored
- Clicking it fires an HTMX GET to `user_delete_confirm` which loads an inline confirmation section

### Clean Delete (no related data)

When the user has no associated records across any model:

```
This user has no associated data. Delete permanently?
[Cancel] [Delete]
```

### Force Delete With Warning (has related data)

When the user has associated records, show counts:

```
This will permanently delete:
  - X todos
  - X notes
  - X comments
  - X attachments
  - X project memberships
  - Salary record (including X salary months and Y payments)

Additionally, X tasks will be unassigned (assignee set to empty).

[Cancel] [Delete Permanently]
```

**Note on notes count**: A single note where the user is both `created_by` and `modified_by` should only be counted once. Use `Note.objects.filter(Q(created_by=user) | Q(modified_by=user))` to deduplicate.

Counts are computed server-side when the confirmation section loads.

### Guards

- **Can't delete yourself** — button hidden
- **Can't delete the last active admin** — server-side check, return error
- Deletion is a real CASCADE delete — all related records are permanently removed

### After Deletion

- User row removed from team list (HTMX swap: delete the row)
- Drawer closes
- No undo

## 5. Backend Changes

### New Views

| View | Method | URL | Purpose |
|------|--------|-----|---------|
| `user_update` | POST | `team/<int:pk>/update/` | Update name, email, role, preset |
| `user_deactivate` | POST | `team/<int:pk>/deactivate/` | Toggle is_active |
| `user_delete_confirm` | GET | `team/<int:pk>/delete-confirm/` | Return deletion confirmation with counts |
| `user_delete` | POST | `team/<int:pk>/delete/` | Perform actual deletion |

### Views to Remove

| View | URL | Replaced By |
|------|-----|-------------|
| `toggle_role` | `team/<int:pk>/toggle-role/` | `user_update` |
| `update_preset` | `team/<int:pk>/update-preset/` | `user_update` |

### All views require:

- `@login_required`
- `@require_permission('access_team')`
- `@require_POST` (for POST endpoints: `user_update`, `user_deactivate`, `user_delete`)
- `request.user.is_admin` check (return 403 if not)

### user_update View Logic

```
1. Get user by pk (404 if not found)
2. Validate: name not blank, email not blank, email unique (excluding current user)
3. If changing role: check last-admin guard
4. Update user fields: name, email, role, permission_preset
5. Return updated user_row partial
```

### user_deactivate View Logic

```
1. Get user by pk
2. Guard: can't deactivate yourself
3. Guard: if deactivating, check not last active admin
4. Toggle is_active
5. Return updated user_row partial
```

### user_delete_confirm View Logic

```
1. Get user by pk
2. Guard: can't delete yourself
3. Count related objects (CASCADE deletions):
   - todos: Todo.objects.filter(owner=user).count()
   - notes: Note.objects.filter(Q(created_by=user) | Q(modified_by=user)).count()  # deduplicated
   - comments: TaskComment.objects.filter(author=user).count()
   - attachments: Attachment.objects.filter(uploaded_by=user).count()
   - project_memberships: ProjectMember.objects.filter(user=user).count()
   - salary: EmployeeSalary.objects.filter(user=user) — if exists, also count related SalaryMonth and Payment records
4. Count SET_NULL side effects:
   - tasks_unassigned: Task.objects.filter(assignee=user).count()
5. Return user_delete_confirm partial with all counts
```

### user_delete View Logic

```
1. Get user by pk
2. Guard: can't delete yourself
3. Guard: can't delete last active admin
4. user.delete() — Django CASCADE handles related records
5. Return empty response with HX-Trigger for row removal
```

## 6. Assignee Filtering

All querysets where users can be selected for assignment must filter `is_active=True`:

- Task assignee dropdowns
- Project member selection
- Any other user-selection UI

This prevents inactive users from receiving new assignments while preserving their existing ones.

## 7. Template Structure

```
templates/accounts/
├── team_list.html                    (modify: inactive row styling)
├── partials/
│   ├── user_detail_drawer.html       (rewrite: full edit form + footer actions)
│   ├── user_row.html                 (modify: inactive badge + greyed styling)
│   └── user_delete_confirm.html      (new: inline deletion confirmation)
```

## 8. URL Changes Summary

### Remove

```python
path('team/<int:pk>/toggle-role/', views.toggle_role, name='toggle_role'),
path('team/<int:pk>/update-preset/', views.update_preset, name='update_preset'),
```

### Add

```python
path('team/<int:pk>/update/', views.user_update, name='user_update'),
path('team/<int:pk>/deactivate/', views.user_deactivate, name='user_deactivate'),
path('team/<int:pk>/delete-confirm/', views.user_delete_confirm, name='user_delete_confirm'),
path('team/<int:pk>/delete/', views.user_delete, name='user_delete'),
```

## 9. Out of Scope

- Custom invitation/signup flow (keep allauth as-is)
- Email change verification/confirmation email
- Password management by admins
- Bulk user operations
- Activity log/audit trail for admin actions
- GitHub token management
- Session invalidation on deactivation (accepted risk — sessions expire naturally)
